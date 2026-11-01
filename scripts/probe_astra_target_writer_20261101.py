"""Explore the existing model writer on source messages only; no audit answers."""
import json,os,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
from dotenv import dotenv_values
from app.schemas import Conversation,ConversationMessage
from app.memory_agent.writers import LLMTargetMemoryWriter

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'output/proposal-delivery/astra-product-end-to-end-20261101-v1/sources.json'
OUT=ROOT/'output/proposal-delivery/astra-product-end-to-end-20261101-v1/astra-target-writer-probe.json'
if OUT.exists():raise SystemExit('Existing probe retained; do not repeat')
source=json.loads(SRC.read_text())['histories'][0];base=datetime(2026,1,1,9,tzinfo=timezone.utc)
conversation=Conversation(conversation_id='ASTRA-WRITER-PROBE',authorised=True,created_at=base,
 messages=[ConversationMessage(message_id=f'FS01-M{i+1}',role='user',content=value,timestamp=base+timedelta(days=i)) for i,value in enumerate(source['texts'])])
record={'status':'dispatched','source_sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'provider':'openai','model':'gpt-6-astra',
        'effort':'max','scope':'Exploratory on previously observed synthetic source only; no auditor question or expected answer passed to writer.'}
OUT.write_text(json.dumps(record,indent=2)+'\n');os.environ['OPENAI_API_KEY']=dotenv_values(ROOT/'.env')['OPENAI_API_KEY']
writer=LLMTargetMemoryWriter('openai','gpt-6-astra')
try:
    memories=writer.extract(conversation)
    record.update(status='completed',records=[m.model_dump(mode='json') for m in memories],execution=writer.client.last_execution)
except Exception as exc:record.update(status='failed',error_type=type(exc).__name__,error=str(exc)[:300],execution=writer.client.last_execution)
OUT.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print('status',record['status'],'records',len(record.get('records',[])),'error',record.get('error_type'),flush=True)
