"""Run the frozen 48-pair exploratory retest, preserving all prior data.

Only the retrieval/packaging intervention changes. The target is called once
per new answer; checkpoint before each call and never repeat an ambiguous call.
"""
import hashlib,json,os
from pathlib import Path
from datetime import datetime,timezone
from urllib.error import HTTPError
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'output/experiment-a-expanded-20261030';SOURCE=D/'four-scenario-v7-question-ledger.json';PLAN=D/'retrieval-retest-protocol.json';AMEND=D/'retrieval-retest-protocol-amendment.json';STATE=D/'retrieval-retest-execution.json'
study='retrieval-a-v7-packet-20261030';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=json.loads(SOURCE.read_text());plan=json.loads(PLAN.read_text());amend=json.loads(AMEND.read_text())
if plan['source_question_ledger_sha256']!=sha(SOURCE) or amend['prior_protocol_sha256']!=sha(PLAN):raise SystemExit('Frozen input changed')
sources=[(hid,s) for hid,h in source['histories'].items() for s in h['suites']]
if len(sources)!=12 or sum(len(s['tests']) for _,s in sources)!=48:raise SystemExit('Expected 12 conditions and 48 questions')
app_hashes={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))}
state=json.loads(STATE.read_text()) if STATE.exists() else {'study_id':study,'protocol_sha256':sha(PLAN),'amendment_sha256':sha(AMEND),'application_sha256':app_hashes,'created_at':datetime.now(timezone.utc).isoformat(),'conditions':{},'notes':'Retest only changes private retrieval and bundles selected memories; same weak reader and saved questions. Exploratory, based on observed baseline.'}
if state['protocol_sha256']!=sha(PLAN) or state['application_sha256']!=app_hashes:raise SystemExit('Frozen protocol or application changed; inspect before resuming')
def save():
 p=STATE.with_suffix('.tmp');p.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');os.replace(p,STATE)
def call(row,key,method,path,body=None,timeout=900):
 op={'method':method,'path':path,'body':body};sig=hashlib.sha256(json.dumps(op,sort_keys=True).encode()).hexdigest();prev=row['operations'].get(key)
 if prev:
  if prev['sig']!=sig or prev['state']!='returned':raise RuntimeError(f'{key}: prior attempt requires reconciliation')
  return prev['response']
 row['operations'][key]={**op,'sig':sig,'state':'dispatched'};save()
 req=Request('http://127.0.0.1:8000/api/v1'+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 try:
  with urlopen(req,timeout=timeout) as response:result=json.load(response)
 except HTTPError as exc:row['operations'][key].update(state='http_error',code=exc.code,error=exc.read().decode());save();raise
 except Exception:row['operations'][key]['state']='ambiguous';save();raise
 row['operations'][key].update(state='returned',response=result);save();print(row['history_id'],row['method'],key,flush=True);return result
fields=['target_configuration','provider','model','temperature','random_seed','test_budget','pipeline_provider','pipeline_model','semantic_review_provider','semantic_review_model','evaluator_provider','evaluator_model','retrieval_mode','retrieval_provider','retrieval_model','memory_maintenance_policy','target_memory_capacity','target_memory_writer','target_system_adapter']
def signature(t):return (t['dimension'],t['prompt'],t['expected_behavior'],tuple(sorted(t['supporting_memory_ids'])),t['test_type'])
save()
for hid,suite in sources:
 rid=suite['run_id'];row=state['conditions'].setdefault(rid,{'history_id':hid,'method':suite['method'],'source_run_id':rid,'operations':{}});save()
 try:
  source_audit=call(row,'source-details','GET',f'/audits/{rid}')
  child=call(row,'register','POST',f'/audits/{rid}/retrieval-improvement',{'study_id':study});newid=child['run_id']
  candidate=call(row,'candidate-details','GET',f'/audits/{newid}')
  mismatched=[field for field in fields if source_audit.get(field)!=candidate.get(field)]
  if mismatched or candidate.get('memory_strategy')!='relationship_packet':raise RuntimeError(f'Unexpected settings: {mismatched}')
  if source_audit.get('reproducibility',{}).get('target_memory_profile')!=candidate.get('reproducibility',{}).get('target_memory_profile'):raise RuntimeError('Target profile differs')
  newtests=call(row,'candidate-tests','GET',f'/audits/{newid}/tests')
  if sorted(map(signature,suite['tests']))!=sorted(map(signature,newtests)):raise RuntimeError('Candidate questions differ')
  result=call(row,'execute','POST',f'/audits/{newid}/execute',{})
  if len(result)!=4:raise RuntimeError('Candidate response count incomplete')
  call(row,'evaluate','POST',f'/audits/{newid}/evaluate',{})
  row.update(candidate_run_id=newid,status='completed_review_pending');save()
 except Exception as exc:row.update(status='stopped',error=str(exc));save();raise SystemExit(f'{hid} {suite["method"]} stopped: {exc}') from exc
state['status']='completed_review_pending';save();print('12 conditions, 48 new paired answers saved; review pending.')
