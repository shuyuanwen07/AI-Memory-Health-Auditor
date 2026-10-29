"""One controlled, resumable AC3 target step for a reviewed frozen suite.

This is a backend service, not a public route. Calling it may incur an actual
OpenRouter charge. It refuses incomplete frozen settings and preserves an
unknown dispatch rather than repeating it. Dollar reservations are estimates,
not a guarantee of provider billing. The caller must provision the reviewed
synthetic conversations/memories/audits and research ledger schema first.
"""
from datetime import datetime, timezone
from decimal import Decimal  # noqa: F401
import hashlib
import json
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.models import AuditRunModel, ConversationModel, MemoryModel, TargetResponseModel, TestCaseModel, EvaluationResultModel
from app.schemas import TargetResponse
from app.target_ai.providers import HttpTargetAIConnector, single_attempt_target_request, target_output_limit
from app.target_ai.request_contracts import observe_request_contracts
from app.target_ai.rule_based import selected_memory_context
from app.target_systems.controlled import ControlledTargetSystemAdapter
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.services.ac3_attempt_ledger import AttemptLedger
from app.services.ac3_atomic_settlement import settle_and_save
from app.services.ac3_budget_guard import BudgetedDispatchLedger
from app.services.ac3_locked_preflight import ac3_sequence_locks, locked_ac3_preflight
from app.services.ac3_request_binding import AC3RequestBinding
from app.services.ac3_target_prepare import prepare_ac3_input
from app.services.formal_freeze import formal_input_signature, formal_runtime_signature
from scripts.ac3_fixed_suite_adapter import compile_mock, sha


_SETTINGS_FIELDS = {'target_configuration','provider','model','temperature','random_seed','test_budget',
    'prompt_template_version','pipeline_provider','pipeline_model','evaluator_provider','evaluator_model',
    'retrieval_mode','retrieval_provider','retrieval_model','memory_strategy','memory_maintenance_policy',
    'target_memory_capacity','target_memory_writer','target_memory_writer_version','target_system_adapter',
    'target_system_adapter_version','target_memory_profile'}


