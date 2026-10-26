"""Database-free Luna target/judge smoke on approved synthetic Maple facts."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from smoke_qwen_generation import ROOT, approved_memories
from app.schemas import AuditRun, TestCase
from app.target_ai.providers import HttpTargetAIConnector
from app.evaluator.llm_judge import LLMBehaviourEvaluator
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--generation-report',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--reuse-responses',type=Path)
args=parser.parse_args()
memories, source_hash = approved_memories(ROOT / 'datasets/smoke/qwen-four-dimension-source-v1.json', ROOT / 'datasets/smoke/qwen-four-dimension-approval-v1.json')
source=json.loads(args.generation_report.read_text())
if source.get('source_sha256') != source_hash or source.get('scope') != 'synthetic_generation_and_review_smoke_only' or source.get('status') != 'completed' or source.get('model') != 'openai/gpt-6-luna':
 raise ValueError('Requires the completed Luna report bound to the approved synthetic source.')
audit=AuditRun(run_id='SYN-QWEN-GENERATION',conversation_id='SYN-QWEN-MAPLE',status='CREATED',target_configuration='strong',provider='openrouter',model='openai/gpt-6-luna',temperature=0,random_seed=42,test_budget=4,prompt_template_version='synthetic-luna-target-smoke-v1',created_at=datetime.now(timezone.utc))
previous = json.loads(args.reuse_responses.read_text()) if args.reuse_responses else None
if previous is not None and (previous.get('source_sha256') != source_hash or previous.get('model') != 'openai/gpt-6-luna' or previous.get('research_evidence') is not False or previous.get('scope') != 'synthetic_full_context_target_and_judge_smoke_only'):
 raise ValueError('Only the approved synthetic Luna target receipts can be reassessed.')
previous_cases = {row['test']['test_id']: row for row in previous['cases']} if previous else {}
if previous and (len(previous_cases) != len(previous['cases']) or set(previous_cases) != {row['test_id'] for row in source['tests']}):
 raise ValueError('The response receipt must cover the exact generated suite once.')
report={'scope':'synthetic_full_context_target_and_judge_smoke_only','research_evidence':False,'source_sha256':source_hash,'provider':'openrouter','model':'openai/gpt-6-luna','audit_database_writes':0,'reused_target_responses':previous is not None,'cases':[],'status':'running'}
try:
 for raw in source['tests']:
  test=TestCase.model_validate(raw).model_copy(update={'target_memory_context':[m.canonical_value for m in memories]})
  if previous is not None:
   from app.schemas import TargetResponse
   saved = previous_cases[test.test_id]
   if saved['test'] != test.model_dump(mode='json'):
    raise ValueError('Cannot reassess altered tests or memory context.')
   response=TargetResponse.model_validate(saved['response'])
   if response.test_id != test.test_id or response.run_id != test.run_id or response.model != 'openai/gpt-6-luna':
    raise ValueError('The target response identity does not match the frozen synthetic case.')
  else:
   response=HttpTargetAIConnector().execute(test,audit)
  evaluation=LLMBehaviourEvaluator('openrouter',model='openai/gpt-6-luna').evaluate(test,response,memories)
  report['cases'].append({'test':test.model_dump(mode='json'),'response':response.model_dump(mode='json'),'evaluation':evaluation.model_dump(mode='json')})
  print(json.dumps({'test_id':test.test_id,'answered':True}),flush=True)
 report['status']='completed'
except Exception as exc:
 report.update(status='failed',error_code=type(exc).__name__)
finally:
 args.output.parent.mkdir(parents=True,exist_ok=True)
 args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'status':report['status'],'case_count':len(report['cases'])}),flush=True)
