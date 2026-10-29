"""Synthetic staged audit/ledger checks, without any provider or human claim."""
from unittest.mock import patch
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.models import TargetResponseModel
from app.services.ac3_staging import stage_reviewed_suite
from app.services.ac3_locked_preflight import locked_ac3_preflight
from scripts.ac3_fixed_suite_adapter import sha
from test_ac3_database_mapping import saved_histories, fake_compile, add_fixture_audits


@pytest.fixture
def staged(saved_histories):
    db, frozen, digest, mapping = saved_histories
    add_fixture_audits(db)
    runs = {f'H{i}': f'R{i}' for i in range(8)}
    with patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile):
        stage_reviewed_suite(db, frozen, digest, '0', mapping, runs)
    db.execute(text('CREATE TABLE ac3_attempt_scopes (scope_id TEXT, frozen_sha256 TEXT, status TEXT)'))
    db.execute(text('CREATE TABLE ac3_attempt_receipts (scope_id TEXT, test_id TEXT, status TEXT, response_text TEXT, reported_cost_usd TEXT)'))
    db.execute(text("INSERT INTO ac3_attempt_scopes VALUES ('S', :sha, 'active')"), {'sha':digest})
    db.commit()
    return db, frozen, digest, mapping, runs


def save(staged, history, question):
    db, _, digest, _, _ = staged
    test, run = f'H{history}-Q{question}', f'R{history}'
    local = 'AC3' + sha(f'{digest}|{run}|{test}'.encode())[:32].upper()
    answer = f'synthetic {test}'
    db.add(TargetResponseModel(id=f'ANS-{test}', test_id=local, run_id=run,
                               response_text=answer, model='fixture', temperature=0))
    db.execute(text("INSERT INTO ac3_attempt_receipts VALUES ('S', :test, 'settled', :answer, '0.001')"), {'test':test,'answer':answer})
    db.commit()


def check(staged):
    db, frozen, digest, mapping, runs = staged
    with patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile):
        with locked_ac3_preflight(db, frozen, digest, '0', mapping, runs, ledger_scope='S') as result:
            assert not result['execution_authorized']


def test_resume_with_multiple_settled_responses(staged):
    save(staged, 0, 0)
    save(staged, 1, 1)
    check(staged)
    # A new session has no in-memory state from the first observation.
    fresh = Session(staged[0].get_bind())
    try:
        check((fresh, *staged[1:]))
    finally:
        fresh.close()


def test_unresolved_scope_is_blocked(staged):
    staged[0].execute(text("UPDATE ac3_attempt_scopes SET status = 'unknown'")); staged[0].commit()
    with pytest.raises(ValueError, match='unresolved'):
        check(staged)


def test_mismatched_response_is_blocked(staged):
    save(staged, 0, 0)
    db = staged[0]
    db.get(TargetResponseModel, 'ANS-H0-Q0').response_text = 'tampered'
    db.commit()
    with pytest.raises(ValueError, match='differs'):
        check(staged)


def test_duplicate_receipt_is_blocked(staged):
    save(staged, 0, 0)
    db = staged[0]
    db.execute(text("INSERT INTO ac3_attempt_receipts VALUES ('S', 'H0-Q0', 'settled', 'synthetic H0-Q0', '0.001')")); db.commit()
    with pytest.raises(ValueError, match='duplicate'):
        check(staged)


def test_settled_receipt_without_saved_response_is_blocked(staged):
    db = staged[0]
    db.execute(text("INSERT INTO ac3_attempt_receipts VALUES ('S', 'H0-Q0', 'settled', 'missing', '0.001')")); db.commit()
    with pytest.raises(ValueError, match='differ'):
        check(staged)


def test_unknown_question_and_bad_cost_are_blocked(staged):
    db = staged[0]
    db.execute(text("INSERT INTO ac3_attempt_receipts VALUES ('S', 'UNKNOWN', 'settled', 'synthetic', '0.001')")); db.commit()
    with pytest.raises(ValueError, match='unknown frozen'):
        check(staged)
    db.execute(text("UPDATE ac3_attempt_receipts SET test_id = 'H0-Q0', reported_cost_usd = '-1'")); db.commit()
    with pytest.raises(ValueError, match='invalid'):
        check(staged)
