"""PostgreSQL checks using only a disposable, explicitly named test container.

Never set this test's URL from user configuration: the hostname and database
must be the isolated test container on its private network.
"""
import json
import os
import threading
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import AuditRunModel, ConversationModel, MemoryModel, MessageModel, TestCaseModel
from app.models.entities import Base
from app.services.ac3_staging import stage_reviewed_suite
from app.services.stage_lock import stage_lock_key
from scripts.ac3_fixed_suite_adapter import sha
from test_ac3_database_mapping import fake_compile

URL = 'postgresql+psycopg://ac3_test:ac3_test_only@ac3-postgres-isolated-20261028:5432/ac3_test'
pytestmark = pytest.mark.skipif(os.environ.get('AC3_DISPOSABLE_POSTGRES_TEST') != 'yes', reason='Requires explicitly enabled disposable PostgreSQL container')


@pytest.fixture
def isolated_db(tmp_path):
    engine = create_engine(URL, isolation_level='SERIALIZABLE', pool_size=2, max_overflow=0, pool_timeout=2)
    # The fixed hostname and explicit opt-in prevent accidental use of a
    # developer or production DATABASE_URL. This DB lives in a disposable container.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    suite = {'cases': []}
    mapping, runs = {}, {}
    with Session(engine) as db:
        for n in range(8):
            db.add(ConversationModel(id=f'C{n}', authorised=True, source_origin='synthetic'))
        db.flush()
        for n in range(8):
            history, conversation, source = f'H{n}', f'C{n}', f'S{n}'
            content = f'Fixture fact {n}'
            tests = [{'test_id': f'{history}-Q{i}', 'dimension': dimension, 'question': f'Question {n}-{i}',
                      'expected_behavior': content, 'supporting_source_message_ids': [source]}
                     for i, dimension in enumerate(('accuracy', 'freshness', 'conflict_resolution', 'appropriate_use'))]
            suite['cases'].append({'history_id': history, 'source_messages': [{'message_id': source, 'order': 1, 'role': 'user', 'text': content}], 'tests': tests})
            mapping[history], runs[history] = conversation, f'R{n}'
            db.add(MessageModel(id=f'Q{n}', conversation_id=conversation, source_message_id=source, sequence=0, role='user', content=content, timestamp=datetime.now(timezone.utc)))
            db.add(MemoryModel(id=f'M{n}', conversation_id=conversation, status='confirmed', canonical_value=content, source_message_ids=[source]))
            db.add(AuditRunModel(id=f'R{n}', conversation_id=conversation, status='CREATED', target_configuration='strong',
                provider='rule_based', model='fixture', temperature=0.0, random_seed=42, test_budget=4,
                prompt_template_version='fixture', evaluator_provider='rule_based', evaluator_model='fixture-evaluator',
                pipeline_provider='rule_based', pipeline_model='fixture-pipeline', memory_strategy='weak_first_hit'))
        db.commit()
    path = tmp_path / 'fixture-frozen.json'
    path.write_text(json.dumps({'suite': suite}))
    yield engine, path, sha(path.read_bytes()), mapping, runs
    engine.dispose()


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_serializable_atomic_stage_and_idempotency(_mock, isolated_db):
    engine, path, digest, mapping, runs = isolated_db
    with Session(engine) as db:
        assert stage_reviewed_suite(db, path, digest, '0', mapping, runs)['status'] == 'staged'
        assert len(list(db.scalars(select(TestCaseModel)))) == 32
        assert all(row.status == 'RESEARCH_STAGED' for row in db.scalars(select(AuditRunModel)))
        db.rollback()
        assert stage_reviewed_suite(db, path, digest, '0', mapping, runs)['status'] == 'already_staged'


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_cross_connection_advisory_conflict_releases_partial_locks(_mock, isolated_db):
    engine, path, digest, mapping, runs = isolated_db
    # An external connection is enough to test PostgreSQL's cross-connection
    # lock, not just the shared in-process lock dictionary.
    external = create_engine(URL, isolation_level='AUTOCOMMIT')
    with external.connect() as locker:
        assert locker.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': stage_lock_key('suite:R3')})
        try:
            with Session(engine) as db:
                with pytest.raises(HTTPException) as error:
                    stage_reviewed_suite(db, path, digest, '0', mapping, runs)
                assert error.value.status_code == 409
            assert locker.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': stage_lock_key('R0')})
            locker.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': stage_lock_key('R0')})
            with Session(engine) as db:
                assert not list(db.scalars(select(TestCaseModel)))
                assert all(row.status == 'CREATED' for row in db.scalars(select(AuditRunModel)))
        finally:
            locker.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': stage_lock_key('suite:R3')})
    external.dispose()


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_nonserializable_postgres_is_rejected(_mock, isolated_db):
    _engine, path, digest, mapping, runs = isolated_db
    weaker = create_engine(URL, isolation_level='READ COMMITTED')
    with Session(weaker) as db:
        with pytest.raises(ValueError, match='SERIALIZABLE'):
            stage_reviewed_suite(db, path, digest, '0', mapping, runs)
    weaker.dispose()


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_transaction_rolls_back_tests_if_audit_status_write_fails(_mock, isolated_db):
    engine, path, digest, mapping, runs = isolated_db
    def fail_status_write(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith('UPDATE AUDIT_RUNS'):
            raise RuntimeError('Injected failure before audit status write')
    event.listen(engine, 'before_cursor_execute', fail_status_write)
    try:
        with Session(engine) as db:
            with pytest.raises(RuntimeError, match='Injected failure'):
                stage_reviewed_suite(db, path, digest, '0', mapping, runs)
    finally:
        event.remove(engine, 'before_cursor_execute', fail_status_write)
    with Session(engine) as db:
        assert not list(db.scalars(select(TestCaseModel)))
        assert all(row.status == 'CREATED' for row in db.scalars(select(AuditRunModel)))


def test_source_rows_are_locked_until_staging_commits(isolated_db):
    engine, path, digest, mapping, runs = isolated_db
    checked = threading.Event()
    release = threading.Event()
    errors = []

    def coordinated_compile(path, expected, reservation, snapshot=None):
        result = fake_compile(path, expected, reservation, snapshot)
        if snapshot is not None:
            checked.set()
            if not release.wait(5):
                raise RuntimeError('Test coordination timed out')
        return result

    def stage():
        try:
            with Session(engine) as db:
                stage_reviewed_suite(db, path, digest, '0', mapping, runs)
        except BaseException as error:
            errors.append(error)

    with patch('scripts.ac3_database_mapping.compile_mock', side_effect=coordinated_compile):
        worker = threading.Thread(target=stage)
        worker.start()
        try:
            assert checked.wait(5)
            external = create_engine(URL)
            with external.connect() as conn:
                with pytest.raises(OperationalError):
                    with conn.begin():
                        conn.execute(text("SET LOCAL lock_timeout = '300ms'"))
                        conn.execute(text("UPDATE memories SET canonical_value = 'changed' WHERE id = 'M0'"))
                with pytest.raises(OperationalError):
                    with conn.begin():
                        conn.execute(text("SET LOCAL lock_timeout = '300ms'"))
                        conn.execute(text("INSERT INTO messages (id, conversation_id, source_message_id, sequence, role, content, timestamp) VALUES ('extra', 'C0', 'extra', 1, 'user', 'new', CURRENT_TIMESTAMP)"))
            external.dispose()
        finally:
            release.set()
            worker.join(5)
        assert not worker.is_alive()
        assert errors == []
    with Session(engine) as db:
        assert db.get(MemoryModel, 'M0').canonical_value == 'Fixture fact 0'
        assert len(list(db.scalars(select(TestCaseModel)))) == 32


@patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile)
def test_locked_preflight_blocks_concurrent_source_mutation(_mock, isolated_db):
    from app.services.ac3_locked_preflight import locked_ac3_preflight
    engine, path, digest, mapping, runs = isolated_db
    with Session(engine) as db:
        stage_reviewed_suite(db, path, digest, '0', mapping, runs)
        with locked_ac3_preflight(db, path, digest, '0', mapping, runs) as observation:
            assert observation['execution_authorized'] is False
            external = create_engine(URL)
            try:
                with external.connect() as conn:
                    with pytest.raises(OperationalError):
                        with conn.begin():
                            conn.execute(text("SET LOCAL lock_timeout = '300ms'"))
                            conn.execute(text("UPDATE memories SET canonical_value = 'changed' WHERE id = 'M0'"))
            finally:
                external.dispose()
