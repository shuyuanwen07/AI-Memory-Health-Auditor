"""No provider calls or persistent database in these integration tests."""
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from sqlalchemy import select, create_engine, event
from sqlalchemy.orm import Session
from app.api.routes import audit_run_locks
from app.models import TargetResponseModel
from app.services.ac3_dispatch_fixture import exercise_locked_fixture_dispatch
from app.services.ac3_staging import stage_reviewed_suite
from test_ac3_database_mapping import saved_histories as saved_histories, fake_compile, add_fixture_audits


def setup(db, path, digest, mapping):
    add_fixture_audits(db)
    runs = {f'H{i}': f'R{i}' for i in range(8)}
    stage_reviewed_suite(db, path, digest, '0', mapping, runs)
    return runs


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_locked_revalidation_then_fixture_responses_are_atomic(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    runs = setup(db, path, digest, mapping)
    result = exercise_locked_fixture_dispatch(db, path, digest, '0', mapping, runs)
    assert result['responses_written_in_memory'] == 32 and not result['provider_called']
    assert not result['real_execution_authorized']
    responses = list(db.scalars(select(TargetResponseModel)))
    assert len(responses) == 32 and all(r.execution_metadata['synthetic_fixture'] for r in responses)
    db.rollback()
    with pytest.raises(ValueError, match='unexpected target responses'):
        exercise_locked_fixture_dispatch(db, path, digest, '0', mapping, runs)


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_changed_frozen_suite_never_dispatches(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    runs = setup(db, path, digest, mapping)
    path.write_text('{}')
    with pytest.raises(ValueError, match='changed'):
        exercise_locked_fixture_dispatch(db, path, digest, '0', mapping, runs)
    assert not list(db.scalars(select(TargetResponseModel)))


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_locked_audit_blocks_dispatch(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    runs = setup(db, path, digest, mapping)
    with audit_run_locks(['R0'], db=db):
        with pytest.raises(HTTPException) as error:
            exercise_locked_fixture_dispatch(db, path, digest, '0', mapping, runs)
        assert error.value.status_code == 409
    assert not list(db.scalars(select(TargetResponseModel)))


def test_refuses_file_database(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'not-allowed.sqlite'))
    with Session(engine) as db:
        with pytest.raises(ValueError, match='in-memory'):
            exercise_locked_fixture_dispatch(db, None, '0' * 64, '0', {}, {})
    engine.dispose()


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_response_write_failure_rolls_back_all(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    runs = setup(db, path, digest, mapping)
    engine = db.get_bind()
    def fail_after_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.lower().lstrip().startswith('insert into target_responses'):
            raise RuntimeError('simulated failure after insert')
    event.listen(engine, 'after_cursor_execute', fail_after_insert)
    try:
        with pytest.raises(RuntimeError, match='simulated failure'):
            exercise_locked_fixture_dispatch(db, path, digest, '0', mapping, runs)
    finally:
        event.remove(engine, 'after_cursor_execute', fail_after_insert)
    assert not list(db.scalars(select(TargetResponseModel)))
