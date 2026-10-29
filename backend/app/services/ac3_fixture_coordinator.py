"""End-to-end AC3 rehearsal on in-memory SQLite only; live execution stays disabled.

It cannot receive an arbitrary transport or access a network. Its provider and
all outcomes are synthetic, and it deliberately does not authorize a real run.
The separately committed rehearsal steps do not prove production atomic locking.
"""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
import os
import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.models import AuditRunModel, TestCaseModel, MemoryModel, TargetResponseModel, EvaluationResultModel
from app.schemas import AuditRun, TestCase, TargetResponse, Memory
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.services.ac3_locked_preflight import locked_ac3_preflight
from app.services.ac3_request_binding import AC3RequestBinding
from app.services.ac3_atomic_settlement import settle_and_save
from app.target_ai.providers import HttpTargetAIConnector, single_attempt_target_request
from app.target_ai.request_contracts import observe_request_contracts
from scripts.ac3_fixed_suite_adapter import sha, compile_mock


class FixtureProvider:
    """A fixed local response; exact type required to avoid injected live transports."""
    def __init__(self, answer='Fixture fact 0', reported_cost='0.001', billed_cost='0.001'):
        self.answer, self.reported_cost, self.billed_cost = answer, reported_cost, billed_cost
        self.calls = 0

    def _post(self, url, **kwargs):
        self.calls += 1
        return httpx.Response(200, json={'model':'openai/gpt-6-luna',
            'choices':[{'finish_reason':'stop','message':{'content':self.answer}}],
            'usage':{'cost':float(self.reported_cost)}})


class _FixtureLedger:
    def __init__(self, engine): self.engine = engine
    def begin(self, scope, frozen_sha, request_key, contract_sha, test_id):
        with Session(self.engine) as db, db.begin():
            record = db.execute(text('SELECT status FROM ac3_attempt_scopes WHERE scope_id=:scope AND frozen_sha256=:sha'), {'scope':scope,'sha':frozen_sha}).mappings().first()
            if not record or record['status'] != 'active': raise ValueError('Fixture scope is not active')
            if db.execute(text('SELECT request_key FROM ac3_attempt_receipts WHERE request_key=:key OR (scope_id=:scope AND test_id=:test)'), {'key':request_key,'scope':scope,'test':test_id}).first():
                raise ValueError('Fixture request already recorded')
            db.execute(text("INSERT INTO ac3_attempt_receipts (scope_id,test_id,status,response_text,reported_cost_usd,request_key,contract_sha256) VALUES (:scope,:test,'dispatched',NULL,NULL,:key,:contract)"), {'scope':scope,'test':test_id,'key':request_key,'contract':contract_sha})
            db.execute(text("UPDATE ac3_attempt_scopes SET status='unknown' WHERE scope_id=:scope"), {'scope':scope})
        return {'state':'dispatched','duplicate':False}


def disabled_live_runner(*args, **kwargs):
    raise RuntimeError('AC3 real provider execution is disabled')


