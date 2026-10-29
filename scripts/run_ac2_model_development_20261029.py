"""Exploratory model-backed question generation on previously observed sources.

No answer generation, human labelling or post-failure retry. Never an independent retest.
"""
import hashlib,json,pathlib,subprocess,urllib.request,urllib.error,threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime,timezone
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'output/proposal-delivery/ac2-v4-prospective-product-20261029-v1/ledger.json'
OUT=ROOT/'output/proposal-delivery/ac2-model-development-20261029-v1'
SCRIPT=pathlib.Path(__file__).resolve()
URL='http://127.0.0.1:8000/api/v1'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()
def hashes():return {str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))}
def save(path,data,exclusive=False):
 if exclusive:
  with path.open('x',encoding='utf8') as f: json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
 else:
  tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
ledger=json.loads(SOURCE.read_bytes())
sources=[{'history_id':h['history_id'],'conversation_id':h['product_conversation_id']} for h in ledger['histories'][:3]]
if [x['history_id'] for x in sources]!=['prospective-01','prospective-02','prospective-03']:raise ValueError('Unexpected frozen source order')
OUT.mkdir(parents=True,exist_ok=False)
config={'format':'ac2-model-development-freeze-v1','frozen_utc':utc(),'source_ledger_sha256':sha(SOURCE),'sources':sources,'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'application_sha256':hashes(),'runner_sha256':sha(SCRIPT),'budget_per_history':4,'settings':{'target_configuration':'weak','provider':'rule_based','model':'rule-based-target-ai','pipeline_provider':'openrouter','pipeline_model':'openai/gpt-6-luna','semantic_review_provider':'openrouter','semantic_review_model':'openai/gpt-6-luna','evaluator_provider':'rule_based','test_budget':4,'random_seed':42,'temperature':0,'memory_strategy':'weak_first_hit'},'protocol':'Create one audit and make one generation API request per history; do not retry, execute target answers, change source memories or supply human judgments. Log every request, model execution and failure. Concurrent histories; fail closed if code/source differs before dispatch.','limitations':['Development examples selected after prior observed outcomes; not a prospective held-out evaluation.','Synthetic histories share source patterns and author references are not human gold.','Memory confirmation in original study was a simulated operator action, not human validation.','Generated questions and expected answers need source-grounded human review.','Provider costs are reported only when available; failed requests may incur unreported charges.']}
save(OUT/'protocol.json',config,True)
if hashes()!=config['application_sha256'] or sha(SOURCE)!=config['source_ledger_sha256'] or sha(SCRIPT)!=config['runner_sha256']:raise ValueError('Inputs changed before dispatch')
print('Protocol frozen; three generation operations will be recorded.',flush=True)
def work(source):
 path=OUT/(source['history_id']+'.json')
 row={'source':source,'protocol_sha256':sha(OUT/'protocol.json'),'started_utc':utc(),'requests':[],'status':'started'};save(path,row,True)
 def request(method,endpoint,data=None,timeout=1200):
  obj={'method':method,'path':endpoint,'request':data,'dispatched_utc':utc(),'status':'dispatched'};row['requests'].append(obj);save(path,row)
  req=urllib.request.Request(URL+endpoint,method=method,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(req,timeout=timeout) as r: obj.update(status='returned',http_status=r.status,response=json.load(r))
  except urllib.error.HTTPError as exc:obj.update(status='http_error',http_status=exc.code,response=exc.read().decode(errors='replace'))
  except Exception as exc:obj.update(status='transport_error',error_type=type(exc).__name__,error=str(exc))
  obj['finished_utc']=utc();save(path,row);return obj
 try:
  if hashes()!=config['application_sha256']:raise ValueError('Application sources changed before this audit')
  created=request('POST','/audits',{'conversation_id':source['conversation_id'],**config['settings']})
  if created['status']!='returned':raise ValueError('Audit creation failed')
  rid=created['response']['run_id'];row['run_id']=rid;save(path,row)
  result=request('POST',f'/audits/{rid}/generate-tests',None)
  if result['status']=='returned':
   tests=result['response']; row['generated_count']=len(tests);row['dimensions']={d:sum(t['dimension']==d for t in tests) for d in sorted({t['dimension'] for t in tests})};row['quality']={s:sum(t['quality_status']==s for t in tests) for s in sorted({t['quality_status'] for t in tests})}
   request('GET',f'/audits/{rid}/test-review',None)
   request('POST',f'/audits/{rid}/tests/scope-review',None)
  request('GET',f'/audits/{rid}/agent-executions',None,timeout=60)
  request('GET',f'/audits/{rid}',None,timeout=60)
  row['status']='completed' if result['status']=='returned' else 'generation_failed'
 except Exception as exc:row.update(status='failed',error_type=type(exc).__name__,error=str(exc))
 row['finished_utc']=utc();save(path,row);print(source['history_id'],row['status'],row.get('generated_count',0),flush=True)
with ThreadPoolExecutor(max_workers=3) as pool:
 futures=[pool.submit(work,s) for s in sources]
 for f in as_completed(futures):f.result()
rows=[json.loads((OUT/(s['history_id']+'.json')).read_text()) for s in sources]
save(OUT/'summary.json',{'format':'ac2-model-development-summary-v1','protocol_sha256':sha(OUT/'protocol.json'),'histories':3,'requested_max_questions':12,'generated':sum(r.get('generated_count',0) for r in rows),'generation_success_histories':sum(r['status']=='completed' for r in rows),'runs':[{'history_id':r['source']['history_id'],'run_id':r.get('run_id'),'status':r['status'],'generated_count':r.get('generated_count',0),'record_sha256':sha(OUT/(r['source']['history_id']+'.json'))} for r in rows],'limitations':config['limitations']},True)
print('Complete; all individual records preserved.',flush=True)
