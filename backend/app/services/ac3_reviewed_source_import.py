"""Import a prospectively frozen, independently reviewed synthetic AC3 source.

This never runs a model or changes existing conversation data. New objects are
created in one transaction with deterministic identities. Each memory and
relationship is copied only from the hash-bound human-reviewed fact plan.
"""
from datetime import datetime, timezone, timedelta
import json
import hashlib
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import ConversationModel, MessageModel, MemoryModel, MemoryRelationshipModel
from scripts.ac3_fixed_suite_adapter import compile_mock, sha
from scripts.ac3_reviewed_fact_map import validate_fact_plan


def _object_id(prefix, digest, *pieces):
    return prefix + sha(('|'.join((digest, *pieces))).encode())[:32].upper()


def import_reviewed_ac3_sources(engine, *, frozen_path, frozen_sha256, reservation):
    dialect = engine.url.get_backend_name()
    if dialect == 'postgresql':
        with engine.connect() as conn:
            if conn.get_isolation_level() != 'SERIALIZABLE':
                raise ValueError('Source import requires SERIALIZABLE PostgreSQL')
    elif dialect != 'sqlite' or engine.url.database not in (None, ':memory:'):
        raise ValueError('Source import requires PostgreSQL or disposable SQLite')
    plan = compile_mock(frozen_path, frozen_sha256, reservation)
    facts, reviews = plan.get('reviewed_fact_plan'), plan.get('fact_plan_reviews')
    if not facts or not reviews:
        raise ValueError('A frozen reviewed multi-fact plan is required')
    frozen = json.loads(frozen_path.read_text())
    suite, cfg = frozen['suite'], plan['model_configuration']
    validate_fact_plan(suite, facts, reviews)
    raw_time = cfg.get('synthetic_source_timestamp_utc')
    if not isinstance(raw_time, str):
        raise ValueError('Frozen protocol must supply the synthetic placeholder timestamp')
    try:
        parsed = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
        if parsed.utcoffset() is None or parsed.utcoffset() != timedelta(0): raise ValueError
        base_time = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError as exc:
        raise ValueError('Synthetic placeholder timestamp must be an ISO UTC timestamp') from exc
    histories = suite['cases']
    # Source identity is per history, not per experiment. A later frozen repeat
    # can reuse exactly the same reviewed source and fact graph without
    # replacing it or colliding on the human-reviewed fact IDs. Any content or
    # timestamp-policy change produces a new identity and cannot overwrite it.
    source_keys = {}
    for case in histories:
        history = case['history_id']
        payload = {'history_id':history, 'source_messages':case['source_messages'],
                   'facts_and_relationships':facts['histories'][history], 'synthetic_timestamp_utc':raw_time}
        source_keys[history] = hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    mapping = {case['history_id']:_object_id('AC3C', source_keys[case['history_id']], case['history_id']) for case in histories}
    memory_ids = [fact['memory_id'] for part in facts['histories'].values() for fact in part['facts']]
    if len(memory_ids) != len(set(memory_ids)):
        raise ValueError('Reviewed fact IDs are not globally unique')
    from app.api.routes import audit_run_locks
    with Session(engine) as db:
        with audit_run_locks(['ac3-import:' + frozen_sha256], db=db):
            with db.begin():
                existing = list(db.scalars(select(ConversationModel).where(ConversationModel.id.in_(mapping.values())).with_for_update()))
                existing_ids = {row.id for row in existing}
                if len(existing_ids) == len(mapping):
                    # Revalidate all imported sources and facts; never repair changed data.
                    from scripts.ac3_database_mapping import compile_database_stage
                    checked = compile_database_stage(db, frozen_path, frozen_sha256, reservation, mapping)
                    if not checked['memory_records_verified_in_app']:
                        raise ValueError('Existing imported records could not be verified')
                    return {'status':'already_imported','history_conversations':mapping,'model_called':False}
                new_histories = {history for history, identifier in mapping.items() if identifier not in existing_ids}
                new_memory_ids = [fact['memory_id'] for history in new_histories for fact in facts['histories'][history]['facts']]
                if db.scalar(select(MemoryModel.id).where(MemoryModel.id.in_(new_memory_ids)).limit(1)):
                    raise ValueError('A reviewed fact ID already belongs to another record')
                for case in histories:
                    history = case['history_id']; conversation_id = mapping[history]
                    if history not in new_histories:
                        continue
                    db.add(ConversationModel(id=conversation_id, authorised=True, source_origin='synthetic',
                        extraction_provenance={'kind':'ac3_reviewed_source_import','frozen_sha256':frozen_sha256,
                            'history_id':history,'timestamp_policy':'synthetic_placeholder_not_observed_time',
                            'synthetic_timestamp_utc':raw_time,'reviewed_source_sha256':source_keys[history]}))
                    db.flush()
                    for index, message in enumerate(case['source_messages']):
                        db.add(MessageModel(id=_object_id('AC3M', source_keys[history], history, message['message_id']),
                            conversation_id=conversation_id, source_message_id=message['message_id'], sequence=index,
                            role=message['role'], content=message['text'], timestamp=base_time + timedelta(seconds=index)))
                    for fact in facts['histories'][history]['facts']:
                        db.add(MemoryModel(id=fact['memory_id'], conversation_id=conversation_id,
                            canonical_value=fact['canonical_value'], status='confirmed',
                            source_message_ids=[fact['source_message_id']]))
                    db.flush()
                    for edge in facts['histories'][history]['relationships']:
                        db.add(MemoryRelationshipModel(id=_object_id('AC3E', source_keys[history], history, edge['memory_id'], edge['relationship_type'], edge['target_memory_id']),
                            memory_id=edge['memory_id'], target_memory_id=edge['target_memory_id'],
                            relationship_type=edge['relationship_type'], evidence_message_ids=edge['evidence_message_ids']))
                db.flush()
                # Ensure the DB projection exactly matches reviewed input before commit.
                from scripts.ac3_database_mapping import compile_database_stage
                checked = compile_database_stage(db, frozen_path, frozen_sha256, reservation, mapping)
                if not checked['memory_records_verified_in_app']:
                    raise ValueError('Imported records could not be verified')
                if compile_mock(frozen_path, frozen_sha256, reservation)['frozen_sha256'] != frozen_sha256:
                    raise ValueError('Frozen evidence changed while importing')
    return {'status':'imported','history_conversations':mapping,'history_count':len(mapping),
            'memory_count':len(memory_ids),'model_called':False,
            'notice':'Human-reviewed synthetic source import; no target responses or evaluation outcomes generated.'}
