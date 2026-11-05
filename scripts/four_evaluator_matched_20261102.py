import hashlib,json,os,sys,time,datetime
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import httpx
from app.evaluator.taxonomy_evaluator import RUBRIC
from app.evaluator.llm_judge import LLMBehaviourEvaluator
ROOT=Path('/output/proposal-delivery')
OLD=ROOT/'ac3-astra-max-retest-20261101-v2'
OUT=Path('/ac3-results/four-evaluator-matched-20261102-v1')
SCHEMA={'type':'object','additionalProperties':False,'required':['passed','reason','evidence_memory_ids','failure_type','classification_reason'],'properties':{'passed':{'type':['boolean','null']},'reason':{'type':'string'},'evidence_memory_ids':{'type':'array','items':{'type':'string'}},'failure_type':{'type':['string','null'],'enum':['accuracy','freshness','conflict_resolution','appropriate_use',None]},'classification_reason':{'type':'string'}}}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(path,obj):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
items=json.loads((OLD/'private-scorer-inputs.json').read_text())['items']
protocol={'cohort':'existing AC3 Astra MAX 120 model answers, 30 related synthetic histories','inputs_sha256':sha(OLD/'private-scorer-inputs.json'),'reference_sha256':sha(OLD/'reference-consensus.json'),'reference':'two user-confirmed independent human checks of AI-assisted reviews; prior observations mean this is not a held-out comparison','models':{'rule':'archived rule-based-v65 saved judgments','astra':'existing gpt-6-astra max saved judgments','qwen':'ollama qwen3:1.7b think=false','luna':'OpenAI gpt-6-luna medium'},'model_scorers':'same source-derived taxonomy rubric and structured output, question + answer + confirmed memories; no expected answer, human label, or dimension','scoring':'failure recall = correctly identified human-reference failures / all 69 agreed failures; false-positive numerator and all 51 human-pass denominator reported; abstentions and transport errors counted as not detected and separately reported','call_policy':'one attempt per answer, no outcome-based retries; no invented results; raw outputs preserved','caveats':['model endpoints and structured output implementation differ','rule baseline is deterministic and uses its archived inputs and implementation','existing answers were produced by Astra MAX','previous reference reviews used AI assistance','reuse of cases means not prospective held-out evidence']}
OUT.mkdir(exist_ok=True,parents=True)
pp=OUT/'protocol.json'
if pp.exists():
 if json.loads(pp.read_text())!=protocol:raise SystemExit('protocol mismatch')
else:write(pp,protocol)
def one(model,item):
 tid=item['test']['test_id']; dest=OUT/model/(str(tid)+'.json');dest.parent.mkdir(exist_ok=True)
 if dest.exists():return 'existing'
 mem=[{'memory_id':m['memory_id'],'canonical_value':m['canonical_value'],'timestamp':m.get('timestamp')} for m in item['memories']]
 prompt='Question: '+item['test']['prompt']+'\nTarget answer: '+item['response']['response_text']+'\nConfirmed memory records: '+json.dumps(mem,ensure_ascii=False)
 result={'test_id':tid,'model':model,'state':'started','attempts':1,'started':datetime.datetime.now(datetime.timezone.utc).isoformat()};write(dest,result)
 try:
  if model=='luna':
   payload={'model':'gpt-6-luna','reasoning':{'effort':'medium'},'max_output_tokens':8192,'instructions':RUBRIC,'input':prompt,'text':{'format':{'type':'json_schema','name':'ac3_taxonomy_judgment','strict':True,'schema':SCHEMA}}}
   r=httpx.post('https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},json=payload,timeout=300);result['http_status']=r.status_code;r.raise_for_status();d=r.json();result['provider_response_id']=d.get('id');result['reported_model']=d.get('model');result['usage']=d.get('usage'); result['completion_status']=d.get('status');result['raw_content']=d.get('output',[])
   if d.get('model')!='gpt-6-luna' or d.get('status')!='completed':raise ValueError('model_or_completion_mismatch')
   t=''.join(p.get('text','') for o in d.get('output',[]) if o.get('type')=='message' for p in o.get('content',[]) if p.get('type')=='output_text')
  else:
   payload={'model':'qwen3:1.7b','stream':False,'think':False,'format':SCHEMA,'messages':[{'role':'system','content':RUBRIC},{'role':'user','content':prompt}],'options':{'num_predict':2048,'temperature':0}}
   r=httpx.post('http://host.docker.internal:11434/api/chat',json=payload,timeout=300);result['http_status']=r.status_code;r.raise_for_status();d=r.json();result['reported_model']=d.get('model');result['usage']={k:d.get(k) for k in ('prompt_eval_count','eval_count','total_duration')};result['raw_content']=d.get('message');t=d.get('message',{}).get('content','')
   if d.get('model')!='qwen3:1.7b' or not d.get('done'):raise ValueError('model_or_completion_mismatch')
  j=json.loads(t);LLMBehaviourEvaluator._validated_result(j,{m['memory_id'] for m in mem})
  if j.get('passed') is not None and not j.get('evidence_memory_ids'):raise ValueError('decided_without_evidence')
  result.update(state='returned',judgment=j)
 except Exception as e:result.update(state='failed',error_type=type(e).__name__)
 result['finished']=datetime.datetime.now(datetime.timezone.utc).isoformat();write(dest,result);return result['state']
model=sys.argv[1]
if model not in ('qwen','luna'):raise SystemExit('invalid model')
workers=2 if model=='qwen' else 4
with ThreadPoolExecutor(max_workers=workers) as ex:
 futures=[ex.submit(one,model,x) for x in items]
 for i,f in enumerate(as_completed(futures),1):
  state=f.result()
  if i%10==0 or i==len(items):print(json.dumps({'model':model,'processed':i,'total':len(items),'last_state':state}),flush=True)