def target_settings_sha256(audit):
    """Hash all execution-affecting target settings, including full memory profile."""
    data = audit.model_dump(mode='json', include=_SETTINGS_FIELDS)
    if set(data) != _SETTINGS_FIELDS:
        raise ValueError('Audit target settings are incomplete')
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def run_controlled_ac3_step(engine, *, frozen_path, frozen_sha256, reservation, scope,
                            history_conversations, history_runs, frozen_test_id, request_key):
    """Execute exactly one authorized frozen question; no automatic network retry."""
    if engine.url.get_backend_name() != 'postgresql':
        raise ValueError('Live AC3 requires the reviewed PostgreSQL ledger')
    with engine.connect() as conn:
        if conn.get_isolation_level() != 'SERIALIZABLE':
            raise ValueError('Live AC3 requires SERIALIZABLE PostgreSQL')
    plan = compile_mock(frozen_path, frozen_sha256, reservation)
    cfg = plan['model_configuration']
    if cfg.get('target_provider') != 'openrouter' or cfg.get('evaluator_provider') != 'rule_based':
        raise ValueError('Only OpenRouter target and local rule evaluator are supported')
    if cfg.get('evaluator_implementation_version') != RuleBasedBehaviourEvaluator.VERSION:
        raise ValueError('Evaluator implementation differs from frozen protocol')
    runtime = formal_runtime_signature()
    if cfg.get('runtime_source_sha256') != runtime['source_sha256']:
        raise ValueError('Application runtime differs from frozen protocol')
    item = next((x for x in plan['items'] if x['test_id'] == frozen_test_id and x['grounding_review'] == 'valid'), None)
    if not item or item['history_id'] not in history_runs:
        raise ValueError('Question is not in the reviewed frozen suite')
    run_id = history_runs[item['history_id']]
    local_id = 'AC3' + sha(f'{frozen_sha256}|{run_id}|{frozen_test_id}'.encode())[:32].upper()
    AttemptLedger(engine).register_reviewed_scope(scope, frozen_path, frozen_sha256, reservation)
    BudgetedDispatchLedger(engine, frozen_path, frozen_sha256, reservation).register(scope)
    from app.api.routes import audit_schema, conversation_schema, memory_schema, test_schema
    with Session(engine) as db:
        with ac3_sequence_locks(db, history_runs):
            with locked_ac3_preflight(db, frozen_path, frozen_sha256, reservation, history_conversations,
                                      history_runs, ledger_scope=scope, ledger_write_handoff=True):
                audit_row, test_row = db.get(AuditRunModel, run_id), db.get(TestCaseModel, local_id)
                if not audit_row or not test_row or test_row.run_id != run_id:
                    raise ValueError('Staged audit or question is missing')
                audit, test = audit_schema(audit_row), test_schema(test_row)
                settings = target_settings_sha256(audit)
                expected_settings = cfg.get('target_settings_sha256')
                if isinstance(expected_settings, dict): expected_settings = expected_settings.get(item['history_id'])
                if settings != expected_settings:
                    raise ValueError('Target settings differ from frozen protocol')
                if target_output_limit(audit) is None or target_output_limit(audit) != cfg.get('target_output_token_limit'):
                    raise ValueError('A fixed output-token limit is required and must match the frozen protocol')
                previous = list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.test_id == local_id)))
                if previous:
                    receipt = db.execute(text("SELECT request_key,status FROM ac3_attempt_receipts WHERE scope_id=:scope AND test_id=:test"), {'scope':scope,'test':frozen_test_id}).mappings().first()
                    if len(previous) != 1 or not receipt or receipt['status'] != 'settled' or receipt['request_key'] != request_key:
                        raise ValueError('Saved answer is not uniquely bound to this request')
                    saved_response_id, response, cost, meta = previous[0].id, None, None, None
                else:
                    saved_response_id = None
                    conversation = conversation_schema(db, db.get(ConversationModel, audit.conversation_id))
                    adapter = ControlledTargetSystemAdapter(db, audit)
                    adapter.ingest(conversation)
                    private, evidence = prepare_ac3_input(adapter, test, audit, frozen_test_id)
                    ledger = BudgetedDispatchLedger(engine, frozen_path, frozen_sha256, reservation, request_evidence=evidence)
                    binder = AC3RequestBinding(ledger, scope, frozen_sha256, request_key, private, audit,
                                               frozen_test_id=frozen_test_id)
                    with single_attempt_target_request(), observe_request_contracts(binder):
                        response = HttpTargetAIConnector().execute(private, audit)
                    # Match the regular target adapter's final selection receipt.
                    memory_input = response.execution_metadata.memory_input
                    if memory_input is not None:
                        by_value = {}
                        for value, memory_id in zip(evidence['target_memory_context'], evidence['selected_memory_ids'], strict=True):
                            by_value.setdefault(value.strip(), memory_id)
                        memory_input.sent_memory_ids = [by_value[value] for value in selected_memory_context(private, audit.target_configuration)]
                    meta = response.execution_metadata.model_dump(mode='json')
                    cost = response.execution_metadata.reported_cost_usd
                    pending = ledger.record_pending_response(scope, frozen_sha256, request_key, response.response_text, cost,
                                                             response_metadata=meta)
            if saved_response_id is None:
                if pending['cost_unknown'] or not pending['metadata_verified']:
                    return {'status':'provider_evidence_unresolved', 'target_response_preserved':True, 'automatic_retry_allowed':False}
                settled = settle_and_save(engine, frozen_path=frozen_path, frozen_sha256=frozen_sha256,
                    reservation=reservation, scope=scope, request_key=request_key,
                    contract_sha256=meta['request_contract_sha256'], frozen_test_id=frozen_test_id, run_id=run_id,
                    response=response.response_text, reported_cost_usd=str(cost), budgeted=True)
                if settled['state'] == 'budget_overrun':
                    return {'status':'budget_overrun', 'target_response_preserved':True, 'automatic_retry_allowed':False}
                saved_response_id = settled['response_id']
            with Session(engine) as score_db, score_db.begin():
                score_audit = score_db.get(AuditRunModel, run_id)
                stored_test = score_db.get(TestCaseModel, local_id)
                stored_answer = score_db.get(TargetResponseModel, saved_response_id)
                if not score_audit or not stored_test or not stored_answer or (score_audit.reproducibility_metadata or {}).get('ac3_staged_suite', {}).get('input_sha256') != formal_input_signature(score_db, score_audit):
                    raise ValueError('Frozen audit inputs changed before scoring')
                existing = list(score_db.scalars(select(EvaluationResultModel).where(EvaluationResultModel.response_id == stored_answer.id)))
                if len(existing) > 1:
                    raise ValueError('Duplicate evaluation for saved answer')
                if not existing:
                    answer = TargetResponse(response_id=stored_answer.id, test_id=local_id, run_id=run_id,
                        response_text=stored_answer.response_text, model=stored_answer.model,
                        temperature=stored_answer.temperature, created_at=datetime.now(timezone.utc))
                    memories = [memory_schema(score_db, row) for row in score_db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == score_audit.conversation_id))]
                    evaluation = RuleBasedBehaviourEvaluator().evaluate(test_schema(stored_test), answer, memories)
                    score_db.add(EvaluationResultModel(id=evaluation.evaluation_id,test_id=evaluation.test_id,
                        response_id=evaluation.response_id, passed=evaluation.passed,
                        failure_type=evaluation.failure_type.value if evaluation.failure_type else None,
                        reason=evaluation.reason, evidence_memory_ids=evaluation.evidence_memory_ids,
                        evaluator=evaluation.evaluator, failure_classification=evaluation.failure_classification.model_dump()))
    return {'status':'completed','target_response_preserved':True,'automatic_retry_allowed':False,
            'provider_cost_status':'provider_report_unreconciled'}