def run_fixture_step(engine, frozen_path, frozen_sha, reservation, conversations, runs,
                     scope, frozen_test_id, request_key, provider, *, request_ceiling_usd):
    if engine.url.get_backend_name() != 'sqlite' or engine.url.database not in (None, ':memory:') or type(provider) is not FixtureProvider:
        raise ValueError('Fixture coordinator requires in-memory SQLite and its own fake provider')
    ceiling = Decimal(request_ceiling_usd)
    if not ceiling.is_finite() or ceiling <= 0: raise ValueError('Invalid fixture request ceiling')
    plan = compile_mock(frozen_path, frozen_sha, reservation)
    if plan['model_configuration'].get('evaluator_implementation_version') != RuleBasedBehaviourEvaluator.VERSION:
        raise ValueError('Fixture evaluator implementation differs from frozen version')
    if plan['model_configuration'].get('pipeline_implementation_version') != RuleBasedTestGenerator.VERSION:
        raise ValueError('Fixture pipeline implementation differs from frozen version')
    with Session(engine) as db:
        with locked_ac3_preflight(db, frozen_path, frozen_sha, reservation, conversations, runs, ledger_scope=scope):
            pass
    history = next((h for h in runs if frozen_test_id.startswith(h + '-')), None)
    if history is None: raise ValueError('Unknown fixture history')
    run_id = runs[history]
    local_id = 'AC3' + sha(f'{frozen_sha}|{run_id}|{frozen_test_id}'.encode())[:32].upper()
    with Session(engine) as db:
        audit_row = db.get(AuditRunModel, run_id); test_row = db.get(TestCaseModel, local_id)
        if not audit_row or not test_row or test_row.run_id != run_id: raise ValueError('Unknown staged fixture test')
        audit = AuditRun(run_id=run_id, conversation_id=audit_row.conversation_id, status=audit_row.status,
                         target_configuration=audit_row.target_configuration, provider=audit_row.provider,
                         model=audit_row.model, temperature=audit_row.temperature, random_seed=audit_row.random_seed,
                         test_budget=audit_row.test_budget, prompt_template_version=audit_row.prompt_template_version,
                         evaluator_provider=audit_row.evaluator_provider, evaluator_model=audit_row.evaluator_model,
                         pipeline_provider=audit_row.pipeline_provider, pipeline_model=audit_row.pipeline_model,
                         memory_strategy=audit_row.memory_strategy, created_at=datetime.now(timezone.utc))
        test = TestCase(test_id=test_row.id, run_id=run_id, dimension=test_row.dimension, prompt=test_row.prompt,
                        expected_behavior=test_row.expected_behavior, supporting_memory_ids=test_row.supporting_memory_ids,
                        generator_version=test_row.generator_version)
        memories = [Memory(memory_id=m.id, conversation_id=m.conversation_id, canonical_value=m.canonical_value,
                           status=m.status, source_message_ids=m.source_message_ids)
                    for m in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == audit_row.conversation_id))]
        receipt = db.execute(text('SELECT request_key,status,response_text,reported_cost_usd FROM ac3_attempt_receipts WHERE scope_id=:scope AND test_id=:test'), {'scope':scope,'test':frozen_test_id}).mappings().first()
        if receipt and receipt['request_key'] != request_key: raise ValueError('Fixture test already bound to another request')
        prior = db.scalar(select(TargetResponseModel).where(TargetResponseModel.test_id == local_id))
        if receipt and receipt['status'] == 'settled' and prior:
            saved_id = prior.id
        elif receipt or prior:
            raise ValueError('Fixture attempt is incomplete; stop without retry')
        else:
            saved_id = None
    if saved_id is None:
        binder = AC3RequestBinding(_FixtureLedger(engine), scope, frozen_sha, request_key, test, audit, frozen_test_id=frozen_test_id)
        # Both credential and HTTP transport are local, fixed fixtures.
        with patch.dict(os.environ, {'OPENROUTER_API_KEY':'fixture-only'}), patch('app.target_ai.providers.httpx.post', side_effect=provider._post):
            with single_attempt_target_request(), observe_request_contracts(binder):
                answer = HttpTargetAIConnector().execute(test, audit)
        reported = answer.execution_metadata.reported_cost_usd
        if reported is None or Decimal(str(reported)) != Decimal(provider.billed_cost) or Decimal(str(reported)) > ceiling:
            raise ValueError('Fixture billing mismatch or ceiling exceeded; scope remains unresolved')
        saved = settle_and_save(engine, frozen_path=frozen_path, frozen_sha256=frozen_sha, reservation=reservation,
                                scope=scope, request_key=request_key, contract_sha256=_contract_for(engine, request_key),
                                frozen_test_id=frozen_test_id, run_id=run_id, response=answer.response_text,
                                reported_cost_usd=str(reported))
        saved_id = saved['response_id']
    with Session(engine) as db, db.begin():
        row = db.get(TargetResponseModel, saved_id)
        previous = list(db.scalars(select(EvaluationResultModel).where(EvaluationResultModel.response_id == saved_id)))
        if len(previous) > 1: raise ValueError('Duplicate fixture evaluations')
        if not previous:
            response = TargetResponse(response_id=row.id, test_id=row.test_id, run_id=row.run_id,
                                      response_text=row.response_text, model=row.model, temperature=row.temperature,
                                      created_at=datetime.now(timezone.utc))
            result = RuleBasedBehaviourEvaluator().evaluate(test, response, memories)
            db.add(EvaluationResultModel(id='ACE' + sha(saved_id.encode())[:32].upper(), test_id=local_id,
                    response_id=saved_id, passed=result.passed,
                    failure_type=result.failure_type.value if result.failure_type else None,
                    reason=result.reason, evidence_memory_ids=result.evidence_memory_ids,
                    evaluator=result.evaluator, failure_classification=result.failure_classification.model_dump(mode='json')))
    return {'status':'fixture_completed', 'real_provider_called':False, 'response_id':saved_id}


def _contract_for(engine, request_key):
    with Session(engine) as db:
        return db.execute(text('SELECT contract_sha256 FROM ac3_attempt_receipts WHERE request_key=:key'), {'key':request_key}).scalar_one()
