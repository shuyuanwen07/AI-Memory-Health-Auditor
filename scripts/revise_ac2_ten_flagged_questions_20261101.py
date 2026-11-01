"""Apply independent AI feedback through the product's pre-execution regeneration UI/API."""
import concurrent.futures
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'output/proposal-delivery/ac2-original-ten-repaired-full-retest-20261101-v1'
ANALYSIS=ROOT/'output/proposal-delivery/ac2-original-ten-repaired-review-analysis-20261101-v1/summary.json'
OUT=ROOT/'output/proposal-delivery/ac2-original-ten-question-revisions-20261101-v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=lambda:datetime.now(timezone.utc).isoformat()
def save(p,v):
 t=p.with_suffix('.tmp');t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');t.replace(p)
def hashes():return {str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))}
notes={
 'prospective-10':('freshness','Independent Astra high reviews found the Freshness question can be answered without recounting the update. Explicitly ask what the earlier reading format was and what changed in the recorded update, then ask how to handle the incompatible records for the same effective period. Preserve unresolved conflict. Make every required part of the reference answer explicitly requested by the prompt. Do not disclose concrete formats in the prompt.'),
 'prospective-13':('appropriate_use','Independent Astra high review found daily planning during launch week can coexist with a longer standard planning cycle. Do not assert that daily planning changes or overrides the duration of the standard cycle. Ask how to apply the launch-only planning instruction without settling the incompatible standard-cycle records. Scope daily planning to launch week, preserve both general cycle claims and seek clarification for regular-cycle decisions. Do not invent a temporal overlap or incompatibility of planning frequency and cycle duration.')}
OUT.mkdir(parents=True,exist_ok=False)
protocol={'source_summary_sha256':sha(SOURCE/'summary.json'),'independent_ai_review_sha256':sha(ANALYSIS),
 'app_sha256':hashes(),'started_utc':now(),'scope':'Post-review development revisions of exactly two questions. Original raw cohort and independent judgments retained. Feedback is AI, not human confirmation. Use actual product review+regenerate endpoints; same frozen OpenAI Astra max pipeline; no target answers collected.'}
save(OUT/'protocol.json',protocol)
def revise(hid):
 row=json.loads((SOURCE/(hid+'.json')).read_text());rid=row['run_id'];dim,note=notes[hid]
 old=next(q for r in row['requests'] if r['path'].endswith('/generate-tests') and r['status']=='returned' for q in r['response'] if q['dimension']==dim)
 state={'history_id':hid,'run_id':rid,'original_question':old,'feedback':note,'requests':[],'status':'started'};p=OUT/(hid+'.json');save(p,state)
 def call(method,path,body=None):
  if hashes()!=protocol['app_sha256']:raise ValueError('Runtime changed; no dispatch')
  q={'method':method,'path':path,'request':body,'status':'dispatched','time':now()};state['requests'].append(q);save(p,state)
  try:
   with urlopen(Request('http://127.0.0.1:8000/api/v1'+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=1200) as r:q.update(status='returned',http_status=r.status,response=json.load(r))
  except HTTPError as e:q.update(status='http_error',http_status=e.code,response=e.read().decode(errors='replace'))
  except Exception as e:q.update(status='ambiguous',error_type=type(e).__name__)
  save(p,state)
  if q['status']!='returned':raise RuntimeError('Operation did not return; inspect without automatic replay')
  return q['response']
 try:
  call('PATCH',f"/audits/{rid}/tests/{old['test_id']}/review",{'quality_status':'rejected','note':note})
  new=call('POST',f"/audits/{rid}/tests/{old['test_id']}/regenerate")
  if new['test_id']!=old['test_id'] or new['dimension']!=dim:raise ValueError('Unexpected replacement identity')
  call('GET',f'/audits/{rid}/tests');call('GET',f'/audits/{rid}/agent-executions')
  state['status']='revised_independent_review_pending'
 except Exception as e:state.update(status='stopped',error_type=type(e).__name__,error=str(e)[:250])
 save(p,state);print(hid,state['status'],flush=True);return {'history_id':hid,'status':state['status'],'record_sha256':sha(p)}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(revise,notes))
save(OUT/'summary.json',{'revisions':results,'human_review':'pending'})
