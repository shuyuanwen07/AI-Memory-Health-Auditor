"""Prospectively freeze and run the product rule-based generator on reviewed memories.

Local only. No target model call, app database write, or AC3 output is made.
"""
import argparse
from datetime import datetime, timezone
import hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ac3_fixed_suite_adapter import compile_mock
from scripts.run_ac1_extraction import source_code_sha, read_regular, exclusive_json

def sha(b): return hashlib.sha256(b).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
RUNNER=r'''import json,sys
from datetime import datetime,timezone
from app.schemas import AuditRun,Memory,MemoryRelationship
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.test_generator.quality import RuleBasedTestQualityValidator
from app.services.formal_freeze import formal_runtime_signature
x=json.load(sys.stdin)
if formal_runtime_signature()['source_sha256']!=x['runtime_source_sha256']:raise ValueError('Runtime source changed')
if RuleBasedTestGenerator.VERSION!=x['generator_version'] or RuleBasedTestQualityValidator.VERSION!=x['validator_version']:raise ValueError('Version changed')
rows=[]
for case in x['histories']:
 hid=case['history_id']; plan=case['reviewed_reference']; memories=[]
 for fact in plan['facts']:
  rels=[MemoryRelationship(type=e['relationship_type'],target_memory_id=e['target_memory_id'],evidence_message_ids=e['evidence_message_ids']) for e in plan['relationships'] if e['memory_id']==fact['memory_id']]
  memories.append(Memory(memory_id=fact['memory_id'],conversation_id=hid,canonical_value=fact['canonical_value'],status='confirmed',source_message_ids=[fact['source_message_id']],relationships=rels))
 audit=AuditRun(run_id='AC2-'+hid,conversation_id=hid,status='CREATED',target_configuration='strong',provider='rule_based',model='rule-based-v2',temperature=0,random_seed=42,test_budget=x['test_budget'],prompt_template_version='rule-based-v4',created_at=datetime(2000,1,1,tzinfo=timezone.utc))
 try:
  tests=RuleBasedTestGenerator().generate(memories,audit)
  validator=RuleBasedTestQualityValidator(); suite_problem=validator.validate_suite(tests)
  items=[]
  for t in tests:
   a=validator.validate(t,memories)
   items.append({'test':t.model_dump(mode='json'),'quality_assessment':a.model_dump(mode='json')})
  rejected=[i['test']['test_id'] for i in items if i['quality_assessment']['quality_status']=='REJECTED']
  status='rejected_by_product_gate' if suite_problem or rejected else ('empty' if not tests else 'completed')
  rows.append({'history_id':hid,'status':status,'suite_problem':suite_problem,'rejected_test_ids':rejected,'tests':items})
 except Exception as e:
  rows.append({'history_id':hid,'status':'failed','error_type':type(e).__name__,'error':str(e),'tests':[]})
print(json.dumps(rows,ensure_ascii=False))
'''

def frozen_source(path,digest):
 raw=read_regular(path)
 if sha(raw)!=digest:raise ValueError('Frozen source hash mismatch')
 d=json.loads(raw); stage=compile_mock(Path(path),digest,0.008)
 if len(d['suite']['cases'])!=30 or not stage.get('reviewed_fact_plan'):raise ValueError('Expected the 30-history reviewed source')
 return d

def freeze(a):
 source=frozen_source(a.source,a.source_sha256)
 return {'format':'ac2-reference-generation-frozen-v1','frozen_at_utc':now(),'source_frozen_sha256':a.source_sha256,'source_path':str(Path(a.source).resolve()),
  'script_sha256':sha(Path(__file__).read_bytes()),'runtime_source_sha256':source_code_sha(),'generator_version':'rule-based-v35','validator_version':'rule-based-quality-v24',
  'generator_provider':'rule_based','test_budget_per_history':4,'history_ids':[c['history_id'] for c in source['suite']['cases']],
  'input_policy':'Human-confirmed v8 reference facts and confirmed relations directly supplied; not automatically extracted memories. H19 unresolved relation excluded.',
  'evaluation_policy':'All generated questions, including product gate rejections, are independently reviewed by two people for source grounding and structural executability; retain disagreements, uncertain and missing outputs. Report counts and denominators, and distinguish the raw generator from product gate.',
  'selection_policy':'Exactly one deterministic generation per history; retain every generated question, all failures and shortages. No target execution.', 'model_called':False,'results_observed':False}

