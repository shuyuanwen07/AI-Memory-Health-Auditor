"""OpenAI Astra paired-source AC2 comparison. Append-only outputs; no product DB writes."""
import concurrent.futures, hashlib, json, os, random, urllib.error, urllib.request, zipfile
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'output/proposal-delivery/ac3-retest-diverse-candidate-2026-10-28-v6'
OUT=ROOT/'output/proposal-delivery/ac2-astra-original-30-max-20261101'
FROZEN=ROOT/'output/proposal-delivery/human-return-2026-10-29-ff607492/ac2-frozen.json'
SOURCE=BASE/'candidate-inputs.json'; PLAN=BASE/'proposed-fact-plan.json'
INSTRUCTIONS='''You create memory-audit questions from confirmed memory records and their relationship labels. Generate up to four distinct questions testing the given memory: use only facts and relationships supported by these records, and do not invent details. Each question should be understandable and answerable without access to memory IDs. Select appropriate dimensions from accuracy, freshness, conflict_resolution, appropriate_use where the records support them; do not invent a conflict or an update merely to fill a dimension. For an unresolved conflict, expect acknowledgement of the conflict rather than guessing which claim is correct. Include concise expected_behavior and supporting_memory_ids for each question. Return a JSON object with a tests array; each test has dimension, question, expected_behavior, supporting_memory_ids. If fewer than four are defensible, return fewer. Do not quote or reuse reference test questions.'''
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):
 t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');t.replace(p)
def now():return datetime.now(timezone.utc).isoformat()
def initialize():
 old=json.loads(FROZEN.read_text())['inputs']; cases=json.loads(SOURCE.read_text())['cases'];plan=json.loads(PLAN.read_text())['histories']
 if sha(SOURCE)!=old['source_sha256'] or sha(PLAN)!=old['plan_sha256'] or [c['history_id'] for c in cases]!=old['history_ids']:raise ValueError('Original source mismatch')
 OUT.mkdir(parents=True,exist_ok=False);(OUT/'responses').mkdir()
 protocol={'created_utc':now(),'history_ids':old['history_ids'],'original_source_sha256':sha(SOURCE),'original_fact_plan_sha256':sha(PLAN),'original_protocol_sha256':sha(FROZEN),'runner_sha256':sha(Path(__file__)),'scheduled_slots':120,'one_call_per_history':True,'generator':'gpt-6-astra','provider':'OpenAI Responses API','reasoning_effort':'max','max_output_tokens':8000,'instructions':INSTRUCTIONS,'input':'Same reviewed fact plan and relationships as original generators. Reference questions and human labels withheld. Source messages supplied to reviewers, not the generator.','limits':['Generator and sampling settings differ from original deterministic rule generator, so comparison assesses a different generator condition, not a model-only switch.','Same 30 synthetic histories previously observed, not held-out independent validation.','A question counts as valid only after two blinded human reviews agree on grounding and executability; missing/uncertain are not counted as valid in scheduled 120 denominator.','No automatic target runs, no product database writes, no retry on failure.']}
 save(OUT/'protocol.json',protocol);save(OUT/'source.json',{'cases':[{'history_id':c['history_id'],'scenario_title':c['scenario_title'],'source_messages':c['source_messages']} for c in cases]});save(OUT/'fact-plan.json',plan)
def call(case):
 hid=case['history_id'];path=OUT/'responses'/f'{hid}.json'
 if path.exists(): return json.loads(path.read_text())
 facts=json.loads((OUT/'fact-plan.json').read_text())[hid]
 payload={'model':'gpt-6-astra','reasoning':{'effort':'max'},'max_output_tokens':8000,'store':False,'input':[{'role':'system','content':INSTRUCTIONS},{'role':'user','content':json.dumps(facts,ensure_ascii=False)}]}
 r={'history_id':hid,'request':payload,'status':'dispatched','started_at':now()};save(path,r)
 request=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+os.environ['AC2_RUN_OPENAI_KEY'],'Content-Type':'application/json'},method='POST')
 try:
  with urllib.request.urlopen(request,timeout=600) as x:r.update(status='returned',response=json.load(x))
 except urllib.error.HTTPError as e:r.update(status='http_error',http_status=e.code,error=e.read().decode(errors='replace')[:1000])
 except Exception as e:r.update(status='transport_error',error_type=type(e).__name__)
 r['finished_at']=now();save(path,r);print(hid,r['status'],flush=True);return r
