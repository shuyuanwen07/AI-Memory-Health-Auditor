"""Read-only exploratory retrieval probe in isolated SQLite; never sends gold to a target."""
import json
from datetime import datetime,timezone,timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base
from app.models import AuditRunModel,ConversationModel
from app.memory_agent.store import SqlTargetMemoryStore
from app.schemas import Conversation,ConversationMessage,MemoryStrategy,TestCase,TargetMemoryProfile

path='/output/experiment-a-expanded-20261030/'
source=json.load(open(path+'four-scenario-frozen-input.json'))
questions=json.load(open(path+'four-scenario-v7-question-ledger.json'))
draft=json.load(open(path+'v7-offline-question-draft.json'))
actual={h['history_id']:h for h in draft['histories']}
engine=create_engine('sqlite://');Base.metadata.create_all(engine);db=sessionmaker(bind=engine)()
results=[]
for history in source['histories']:
 hid=history['history_id']; cid='C-'+hid; rid='R-'+hid;now=datetime.now(timezone.utc)
 db.add(ConversationModel(id=cid,authorised=True)); db.add(AuditRunModel(id=rid,conversation_id=cid,status='CREATED',target_configuration='weak',provider='rule_based',model='fixture',temperature=0,random_seed=42,test_budget=4,prompt_template_version='rule-based-v4',pipeline_provider='rule_based',pipeline_model='rule-based-v2',evaluator_provider='rule_based',evaluator_model='rule-based-v65',memory_strategy='weak_first_hit'));db.commit()
 msgs=[ConversationMessage(message_id=m['message_id'],role=m['role'],content=m['content'],timestamp=now+timedelta(microseconds=i)) for i,m in enumerate(history['messages'])]
 conv=Conversation(conversation_id=cid,authorised=True,source_origin='synthetic',created_at=now,messages=msgs)
 store=SqlTargetMemoryStore(db,profile=TargetMemoryProfile(max_retrieved_records=50,context_character_budget=16000))
 refs={m['memory_id']:set(m['source_message_ids']) for m in actual[hid]['confirmed_memories']}
 for suite in questions['histories'][hid]['suites']:
  for raw in suite['tests']:
   q=TestCase.model_validate({**raw,'run_id':rid}); needed=set().union(*(refs[i] for i in q.supporting_memory_ids)); a=store.retrieve(rid,conv,q,MemoryStrategy.WEAK_FIRST_HIT);b=store.retrieve(rid,conv,q,MemoryStrategy.RELATIONSHIP_PACKET)
   packet=json.loads(b.context[0])['memory_packet'] if b.context else []; found={s for row in packet for s in row['source_message_ids']}
   results.append({'history':hid,'method':suite['method'],'dimension':q.dimension.value,'required_source_ids':sorted(needed),'candidate_source_ids':sorted(found),'full_source_coverage':needed.issubset(found),'baseline_records':len(a.evidence.selected_memory_ids),'packet_records':len(b.evidence.selected_memory_ids),'packet_chars':len(b.context[0]) if b.context else 0})
 print(hid,'private records',len(store._records(rid)),flush=True)
from collections import Counter
for dim in ('accuracy','freshness','conflict_resolution','appropriate_use'):
 rows=[r for r in results if r['dimension']==dim];print(dim,'full provenance coverage',sum(r['full_source_coverage'] for r in rows),'/',len(rows),'packet records',dict(Counter(r['packet_records'] for r in rows)),flush=True)
print('TOTAL',len(results),'full provenance coverage',sum(r['full_source_coverage'] for r in results)); print('NOT FULL',json.dumps([r for r in results if not r['full_source_coverage']],ensure_ascii=False))
