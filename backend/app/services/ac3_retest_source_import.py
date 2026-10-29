"""Quarantined paired-retest source import; no model or audit execution."""
import hashlib
import json
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import ConversationModel, MemoryModel, MemoryRelationshipModel, MessageModel
from app.services.ac3_retest_binding import verify_database_binding
from scripts.ac3_retest_paired_freeze import canonical
from scripts.ac3_retest_reference_stage import compile_reference_stage


def _identity(prefix, frozen_sha, *parts):
    return prefix+hashlib.sha256('|'.join((frozen_sha,*parts)).encode()).hexdigest()[:32].upper()


def import_paired_sources(engine, frozen, source_raw, plan_raw, reviews, components):
    dialect=engine.url.get_backend_name()
    if dialect=='postgresql':
        with engine.connect() as conn:
            if conn.get_isolation_level()!='SERIALIZABLE':raise ValueError('Source import requires SERIALIZABLE PostgreSQL')
    elif dialect!='sqlite' or engine.url.database not in (None,':memory:'):
        raise ValueError('Only SERIALIZABLE PostgreSQL or isolated in-memory SQLite is supported')
    stage=compile_reference_stage(frozen,source_raw,plan_raw,reviews,components)
    frozen_sha=hashlib.sha256(canonical(frozen)).hexdigest()
    mapping={h['history_id']:_identity('AC3C',frozen_sha,h['history_id']) for h in stage['histories']}
    fact_ids=[f['memory_id'] for h in stage['histories'] for f in h['reviewed_facts']]
    if len(fact_ids)!=len(set(fact_ids)):raise ValueError('Reviewed fact IDs must be globally distinct')
    from app.api.routes import audit_run_locks
    with Session(engine) as db:
        with audit_run_locks(['ac3-paired-import:'+frozen_sha],db=db):
            with db.begin():
                # Evidence is recompiled after acquiring the shared import lock.
                current=compile_reference_stage(frozen,source_raw,plan_raw,reviews,components)
                if current!=stage:raise ValueError('Reviewed evidence changed during import')
                existing=list(db.scalars(select(ConversationModel).where(ConversationModel.id.in_(list(mapping.values()))).with_for_update()))
                if existing:
                    if len(existing)!=len(mapping):raise ValueError('Partial prior import requires investigation')
                    verify_database_binding(db,frozen,source_raw,plan_raw,reviews,components,mapping)
                    return {'status':'already_imported','history_conversations':mapping,'model_called':False,'execution_supported':False}
                if db.scalar(select(MemoryModel.id).where(MemoryModel.id.in_(fact_ids)).limit(1)):
                    raise ValueError('A reviewed fact ID already belongs to an existing record')
                for history in stage['histories']:
                    hid=history['history_id'];cid=mapping[hid]
                    db.add(ConversationModel(id=cid,authorised=True,source_origin='synthetic',extraction_provenance={
                        'kind':'ac3_paired_reviewed_source','frozen_sha256':frozen_sha,'history_id':hid,
                        'timestamp_policy':'synthetic placeholder, not observed time'}))
                    db.flush()
                    for n,msg in enumerate(history['source_messages']):
                        db.add(MessageModel(id=_identity('AC3M',frozen_sha,hid,msg['message_id']),conversation_id=cid,
                            source_message_id=msg['message_id'],sequence=n,role=msg['role'],content=msg['text'],
                            timestamp=datetime(2000,1,1)+timedelta(seconds=n)))
                    for fact in history['reviewed_facts']:
                        db.add(MemoryModel(id=fact['memory_id'],conversation_id=cid,status='confirmed',
                            canonical_value=fact['canonical_value'],source_message_ids=[fact['source_message_id']]))
                    db.flush()
                    for edge in history['reviewed_relationships']:
                        db.add(MemoryRelationshipModel(id=_identity('AC3E',frozen_sha,hid,edge['memory_id'],edge['relationship_type'],edge['target_memory_id']),
                            memory_id=edge['memory_id'],target_memory_id=edge['target_memory_id'],relationship_type=edge['relationship_type'],
                            evidence_message_ids=edge['evidence_message_ids']))
                db.flush()
                verify_database_binding(db,frozen,source_raw,plan_raw,reviews,components,mapping)
    return {'status':'imported','history_conversations':mapping,'history_count':len(mapping),
            'memory_count':len(fact_ids),'model_called':False,'execution_supported':False}
