"""Recover only B suite-lock rejections proven to have made zero model calls.

Original journals are archived and hashed, never overwritten. A successful,
failed-provider or ambiguous provider dispatch is never repeated. This wrapper
serialises conditions within each history while running three histories in
parallel, using the original frozen condition implementation unchanged.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor as RealExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output/proposal-delivery/bc-reader-retest-20261101-v2/B'
ORIGINAL = ROOT/'scripts/bc_retest_b_20261101.py'
def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p, value): Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def candidate_journals():
    found = []
    for path in sorted((OUT/'executions').glob('*.json')):
        data = read(path)
        posts = [o for o in data['operations'] if o['method']=='POST' and o['path'].endswith('/execute')]
        if len(posts)==1 and posts[0].get('state')=='failed_without_retry' and posts[0].get('status')==409 and posts[0].get('error')=='This audit stage is already running.':
            found.append((path, data))
    return found


def proof():
    from sqlalchemy import select, func
    from app.database.session import SessionLocal
    from app.models import (AuditRunModel, TargetResponseModel, AgentExecutionModel,
        TargetAgentMemoryModel, TargetAgentRetrievalModel)
    results = []
    with SessionLocal() as db:
        for path, data in candidate_journals():
            rid=data['run_id']; audit=db.get(AuditRunModel,rid)
            counts={name: db.scalar(select(func.count()).select_from(model).where(model.run_id==rid))
                    for name,model in [('responses',TargetResponseModel),('agent_executions',AgentExecutionModel),
                        ('target_memories',TargetAgentMemoryModel),('retrievals',TargetAgentRetrievalModel)]}
            results.append({'run_id':rid,'journal':path.name,'journal_sha256':sha(path),
                'audit_status':audit.status,'counts':counts,
                'eligible':audit.status=='TESTS_GENERATED' and not any(counts.values())})
    print(json.dumps({'observed_utc':datetime.now(timezone.utc).isoformat(),'proofs':results}))


def snapshot():
    from sqlalchemy import select
    from app.database.session import SessionLocal
    from app.models import AuditRunModel,TargetResponseModel,TestCaseModel,AgentExecutionModel
    from app.api.routes import audit_schema,response_schema,public_test_schema,target_memory_trace_payload
    regs=read(OUT/'registrations.json')['registrations']; results=[]
    with SessionLocal() as db:
        for row in regs:
            rid=row['run_id']; audit=db.get(AuditRunModel,rid)
            answers=list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id==rid)).all())
            tests=list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==rid)).all())
            agents=list(db.scalars(select(AgentExecutionModel).where(AgentExecutionModel.run_id==rid)).all())
            results.append({**row,'audit':audit_schema(audit).model_dump(mode='json'),
                'tests':[public_test_schema(t).model_dump(mode='json') for t in tests],
                'responses':[response_schema(r).model_dump(mode='json') for r in answers],
                'trace':target_memory_trace_payload(audit,db).model_dump(mode='json'),
                'agent_statuses':[{'role':a.role,'status':a.status,'error_code':a.error_code} for a in agents]})
    print(json.dumps({'observed_utc':datetime.now(timezone.utc).isoformat(),'conditions':results},ensure_ascii=False))


class HistorySequentialExecutor:
    def __init__(self, max_workers=3): self.real=RealExecutor(max_workers=3)
    def __enter__(self): return self
    def __exit__(self,*args): return self.real.__exit__(*args)
    def map(self, fn, rows):
        groups={}
        for row in rows: groups.setdefault(row['history_id'],[]).append(row)
        def stream(group): return [fn(row) for row in group]
        return [value for group in self.real.map(stream,groups.values()) for value in group]


def docker(mode):
    proc=subprocess.run(['docker','compose','exec','-T','backend','python',
        '/scripts/bc_retest_b_zero_dispatch_recovery_20261101.py',mode],cwd=ROOT,
        capture_output=True,text=True,check=True)
    return json.loads(proc.stdout)


def recover():
    if not (OUT/'collection-status.json').exists():
        raise ValueError('Wait for the initial dispatcher to finish before recovery')
    result=docker('--proof')
    if not result['proofs'] or not all(row['eligible'] for row in result['proofs']):
        raise ValueError('A precondition reject lacks zero-dispatch proof; do not redispatch')
    amendment={'format':'b-zero-provider-dispatch-infrastructure-amendment-v1',
        'recorded_utc':datetime.now(timezone.utc).isoformat(), 'protocol_sha256':sha(OUT/'protocol.json'),
        'original_script_sha256':sha(ORIGINAL),'recovery_script_sha256':sha(__file__),
        'reason':'Concurrent conditions within one experiment hit the suite lock before target ingestion or any provider call.',
        'correction':'One sequential condition stream per history; at most three histories run concurrently.',
        'no_outcome_selection':'Every and only 409 suite-lock precondition rejection with zero responses, zero target memories, zero retrievals and zero agent calls is rescheduled. Returned/provider-failed/ambiguous calls are never repeated.',
        'proof':result}
    dest=OUT/'infrastructure-recovery-amendment.json'
    if dest.exists(): raise ValueError('Existing recovery amendment retained')
    write(dest,amendment)
    archive=OUT/'pre-dispatch-blocks';archive.mkdir(exist_ok=False)
    for row in result['proofs']:
        source=OUT/'executions'/row['journal']
        if sha(source)!=row['journal_sha256']: raise ValueError('Journal changed after proof')
        source.rename(archive/source.name)
    spec=importlib.util.spec_from_file_location('frozen_b_retest',ORIGINAL)
    original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    original.concurrent.futures.ThreadPoolExecutor=HistorySequentialExecutor
    original.execute()
    enrich()


def enrich():
    result=docker('--snapshot')
    write(OUT/'read-only-final-snapshots.json',result)
    # Add the read-only trace to each retained journal without hiding its
    # original public-endpoint 409; the byte-exact original is archived first.
    archive=OUT/'before-read-only-enrichment';archive.mkdir(exist_ok=True)
    for row in result['conditions']:
        path=OUT/'executions'/f"r{row['repetition']}-{row['history_id']}-{row['strategy']}.json"
        if not path.exists(): continue
        original=path.read_bytes(); archived=archive/path.name
        if not archived.exists(): archived.write_bytes(original)
        data=json.loads(original)
        if not any(o.get('read_only_recovery') for o in data['operations']):
            data['operations'].append({'method':'GET','path':f"/audits/{row['run_id']}/target-memory-trace",
                'state':'returned','status':200,'read_only_recovery':True,'response':row['trace']})
            data['operations'].append({'method':'GET','path':f"/audits/{row['run_id']}/responses",
                'state':'returned','status':200,'read_only_recovery':True,'response':row['responses']})
        if len(row['responses'])==4:
            data['answer_collection_status']='complete_four_saved_answers_ai_review_pending'
        elif row['responses']:
            data['answer_collection_status']='partial_saved_answers_missing_retained'
        else:
            data['answer_collection_status']='no_saved_answer'
        write(path,data)
    spec=importlib.util.spec_from_file_location('frozen_b_prepare',ORIGINAL)
    original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    draft_archive=OUT/'initial-infrastructure-review-drafts';draft_archive.mkdir(exist_ok=True)
    for blank in (OUT/'blind-review').glob('reviewer-*.blank.json'):
        saved_count=sum(len(row['responses']) for row in result['conditions'])
        if len(read(blank).get('items',[]))!=saved_count:
            old=draft_archive/blank.name
            if not old.exists(): blank.rename(old)
            else: blank.unlink()
    original.prepare_review()


if __name__=='__main__':
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    for mode in ('proof','snapshot','recover','enrich'):g.add_argument('--'+mode,action='store_true')
    a=p.parse_args()
    if a.proof:proof()
    elif a.snapshot:snapshot()
    elif a.recover:recover()
    else:enrich()