def pack(cases):
 records=[json.loads((OUT/'responses'/f"{c['history_id']}.json").read_text()) for c in cases]
 sources={c['history_id']:c for c in json.loads((OUT/'source.json').read_text())['cases']};items=[];stats=[]
 for rec in records:
  data=rec.get('response',{});parts=[v.get('text','') for o in data.get('output',[]) for v in o.get('content',[]) if v.get('type')=='output_text']
  try:
   body=json.loads(''.join(parts));tests=body['tests'];assert isinstance(tests,list)
  except Exception:tests=[]
  for n,q in enumerate(tests,1):
   items.append({'item_id':f"{rec['history_id']}-{n:02d}",'history_id':rec['history_id'],'source_messages':sources[rec['history_id']]['source_messages'],'test':q,'source_grounding':'','question_executability':'','reference_answer_validity':'','review_note':''})
  stats.append({'history_id':rec['history_id'],'request_status':rec['status'],'model_status':data.get('status'),'generated_count':len(tests),'scheduled':4,'missing':max(0,4-len(tests)),'over_budget':max(0,len(tests)-4),'usage':data.get('usage')})
 random.Random(1112026).shuffle(items)
 instructions='逐题核对原始历史、题目及参考答案；每个判断填写 valid、invalid 或 uncertain，并填写原因。source_grounding 检查来源是否支持；question_executability 检查题目是否明确、可执行；reference_answer_validity 检查参考答案是否正确且无缺失。两位审核者请独立填写，保留分歧。题目和历史均为合成材料。'
 for num in (1,2): save(OUT/f'reviewer-{num}.json',{'instructions':instructions,'reviewer':f'reviewer-{num}','independent_review_confirmed':None,'items':items})
 save(OUT/'summary.json',{'requested_histories':30,'scheduled_questions':120,'returned':sum(x['request_status']=='returned' for x in stats),'generated_questions':len(items),'histories':stats,'human_review':'pending','valid_count':'pending','baseline_candidate_valid_scheduled':62,'note':'Original 62/120 was human-reviewed rule-based v36; Astra generates from the same frozen facts but is a different generator. Missing, uncertainty and disagreement remain visible.'})
 (OUT/'审核说明.txt').write_text('两位审核者分别填写对应的 reviewer JSON；仅填写空白字段。source_messages 为题目依据，test 为需要检查的题目。\n'+instructions+'\n',encoding='utf8')
 with zipfile.ZipFile(OUT/'AC2-Astra-30历史-双人审核包.zip','w',zipfile.ZIP_DEFLATED) as z:
  for f in ('审核说明.txt','reviewer-1.json','reviewer-2.json'):z.write(OUT/f,f)
 print('packaged items',len(items),'returned',sum(x['request_status']=='returned' for x in stats),flush=True)
def main():
 if not OUT.exists():initialize()
 protocol=json.loads((OUT/'protocol.json').read_text());cases=json.loads(SOURCE.read_text())['cases']
 if sha(SOURCE)!=protocol['original_source_sha256'] or sha(PLAN)!=protocol['original_fact_plan_sha256'] or sha(Path(__file__))!=protocol['runner_sha256']:raise ValueError('Frozen inputs changed')
 os.environ['AC2_RUN_OPENAI_KEY']=dotenv_values(ROOT/'.env')['OPENAI_API_KEY']
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:list(ex.map(call,cases))
 pack(cases)
if __name__=='__main__':main()
