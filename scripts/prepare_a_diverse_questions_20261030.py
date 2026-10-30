"""Freeze source-reviewed inventories and generate A questions; no target calls or human labels.

Reviewer IDs identify independent AI reviews, not human reviewers. The user
confirmed the source and fixed-question release separately; newly generated
questions still require actual user confirmation before the validity gate.
"""
import json,hashlib,os,sys
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output/experiment-a-expanded-20261030'
frozen=OUT/'four-scenario-frozen-input.json'; state_path=OUT/'four-scenario-v7-question-ledger.json'
sources=json.loads(frozen.read_text()); histories={h['history_id']:h for h in sources['histories']}
ledger_paths=[OUT/'four-scenario-v7-source-ledger.json']
prior={}
for path in ledger_paths:
 if path.exists():prior.update(json.loads(path.read_text())['histories'])
state=json.loads(state_path.read_text()) if state_path.exists() else {'source_sha256':hashlib.sha256(frozen.read_bytes()).hexdigest(),'histories':{}}
if state['source_sha256']!=hashlib.sha256(frozen.read_bytes()).hexdigest():raise SystemExit('Frozen source changed')
def save():
 tmp=state_path.with_suffix('.tmp');tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,state_path)
def call(row,key,method,path,body=None):
 op={'method':method,'path':path,'body':body}; sha=hashlib.sha256(json.dumps(op,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 old=row['operations'].get(key)
 if old:
  if old['sha256']!=sha or old['status']!='returned':raise RuntimeError(f'{key}: unresolved previous attempt')
  return old['response']
 row['operations'][key]={**op,'sha256':sha,'status':'dispatched'};save()
 req=Request('http://127.0.0.1:8000/api/v1'+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 try:
  with urlopen(req,timeout=300) as response:value=json.load(response)
 except HTTPError as e:
  row['operations'][key].update(status='http_error',code=e.code,error=e.read().decode());save();raise
 except Exception:
  row['operations'][key]['status']='ambiguous';save();raise
 row['operations'][key].update(status='returned',response=value);save();print(row['history_id'],key,flush=True);return value

for hid in sys.argv[1:]:
 h=histories[hid]; p=prior[hid]
 if p.get('status')!='prepared_inventory_not_frozen':raise SystemExit(f'{hid}: no prepared source')
 row=state['histories'].setdefault(hid,{'history_id':hid,'operations':{}})
 c=p['operations']['campaign-register']['response']; memory_by_source={m['message_id']:p['memory_ids'][i] for i,m in enumerate(h['messages'])}
 def evidence(item):
  ids=item['source_message_ids'];return {'source_message_ids':ids,'supporting_memory_ids':[memory_by_source[i] for i in ids]}
 inv=c['inventory_template'].copy();inv.update(release_id=f'{hid}-user-confirmed-v1',reviewers=['AI-independent-reviewer-1','AI-independent-reviewer-2'],fixed_template_release_id=f'{hid}-user-confirmed-v1',fixed_template_reviewers=['user-confirmed'],fixed_template_review_confirmed=True,
  defects=[{'defect_id':d['defect_id'],'dimension':d['dimension'],'explanation':d['description'],**evidence(d)} for d in h['candidate_failure_patterns']],
  fixed_template_questions=[{'template_id':q['question_id'],'dimension':q['dimension'],'prompt':q['prompt'],'expected_behavior':('Expected: '+q['expected_behavior']+(' Ask the user to clarify which record controls.' if q['dimension']=='conflict_resolution' else '')),'test_type':'contextual',**evidence(q)} for q in h['fixed_question_draft']])
 source=p['source_run_id'];call(row,'inventory','POST',f'/audits/{source}/method-comparison-inventory',inv)
 for run in c['runs']:
  tests=call(row,'generate-'+run['run_id'],'POST',f"/audits/{run['run_id']}/generate-tests",{})
  row.setdefault('suites',[])
  if not any(x['run_id']==run['run_id'] for x in row['suites']):row['suites'].append({'run_id':run['run_id'],'method':run['label'],'tests':tests});save()
  if len(tests)!=4 or {t['dimension'] for t in tests}!={'accuracy','freshness','conflict_resolution','appropriate_use'}:
   row['status']='stopped: incomplete or unbalanced question suite';save();raise SystemExit(f'{hid} {run["label"]}: expected four questions, one per dimension; saved {len(tests)}')
 row['status']='awaiting AI and human question validity review';save()
print('Question preparation complete. No A target calls or human-validity records were made.')
