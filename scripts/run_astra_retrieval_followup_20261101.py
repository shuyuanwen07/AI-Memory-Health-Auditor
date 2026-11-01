"""Execute a previously frozen exploratory same-question retrieval retest."""
import hashlib,json
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/astra-product-end-to-end-20261101-v1'
PLAN=OUT/'retrieval-followup-protocol.json';LEDGER=OUT/'retrieval-followup-ledger.json'
SOURCE='RUN49C874718ED54D76AFFAC79518A43B9E';CHILD='RUNBF02BDD704734F88B762577C86FDA87F'
if LEDGER.exists():raise SystemExit('Existing attempt retained; inspect before any further request.')
sha=lambda b:hashlib.sha256(b).hexdigest()
plan=json.loads(PLAN.read_bytes())
if plan['source_run_id']!=SOURCE or plan['fork_implementation_sha256']!=sha((ROOT/'scripts/fork_astra_diagnostic_20261101.py').read_bytes()):raise SystemExit('Frozen protocol mismatch')
state={'protocol_sha256':sha(PLAN.read_bytes()),'source_run_id':SOURCE,'candidate_run_id':CHILD,'operations':[],'status':'prepared'}
def save():LEDGER.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
def call(method,path,body=None):
    row={'method':method,'path':path,'body':body,'state':'dispatched'};state['operations'].append(row);save()
    try:
        with urlopen(Request('http://127.0.0.1:8000/api/v1'+path,method=method,
             data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=900) as r:row.update(state='returned',status=r.status,response=json.load(r))
    except HTTPError as e:row.update(state='http_error',status=e.code,error=e.read().decode(errors='replace')[:2000]);save();raise
    except Exception as e:row.update(state='ambiguous',error_type=type(e).__name__);save();raise
    save();return row['response']
save()
try:
    old=call('GET',f'/audits/{SOURCE}');new=call('GET',f'/audits/{CHILD}')
    fields=['provider','model','target_configuration','retrieval_mode','test_budget','temperature','random_seed','target_memory_capacity','target_memory_writer','memory_maintenance_policy','target_system_adapter','evaluator_provider','evaluator_model']
    if any(old.get(k)!=new.get(k) for k in fields) or new.get('memory_strategy')!='relationship_packet' or old.get('memory_strategy')!='weak_first_hit':raise ValueError('Paired configuration mismatch')
    if old.get('reproducibility',{}).get('target_memory_profile')!=new.get('reproducibility',{}).get('target_memory_profile'):raise ValueError('Target profile mismatch')
    tests=call('GET',f'/audits/{CHILD}/tests')
    signature=lambda x:(x['dimension'],x['prompt'],x['expected_behavior'],tuple(sorted(x['supporting_memory_ids'])))
    if sorted(map(signature,tests))!=sorted(map(signature,plan['questions'])):raise ValueError('Frozen questions differ')
    responses=call('POST',f'/audits/{CHILD}/execute',{})
    if len(responses)!=4 or any(r.get('execution_metadata',{}).get('reported_model')!='gpt-6-astra' or r.get('execution_metadata',{}).get('requested_reasoning_effort')!='max' for r in responses):raise ValueError('Candidate response or provider receipt mismatch')
    evaluations=call('POST',f'/audits/{CHILD}/evaluate',{})
    if len(evaluations)!=4:raise ValueError('Candidate assessment count mismatch')
    call('GET',f'/audits/{CHILD}/results');call('GET',f'/audits/{CHILD}/target-memory-trace')
    state['status']='completed_human_review_pending';save()
    print('Candidate completed: 4 answers, human review pending',flush=True)
except Exception as e:
    state.update(status='stopped',error_type=type(e).__name__,error=str(e)[:300]);save();print('Stopped:',type(e).__name__,str(e)[:150],flush=True)
