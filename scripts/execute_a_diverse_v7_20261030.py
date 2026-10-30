"""Run accepted v7 suites after explicit user confirmation; preserve every request."""
import hashlib,json,os
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/experiment-a-expanded-20261030'
suite_path=OUT/'four-scenario-v7-question-ledger.json';confirm_path=OUT/'four-scenario-v7-user-confirmation.json';target=OUT/'four-scenario-v7-execution-ledger.json'
raw=suite_path.read_bytes(); suites=json.loads(raw); sha=hashlib.sha256(raw).hexdigest()
for h in suites['histories'].values():
 if len(h.get('suites',[]))!=3:raise SystemExit('Every scenario requires three complete method suites.')
 for suite in h['suites']:
  if len(suite['tests'])!=4 or {t['dimension'] for t in suite['tests']}!={'accuracy','freshness','conflict_resolution','appropriate_use'}:raise SystemExit('Each method requires four questions and four dimensions.')
confirmation=json.loads(confirm_path.read_text())
if confirmation.get('question_ledger_sha256')!=sha or confirmation.get('questions_confirmed') is not True:raise SystemExit('Explicit user confirmation for this exact question ledger required.')
state=json.loads(target.read_text()) if target.exists() else {'question_ledger_sha256':sha,'conditions':{},'notes':'User-confirmed question validity after two AI reviews; response human judgments remain pending.'}
if state['question_ledger_sha256']!=sha:raise SystemExit('Frozen questions changed')
def save():
 p=target.with_suffix('.tmp');p.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');os.replace(p,target)
def call(row,key,method,path,body):
 op={'method':method,'path':path,'body':body};sig=hashlib.sha256(json.dumps(op,sort_keys=True).encode()).hexdigest();old=row['operations'].get(key)
 if old:
  if old['sig']!=sig or old['status']!='returned':raise RuntimeError(f'{key} requires reconciliation before retry')
  return old['response']
 row['operations'][key]={**op,'sig':sig,'status':'dispatched'};save()
 req=Request('http://127.0.0.1:8000/api/v1'+path,method=method,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 try:
  with urlopen(req,timeout=900) as response:value=json.load(response)
 except HTTPError as e:row['operations'][key].update(status='http_error',code=e.code,error=e.read().decode());save();raise
 except Exception:row['operations'][key]['status']='ambiguous';save();raise
 row['operations'][key].update(status='returned',response=value);save();print(row['history_id'],row['method'],key,flush=True);return value
for hid,h in suites['histories'].items():
 for suite in h.get('suites',[]):
  rid=suite['run_id'];row=state['conditions'].setdefault(rid,{'history_id':hid,'method':suite['method'],'operations':{}});save()
  for test in suite['tests']:
   if test['quality_status']!='accepted':raise SystemExit(f'{test["test_id"]}: quality not accepted')
   call(row,'validity-'+test['test_id'],'PATCH',f'/audits/{rid}/tests/{test["test_id"]}/human-validity-review',{'decision':'accepted','reviewer_pseudonym':'user-confirmed','note':'User explicitly confirmed the source-bound v7 generated question set after two independent AI reviews; user identity and review method self-declared.'})
  call(row,'execute','POST',f'/audits/{rid}/execute',{})
  call(row,'evaluate','POST',f'/audits/{rid}/evaluate',{})
  row['status']='completed_answer_review_pending';save()
print('Comparison runs complete; answer labels and mappings await AI and human review.')
