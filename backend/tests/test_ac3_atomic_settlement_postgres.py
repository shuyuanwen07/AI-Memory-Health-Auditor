"""Destructive schema setup confined to a named throwaway PostgreSQL container."""
import json, os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session
from app.models import ConversationModel, MemoryModel, MessageModel, TargetResponseModel
from app.models.entities import Base
from app.services.ac3_atomic_settlement import settle_and_save
from app.services.ac3_staging import stage_reviewed_suite
from scripts.ac3_fixed_suite_adapter import sha
from test_ac3_database_mapping import fake_compile, add_fixture_audits

URL = 'postgresql+psycopg://ac3_test:ac3_test_only@ac3-atomic-postgres-test:5432/ac3_test'
pytestmark = pytest.mark.skipif(os.environ.get('AC3_ATOMIC_DISPOSABLE') != 'yes', reason='isolated DB only')

@pytest.fixture
def prepared(tmp_path):
    engine = create_engine(URL, isolation_level='SERIALIZABLE', pool_size=10)
    assert (engine.url.host, engine.url.database, engine.url.username) == ('ac3-atomic-postgres-test','ac3_test','ac3_test')
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS ac3_attempt_receipts'))
        conn.execute(text('DROP TABLE IF EXISTS ac3_attempt_scopes'))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    sql = Path('/app/research_migrations/ac3_attempt_ledger.sql').read_text()
    with engine.begin() as conn:
        for statement in sql.split(';'):
            if statement.strip(): conn.execute(text(statement))
    db = Session(engine)
    suite = {'cases': []}; mapping = {}
    for n in range(8):
        history, conversation, source, memory = f'H{n}', f'C{n}', f'S{n}', f'M{n}'
        content = f'Fixture fact {n}'
        tests = [{'test_id':f'{history}-Q{i}','dimension':dimension,'question':f'Question {n}-{i}',
                  'expected_behavior':content,'supporting_source_message_ids':[source]}
                 for i, dimension in enumerate(('accuracy','freshness','conflict_resolution','appropriate_use'))]
        suite['cases'].append({'history_id':history,'source_messages':[{'message_id':source,'order':1,'role':'user','text':content}],'tests':tests})
        mapping[history] = conversation
        db.add(ConversationModel(id=conversation, authorised=True, source_origin='synthetic'))
        db.add(MessageModel(id=f'Q{n}', conversation_id=conversation, source_message_id=source, sequence=0, role='user', content=content, timestamp=datetime.now(timezone.utc)))
        db.add(MemoryModel(id=memory, conversation_id=conversation, status='confirmed', canonical_value=content, source_message_ids=[source]))
    db.commit()
    frozen = tmp_path / 'synthetic-frozen.json'; frozen.write_text(json.dumps({'suite':suite}))
    digest = sha(frozen.read_bytes()); add_fixture_audits(db)
    runs = {f'H{i}':f'R{i}' for i in range(8)}
    with patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile):
        stage_reviewed_suite(db, frozen, digest, '0', mapping, runs)
    db.close()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO ac3_attempt_scopes VALUES ('S', :sha, 'unknown')"), {'sha':digest})
        conn.execute(text("INSERT INTO ac3_attempt_receipts (request_key, scope_id, contract_sha256, test_id, status) VALUES ('request-1', 'S', :contract, 'H0-Q0', 'dispatched')"), {'contract':'b'*64})
    yield engine, frozen, digest
    engine.dispose()


def settle(prepared):
    engine, frozen, digest = prepared
    with patch('app.services.ac3_atomic_settlement.compile_mock', side_effect=fake_compile):
        return settle_and_save(engine, frozen_path=frozen, frozen_sha256=digest, reservation='0', scope='S', request_key='request-1', contract_sha256='b'*64, frozen_test_id='H0-Q0', run_id='R0', response='synthetic answer', reported_cost_usd='0.001')


def snapshot(engine):
    with Session(engine) as db:
        return (db.scalar(select(__import__('sqlalchemy').func.count()).select_from(TargetResponseModel)),
                db.execute(text("SELECT status FROM ac3_attempt_scopes WHERE scope_id='S'")).scalar_one(),
                db.execute(text("SELECT status FROM ac3_attempt_receipts WHERE request_key='request-1'")).scalar_one())


def test_postgres_atomic_rollback_then_retry(prepared):
    engine = prepared[0]
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('UPDATE ac3_attempt_receipts SET status'):
            raise RuntimeError('synthetic failure')
    event.listen(engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='synthetic'):
            settle(prepared)
    finally:
        event.remove(engine, 'before_cursor_execute', fail)
    assert snapshot(engine) == (0, 'unknown', 'dispatched')
    assert not settle(prepared)['duplicate']
    assert settle(prepared)['duplicate']
    assert snapshot(engine) == (1, 'active', 'settled')


def test_postgres_concurrent_settlement_never_duplicates(prepared):
    def run(_):
        try: return settle(prepared)['state']
        except Exception as exc: return getattr(getattr(exc, 'orig', None), 'sqlstate', type(exc).__name__)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert 'settled' in results
    assert all(result in ('settled', '40001') for result in results), results
    assert snapshot(prepared[0]) == (1, 'active', 'settled')
    assert settle(prepared)['duplicate']
