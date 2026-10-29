"""The AC3 database check must not invent labels, write rows or run models."""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import AuditRunModel, ConversationModel, MemoryModel, MemoryRelationshipModel, MessageModel, TestCaseModel
from app.models.entities import Base
from app.services.ac3_staging import stage_reviewed_suite_in_test_db
from app.services.runtime_freeze import assert_audit_runtime_frozen
from app.services.audit_execution import AuditExecutionService
from app.schemas.domain import AuditStatus
from scripts.ac3_database_mapping import compile_database_stage, exercise_import_in_memory
from scripts.ac3_fixed_suite_adapter import sha


@pytest.fixture
def saved_histories(tmp_path):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    suite = {'cases': []}
    mapping = {}
    db = Session(engine)
    for n in range(8):
        history, conversation, source, memory = f'H{n}', f'C{n}', f'S{n}', f'M{n}'
        content = f'Fixture fact {n}'
        tests = [{'test_id': f'{history}-Q{i}', 'dimension': dimension, 'question': f'Question {n}-{i}',
                  'expected_behavior': content, 'supporting_source_message_ids': [source]}
                 for i, dimension in enumerate(('accuracy', 'freshness', 'conflict_resolution', 'appropriate_use'))]
        suite['cases'].append({'history_id': history, 'source_messages': [{'message_id': source, 'order': 1, 'role': 'user', 'text': content}], 'tests': tests})
        mapping[history] = conversation
        db.add(ConversationModel(id=conversation, authorised=True, source_origin='synthetic'))
        from datetime import datetime, timezone
        db.add(MessageModel(id=f'Q{n}', conversation_id=conversation, source_message_id=source, sequence=0, role='user', content=content, timestamp=datetime.now(timezone.utc)))
        db.add(MemoryModel(id=memory, conversation_id=conversation, status='confirmed', canonical_value=content, source_message_ids=[source]))
    db.commit()
    path = tmp_path / 'fixture-frozen.json'
    path.write_text(json.dumps({'suite': suite}))
    yield db, path, sha(path.read_bytes()), mapping
    db.close()
    engine.dispose()


