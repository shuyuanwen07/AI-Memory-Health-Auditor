"""Synthetic reviewed plan and in-memory DB; no real human evidence."""
import json
from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models import AuditRunModel, ConversationModel, MemoryModel, MemoryRelationshipModel, MessageModel, TestCaseModel
from app.models.entities import Base
from app.services.ac3_staging import stage_reviewed_suite
from scripts.ac3_database_mapping import compile_database_stage
from scripts.ac3_fixed_suite_adapter import sha
from scripts.tests.test_ac3_reviewed_fact_map import fixture as fact_fixture  # noqa: F401

@pytest.fixture
def saved_fact_plan(tmp_path, fact_fixture):  # noqa: F811
    suite, plan, reviews, snapshot = fact_fixture
    for n, message in enumerate(suite['cases'][0]['source_messages']):
        message.update(role='user', order=n + 1)
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(ConversationModel(id='C', authorised=True, source_origin='synthetic')); db.flush()
    for n, message in enumerate(suite['cases'][0]['source_messages']):
        db.add(MessageModel(id=f'MSG{n}', conversation_id='C', source_message_id=message['message_id'], sequence=n, role='user', content=message['text'], timestamp=datetime.now(timezone.utc)))
    for memory in snapshot['histories']['H']['memories']:
        db.add(MemoryModel(id=memory['memory_id'], conversation_id='C', status=memory['status'], canonical_value=memory['canonical_value'], source_message_ids=memory['source_message_ids']))
    db.flush()
    for n, edge in enumerate(snapshot['histories']['H']['relationships']):
        db.add(MemoryRelationshipModel(id=f'REL{n}', **edge))
    db.add(AuditRunModel(id='R', conversation_id='C', status='CREATED', target_configuration='strong',
        provider='rule_based', model='fixture', temperature=0, random_seed=42, test_budget=1,
        prompt_template_version='fixture', evaluator_provider='rule_based', evaluator_model='fixture-evaluator',
        pipeline_provider='rule_based', pipeline_model='fixture-pipeline', memory_strategy='weak_first_hit'))
    db.commit()
    path = tmp_path / 'frozen.json'; path.write_text(json.dumps({'suite': suite}))
    digest = sha(path.read_bytes())
    def compile_fixture(path, expected, reservation, snapshot=None):
        assert sha(path.read_bytes()) == expected and snapshot is None
        return {'frozen_sha256': expected, 'model_called': False, 'database_written': False,
            'eligible_question_count': 1, 'reviewed_fact_plan': plan, 'fact_plan_reviews': reviews,
            'items': [{'history_id': 'H', 'test_id': 'T', 'dimension': 'conflict_resolution',
                'question': 'Fixture question', 'expected_behavior': 'Fixture expectation',
                'grounding_review': 'valid', 'supporting_source_message_ids': ['H-M4']}],
            'model_configuration': {'target_provider': 'rule_based', 'target_model': 'fixture',
                'evaluator_provider': 'rule_based', 'evaluator_model': 'fixture-evaluator',
                'pipeline_provider': 'rule_based', 'pipeline_model': 'fixture-pipeline', 'target_strategy': 'weak_first_hit'}}
    yield db, path, digest, compile_fixture
    db.close(); engine.dispose()


def test_reviewed_multifact_database_import_keeps_both_memories(saved_fact_plan):
    db, path, digest, compile_fixture = saved_fact_plan
    with patch('scripts.ac3_database_mapping.compile_mock', side_effect=compile_fixture):
        report = compile_database_stage(db, path, digest, '0', {'H': 'C'})
        assert report['items'][0]['supporting_memory_ids'] == ['F3', 'F4']
        db.rollback()
        assert stage_reviewed_suite(db, path, digest, '0', {'H': 'C'}, {'H': 'R'})['status'] == 'staged'
        saved = db.scalar(select(TestCaseModel))
        assert saved.supporting_memory_ids == ['F3', 'F4']
        assert db.get(AuditRunModel, 'R').status == 'RESEARCH_STAGED'


def test_unreviewed_database_edge_cannot_be_imported(saved_fact_plan):
    db, path, digest, compile_fixture = saved_fact_plan
    db.delete(db.get(MemoryRelationshipModel, 'REL1')); db.commit()
    with patch('scripts.ac3_database_mapping.compile_mock', side_effect=compile_fixture):
        with pytest.raises(ValueError, match='relationships differ'):
            compile_database_stage(db, path, digest, '0', {'H': 'C'})
