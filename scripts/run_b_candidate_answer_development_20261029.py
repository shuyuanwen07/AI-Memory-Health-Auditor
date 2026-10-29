"""Frozen development retest of reconstructed B contexts, not a live retrieval study."""
import argparse,hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path
from app.schemas import AuditRun,TestCase
from app.target_ai.providers import HttpTargetAIConnector

ROOT=Path(__file__).resolve().parents[1]
TRACE=ROOT/'output/proposal-delivery/b-freshness-all-traces-20261029-v1/candidate-profile-context.json'
B=ROOT/'output/proposal-delivery/experiment-b-four-strategy-20261029-v1/protocol.json'
OUT=Path(os.environ.get('B_RETEST_OUTPUT','/ac3-results/b-candidate-answer-development-20261029-v1'))
SCRIPT=Path(__file__).resolve()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def now():return datetime.now(timezone.utc).isoformat()
def freeze():
 OUT.mkdir(parents=True,exist_ok=False);t=json.loads(TRACE.read_text());b=json.loads(B.read_text())
 assert t['cases']==9 and t['both_endpoints_selected']==9
 settings=b['target'];assert settings['provider']=='openrouter' and settings['model']=='openai/gpt-6-luna'
 protocol={'frozen_at_utc':now(),'context_sha256':sha(TRACE),'b_protocol_sha256':sha(B),'runner_sha256':sha(SCRIPT),
  'target':settings,'rows':t['rows'],'execution':'Each fixed question and reconstructed context is sent once via the application target connector, in saved order. Connector internal retry behavior is recorded. Expected answer is never sent.',
  'limits':'Post-outcome same questions, reconstructed context, no live retrieval, no concurrent baseline; repeated related histories. AI/human labels pending. Not independent effectiveness.'}
 write(OUT/'protocol.json',protocol);print('Frozen nine reconstructed contexts; no calls made.')
def run():
 p=json.loads((OUT/'protocol.json').read_text());assert sha(TRACE)==p['context_sha256'] and sha(B)==p['b_protocol_sha256'] and sha(SCRIPT)==p['runner_sha256']
 ledger_path=OUT/'ledger.json'
 if ledger_path.exists():raise ValueError('existing ledger: do not repeat calls')
 ledger={'protocol_sha256':sha(OUT/'protocol.json'),'started_at_utc':now(),'rows':[{'history':r['history'],'repeat':r['repeat'],'state':'not_started'} for r in p['rows']]}
 write(ledger_path,ledger);connector=HttpTargetAIConnector()
 for idx,(row,item) in enumerate(zip(p['rows'],ledger['rows'])):
  assert sha(TRACE)==p['context_sha256'] and sha(B)==p['b_protocol_sha256'] and sha(SCRIPT)==p['runner_sha256']
  item.update(state='dispatched',started_at_utc=now());write(ledger_path,ledger)
  audit=AuditRun(run_id=f'REPLAY{idx:03}',conversation_id='synthetic',status='TESTS_GENERATED',target_configuration='strong',provider='openrouter',model=p['target']['model'],temperature=p['target']['temperature'],random_seed=p['target']['random_seed'],test_budget=1,prompt_template_version='development-replay-v1',target_memory_profile=p['target']['profile'],created_at=datetime.now(timezone.utc))
  test=TestCase(test_id=f'T{idx:03}',run_id=audit.run_id,dimension='freshness',prompt=row['question'],expected_behavior='',supporting_memory_ids=[],generator_version='development-replay-v1',target_memory_context=row['selected_context'])
  try:
   response=connector.execute(test,audit);item.update(state='returned',response=response.model_dump(mode='json'))
  except Exception as exc:
   item.update(state='failed',error_type=type(exc).__name__,failure_receipt=getattr(exc,'target_execution',None))
  item['finished_at_utc']=now();write(ledger_path,ledger);print(item['history'],item['repeat'],item['state'],flush=True)
 ledger['finished_at_utc']=now();write(ledger_path,ledger)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['freeze','run']);globals()[parser.parse_args().stage]()
