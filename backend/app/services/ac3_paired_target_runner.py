"""Internal one-answer paired AC3 step, with durable budget and response evidence.

No public endpoint invokes this service. Formal use additionally requires a
reviewed pre-outcome protocol, verified shared budget and scorer integration.
It does not evaluate answers or declare acceptance.
"""
import hashlib
from sqlalchemy.orm import Session

from app.models import AuditRunModel, ConversationModel, TestCaseModel
from app.services.ac3_locked_preflight import ac3_sequence_locks
from app.services.ac3_paired_locked_preflight import locked_paired_preflight
from app.services.ac3_paired_request_binding import PairedTargetRequestBinding
from app.services.ac3_paired_target_settlement import settle_target
from app.services.ac3_target_prepare import prepare_ac3_input
from app.services.formal_freeze import formal_runtime_signature
from app.target_ai.providers import HttpTargetAIConnector, single_attempt_target_request
from app.target_ai.request_contracts import observe_request_contracts
from app.target_ai.rule_based import selected_memory_context
from app.target_systems.controlled import ControlledTargetSystemAdapter
from scripts.ac3_retest_paired_freeze import canonical, compile_isolated
from scripts.ac3_retest_snapshot_verify import formal_signature


def run_paired_target_step(engine, *, ledger, frozen, source, plan, reviews, components,
                           history_conversations, history_runs, scope, test_id, request_key):
    """Execute one question only; never retry an unresolved or duplicate request."""
    if engine.url.get_backend_name()!='postgresql' or ledger.engine is not engine:
        raise ValueError('Paired live execution requires the matching PostgreSQL ledger')
    if any(getattr(ledger,key)!=value for key,value in (('source',source),('plan',plan),('reviews',reviews),('components',components))):
        raise ValueError('Ledger evidence differs from the requested study')
    frozen_sha=hashlib.sha256(canonical(frozen)).hexdigest()
    if ledger.frozen_sha256!=frozen_sha:
        raise ValueError('Ledger does not bind the canonical frozen study')
    stage=compile_isolated(frozen,source,plan,reviews,components)
    items=[item for item in stage['items'] if item['test_id']==test_id]
    if len(items)!=1 or items[0]['history_id'] not in history_runs:
        raise ValueError('Question is not part of the frozen study')
    item=items[0];run_id=history_runs[item['history_id']]
    target=frozen['protocol']['target']
    if target['provider']!='openrouter' or target['retry_limit']!=0:
        raise ValueError('Only a single-attempt OpenRouter target is supported')
    if formal_signature(components['target_runtime'])['app_source_sha256']!=formal_runtime_signature()['source_sha256']:
        raise ValueError('Target runtime differs from the reviewed snapshot')
    # Registering a scope is safe only after the ledger has revalidated its
    # combined billing evidence and frozen budget; it makes no network call.
    ledger.register(scope)
    local_id='AC3'+hashlib.sha256(f'{frozen_sha}|{run_id}|{test_id}'.encode()).hexdigest()[:32].upper()
    from app.api.routes import audit_schema, conversation_schema, test_schema
    with Session(engine) as db, ac3_sequence_locks(db,history_runs):
        with locked_paired_preflight(db,frozen,source,plan,reviews,components,history_conversations,history_runs):
            audit_row=db.get(AuditRunModel,run_id);test_row=db.get(TestCaseModel,local_id)
            if not audit_row or not test_row or test_row.run_id!=run_id:
                raise ValueError('Frozen audit or question is missing')
            audit,test=audit_schema(audit_row),test_schema(test_row)
            conversation=conversation_schema(db,db.get(ConversationModel,audit.conversation_id))
            adapter=ControlledTargetSystemAdapter(db,audit);adapter.ingest(conversation)
            private,evidence=prepare_ac3_input(adapter,test,audit,test_id)
            binder=PairedTargetRequestBinding(ledger,scope,frozen_sha,request_key,private,audit,
                frozen_test_id=test_id,frozen_question=item,request_evidence=evidence)
            with single_attempt_target_request(), observe_request_contracts(binder):
                response=HttpTargetAIConnector().execute(private,audit)
            memory_input=response.execution_metadata.memory_input
            if memory_input is not None:
                by_value={}
                for value,memory_id in zip(evidence['target_memory_context'],evidence['selected_memory_ids'],strict=True):
                    by_value.setdefault(value.strip(),memory_id)
                memory_input.sent_memory_ids=[by_value[value] for value in selected_memory_context(private,audit.target_configuration)]
            meta=response.execution_metadata.model_dump(mode='json')
            contract=meta.get('request_contract_sha256')
            # First persist the answer as pending even when the provider cost is
            # known. A crash cannot authorize a second request for this item.
            ledger.settle(scope,request_key,contract,response.response_text,None,response_metadata=meta)
        cost=response.execution_metadata.reported_cost_usd
        if cost is None:
            return {'status':'cost_unknown','target_response_preserved':True,'automatic_retry_allowed':False}
        settled=settle_target(ledger,frozen=frozen,scope=scope,test_id=test_id,run_id=run_id,
            request_key=request_key,contract_sha256=contract,response=response.response_text,
            reported_cost_usd=str(cost),execution_metadata=meta)
    return {'status':settled['status'],'target_response_preserved':True,'automatic_retry_allowed':False,
            'provider_cost_status':'provider_report_unreconciled'}