def run(a):
 raw=read_regular(a.protocol);p=json.loads(raw)
 if sha(raw)!=a.protocol_sha256 or p.get('format')!='ac2-reference-generation-frozen-v1' or p.get('results_observed') is not False or p['script_sha256']!=sha(Path(__file__).read_bytes()) or p['runtime_source_sha256']!=source_code_sha():raise ValueError('Frozen protocol or implementation changed')
 src=frozen_source(p['source_path'],p['source_frozen_sha256'])
 cases=src['suite']['cases'];plan=src['reviewed_fact_plan']['histories']
 if p['history_ids']!=[c['history_id'] for c in cases]:raise ValueError('History set changed')
 data={'runtime_source_sha256':p['runtime_source_sha256'],'generator_version':p['generator_version'],'validator_version':p['validator_version'],'test_budget':p['test_budget_per_history'],
       'histories':[{'history_id':c['history_id'],'reviewed_reference':plan[c['history_id']]} for c in cases]}
 exclusive_json(a.started,{'format':'ac2-reference-generation-started-v1','protocol_sha256':sha(raw),'started_at_utc':now(),'model_called':False})
 proc=subprocess.run(['docker','compose','exec','-T','backend','python','-c',RUNNER],cwd=ROOT,input=json.dumps(data),text=True,capture_output=True,timeout=60)
 if proc.returncode:raise RuntimeError('Generation failed; started marker retained: '+proc.stderr[-1000:])
 rows=json.loads(proc.stdout)
 if [x['history_id'] for x in rows]!=p['history_ids']:raise ValueError('Generated history set mismatch')
 out={'format':'ac2-reference-generation-output-v1','protocol_sha256':sha(raw),'source_frozen_sha256':p['source_frozen_sha256'],'finished_at_utc':now(),'model_called':False,'histories':rows}
 exclusive_json(a.output,out)
 return src,p,out

def review(a):
 p=json.loads(read_regular(a.protocol)); data=json.loads(read_regular(a.output));src=frozen_source(p['source_path'],p['source_frozen_sha256'])
 if data['protocol_sha256']!=sha(read_regular(a.protocol)) or data['source_frozen_sha256']!=p['source_frozen_sha256']:raise ValueError('Output mismatch')
 by_id={c['history_id']:c for c in src['suite']['cases']};plan=src['reviewed_fact_plan']['histories']
 rows=[]
 for row in data['histories']:
  hid=row['history_id'];rows.append({'history_id':hid,'source_messages':by_id[hid]['source_messages'],'reviewed_reference':plan[hid],
   'generation_status':row['status'],'requested_test_count':p['test_budget_per_history'],'generated_test_count':len(row['tests']),
   'missing_test_count':max(0,p['test_budget_per_history']-len(row['tests'])),'suite_problem':row.get('suite_problem'),'error':row.get('error'),
   'generated_tests':[{'test':x['test'],'product_quality_assessment':x['quality_assessment'],'review':{'grounded':None,'structurally_executable':None,'note':''}} for x in row['tests']]})
 target=Path(a.output_dir);target.mkdir(parents=True,exist_ok=False)
 for slot in (1,2):
  exclusive_json(target/f'reviewer-{slot}.json',{'format':'ac2-reference-generation-human-review-v1','reviewer_slot':slot,'protocol_sha256':sha(read_regular(a.protocol)),'output_sha256':sha(read_regular(a.output)),
   'instructions':['独立逐题审核；grounded 与 structurally_executable 填 valid、invalid 或 uncertain。','对 invalid 或 uncertain 写明理由；不修改题目、来源或系统质量门禁结果。','系统自动判定供参考，不代表人工判断；此结果来自人工确认记忆输入，不是自动提取。'],
   'reviewer_declaration':{'reviewer_label':None,'completed_by_human':None,'completed_independently':None,'used_ai_assistance':None,'note':''},'histories':rows})
 print(json.dumps({'histories':len(rows),'questions':sum(len(x['generated_tests']) for x in rows),'reviewers':2,'human_decisions_created':False}))

def main():
 p=argparse.ArgumentParser();sp=p.add_subparsers(dest='cmd',required=True)
 f=sp.add_parser('freeze');f.add_argument('--source',required=True);f.add_argument('--source-sha256',required=True);f.add_argument('--output',required=True)
 r=sp.add_parser('run');r.add_argument('--protocol',required=True);r.add_argument('--protocol-sha256',required=True);r.add_argument('--started',required=True);r.add_argument('--output',required=True)
 v=sp.add_parser('review');v.add_argument('--protocol',required=True);v.add_argument('--output',required=True);v.add_argument('--output-dir',required=True)
 a=p.parse_args()
 if a.cmd=='freeze':
  data=freeze(a);exclusive_json(a.output,data);print(json.dumps({'output':a.output,'sha256':sha(read_regular(a.output))}))
 elif a.cmd=='run':
  _,_,out=run(a);print(json.dumps({'output':a.output,'sha256':sha(read_regular(a.output)),'statuses':{s:sum(h['status']==s for h in out['histories']) for s in set(h['status'] for h in out['histories'])}}))
 else:review(a)
if __name__=='__main__':main()
