"""Verify provider-reported judge identity on an approved synthetic saved answer."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.schemas import Memory,TestCase,TargetResponse
from app.evaluator.llm_judge import LLMBehaviourEvaluator
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--all-answers',action='store_true')
parser.add_argument('--test-id',help='Reassess only this exact saved synthetic question')
args=parser.parse_args()
source_path=ROOT/'datasets/smoke/qwen-four-dimension-source-v1.json'
source=json.loads(source_path.read_text())
report=json.loads(args.input.read_text())
assert report.get('source_sha256')==hashlib.sha256(source_path.read_bytes()).hexdigest()
assert report.get('scope')=='synthetic_isolated_api_e2e_engineering_only' and report.get('research_evidence') is False
facts={m['message_id']:m['content'] for m in source['messages']}
inventory=report['confirmation']['inventory']
assert len(inventory)==len(facts) and {m['source_message_ids'][0] for m in inventory}==set(facts)
assert all(len(m['source_message_ids'])==1 and m['canonical_value']==facts[m['source_message_ids'][0]] for m in inventory)
repetitions=report.get('planned_repetitions_per_strategy',1)
assert type(repetitions) is int and 1 <= repetitions <= 3
assert len(report['runs'])==2*repetitions
assert not (args.all_answers and args.test_id)
if args.test_id:
 assert sum(t['test_id']==args.test_id for r in report['runs'] for t in r['tests'])==1
memories=[Memory.model_validate(m) for m in inventory]
evaluations=[]
for run in report['runs'] if args.all_answers or args.test_id else report['runs'][:1]:
 assert len(run['tests'])==len(run['responses'])==4
 assert len({t['test_id'] for t in run['tests']})==4
 assert len({r['test_id'] for r in run['responses']})==4
 assert {r['test_id'] for r in run['responses']}=={t['test_id'] for t in run['tests']}
 selected=([t for t in run['tests'] if t['test_id']==args.test_id] if args.test_id else
           run['tests'] if args.all_answers else [next(t for t in run['tests'] if t['dimension']=='accuracy')])
 for case in selected:
  response=next(r for r in run['responses'] if r['test_id']==case['test_id'])
  result=LLMBehaviourEvaluator('openrouter',model='openai/gpt-6-luna').evaluate(TestCase.model_validate(case),TargetResponse.model_validate(response),memories)
  evaluations.append({'run_id':run['run_id'],'strategy':run['strategy'],'dimension':case['dimension'],'result':result.model_dump(mode='json')})
  print(json.dumps({'test_id':case['test_id'],'passed':result.passed,'reported_model':result.judge_execution.reported_model}),flush=True)
output={'scope':'synthetic_saved_answer_reassessment' if args.all_answers or args.test_id else 'synthetic_saved_answer_judge_identity_probe','research_evidence':False,'source_sha256':report['source_sha256'],'source_report_sha256':hashlib.sha256(args.input.read_bytes()).hexdigest(),'production_database_writes':0,'target_requests':0,'evaluations':evaluations,'result':evaluations[0]['result']}
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'evaluation_count':len(evaluations),'all_models_reported':all(e['result']['judge_execution']['reported_model']=='openai/gpt-6-luna' for e in evaluations)}),flush=True)
