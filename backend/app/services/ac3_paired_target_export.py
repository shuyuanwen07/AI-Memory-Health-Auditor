"""Read complete paired target answers under frozen source and ledger locks.

This service returns private source-bound data only. It does not call a model,
write files or publish results; incomplete and unknown outcomes are rejected.
"""
import hashlib
import json
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from app.models import TargetResponseModel
from app.services.ac3_locked_preflight import ac3_sequence_locks
from app.services.ac3_paired_locked_preflight import locked_paired_preflight
from scripts.ac3_paired_target_export import build_target_export
from scripts.ac3_retest_paired_freeze import canonical
from scripts.ac3_retest_reference_stage import compile_reference_stage


def collect_paired_targets(engine, *, ledger, frozen, source, plan, reviews, components,
                           history_conversations, history_runs, scope):
    if engine.url.get_backend_name()!='postgresql' or ledger.engine is not engine:
        raise ValueError('Export requires the matching PostgreSQL ledger')
    if any(getattr(ledger,k)!=v for k,v in (('source',source),('plan',plan),('reviews',reviews),('components',components))):
        raise ValueError('Ledger evidence differs from reviewed sources')
    frozen_sha=hashlib.sha256(canonical(frozen)).hexdigest()
    if frozen_sha!=ledger.frozen_sha256:raise ValueError('Frozen study differs from the ledger')
    ledger._validated()
    stage=compile_reference_stage(frozen,source,plan,reviews,components)
    with Session(engine) as db, ac3_sequence_locks(db,history_runs):
        with locked_paired_preflight(db,frozen,source,plan,reviews,components,history_conversations,history_runs):
            budget=db.execute(text('SELECT * FROM ac3_paired_budget_scopes WHERE scope_id=:scope FOR UPDATE'),{'scope':scope}).mappings().first()
            if (not budget or budget['frozen_sha256']!=frozen_sha or budget['budget_sha256']!=ledger.budget_sha256
                    or budget['status']!='active'):
                raise ValueError('Study budget scope is missing, changed or unresolved')
            receipts=[dict(row) for row in db.execute(text("SELECT * FROM ac3_paired_budget_receipts WHERE scope_id=:scope AND role='target' ORDER BY test_id FOR UPDATE"),{'scope':scope}).mappings()]
            by_id={row['test_id']:row for row in receipts};responses=[]
            for question in stage['questions']:
                ident=question['test_id'];run_id=history_runs[question['history_id']];receipt=by_id.get(ident)
                if not receipt:raise ValueError('A frozen question has no target receipt')
                evidence=receipt.get('request_evidence_json');evidence_sha=receipt.get('request_evidence_sha256')
                if not isinstance(evidence,str) or hashlib.sha256(evidence.encode()).hexdigest()!=evidence_sha:
                    raise ValueError('Request evidence is missing or changed')
                evidence_data=json.loads(evidence)
                if evidence_data.get('frozen_test_id')!=ident or evidence_data.get('run_id')!=run_id:
                    raise ValueError('Request evidence points to another target')
                local_id='AC3'+hashlib.sha256(f'{frozen_sha}|{run_id}|{ident}'.encode()).hexdigest()[:32].upper()
                expected_id='ACR'+hashlib.sha256(f"{scope}|{receipt['request_key']}".encode()).hexdigest()[:32].upper()
                saved=list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.test_id==local_id).with_for_update()))
                if (len(saved)!=1 or saved[0].id!=expected_id or saved[0].run_id!=run_id
                        or (saved[0].execution_metadata or {}).get('ac3_paired_request_evidence_sha256')!=evidence_sha):
                    raise ValueError('System answer is not uniquely bound to the target receipt')
                responses.append({'test_id':ident,'response_text':saved[0].response_text,
                                  'request_evidence_sha256':evidence_sha})
            return build_target_export(frozen,stage['questions'],receipts,responses,scope=scope,
                                       ledger_frozen_sha256=budget['frozen_sha256'],ledger_status=budget['status'])
