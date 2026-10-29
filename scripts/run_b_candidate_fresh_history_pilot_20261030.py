"""Fresh synthetic paired engineering pilot; isolated SQLite, no production changes."""
import argparse,hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base
from app.memory_agent.store import SqlTargetMemoryStore
from app.models import AuditRunModel,ConversationModel
from app.schemas import AuditRun,Conversation,ConversationMessage,Memory,MemoryRelationship,MemoryStatus,MemoryStrategy,RelationshipType,TestCase
from app.target_ai.providers import HttpTargetAIConnector
from scripts.b_update_history_candidate_v2_20261029 import include_update_history
ROOT=Path(__file__).resolve().parents[1];SCRIPT=Path(__file__).resolve();OUT=Path(os.environ.get('B_FRESH_PILOT_OUTPUT','/ac3-results/b-candidate-fresh-history-pilot-20261030-v1'))
CASES=[{'id':'FH1','old':'The Atlas project database used SQLite.','new':'The Atlas project database now uses MariaDB.','history_question':'How did the Atlas project database change from its previous value?','current_question':'Which database does the Atlas project use now?','old_value':'SQLite','new_value':'MariaDB'},
{'id':'FH2','old':'The Lumen project database used PostgreSQL.','new':'The Lumen project database now uses MySQL.','history_question':'What changed from the previous database for the Lumen project?','current_question':'Which database does the Lumen project use now?','old_value':'PostgreSQL','new_value':'MySQL'},
{'id':'FH3','old':'The Cedar project database used MongoDB.','new':'The Cedar project database now uses PostgreSQL.','history_question':'Explain how the Cedar project database changed from the earlier setup.','current_question':'Which database does the Cedar project use now?','old_value':'MongoDB','new_value':'PostgreSQL'},
{'id':'FH4','old':'The Vale project database used MariaDB.','new':'The Vale project database now uses SQLite.','history_question':'Compare the previous and current database used by the Vale project.','current_question':'Which database does the Vale project use now?','old_value':'MariaDB','new_value':'SQLite'}]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def write(p,j):p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n')
def sources():return {str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))}
def freeze():
 OUT.mkdir(parents=True,exist_ok=False);write(OUT/'protocol.json',{'created_at_utc':now(),'runner_sha256':sha(SCRIPT),'candidate_sha256':sha(ROOT/'scripts/b_update_history_candidate_v2_20261029.py'),'application_sha256':sources(),'cases':CASES,'target':'openai/gpt-6-luna','arms':['baseline','candidate'],'types':['history','current'],'planned_calls':16,'operator':'Simulated annotated synthetic reference, not human-reviewed gold.','limits':'Four authored similar synthetic database histories; development pilot, not independent random sampling. Real store uses injected candidate only in isolated process. No changes to running system; two trials per source are correlated. Predeclared call order; no retry by runner, connector may retry.'});print('Frozen four synthetic cases and paired conditions, no target calls.')
def check(p):
 assert sha(SCRIPT)==p['runner_sha256'] and sha(ROOT/'scripts/b_update_history_candidate_v2_20261029.py')==p['candidate_sha256'] and sources()==p['application_sha256']
def run():
 p=json.loads((OUT/'protocol.json').read_text());check(p);path=OUT/'ledger.json'
 if path.exists():raise ValueError('Existing ledger: do not re-dispatch')
 rows=[{'case_id':c['id'],'type':kind,'arm':arm,'state':'not_started'} for c in p['cases'] for kind in p['types'] for arm in p['arms']]
 ledger={'protocol_sha256':sha(OUT/'protocol.json'),'started_at_utc':now(),'rows':rows};write(path,ledger)
 engine=create_engine('sqlite://');Base.metadata.create_all(engine);db=sessionmaker(bind=engine,autoflush=False)();clock=datetime(2026,1,1,tzinfo=timezone.utc);connector=HttpTargetAIConnector();original_hook=SqlTargetMemoryStore._include_update_history_for_question_context
 def hook(candidates,relations,question,strategy):original_hook(candidates,relations,question,strategy);include_update_history(candidates,relations,question,strategy)
 for idx,row in enumerate(rows):
  check(p);case=next(c for c in p['cases'] if c['id']==row['case_id']);cid='C'+str(idx);rid='R'+str(idx)
  db.add(ConversationModel(id=cid,authorised=True));db.add(AuditRunModel(id=rid,conversation_id=cid,status='CREATED',target_configuration='strong',provider='openrouter',model=p['target'],temperature=0,random_seed=42,test_budget=1,prompt_template_version='isolated-pilot'));db.commit()
  conv=Conversation(conversation_id=cid,authorised=True,created_at=clock,messages=[ConversationMessage(message_id='M1',role='user',content=case['old'],timestamp=clock),ConversationMessage(message_id='M2',role='user',content=case['new'],timestamp=clock)])
  class Extractor:
   def extract(self,conversation):return [Memory(memory_id='old',conversation_id=cid,canonical_value=case['old'],status=MemoryStatus.CANDIDATE,source_message_ids=['M1'],timestamp=clock),Memory(memory_id='new',conversation_id=cid,canonical_value=case['new'],status=MemoryStatus.CANDIDATE,source_message_ids=['M2'],timestamp=clock,relationships=[MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id='old')])]
  test=TestCase(test_id='T'+str(idx),run_id=rid,dimension='freshness',prompt=case[row['type']+'_question'],expected_behavior='',supporting_memory_ids=[],generator_version='isolated-pilot')
  store=SqlTargetMemoryStore(db,extractor=Extractor())
  if row['arm']=='candidate':
   with patch.object(SqlTargetMemoryStore,'_include_update_history_for_question_context',staticmethod(hook)):retrieval=store.retrieve(rid,conv,test,MemoryStrategy.STRONG_RULE_BASED)
  else:retrieval=store.retrieve(rid,conv,test,MemoryStrategy.STRONG_RULE_BASED)
  row['retrieved_context']=retrieval.context;row['retrieval_evidence']=retrieval.evidence.model_dump(mode='json');row['state']='dispatched';row['started_at_utc']=now();write(path,ledger)
  audit=AuditRun(run_id=rid,conversation_id=cid,status='TESTS_GENERATED',target_configuration='strong',provider='openrouter',model=p['target'],temperature=0,random_seed=42,test_budget=1,prompt_template_version='isolated-pilot',created_at=clock)
  try:row['response']=connector.execute(test.model_copy(update={'target_memory_context':retrieval.context}),audit).model_dump(mode='json');row['state']='returned'
  except Exception as exc:row.update(state='failed',error_type=type(exc).__name__,failure_receipt=getattr(exc,'target_execution',None))
  row['finished_at_utc']=now();write(path,ledger);print(row['case_id'],row['type'],row['arm'],row['state'],flush=True)
 db.close();engine.dispose();ledger['finished_at_utc']=now();write(path,ledger)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['freeze','run']);globals()[parser.parse_args().stage]()
