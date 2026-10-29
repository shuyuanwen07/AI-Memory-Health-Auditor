"""Atomic paired-retest target-response settlement; never dispatches a model.

No route invokes this service. Scorer settlement and the live transport remain
separate; provider authenticity and billing must be checked independently.
"""
import hashlib
import json
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.models import AuditRunModel, TargetResponseModel, TestCaseModel
from app.services.ac3_attempt_ledger import _digest, _id
from app.services.ac3_budget_guard import money
from app.services.formal_freeze import formal_input_signature
from scripts.ac3_retest_paired_freeze import canonical
from scripts.ac3_retest_reference_stage import compile_reference_stage


def settle_target(ledger,*,frozen,scope,test_id,run_id,request_key,contract_sha256,response,reported_cost_usd,execution_metadata):
    for value,length in ((scope,64),(test_id,120),(run_id,120),(request_key,120)):_id(value,length)
    _digest(contract_sha256)
    if not isinstance(response,str) or not response.strip() or len(response)>1_000_000:raise ValueError('Invalid target response')
    cost=money(reported_cost_usd)
    if (not isinstance(execution_metadata,dict) or execution_metadata.get('request_contract_sha256')!=contract_sha256
            or money(execution_metadata.get('reported_cost_usd'))!=cost):
        raise ValueError('Provider metadata is incomplete or differs from the receipt')
    if hashlib.sha256(canonical(frozen)).hexdigest()!=ledger.frozen_sha256:
        raise ValueError('Frozen file must use the canonical staged digest')
    plan,prior,scorer=ledger._validated()
    stage=compile_reference_stage(frozen,ledger.source,ledger.plan,ledger.reviews,ledger.components)
    items=[q for q in stage['questions'] if q['test_id']==test_id]
    if len(items)!=1:raise ValueError('Unknown frozen question')
    item=items[0];cfg=frozen['protocol']['target']
    local_id='AC3'+hashlib.sha256(f'{ledger.frozen_sha256}|{run_id}|{test_id}'.encode()).hexdigest()[:32].upper()
    response_id='ACR'+hashlib.sha256(f'{scope}|{request_key}'.encode()).hexdigest()[:32].upper()
    suffix=' FOR UPDATE' if ledger.engine.dialect.name=='postgresql' else ''
    with Session(ledger.engine) as db,db.begin():
        audit=db.scalar(select(AuditRunModel).where(AuditRunModel.id==run_id).with_for_update())
        test=db.scalar(select(TestCaseModel).where(TestCaseModel.id==local_id).with_for_update())
        if not audit or audit.status!='RESEARCH_STAGED' or not test or test.run_id!=run_id:
            raise ValueError('Expected quarantined audit and question')
        marker=(audit.reproducibility_metadata or {}).get('ac3_paired_retest') or {}
        if (marker.get('frozen_sha256')!=ledger.frozen_sha256 or marker.get('history_id')!=item['history_id']
                or marker.get('input_sha256')!=formal_input_signature(db,audit) or audit.provider!=cfg['provider']
                or audit.model!=cfg['model'] or audit.memory_strategy!=cfg['strategy']
                or test.prompt!=item['question'] or test.expected_behavior!=item['expected_behavior']
                or test.dimension!=item['dimension'] or test.supporting_memory_ids!=item['supporting_memory_ids']):
            raise ValueError('Stored audit inputs differ from frozen question')
        budget=db.execute(text('SELECT * FROM ac3_paired_budget_scopes WHERE scope_id=:scope'+suffix),{'scope':scope}).mappings().first()
        receipt=db.execute(text('SELECT * FROM ac3_paired_budget_receipts WHERE request_key=:key'+suffix),{'key':request_key}).mappings().first()
        if (not budget or budget['frozen_sha256']!=ledger.frozen_sha256 or budget['budget_sha256']!=ledger.budget_sha256
                or money(budget['max_usd'])!=money(plan['max_usd']) or money(budget['prior_upper_usd'])!=prior
                or money(budget['target_reserve_usd'])!=money(plan['reservation_per_target_usd'])
                or money(budget['scorer_reserve_usd'])!=scorer or not receipt or receipt['scope_id']!=scope
                or receipt['test_id']!=test_id or receipt['role']!='target' or receipt['contract_sha256']!=contract_sha256
                or money(receipt['reserved_usd'])!=money(plan['reservation_per_target_usd'])):
            raise ValueError('Budget or receipt differs from frozen evidence')
        evidence_text=receipt['request_evidence_json']
        if not isinstance(evidence_text,str) or hashlib.sha256(evidence_text.encode()).hexdigest()!=receipt['request_evidence_sha256']:
            raise ValueError('Private retrieval evidence is missing or changed')
        evidence=json.loads(evidence_text)
        if (evidence.get('format')!='ac3-private-request-evidence-v1' or evidence.get('frozen_test_id')!=test_id
                or evidence.get('run_id')!=run_id):
            raise ValueError('Private retrieval evidence belongs to another request')
        saved=list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.test_id==local_id).with_for_update()))
        if receipt['status']=='settled' and budget['status']=='active':
            if (len(saved)!=1 or saved[0].id!=response_id or saved[0].response_text!=response
                    or receipt['response_text']!=response or money(receipt['reported_cost_usd'])!=cost
                    or any((saved[0].execution_metadata or {}).get(k)!=v for k,v in execution_metadata.items())):
                raise ValueError('Existing settled response differs')
            return {'status':'already_settled','response_id':response_id,'provider_called':False}
        if (budget['status']!='unknown' or receipt['status'] not in ('dispatched','pending') or saved
                or (receipt['response_text'] is not None and receipt['response_text']!=response)):
            raise ValueError('Request is not uniquely awaiting settlement')
        if receipt['response_metadata_json'] is not None:
            pending_metadata=json.loads(receipt['response_metadata_json'])
            if any(execution_metadata.get(k)!=v for k,v in pending_metadata.items() if k!='reported_cost_usd'):
                raise ValueError('Saved pending response metadata differs')
        spent=money(budget['spent_usd'])+cost
        overrun=plan.get('budget_mode','capped')!='tracking_only' and (cost>money(receipt['reserved_usd']) or prior+spent>money(budget['max_usd']))
        db.add(TargetResponseModel(id=response_id,test_id=local_id,run_id=run_id,response_text=response,
            model=audit.model,temperature=audit.temperature,execution_metadata={**execution_metadata,
                'ac3_paired_request_key':request_key,'ac3_paired_frozen_sha256':ledger.frozen_sha256,
                'ac3_paired_request_evidence_sha256':receipt['request_evidence_sha256'],
                'cost_source':'provider_report_unreconciled'}))
        db.flush()
        db.execute(text('UPDATE ac3_paired_budget_receipts SET status=:status,response_text=:response,reported_cost_usd=:cost WHERE request_key=:key'),
                   {'status':'overrun' if overrun else 'settled','response':response,'cost':str(cost),'key':request_key})
        db.execute(text('UPDATE ac3_paired_budget_scopes SET spent_usd=:spent,status=:status WHERE scope_id=:scope'),
                   {'spent':str(spent),'status':'overrun' if overrun else 'active','scope':scope})
        ledger._validated()
    return {'status':'overrun' if overrun else 'settled','response_id':response_id,'provider_called':False}
