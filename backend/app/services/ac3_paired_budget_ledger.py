"""Draft durable target/scorer budget ledger; it does not call a provider.

Requires a separately frozen, source-bound budget record and reviewed study.
Reservations are estimates, not a provider-side hard limit. No route or live
connector invokes this draft; target-response database settlement is separate.
"""
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from sqlalchemy import select, text
from app.models import TargetResponseModel
from app.services.ac3_attempt_ledger import _digest, _id
from app.services.ac3_budget_guard import money
from scripts.ac3_retest_budget_plan import budget_plan, combined_budget_preflight


class PairedBudgetLedger:
    def __init__(self,engine,*,frozen_path,frozen_sha256,source,plan,reviews,components,budget_path,budget_sha256,billing_path):
        url=engine.url
        if url.get_backend_name()=='postgresql':
            with engine.connect() as conn:
                if conn.get_isolation_level()!='SERIALIZABLE':raise ValueError('SERIALIZABLE PostgreSQL required')
        elif url.get_backend_name()!='sqlite' or url.database not in (None,':memory:'):
            raise ValueError('Only SERIALIZABLE PostgreSQL or isolated in-memory SQLite is supported')
        self.engine=engine;self.frozen_path=Path(frozen_path);self.frozen_sha256=frozen_sha256
        self.source,self.plan,self.reviews,self.components=source,plan,reviews,components
        self.budget_path=Path(budget_path);self.budget_sha256=budget_sha256;self.billing_path=Path(billing_path)

    @staticmethod
    def _read(path):
        if path.is_symlink() or not path.is_file():raise ValueError('A regular evidence file is required')
        return path.read_bytes()

    def _validated(self):
        raw=self._read(self.budget_path)
        if hashlib.sha256(raw).hexdigest()!=self.budget_sha256:raise ValueError('Budget record changed')
        data=json.loads(raw)
        tracking = data.get('format')=='ac3-paired-tracking-only-v1'
        if (data.get('format') not in ('ac3-paired-combined-budget-v1','ac3-paired-tracking-only-v1')
                or data.get('frozen_sha256')!=self.frozen_sha256
                or data.get('fixed_before_target_results') is not True
                or (not tracking and data.get('billing_reviewed') is not True)
                or (tracking and data.get('historical_billing_status')!='unreconciled')
                or data.get('billing_sha256')!=hashlib.sha256(self._read(self.billing_path)).hexdigest()):
            raise ValueError('Budget provenance is incomplete')
        target=budget_plan(self._read(self.frozen_path),self.frozen_sha256,self.source,self.plan,self.reviews,
                           self.components,data.get('target_reservation_usd'))
        per_scorer=money(data.get('scorer_reservation_usd'),positive=True)
        if tracking != (target['budget_mode']=='tracking_only'):
            raise ValueError('Budget authorization mode differs from the frozen protocol')
        # Tracking-only scope accounts for new calls, and does not claim that
        # historical spending is zero or that historical billing is reconciled.
        prior=money('0') if tracking else money(data.get('prior_upper_usd'))
        if not tracking:
            combined=combined_budget_preflight(prior_upper_bound_usd=prior,
                target_reserved_usd=target['planned_target_reservations_usd'],
                scorer_reserved_usd=per_scorer*target['question_count'],max_usd=target['max_usd'])
            if combined['status']!='within_planning_cap':raise ValueError('Combined reserved budget exceeds the cap')
        return target,prior,per_scorer

    def register(self,scope):
        _id(scope,64);_digest(self.frozen_sha256);_digest(self.budget_sha256)
        target,prior,scorer=self._validated()
        suffix=' FOR UPDATE' if self.engine.dialect.name=='postgresql' else ''
        with self.engine.begin() as conn:
            row=conn.execute(text('SELECT * FROM ac3_paired_budget_scopes WHERE scope_id=:scope'+suffix),{'scope':scope}).mappings().first()
            if row:
                if (row['frozen_sha256']!=self.frozen_sha256 or row['budget_sha256']!=self.budget_sha256
                        or row['status']!='active'):raise ValueError('Existing scope differs or is unresolved')
                return {'status':'already_registered','provider_called':False}
            conn.execute(text('INSERT INTO ac3_paired_budget_scopes VALUES (:scope,:frozen,:budget,:max,:prior,:target,:scorer,:spent,:status)'),
                {'scope':scope,'frozen':self.frozen_sha256,'budget':self.budget_sha256,'max':target['max_usd'],
                 'prior':str(prior),'target':target['reservation_per_target_usd'],'scorer':str(scorer),'spent':'0','status':'active'})
        return {'status':'registered','provider_called':False}

    def begin(self,scope,test_id,role,request_key,contract_sha256,*,target_answer_sha256=None,request_evidence=None):
        _id(scope,64);_id(test_id,120);_id(request_key,120);_digest(contract_sha256)
        target,prior,scorer=self._validated()
        if test_id not in target['eligible_test_ids'] or role not in ('target','scorer'):raise ValueError('Unknown frozen request')
        if role=='target' and target_answer_sha256 is not None:raise ValueError('Target request cannot bind a prior answer')
        if role=='scorer':_digest(target_answer_sha256)
        evidence_json=evidence_sha=None
        if role=='target':
            if (not isinstance(request_evidence,dict) or set(request_evidence)!={'format','frozen_test_id','run_id','retrieval_id','selected_memory_ids','target_memory_context'}
                    or request_evidence.get('format')!='ac3-private-request-evidence-v1' or request_evidence.get('frozen_test_id')!=test_id
                    or any(not isinstance(request_evidence.get(k),str) or not request_evidence[k].strip() for k in ('run_id','retrieval_id'))
                    or any(not isinstance(request_evidence.get(k),list) or any(not isinstance(x,str) for x in request_evidence[k]) for k in ('selected_memory_ids','target_memory_context'))
                    or len(request_evidence['selected_memory_ids'])!=len(request_evidence['target_memory_context'])):
                raise ValueError('Target retrieval evidence is missing or invalid')
            evidence_json=json.dumps(request_evidence,ensure_ascii=False,sort_keys=True,separators=(',',':'))
            if len(evidence_json.encode())>1_000_000:raise ValueError('Target retrieval evidence is too large')
            evidence_sha=hashlib.sha256(evidence_json.encode()).hexdigest()
        elif request_evidence is not None:raise ValueError('Scorer requests cannot replace target retrieval evidence')
        suffix=' FOR UPDATE' if self.engine.dialect.name=='postgresql' else ''
        with self.engine.begin() as conn:
            row=conn.execute(text('SELECT * FROM ac3_paired_budget_scopes WHERE scope_id=:scope'+suffix),{'scope':scope}).mappings().first()
            if (not row or row['frozen_sha256']!=self.frozen_sha256 or row['budget_sha256']!=self.budget_sha256 or row['status']!='active'
                    or money(row['prior_upper_usd'])!=prior or money(row['scorer_reserve_usd'])!=scorer
                    or money(row['target_reserve_usd'])!=money(target['reservation_per_target_usd'])
                    or money(row['max_usd'])!=money(target['max_usd'])):
                raise ValueError('Scope or frozen budget differs or is unresolved')
            reserve=money(row['target_reserve_usd']) if role=='target' else scorer
            if target.get('budget_mode','capped')!='tracking_only' and prior+money(row['spent_usd'])+reserve>money(row['max_usd']):raise ValueError('Budget exhausted')
            if conn.execute(text('SELECT request_key FROM ac3_paired_budget_receipts WHERE request_key=:key OR (scope_id=:scope AND test_id=:test AND role=:role)'),
                            {'key':request_key,'scope':scope,'test':test_id,'role':role}).first():
                raise ValueError('Request already dispatched; automatic retry is forbidden')
            if role=='scorer':
                target_receipt=conn.execute(text("SELECT request_key,response_text,request_evidence_json,request_evidence_sha256 FROM ac3_paired_budget_receipts WHERE scope_id=:scope AND test_id=:test AND role='target' AND status='settled'"),{'scope':scope,'test':test_id}).mappings().first()
                answer=target_receipt['response_text'] if target_receipt else None
                if (not answer or hashlib.sha256(answer.encode()).hexdigest()!=target_answer_sha256
                        or not target_receipt['request_evidence_json']
                        or hashlib.sha256(target_receipt['request_evidence_json'].encode()).hexdigest()!=target_receipt['request_evidence_sha256']):
                    raise ValueError('Scorer must bind the settled target answer')
                run_id=json.loads(target_receipt['request_evidence_json']).get('run_id')
                if not isinstance(run_id,str) or not run_id.strip():raise ValueError('Target run identity is missing')
                local_id='AC3'+hashlib.sha256(f'{self.frozen_sha256}|{run_id}|{test_id}'.encode()).hexdigest()[:32].upper()
                response_id='ACR'+hashlib.sha256(f"{scope}|{target_receipt['request_key']}".encode()).hexdigest()[:32].upper()
                saved=conn.execute(select(TargetResponseModel.id,TargetResponseModel.run_id,TargetResponseModel.response_text,
                    TargetResponseModel.execution_metadata).where(TargetResponseModel.test_id==local_id)).mappings().all()
                if (len(saved)!=1 or saved[0]['id']!=response_id or saved[0]['run_id']!=run_id or saved[0]['response_text']!=answer
                        or (saved[0]['execution_metadata'] or {}).get('ac3_paired_request_evidence_sha256')!=target_receipt['request_evidence_sha256']):
                    raise ValueError('The saved system answer differs from the settled target receipt')
            conn.execute(text("INSERT INTO ac3_paired_budget_receipts (request_key,scope_id,test_id,role,contract_sha256,target_answer_sha256,request_evidence_json,request_evidence_sha256,reserved_usd,status) VALUES (:key,:scope,:test,:role,:contract,:answer_sha,:evidence,:evidence_sha,:reserve,'dispatched')"),
                {'key':request_key,'scope':scope,'test':test_id,'role':role,'contract':contract_sha256,'answer_sha':target_answer_sha256,
                 'evidence':evidence_json,'evidence_sha':evidence_sha,'reserve':str(reserve)})
            conn.execute(text("UPDATE ac3_paired_budget_scopes SET status='unknown' WHERE scope_id=:scope"),{'scope':scope})
        return {'status':'reserved','provider_called':False}

    def settle(self,scope,request_key,contract_sha256,response,reported_cost_usd,*,response_metadata=None):
        _id(scope,64);_id(request_key,120);_digest(contract_sha256)
        if not isinstance(response,str) or not response.strip() or len(response)>1_000_000:raise ValueError('Invalid response')
        metadata_json=None
        if response_metadata is not None:
            if not isinstance(response_metadata,dict) or response_metadata.get('request_contract_sha256')!=contract_sha256:
                raise ValueError('Response metadata does not bind the request')
            metadata_json=json.dumps(response_metadata,ensure_ascii=False,sort_keys=True,separators=(',',':'))
            if len(metadata_json.encode())>1_000_000:raise ValueError('Response metadata is too large')
        target,prior,scorer=self._validated()
        try:
            cost=None if reported_cost_usd is None else money(reported_cost_usd)
        except ValueError:
            # Preserve the answer; an unusable provider cost remains unknown.
            cost=None
        suffix=' FOR UPDATE' if self.engine.dialect.name=='postgresql' else ''
        with self.engine.begin() as conn:
            scope_row=conn.execute(text('SELECT * FROM ac3_paired_budget_scopes WHERE scope_id=:scope'+suffix),{'scope':scope}).mappings().first()
            receipt=conn.execute(text('SELECT * FROM ac3_paired_budget_receipts WHERE request_key=:key'+suffix),{'key':request_key}).mappings().first()
            if (not scope_row or scope_row['frozen_sha256']!=self.frozen_sha256 or scope_row['budget_sha256']!=self.budget_sha256
                    or not receipt or receipt['scope_id']!=scope or receipt['contract_sha256']!=contract_sha256):
                raise ValueError('No uniquely pending request')
            if (money(scope_row['max_usd'])!=money(target['max_usd']) or money(scope_row['prior_upper_usd'])!=prior
                    or money(scope_row['target_reserve_usd'])!=money(target['reservation_per_target_usd'])
                    or money(scope_row['scorer_reserve_usd'])!=scorer or receipt['test_id'] not in target['eligible_test_ids']
                    or receipt['role'] not in ('target','scorer')
                    or money(receipt['reserved_usd'])!=(money(target['reservation_per_target_usd']) if receipt['role']=='target' else scorer)):
                raise ValueError('Stored budget or request differs from frozen assumptions')
            if receipt['role']=='scorer':
                answer=conn.execute(text("SELECT response_text FROM ac3_paired_budget_receipts WHERE scope_id=:scope AND test_id=:test AND role='target' AND status='settled'"),
                                    {'scope':scope,'test':receipt['test_id']}).scalar_one_or_none()
                if not answer or hashlib.sha256(answer.encode()).hexdigest()!=receipt['target_answer_sha256']:
                    raise ValueError('Saved target answer differs from the scorer binding')
            if receipt['role']=='target' and cost is not None:
                raise ValueError('Known-cost target answers require atomic target settlement')
            if receipt['status']=='settled' and scope_row['status']=='active':
                if (cost is None or receipt['response_text']!=response or receipt['reported_cost_usd'] is None
                        or money(receipt['reported_cost_usd'])!=cost):
                    raise ValueError('Existing settled response or cost differs')
                return {'status':'already_settled','provider_called':False}
            if scope_row['status']!='unknown' or receipt['status'] not in ('dispatched','pending'):
                raise ValueError('No uniquely pending request')
            if receipt['response_text'] is not None and receipt['response_text']!=response:raise ValueError('Saved response differs')
            if receipt['response_metadata_json'] is not None and metadata_json!=receipt['response_metadata_json']:
                raise ValueError('Saved response metadata differs')
            if cost is None:
                conn.execute(text("UPDATE ac3_paired_budget_receipts SET response_text=:response,response_metadata_json=:metadata,status='pending' WHERE request_key=:key"),{'response':response,'metadata':metadata_json,'key':request_key})
                return {'status':'cost_unknown','provider_called':False}
            spent=money(scope_row['spent_usd'])+cost
            overrun=target.get('budget_mode','capped')!='tracking_only' and (cost>money(receipt['reserved_usd']) or money(scope_row['prior_upper_usd'])+spent>money(scope_row['max_usd']))
            conn.execute(text('UPDATE ac3_paired_budget_receipts SET response_text=:response,reported_cost_usd=:cost,status=:status WHERE request_key=:key'),
                         {'response':response,'cost':str(cost),'status':'overrun' if overrun else 'settled','key':request_key})
            conn.execute(text('UPDATE ac3_paired_budget_scopes SET spent_usd=:spent,status=:status WHERE scope_id=:scope'),
                         {'spent':str(spent),'status':'overrun' if overrun else 'active','scope':scope})
        return {'status':'overrun' if overrun else 'settled','provider_called':False}
