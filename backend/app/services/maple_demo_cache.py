"""Reuse a source-bound synthetic demo cache without changing historical audits."""
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import hashlib
import json

from sqlalchemy import select
from app.models import ConversationModel, MemoryModel, MemoryRelationshipModel, MessageModel, TestCaseModel


@lru_cache(maxsize=1)
def _cache():
    return json.loads((Path(__file__).resolve().parents[1] / 'maple_ai_cache.json').read_text())


def load_cached_memories(db, conversation, provider, model, ident):
    if not conversation.authorised or conversation.source_origin != 'synthetic' or provider != 'openai' or model != 'gpt-6-astra':
        return None
    cache = _cache()
    messages = db.scalars(select(MessageModel).where(MessageModel.conversation_id == conversation.id)
                          .order_by(MessageModel.sequence)).all()
    actual = [{'message_id': m.source_message_id, 'role': m.role, 'content': m.content,
               'timestamp': m.observation_timestamp} for m in messages]
    expected = [{**m, 'timestamp': datetime.fromisoformat(m['timestamp'].replace('Z', '+00:00'))}
                for m in cache['messages']]
    if actual != expected:
        return None
    identities = {item['memory_id']: ident('M') for item in cache['memories']}
    for item in cache['memories']:
        db.add(MemoryModel(id=identities[item['memory_id']], conversation_id=conversation.id,
            canonical_value=item['canonical_value'], status='candidate', source_message_ids=item['source_message_ids'],
            timestamp=datetime.fromisoformat(item['timestamp']) if item.get('timestamp') else None,
            confidence=item.get('confidence')))
    db.flush()
    for item in cache['memories']:
        for edge in item['relationships']:
            if edge['target_memory_id'] not in identities:
                continue
            db.add(MemoryRelationshipModel(id=ident('MR'), memory_id=identities[item['memory_id']],
                relationship_type=edge['type'], target_memory_id=identities[edge['target_memory_id']],
                evidence_message_ids=edge.get('evidence_message_ids'), confidence=edge.get('confidence')))
    conversation.extraction_provenance = {
        'status': 'completed', 'provider': cache['memory_source']['provider'],
        'model': cache['memory_source']['model'], 'version': cache['memory_source']['version'],
        'extracted_at': cache['memory_source']['extracted_at'], 'candidate_count': len(identities),
        'agent_execution_ids': [], 'cache_format': cache['format'],
        'cached_from_conversation_id': cache['memory_source']['conversation_id'],
    }
    db.commit()
    return db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == conversation.id)).all()


def load_cached_question(db, audit, experiment, memories, ident):
    if (audit.reproducibility_metadata or {}).get('coverage_policy') != 'evidence_supported_only_v1':
        return None
    conversation = db.get(ConversationModel, audit.conversation_id)
    cache = _cache()
    if not conversation or (conversation.extraction_provenance or {}).get('cache_format') != cache['format']:
        return None
    by_value = {memory.canonical_value: memory for memory in memories}
    if len(memories) != len(cache['memories']) or set(by_value) != {m['canonical_value'] for m in cache['memories']}:
        return None
    for original in cache['memories']:
        current = by_value[original['canonical_value']]
        if current.status.value != 'confirmed' or current.source_message_ids != original['source_message_ids']:
            return None
    ids = [by_value[m['canonical_value']].memory_id for m in cache['memories']]
    if not any(r.type.value == 'CONFLICT' and r.target_memory_id == ids[0]
               and set(r.evidence_message_ids or []) == {'FS02-M5', 'FS02-M6'}
               for r in by_value[cache['memories'][1]['canonical_value']].relationships):
        return None
    question = cache['questions'][0]
    slot = {'dimension': question['dimension'], 'test_type': question['test_type'], 'supporting_memory_ids': ids}
    frozen = {'coverage_policy': 'evidence_supported_only_v1', 'requested_test_count': audit.test_budget,
              'planned_test_count': 1, 'coverage_plan': [slot]}
    digest = hashlib.sha256(json.dumps(frozen, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    dimensions = ['accuracy', 'freshness', 'conflict_resolution', 'appropriate_use']
    observation = {**frozen, 'coverage_plan_sha256': digest, 'saved_suite': True,
        'agent_version': question['generator_version'], 'count_target_met': False,
        'quantity_shortfall_reason': 'One source-linked question was selected for this audit.',
        'cache_source_run_id': cache['question_source_run_id'],
        'dimension_coverage': [{'dimension': d, 'evidence_supported': True if d == question['dimension'] else None,
            'required_question_count': 1 if d == question['dimension'] else 0,
            'planned_question_count': 1 if d == question['dimension'] else 0,
            'reason': 'Cached source-linked question requires review.' if d == question['dimension'] else 'Not measured.'}
            for d in dimensions]}
    row = TestCaseModel(id=ident('T'), run_id=audit.id, dimension=question['dimension'], prompt=question['prompt'],
        expected_behavior=question['expected_behavior'], supporting_memory_ids=ids,
        generator_version=question['generator_version'], test_type=question['test_type'],
        quality_status='pending', grounding_status='grounded',
        validation_notes='partial-source-review-v1: Review this source-linked question before execution.',
        target_memory_context=[])
    db.add(row)
    audit.reproducibility_metadata = {**(audit.reproducibility_metadata or {}), 'generation_observations': [observation]}
    audit.status = 'TESTS_GENERATED'
    if experiment:
        experiment.test_suite_source_run_id = audit.id
        experiment.status = 'TEST_SUITE_GENERATED'
        experiment.test_suite_metadata = {**(experiment.test_suite_metadata or {}), 'test_count': 1,
            'dimensions': [question['dimension']], 'generator_version': question['generator_version'],
            'generated_at': None, 'loaded_at': datetime.now(timezone.utc).isoformat(),
            'cache_source_run_id': cache['question_source_run_id']}
    db.commit()
    db.refresh(row)
    return [row]
