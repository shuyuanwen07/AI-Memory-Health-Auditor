"""Explicitly isolated PostgreSQL tests; never connect to production database."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import text
from app.services.ac3_budget_guard import BudgetedDispatchLedger
from test_ac3_atomic_settlement_postgres import prepared, pytestmark
from test_ac3_budget_guard import fake_budget_compile


def test_postgres_serialized_budget_reservation(prepared):
    engine, frozen, digest = prepared
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM ac3_attempt_receipts'))
        conn.execute(text("UPDATE ac3_attempt_scopes SET status='active' WHERE scope_id='S'"))
        for statement in Path('/app/research_migrations/ac3_budget_guard.sql').read_text().split(';'):
            if statement.strip(): conn.execute(text(statement))
    guard = BudgetedDispatchLedger(engine, frozen, digest, '0.002')
    with patch('app.services.ac3_budget_guard.compile_mock', side_effect=fake_budget_compile):
        guard.register('S')
        def dispatch(n):
            try:
                return guard.begin('S', digest, f'req-{n}', 'b'*64, f'H0-Q{n}')['state']
            except Exception:
                return 'blocked'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(dispatch, (0,1)))
    assert sorted(results) == ['blocked','dispatched']
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM ac3_attempt_receipts')).scalar_one() == 1
        assert conn.execute(text('SELECT count(*) FROM ac3_budget_reservations')).scalar_one() == 1
        assert conn.execute(text("SELECT status FROM ac3_attempt_scopes WHERE scope_id='S'")).scalar_one() == 'unknown'


def test_handoff_commits_dispatch_and_pending_answer_without_deadlock(prepared):
    from sqlalchemy.orm import Session
    from app.services.ac3_atomic_settlement import settle_and_save
    from app.services.ac3_locked_preflight import ac3_sequence_locks, locked_ac3_preflight
    engine, frozen, digest = prepared
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM ac3_attempt_receipts'))
        conn.execute(text("UPDATE ac3_attempt_scopes SET status='active' WHERE scope_id='S'"))
        for statement in Path('/app/research_migrations/ac3_budget_guard.sql').read_text().split(';'):
            if statement.strip(): conn.execute(text(statement))
    guard = BudgetedDispatchLedger(engine, frozen, digest, '0.002')
    conversations = {f'H{i}':f'C{i}' for i in range(8)}
    runs = {f'H{i}':f'R{i}' for i in range(8)}
    with patch('app.services.ac3_budget_guard.compile_mock', side_effect=fake_budget_compile), \
         patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_budget_compile), \
         patch('app.services.ac3_atomic_settlement.compile_mock', side_effect=fake_budget_compile):
        guard.register('S')
        with Session(engine) as db:
            with ac3_sequence_locks(db, runs):
                with locked_ac3_preflight(db, frozen, digest, '0.002', conversations, runs,
                                          ledger_scope='S', ledger_write_handoff=True):
                    assert guard.begin('S', digest, 'req-1', 'b'*64, 'H0-Q0')['state'] == 'dispatched'
                    assert guard.record_pending_response('S', digest, 'req-1', 'synthetic answer', '0.001')['state'] == 'pending_settlement'
                result = settle_and_save(engine, frozen_path=frozen, frozen_sha256=digest, reservation='0.002', scope='S',
                    request_key='req-1', contract_sha256='b'*64, frozen_test_id='H0-Q0', run_id='R0',
                    response='synthetic answer', reported_cost_usd='0.001', budgeted=True)
                assert result['state'] == 'settled'
    with engine.connect() as conn:
        assert conn.execute(text("SELECT status FROM ac3_attempt_scopes WHERE scope_id='S'")).scalar_one() == 'active'
        assert conn.execute(text("SELECT status FROM ac3_budget_reservations WHERE request_key='req-1'")).scalar_one() == 'settled'
