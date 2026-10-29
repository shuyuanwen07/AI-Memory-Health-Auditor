from unittest.mock import patch
import pytest
from fastapi import HTTPException
from app.api.routes import audit_run_locks
from app.models import MessageModel
from app.services.ac3_locked_preflight import locked_ac3_preflight
from app.services.ac3_staging import stage_reviewed_suite
from test_ac3_database_mapping import saved_histories, fake_compile, add_fixture_audits


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_preflight_checks_inside_audit_lock_and_stays_disabled(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    add_fixture_audits(db)
    runs = {f'H{i}': f'R{i}' for i in range(8)}
    stage_reviewed_suite(db, path, digest, '0', mapping, runs)
    with locked_ac3_preflight(db, path, digest, '0', mapping, runs) as observation:
        assert observation['eligible_question_count'] == 32
        assert observation['execution_authorized'] is False
        with pytest.raises(HTTPException) as error:
            with audit_run_locks(['R0']): pass
        assert error.value.status_code == 409


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_changed_source_prevents_preflight(_mock, saved_histories):
    db, path, digest, mapping = saved_histories
    add_fixture_audits(db)
    runs = {f'H{i}': f'R{i}' for i in range(8)}
    stage_reviewed_suite(db, path, digest, '0', mapping, runs)
    db.get(MessageModel, 'Q0').content = 'modified'; db.commit()
    with pytest.raises(ValueError, match='source message'):
        with locked_ac3_preflight(db, path, digest, '0', mapping, runs):
            pytest.fail('Must not enter failed preflight')
