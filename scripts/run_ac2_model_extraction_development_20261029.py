"""Model extraction and model question-generation development probe, not validation."""
import collections,hashlib,json,pathlib,subprocess,urllib.request,urllib.error
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'output/proposal-delivery/ac2-prospective-new-histories-20261029/histories.json'
OUT=ROOT/'output/proposal-delivery/ac2-model-extraction-development-20261029-v1'
SCRIPT=pathlib.Path(__file__).resolve(); URL='http://127.0.0.1:8000/api/v1'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def hashes():return {str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))}
def save(path,data,exclusive=False):
 if exclusive:
  with path.open('x',encoding='utf8') as f:json.dump(data,f,indent=2,ensure_ascii=False);f.write('\n')
 else:
  tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n');tmp.replace(path)
rows=json.loads(SOURCE.read_bytes())['conversations'][:3]
if [s['conversation_id'] for s in rows]!=['prospective-01','prospective-02','prospective-03']:raise ValueError('Unexpected source identities')
OUT.mkdir(parents=True,exist_ok=False)
protocol={'format':'ac2-model-extraction-development-freeze-v1','frozen_utc':now(),'source_sha256':sha(SOURCE),'history_ids':[s['conversation_id'] for s in rows],'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'application_sha256':hashes(),'runner_sha256':sha(SCRIPT),'design':'Import a new copy of each source; invoke OpenRouter GPT-6 Luna extraction once; preserve provider trace, then SIMULATE confirming extracted memories with valid source IDs without any claim of human verification; create one model-generator audit per source, budget 4, call generation once, preserve raw outcomes. No target execution; no human labels; no script-level retry. Backend request behavior and provider retries are retained in execution traces.','settings':{'extract':{'provider':'openrouter','model':'openai/gpt-6-luna'},'audit':{'target_configuration':'weak','provider':'rule_based','model':'rule-based-target-ai','pipeline_provider':'openrouter','pipeline_model':'openai/gpt-6-luna','semantic_review_provider':'openrouter','semantic_review_model':'openai/gpt-6-luna','evaluator_provider':'rule_based','test_budget':4,'random_seed':42,'temperature':0,'memory_strategy':'weak_first_hit'}},'limitations':['Three previously observed AI-authored synthetic sources; development only, not independent or representative.','Original author labels and AI review are not human gold.','Operator confirmation here is a simulation and does not establish source validity.','Source and generated questions need separate review.','Provider cost may be absent or incomplete; HTTP failures can still be charged.']}
save(OUT/'protocol.json',protocol,True)
if hashes()!=protocol['application_sha256'] or sha(SOURCE)!=protocol['source_sha256'] or sha(SCRIPT)!=protocol['runner_sha256']:raise ValueError('Source, runner or app changed before execution')
print('Frozen three-source model development probe.',flush=True)
def run(source):
 hid=source['conversation_id'];path=OUT/(hid+'.json');row={'history_id':hid,'started_utc':now(),'protocol_sha256':sha(OUT/'protocol.json'),'requests':[],'status':'started','confirmation':'SIMULATED; not human review or gold'};save(path,row,True)
 def req(method,endpoint,data=None,timeout=1800):
  r={'method':method,'path':endpoint,'request':data,'dispatched_utc':now(),'status':'dispatched'};row['requests'].append(r);save(path,row)
  q=urllib.request.Request(URL+endpoint,method=method,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(q,timeout=timeout) as v:r.update(status='returned',http_status=v.status,response=json.load(v))
  except urllib.error.HTTPError as e:r.update(status='http_error',http_status=e.code,response=e.read().decode(errors='replace'))
  except Exception as e:r.update(status='transport_error',error_type=type(e).__name__,error=str(e))
  r['finished_utc']=now();save(path,row);return r
 def ok(r,stage):
  if r['status']!='returned':raise ValueError(stage+' failed')
  return r['response']
 try:
  if hashes()!=protocol['application_sha256']:raise ValueError('Application changed before source import')
  ms=[{'message_id':m['source_message_id'],'role':m['role'],'content':m['text'],'timestamp':m['timestamp'],'original_timestamp':m['timestamp']} for m in source['messages']]
  c=ok(req('POST','/conversations',{'authorised':True,'source_origin':'synthetic','messages':ms}),'import');cid=c['conversation_id'];row['product_conversation_id']=cid;save(path,row)
  extraction=req('POST',f'/conversations/{cid}/extract',protocol['settings']['extract'])
  req('GET',f'/conversations/{cid}/agent-executions',None,60)
  memories=ok(extraction,'extraction'); row['candidate_count']=len(memories)
  available={m['source_message_id'] for m in source['messages']}
  if not memories or any(not m['source_message_ids'] or not set(m['source_message_ids']).issubset(available) for m in memories):raise ValueError('Missing candidate/source references; no confirmation')
  row['extracted_relationships']=dict(collections.Counter(e['type'] for m in memories for e in m.get('relationships',[])));save(path,row)
  ok(req('POST',f'/conversations/{cid}/confirm-ground-truth',{'confirmed_memory_ids':[m['memory_id'] for m in memories]}),'simulated confirmation')
  if hashes()!=protocol['application_sha256']:raise ValueError('Application changed before audit creation; stop')
  a=ok(req('POST','/audits',{'conversation_id':cid,**protocol['settings']['audit']}),'audit creation');rid=a['run_id'];row['run_id']=rid;save(path,row)
  generated=req('POST',f'/audits/{rid}/generate-tests',None)
  req('GET',f'/audits/{rid}/agent-executions',None,60)
  req('GET',f'/audits/{rid}',None,60)
  if generated['status']=='returned':
   tests=generated['response'];row['generated_count']=len(tests);row['dimensions']=dict(collections.Counter(t['dimension'] for t in tests));row['quality']=dict(collections.Counter(t['quality_status'] for t in tests));req('GET',f'/audits/{rid}/test-review',None,60);req('POST',f'/audits/{rid}/tests/scope-review',None,60)
  row['status']='completed' if generated['status']=='returned' else 'generation_failed'
 except Exception as e:row.update(status='failed',error_type=type(e).__name__,error=str(e))
 row['finished_utc']=now();save(path,row);print(hid,row['status'],row.get('candidate_count'),row.get('generated_count',0),flush=True)
with ThreadPoolExecutor(max_workers=3) as pool:
 for f in as_completed([pool.submit(run,s) for s in rows]):f.result()
results=[json.loads((OUT/(s['conversation_id']+'.json')).read_text()) for s in rows]
summary={'format':'ac2-model-extraction-development-summary-v1','protocol_sha256':sha(OUT/'protocol.json'),'histories':len(results),'requested_max_questions':12,'generated_questions':sum(x.get('generated_count',0) for x in results),'runs':[{'history_id':x['history_id'],'conversation_id':x.get('product_conversation_id'),'run_id':x.get('run_id'),'status':x['status'],'candidate_count':x.get('candidate_count'),'generated_count':x.get('generated_count',0),'record_sha256':sha(OUT/(x['history_id']+'.json'))} for x in results],'limitations':protocol['limitations']}
save(OUT/'summary.json',summary,True);print('Finished; all outcomes preserved.',flush=True)
