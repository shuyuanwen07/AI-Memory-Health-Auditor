"""Paired source-only engineering contracts; no provider calls or human labels."""
import argparse,hashlib,json,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--backend-root',type=Path,default=Path('backend'));p.add_argument('--split',choices=['development','validation'],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();sys.path.insert(0,str(a.backend_root.resolve()))
from app.schemas import Conversation,ConversationMessage,Memory,MemoryStatus,TestCase,TargetResponse,TargetMemoryProfile,MemoryStrategy
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.memory_agent.store import SqlTargetMemoryStore
from app.database.session import Base
from app.models import AuditRunModel,ConversationModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
ROOT=Path(__file__).resolve().parents[1];data=ROOT/'datasets/phase3-engineering-v1';freeze=json.loads((data/'freeze.json').read_text());assert all(hashlib.sha256((data/k).read_bytes()).hexdigest()==v for k,v in freeze['files'].items())
now=datetime(2026,10,27,tzinfo=timezone.utc);evaluation=[];retrieval=[]
for c in json.loads((data/'evaluations.json').read_text()):
 if c['split']!=a.split:continue
 case=TestCase(test_id=c['id'],run_id='R',dimension='accuracy',prompt=c['prompt'],expected_behavior='State the recorded fact: '+c['source'],supporting_memory_ids=['M'],generator_version='frozen-engineering-v1')
 response=TargetResponse(response_id='A'+c['id'],test_id=case.test_id,run_id='R',response_text=c['answer'],model='frozen-synthetic-contract',temperature=0,created_at=now)
 result=RuleBasedBehaviourEvaluator().evaluate(case,response,[Memory(memory_id='M',conversation_id='C',canonical_value=c['source'],status=MemoryStatus.CONFIRMED)])
 evaluation.append({'id':c['id'],'expected_passed':c['expected_passed'],'actual':result.model_dump(mode='json'),'contract_passed':result.passed is c['expected_passed']})
for c in json.loads((data/'retrieval.json').read_text()):
 if c['split']!=a.split:continue
 engine=create_engine('sqlite://');Base.metadata.create_all(engine)
 with Session(engine) as db:
  db.add(ConversationModel(id='C',authorised=True));db.add(AuditRunModel(id='R',conversation_id='C',status='CREATED',target_configuration='strong',provider='rule_based',model='rule-based-target-ai',temperature=0,random_seed=42,test_budget=1,prompt_template_version='frozen-engineering-v1',pipeline_provider='rule_based',pipeline_model='rule-based-v2',evaluator_provider='rule_based',evaluator_model='rule-based'));db.commit()
  conversation=Conversation(conversation_id='C',authorised=True,created_at=now,messages=[ConversationMessage(message_id=f'S{i}',role='user',timestamp=now+timedelta(minutes=i),content=text) for i,text in enumerate(c['messages'])])
  case=TestCase(test_id=c['id'],run_id='R',dimension='conflict_resolution',prompt=c['prompt'],expected_behavior='AUDITOR_SENTINEL_MUST_NOT_REACH_RETRIEVAL',supporting_memory_ids=[],generator_version='frozen-engineering-v1')
  store=SqlTargetMemoryStore(db,profile=TargetMemoryProfile(max_retrieved_records=c['record_budget'],context_character_budget=800))
  for policy in [MemoryStrategy.WEAK_FIRST_HIT,MemoryStrategy.STRONG_RULE_BASED]:
   result=store.retrieve('R',conversation,case,policy);text=' '.join(result.context).lower();options=[value for value in c['required_options'] if value in text]
   passed=(len(options)==2 if c['expected_delivery']=='both' else len(options) in [0,2])
   retrieval.append({'id':c['id'],'policy':policy.value,'context':result.context,'options_delivered':options,'contract_passed':passed if policy==MemoryStrategy.STRONG_RULE_BASED else None,'retrieval':result.evidence.model_dump(mode='json')})
 engine.dispose()
out={'split':a.split,'label_source':'frozen synthetic engineering specification; not independent human gold','evaluator_version':RuleBasedBehaviourEvaluator.VERSION,'evaluations':evaluation,'retrieval':retrieval,'summary':{'evaluation_contracts_passed':sum(x['contract_passed'] for x in evaluation),'evaluation_contracts_total':len(evaluation),'strong_retrieval_contracts_passed':sum(x['contract_passed'] is True for x in retrieval),'strong_retrieval_contracts_total':sum(x['policy']=='strong_rule_based' for x in retrieval)}}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2));print(json.dumps(out['summary']))
