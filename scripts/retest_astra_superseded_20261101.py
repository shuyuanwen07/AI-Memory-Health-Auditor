"""Reassess the exact saved synthetic target answer after the rule fix."""
import hashlib, json, os
from pathlib import Path
from dotenv import dotenv_values
from app.schemas import Dimension, Memory, MemoryStatus, TargetResponse, TestCase
from app.evaluator.llm_judge import LLMBehaviourEvaluator

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'output/proposal-delivery/astra-target-judge-smoke-20261101.json'
OUT=ROOT/'output/proposal-delivery/astra-superseded-retest-v66b-20261101.json'
if OUT.exists(): raise SystemExit('Existing retest preserved; no repeat.')
prior=json.loads(OLD.read_text());os.environ['OPENAI_API_KEY']=dotenv_values(ROOT/'.env')['OPENAI_API_KEY']
test=TestCase(test_id='T001',run_id='ASTRA-SMOKE',dimension=Dimension.FRESHNESS,
 prompt='Which database should the user use now?',expected_behavior='Use PostgreSQL; MySQL is superseded.',
 supporting_memory_ids=['M001','M002'],generator_version='manual-synthetic',
 target_memory_context=['The user previously used MySQL.','The user now uses PostgreSQL instead of MySQL.'])
memories=[Memory(memory_id='M001',conversation_id='C1',canonical_value='The user previously used MySQL.',status=MemoryStatus.CONFIRMED),
 Memory(memory_id='M002',conversation_id='C1',canonical_value='The user now uses PostgreSQL instead of MySQL.',status=MemoryStatus.CONFIRMED)]
response=TargetResponse.model_validate(prior['target'])
record={'status':'dispatched','prior_sha256':hashlib.sha256(OLD.read_bytes()).hexdigest(),
 'rule_sha256':hashlib.sha256((ROOT/'backend/app/evaluator/rule_based.py').read_bytes()).hexdigest(),
 'design':'Same saved target answer and reference; rule implementation changed, Astra judge sampled again; one synthetic case, not held out.'}
OUT.write_text(json.dumps(record,indent=2)+'\n')
try:
 result=LLMBehaviourEvaluator('openai',model='gpt-6-astra').evaluate(test,response,memories)
 record.update(status='completed',before=prior['evaluation'],after=result.model_dump(mode='json'))
except Exception as exc:record.update(status='failed',error_type=type(exc).__name__)
OUT.write_text(json.dumps(record,indent=2)+'\n')
after=record.get('after',{});print('status',record['status'],'before',prior['evaluation']['passed'],'after',after.get('passed'),'judge',after.get('evaluator'),flush=True)