def fake_compile(path, expected, reservation, snapshot=None):
    if sha(path.read_bytes()) != expected:
        raise ValueError('changed')
    if snapshot:
        for case in snapshot['histories']:
            if len(case['memories']) != 1 or case['memories'][0]['status'] != 'confirmed':
                raise ValueError('unconfirmed or extra memory')
            if case['memories'][0]['canonical_value'] != f"Fixture fact {case['history_id'][1:]}":
                raise ValueError('changed memory')
    suite = json.loads(path.read_text())['suite']
    items = []
    for case in suite['cases']:
        for question in case['tests']:
            items.append({'history_id': case['history_id'], **question, 'grounding_review': 'valid',
                          'supporting_memory_ids': [f"M{case['history_id'][1:]}"] if snapshot else None})
    return {'frozen_sha256': expected, 'model_called': False, 'database_written': False,
            'memory_records_verified_in_app': False, 'eligible_question_count': len(items), 'items': items,
            'model_configuration': {'target_provider': 'rule_based', 'target_model': 'fixture',
              'evaluator_provider': 'rule_based', 'evaluator_model': 'fixture-evaluator',
              'pipeline_provider': 'rule_based', 'pipeline_model': 'fixture-pipeline', 'target_strategy': 'weak_first_hit'}}


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_legacy_mapping_rejects_compound_frozen_sources(_mock, saved_histories):
    db, path, _digest, mapping = saved_histories
    data = json.loads(path.read_text())
    data['suite']['cases'][0]['source_messages'][0]['message_id'] = 'H0-M4'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Compound sources'):
        compile_database_stage(db, path, sha(path.read_bytes()), '0', mapping)


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_valid_database_mapping_is_read_only(mock_compile, saved_histories):
    db, path, digest, mapping = saved_histories
    result = compile_database_stage(db, path, digest, '0', mapping)
    assert result['memory_records_verified_in_app'] is True
    assert result['import_supported'] is result['execution_supported'] is False
    assert result['model_called'] is result['database_written'] is False
    assert len(list(db.scalars(select(MemoryModel)))) == 8
    assert not db.new and not db.dirty and not db.deleted
    assert mock_compile.call_count == 2


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_rejects_changed_source_and_dirty_session(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    message = db.get(MessageModel, 'Q0')
    message.content = 'Uncommitted change'
    with pytest.raises(ValueError, match='clean read-only session'):
        compile_database_stage(db, path, digest, '0', mapping)
    db.commit()
    with pytest.raises(ValueError, match='source message'):
        compile_database_stage(db, path, digest, '0', mapping)


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_rejects_unconfirmed_or_reused_conversation(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    mapping['H1'] = mapping['H0']
    with pytest.raises(ValueError, match='distinct'):
        compile_database_stage(db, path, digest, '0', mapping)
    mapping['H1'] = 'C1'
    db.get(MemoryModel, 'M1').status = 'candidate'
    db.commit()
    with pytest.raises(ValueError, match='unconfirmed'):
        compile_database_stage(db, path, digest, '0', mapping)


@pytest.mark.parametrize('field,value', [('authorised', False), ('source_origin', 'unknown')])
@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_rejects_unauthorised_or_non_synthetic_history(_mock, field, value, saved_histories):
    db, path, digest, mapping = saved_histories
    setattr(db.get(ConversationModel, 'C0'), field, value)
    db.commit()
    with pytest.raises(ValueError, match='authorised and explicitly synthetic'):
        compile_database_stage(db, path, digest, '0', mapping)


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_rejects_altered_memory_and_extra_message(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    memory = db.get(MemoryModel, 'M0')
    memory.canonical_value = 'Different fact'
    db.commit()
    with pytest.raises(ValueError, match='changed memory'):
        compile_database_stage(db, path, digest, '0', mapping)
    memory.canonical_value = 'Fixture fact 0'
    from datetime import datetime, timezone
    db.add(MessageModel(id='extra', conversation_id='C0', source_message_id='extra', sequence=1, role='user', content='Extra fact', timestamp=datetime.now(timezone.utc)))
    db.commit()
    with pytest.raises(ValueError, match='complete frozen history'):
        compile_database_stage(db, path, digest, '0', mapping)


def add_fixture_audits(db):
    for n in range(8):
        db.add(AuditRunModel(id=f'R{n}', conversation_id=f'C{n}', status='CREATED', target_configuration='strong',
            provider='rule_based', model='fixture', temperature=0.0, random_seed=42, test_budget=4,
            prompt_template_version='fixture', evaluator_provider='rule_based', evaluator_model='fixture-evaluator',
            pipeline_provider='rule_based', pipeline_model='fixture-pipeline', memory_strategy='weak_first_hit'))
    db.commit()


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_import_rehearsal_rolls_back_without_state_change(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    add_fixture_audits(db)
    runs = {f'H{n}': f'R{n}' for n in range(8)}
    result = exercise_import_in_memory(db, path, digest, '0', mapping, runs)
    assert result['test_rows_exercised'] == 32
    assert result['model_called'] is result['test_rows_retained'] is result['execution_supported'] is False
    assert not list(db.scalars(select(TestCaseModel)))
    assert all(db.get(AuditRunModel, run_id).status == 'CREATED' for run_id in runs.values())


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_import_rehearsal_rejects_mismatched_config_and_existing_tests(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    add_fixture_audits(db)
    runs = {f'H{n}': f'R{n}' for n in range(8)}
    run = db.get(AuditRunModel, 'R0')
    run.model = 'different'
    db.commit()
    with pytest.raises(ValueError, match='differs from the frozen configuration'):
        exercise_import_in_memory(db, path, digest, '0', mapping, runs)
    run.model = 'fixture'
    db.add(TestCaseModel(id='existing', run_id='R0', dimension='accuracy', prompt='Existing', expected_behavior='Expected', supporting_memory_ids=['M0'], generator_version='fixture'))
    db.commit()
    with pytest.raises(ValueError, match='no existing tests'):
        exercise_import_in_memory(db, path, digest, '0', mapping, runs)
    assert len(list(db.scalars(select(TestCaseModel)))) == 1


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_relationship_checks_reject_cross_history_and_untraceable_edges(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    # Two source memories in the same history, so the fixture source is also
    # extended to keep exact source-to-memory checks meaningful.
    suite = json.loads(path.read_text())
    suite['suite']['cases'][0]['source_messages'].append({'message_id': 'S0b', 'order': 2, 'role': 'user', 'text': 'Fixture second fact'})
    path.write_text(json.dumps(suite)); digest = sha(path.read_bytes())
    from datetime import datetime, timezone
    db.add(MessageModel(id='Q0b', conversation_id='C0', source_message_id='S0b', sequence=1, role='user', content='Fixture second fact', timestamp=datetime.now(timezone.utc)))
    db.add(MemoryModel(id='M0b', conversation_id='C0', status='confirmed', canonical_value='Fixture second fact', source_message_ids=['S0b']))
    db.add(MemoryRelationshipModel(id='rel', memory_id='M0b', target_memory_id='M1', relationship_type='UPDATE', evidence_message_ids=['S0b']))
    db.commit()
    with pytest.raises(ValueError, match='relationships'):
        compile_database_stage(db, path, digest, '0', mapping)
    relation = db.get(MemoryRelationshipModel, 'rel')
    relation.target_memory_id = 'M0'
    relation.evidence_message_ids = ['S1']
    db.commit()
    with pytest.raises(ValueError, match='relationships'):
        compile_database_stage(db, path, digest, '0', mapping)


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_rehearsal_refuses_file_backed_databases(_mock, saved_histories, tmp_path):
    _db, path, digest, mapping = saved_histories
    with Session(create_engine(f'sqlite:///{tmp_path / "not-in-memory.db"}')) as disk_db:
        with pytest.raises(ValueError, match='in-memory SQLite'):
            exercise_import_in_memory(disk_db, path, digest, '0', mapping, {})


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_quarantined_import_is_atomic_idempotent_and_cannot_run(_mock, saved_histories):
    from types import SimpleNamespace
    from fastapi import HTTPException

    db, path, digest, mapping = saved_histories
    add_fixture_audits(db)
    runs = {f'H{n}': f'R{n}' for n in range(8)}
    result = stage_reviewed_suite_in_test_db(db, path, digest, '0', mapping, runs)
    assert result['status'] == 'staged'
    assert result['test_count'] == 32 and result['execution_supported'] is result['model_called'] is False
    tests = list(db.scalars(select(TestCaseModel)))
    assert len(tests) == 32 and all(t.quality_status == t.grounding_status == 'pending' for t in tests)
    for run_id in runs.values():
        run = db.get(AuditRunModel, run_id)
        assert run.status == 'RESEARCH_STAGED'
        assert run.reproducibility_metadata['ac3_staged_suite']['execution_supported'] is False
        with pytest.raises(HTTPException, match='staged only'):
            assert_audit_runtime_frozen(run)
    planned = AuditExecutionService.plan_for(SimpleNamespace(audit=SimpleNamespace(status=AuditStatus.RESEARCH_STAGED, run_id='R0')))
    assert planned.retryable is False and planned.next_stage is None
    runner = AuditExecutionService(generator=object(), connector=object(), evaluator=object())
    staged_audit = SimpleNamespace(status=AuditStatus.RESEARCH_STAGED, run_id='R0')
    resumed = runner.resume(SimpleNamespace(audit=staged_audit))
    assert resumed.retry_plan.retryable is False and staged_audit.status == AuditStatus.RESEARCH_STAGED
    altered_status = SimpleNamespace(status=AuditStatus.TESTS_GENERATED, run_id='R0', reproducibility={'ac3_staged_suite': {'execution_supported': False}})
    resumed = runner.resume(SimpleNamespace(audit=altered_status))
    assert resumed.retry_plan.retryable is False and altered_status.status == AuditStatus.TESTS_GENERATED
    db.rollback()
    repeated = stage_reviewed_suite_in_test_db(db, path, digest, '0', mapping, runs)
    assert repeated['status'] == 'already_staged'
    assert len(list(db.scalars(select(TestCaseModel)))) == 32


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_quarantined_import_rejects_changed_or_partial_state(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    add_fixture_audits(db)
    runs = {f'H{n}': f'R{n}' for n in range(8)}
    db.get(AuditRunModel, 'R3').model = 'different'
    db.commit()
    with pytest.raises(ValueError, match='differs from the frozen configuration'):
        stage_reviewed_suite_in_test_db(db, path, digest, '0', mapping, runs)
    assert not list(db.scalars(select(TestCaseModel)))
    assert all(db.get(AuditRunModel, run_id).status == 'CREATED' for run_id in runs.values())
    db.get(AuditRunModel, 'R3').model = 'fixture'
    db.commit()
    stage_reviewed_suite_in_test_db(db, path, digest, '0', mapping, runs)
    item = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == 'R0').limit(1))
    item.prompt = 'Altered after staging'
    db.commit()
    with pytest.raises(ValueError, match='inputs changed after staging'):
        stage_reviewed_suite_in_test_db(db, path, digest, '0', mapping, runs)


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_quarantined_import_respects_busy_suite_lock(_mock, saved_histories):
    from app.api.routes import audit_run_lock
    from fastapi import HTTPException

    db, path, digest, mapping = saved_histories
    add_fixture_audits(db)
    runs = {f'H{n}': f'R{n}' for n in range(8)}
    with audit_run_lock('suite:R0', db=db):
        with pytest.raises(HTTPException) as error:
            stage_reviewed_suite_in_test_db(db, path, digest, '0', mapping, runs)
    assert error.value.status_code == 409
    assert not list(db.scalars(select(TestCaseModel)))
    assert all(db.get(AuditRunModel, run_id).status == 'CREATED' for run_id in runs.values())
