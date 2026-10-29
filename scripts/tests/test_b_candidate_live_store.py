"""Exercise an isolated candidate against the real SQLite target memory store."""
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base
from app.memory_agent.store import SqlTargetMemoryStore
from app.models import AuditRunModel,ConversationModel
from app.schemas import Conversation,ConversationMessage,Memory,MemoryRelationship,MemoryStatus,MemoryStrategy,RelationshipType,TestCase as AuditTestCase
from app.schemas.target_profile import TargetMemoryProfile
from scripts.b_update_history_candidate_v2_20261029 import include_update_history
from scripts.b_update_history_budget_guard_20261030 import guard_selected_updates

class LiveStoreTest(unittest.TestCase):
 def test_record_budget_guard_reports_incomplete_history_in_live_store(self):
  engine=create_engine('sqlite://');Base.metadata.create_all(engine);db=sessionmaker(bind=engine,autoflush=False)();now=datetime(2026,1,1,tzinfo=timezone.utc)
  db.add(ConversationModel(id='C',authorised=True));db.add(AuditRunModel(id='R',conversation_id='C',status='CREATED',target_configuration='strong',provider='rule_based',model='fixture',temperature=0,random_seed=42,test_budget=1,prompt_template_version='fixture'));db.commit()
  conversation=Conversation(conversation_id='C',authorised=True,created_at=now,messages=[ConversationMessage(message_id='M1',role='user',content='The backend used MySQL.',timestamp=now),ConversationMessage(message_id='M2',role='user',content='The backend now uses PostgreSQL.',timestamp=now)])
  class Extractor:
   def extract(self,conversation):
    return [Memory(memory_id='old',conversation_id='C',canonical_value='The backend used MySQL.',status=MemoryStatus.CANDIDATE,source_message_ids=['M1'],timestamp=now),Memory(memory_id='new',conversation_id='C',canonical_value='The backend now uses PostgreSQL.',status=MemoryStatus.CANDIDATE,source_message_ids=['M2'],timestamp=now,relationships=[MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id='old')])]
  store=SqlTargetMemoryStore(db,extractor=Extractor(),profile=TargetMemoryProfile(max_retrieved_records=1));test=AuditTestCase(test_id='T1',run_id='R',dimension='freshness',prompt='How did the backend database change from the previous value?',expected_behavior='private reference',supporting_memory_ids=[],generator_version='fixture')
  original_hook=SqlTargetMemoryStore._include_update_history_for_question_context;original_profile=SqlTargetMemoryStore._apply_profile;notices=[]
  def hook(candidates,relations,question,strategy):
   original_hook(candidates,relations,question,strategy);include_update_history(candidates,relations,question,strategy)
  def guarded_profile(instance,candidates,test,strategy):
   selected=original_profile(instance,candidates,test,strategy);relations=instance._relationships(test.run_id)
   flagged={x['record'].id for x in candidates if 'candidate_update_history_for_explicit_question' in x['reason']}
   pairs=[(r.memory_id,r.target_memory_id) for r in relations if r.relationship_type=='UPDATE' and r.target_memory_id in flagged]
   kept,notice=guard_selected_updates(selected,relations,pairs);notices.append(notice);return kept
  with patch.object(SqlTargetMemoryStore,'_include_update_history_for_question_context',staticmethod(hook)),patch.object(SqlTargetMemoryStore,'_apply_profile',guarded_profile):
   result=store.retrieve('R',conversation,test,MemoryStrategy.STRONG_RULE_BASED)
  self.assertEqual(len(notices),1);self.assertTrue(notices[0]['incomplete_update_history']);self.assertLessEqual(len(result.context),1)
  self.assertFalse(any('MySQL' in x for x in result.context))
  db.close();engine.dispose()

 def test_candidate_uses_actual_ingestion_retrieval_and_preserves_current_only(self):
  engine=create_engine('sqlite://');Base.metadata.create_all(engine);db=sessionmaker(bind=engine,autoflush=False)();now=datetime(2026,1,1,tzinfo=timezone.utc)
  db.add(ConversationModel(id='C',authorised=True));db.add(AuditRunModel(id='R',conversation_id='C',status='CREATED',target_configuration='strong',provider='rule_based',model='fixture',temperature=0,random_seed=42,test_budget=1,prompt_template_version='fixture'));db.commit()
  conversation=Conversation(conversation_id='C',authorised=True,created_at=now,messages=[ConversationMessage(message_id='M1',role='user',content='The backend used MySQL.',timestamp=now),ConversationMessage(message_id='M2',role='user',content='The backend now uses PostgreSQL.',timestamp=now)])
  class Extractor:
   def extract(self,conversation):
    return [Memory(memory_id='old',conversation_id='C',canonical_value='The backend used MySQL.',status=MemoryStatus.CANDIDATE,source_message_ids=['M1'],timestamp=now),Memory(memory_id='new',conversation_id='C',canonical_value='The backend now uses PostgreSQL.',status=MemoryStatus.CANDIDATE,source_message_ids=['M2'],timestamp=now,relationships=[MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id='old')])]
  store=SqlTargetMemoryStore(db,extractor=Extractor());test=AuditTestCase(test_id='T1',run_id='R',dimension='freshness',prompt='How did the backend database change from the previous value?',expected_behavior='private reference',supporting_memory_ids=[],generator_version='fixture')
  original=store.retrieve('R',conversation,test,MemoryStrategy.STRONG_RULE_BASED)
  self.assertTrue(any('PostgreSQL' in x for x in original.context));self.assertFalse(any('MySQL' in x for x in original.context))
  original_hook=SqlTargetMemoryStore._include_update_history_for_question_context
  def isolated_hook(candidates,relations,question,strategy):
   original_hook(candidates,relations,question,strategy);include_update_history(candidates,relations,question,strategy)
  with patch.object(SqlTargetMemoryStore,'_include_update_history_for_question_context',staticmethod(isolated_hook)):
   candidate=store.retrieve('R',conversation,test.model_copy(update={'test_id':'T2'}),MemoryStrategy.STRONG_RULE_BASED)
   self.assertTrue(any('MySQL' in x for x in candidate.context));self.assertTrue(any('PostgreSQL' in x for x in candidate.context))
   current=store.retrieve('R',conversation,test.model_copy(update={'test_id':'T3','prompt':'What database is used now?'}),MemoryStrategy.STRONG_RULE_BASED)
   self.assertFalse(any('MySQL' in x for x in current.context))
  db.close();engine.dispose()
if __name__=='__main__':unittest.main()
