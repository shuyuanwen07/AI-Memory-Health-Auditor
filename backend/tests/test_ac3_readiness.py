"""Read-only readiness checks must never release or run a staged audit."""
from unittest.mock import patch
import pytest
from sqlalchemy import select
from app.models import AuditRunModel, TestCaseModel
from app.services.ac3_readiness import inspect_staged_ac3
from app.services.ac3_staging import stage_reviewed_suite
from test_ac3_database_mapping import saved_histories, fake_compile, add_fixture_audits


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_staged_readiness_is_observation_only(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    add_fixture_audits(db)
    runs = {f'H{i}': f'R{i}' for i in range(8)}
    stage_reviewed_suite(db, path, digest, '0', mapping, runs)
    result = inspect_staged_ac3(db, path, digest, '0', mapping, runs)
    assert result['eligible_question_count'] == 32
    assert result['execution_authorized'] is result['model_called'] is result['database_written'] is False
    assert len(result['blocking_conditions']) == 4
    assert all(db.get(AuditRunModel, run).status == 'RESEARCH_STAGED' for run in runs.values())
    assert not db.new and not db.dirty and not db.deleted


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_changed_staged_questions_block_inspection(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    add_fixture_audits(db)
    runs = {f'H{i}': f'R{i}' for i in range(8)}
    stage_reviewed_suite(db, path, digest, '0', mapping, runs)
    test = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == 'R0'))
    test.prompt = 'tampered'
    db.commit()
    with pytest.raises(ValueError, match='fingerprint changed'):
        inspect_staged_ac3(db, path, digest, '0', mapping, runs)


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_created_audits_cannot_be_released_by_inspection(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    add_fixture_audits(db)
    runs = {f'H{i}': f'R{i}' for i in range(8)}
    with pytest.raises(ValueError, match='quarantined staged'):
        inspect_staged_ac3(db, path, digest, '0', mapping, runs)
    assert all(db.get(AuditRunModel, run).status == 'CREATED' for run in runs.values())
