"""One synthetic target-and-judge interface smoke; not an accuracy experiment."""
import json, os
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values
from app.schemas import AuditRun, AuditStatus, Dimension, Memory, MemoryStatus, TargetConfiguration, TargetProvider, TestCase
from app.target_ai.providers import HttpTargetAIConnector
from app.evaluator.llm_judge import LLMBehaviourEvaluator

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/astra-target-judge-smoke-20261101.json'
if OUT.exists(): raise SystemExit('Existing smoke preserved; no repeated calls.')
os.environ['OPENAI_API_KEY']=dotenv_values(ROOT/'.env')['OPENAI_API_KEY']
now=datetime.now(timezone.utc)
test=TestCase(test_id='T001',run_id='ASTRA-SMOKE',dimension=Dimension.FRESHNESS,
 prompt='Which database should the user use now?',expected_behavior='Use PostgreSQL; MySQL is superseded.',
 supporting_memory_ids=['M001','M002'],generator_version='manual-synthetic',
 target_memory_context=['The user previously used MySQL.','The user now uses PostgreSQL instead of MySQL.'])
memories=[Memory(memory_id='M001',conversation_id='C1',canonical_value='The user previously used MySQL.',status=MemoryStatus.CONFIRMED),
 Memory(memory_id='M002',conversation_id='C1',canonical_value='The user now uses PostgreSQL instead of MySQL.',status=MemoryStatus.CONFIRMED)]
audit=AuditRun(run_id='ASTRA-SMOKE',conversation_id='C1',status=AuditStatus.CREATED,target_configuration=TargetConfiguration.STRONG,
 provider=TargetProvider.OPENAI,model='gpt-6-astra',temperature=0,random_seed=42,test_budget=1,prompt_template_version='synthetic-smoke',created_at=now)
data={'scope':'Synthetic functional smoke, no human validity claims or database changes.', 'requested_provider':'openai','model':'gpt-6-astra','reasoning_effort':'max','started_at':now.isoformat(),'status':'dispatched'}
OUT.write_text(json.dumps(data,indent=2)+'\n')
try:
 response=HttpTargetAIConnector().execute(test,audit);data['target']=response.model_dump(mode='json');data['status']='target_completed';OUT.write_text(json.dumps(data,indent=2)+'\n')
 result=LLMBehaviourEvaluator('openai',model='gpt-6-astra').evaluate(test,response,memories)
 data['evaluation']=result.model_dump(mode='json');data['status']='completed' if not result.evaluator.startswith('fallback-') else 'judge_fallback'
except Exception as exc:data.update(status='failed',error_type=type(exc).__name__,error=str(exc)[:400])
data['finished_at']=datetime.now(timezone.utc).isoformat();OUT.write_text(json.dumps(data,indent=2)+'\n')
print('status:',data['status'],'target:',data.get('target',{}).get('execution_metadata',{}).get('reported_model'), 'judge:',data.get('evaluation',{}).get('evaluator'),flush=True)
