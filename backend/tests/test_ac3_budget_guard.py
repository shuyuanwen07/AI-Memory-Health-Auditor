"""Durable cost reservation tests; no real billing or model call."""
from unittest.mock import patch
import pytest
from sqlalchemy import event, text
from app.services.ac3_budget_guard import BudgetedDispatchLedger
from app.services.ac3_atomic_settlement import settle_and_save
from test_ac3_locked_resume import staged
from test_ac3_database_mapping import saved_histories, fake_compile


def fake_budget_compile(path, digest, reservation, snapshot=None):
    result = fake_compile(path, digest, reservation, snapshot)
    result['max_new_estimated_usd'] = '0.003'
    return result


@pytest.fixture
def prepared(staged):
    db, path, digest, mapping, runs = staged
    db.execute(text('ALTER TABLE ac3_attempt_receipts ADD COLUMN request_key TEXT'))
    db.execute(text('ALTER TABLE ac3_attempt_receipts ADD COLUMN contract_sha256 TEXT'))
    db.execute(text('CREATE TABLE ac3_budget_scopes (scope_id TEXT PRIMARY KEY, max_new_usd TEXT, reservation_usd TEXT, spent_usd TEXT, status TEXT)'))
    db.execute(text('CREATE TABLE ac3_budget_reservations (request_key TEXT PRIMARY KEY, scope_id TEXT, reserved_usd TEXT, status TEXT)'))
    db.execute(text('CREATE TABLE ac3_request_evidence (request_key TEXT PRIMARY KEY, evidence_json TEXT, evidence_sha256 TEXT, response_metadata_json TEXT)'))
    db.commit()
    guard = BudgetedDispatchLedger(db.get_bind(), path, digest, '0.002')
    with patch('app.services.ac3_budget_guard.compile_mock', side_effect=fake_budget_compile):
        assert guard.register('S')['state'] == 'registered'
    return staged, guard


def dispatch(prepared, key='req-1', test='H0-Q0'):
    staged_data, guard = prepared
    with patch('app.services.ac3_budget_guard.compile_mock', side_effect=fake_budget_compile):
        return guard.begin('S', staged_data[2], key, 'b'*64, test)


def settle(prepared, amount='0.001', response='synthetic'):
    staged_data, _ = prepared
    db, path, digest, _, _ = staged_data
    with patch('app.services.ac3_atomic_settlement.compile_mock', side_effect=fake_budget_compile):
        return settle_and_save(db.get_bind(), frozen_path=path, frozen_sha256=digest, reservation='0.002', scope='S',
            request_key='req-1', contract_sha256='b'*64, frozen_test_id='H0-Q0', run_id='R0',
            response=response, reported_cost_usd=amount, budgeted=True)


def test_reserve_settle_recover_and_budget_exhaustion(prepared):
    assert dispatch(prepared)['state'] == 'dispatched'
    with pytest.raises(ValueError, match='Unresolved'):
        dispatch(prepared, 'req-2', 'H0-Q1')
    assert settle(prepared)['state'] == 'settled'
    assert settle(prepared)['duplicate'] is True
    assert dispatch(prepared, 'req-2', 'H0-Q1')['state'] == 'dispatched'


def test_cost_overrun_saves_evidence_and_blocks_future_dispatch(prepared):
    dispatch(prepared)
    assert settle(prepared, '0.0025')['state'] == 'budget_overrun'
    db = prepared[0][0]; db.expire_all()
    assert db.execute(text("SELECT status FROM ac3_budget_scopes WHERE scope_id='S'")).scalar_one() == 'overrun'
    assert db.execute(text("SELECT response_text FROM ac3_attempt_receipts WHERE request_key='req-1'")).scalar_one() == 'synthetic'
    with pytest.raises(ValueError, match='Unresolved'):
        dispatch(prepared, 'req-2', 'H0-Q1')


def test_remaining_budget_blocks_the_next_reservation(prepared):
    dispatch(prepared)
    assert settle(prepared, '0.0011')['state'] == 'settled'
    with pytest.raises(ValueError, match='Remaining budget'):
        dispatch(prepared, 'req-2', 'H0-Q1')


def test_wrong_or_missing_reservation_does_not_settle(prepared):
    dispatch(prepared)
    db = prepared[0][0]
    db.execute(text("UPDATE ac3_budget_reservations SET reserved_usd='0.001'")); db.commit()
    with pytest.raises(ValueError, match='Budget differs'):
        settle(prepared)
    assert db.execute(text("SELECT status FROM ac3_attempt_receipts WHERE request_key='req-1'")).scalar_one() == 'dispatched'


def test_budgeted_receipt_rejects_unbudgeted_settlement(prepared):
    dispatch(prepared)
    (db, path, digest, _, _), _guard = prepared
    with patch('app.services.ac3_atomic_settlement.compile_mock', side_effect=fake_budget_compile):
        with pytest.raises(ValueError, match='budget-aware'):
            settle_and_save(db.get_bind(), frozen_path=path, frozen_sha256=digest, reservation='0.002', scope='S',
                request_key='req-1', contract_sha256='b'*64, frozen_test_id='H0-Q0', run_id='R0',
                response='synthetic', reported_cost_usd='0.001')


def test_budget_update_failure_rolls_back_answer_and_receipt(prepared):
    dispatch(prepared)
    db = prepared[0][0]; engine = db.get_bind()
    def fail(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith('UPDATE ac3_budget_scopes SET spent_usd'):
            raise RuntimeError('synthetic cost-ledger failure')
    event.listen(engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='cost-ledger'):
            settle(prepared)
    finally:
        event.remove(engine, 'before_cursor_execute', fail)
    db.expire_all()
    assert db.execute(text("SELECT status FROM ac3_attempt_receipts WHERE request_key='req-1'")).scalar_one() == 'dispatched'
    assert db.execute(text("SELECT status FROM ac3_budget_reservations WHERE request_key='req-1'")).scalar_one() == 'reserved'
    from app.models import TargetResponseModel
    assert not db.query(TargetResponseModel).count()
    db.rollback()
    assert settle(prepared)['state'] == 'settled'


def test_pending_answer_is_durable_before_settlement_and_immutable(prepared):
    dispatch(prepared)
    staged_data, guard = prepared
    digest = staged_data[2]
    assert not guard.record_pending_response('S', digest, 'req-1', 'synthetic', '0.001')['duplicate']
    assert guard.record_pending_response('S', digest, 'req-1', 'synthetic', '0.001')['duplicate']
    with pytest.raises(ValueError, match='differs'):
        guard.record_pending_response('S', digest, 'req-1', 'changed', '0.001')
    assert settle(prepared)['state'] == 'settled'


def test_missing_provider_cost_preserves_answer_but_does_not_settle(prepared):
    dispatch(prepared)
    staged_data, guard = prepared
    assert guard.record_pending_response('S', staged_data[2], 'req-1', 'synthetic', None)['cost_unknown']
    with pytest.raises(ValueError, match='unknown cost'):
        settle(prepared)
    with pytest.raises(ValueError, match='Unresolved'):
        dispatch(prepared, 'req-2', 'H0-Q1')


def test_private_evidence_and_metadata_survive_atomic_settlement(prepared):
    (db, path, digest, _, _), _guard = prepared
    evidence = {'format':'ac3-private-request-evidence-v1', 'frozen_test_id':'H0-Q0', 'run_id':'R0',
                'retrieval_id':'RET1', 'selected_memory_ids':['TM1'], 'target_memory_context':['synthetic private memory']}
    guard = BudgetedDispatchLedger(db.get_bind(), path, digest, '0.002', request_evidence=evidence)
    with patch('app.services.ac3_budget_guard.compile_mock', side_effect=fake_budget_compile):
        guard.begin('S', digest, 'req-1', 'b'*64, 'H0-Q0')
    metadata = {'request_contract_sha256':'b'*64, 'reported_cost_usd':'0.001'}
    guard.record_pending_response('S', digest, 'req-1', 'synthetic', '0.001', response_metadata=metadata)
    assert settle(prepared)['state'] == 'settled'
    from app.models import TargetResponseModel
    saved = db.query(TargetResponseModel).one()
    assert saved.execution_metadata['request_contract_sha256'] == 'b'*64
    assert saved.execution_metadata['ac3_request_evidence_sha256']


def test_wrong_metadata_preserves_answer_and_prevents_settlement(prepared):
    (db, path, digest, _, _), _guard = prepared
    evidence = {'format':'ac3-private-request-evidence-v1', 'frozen_test_id':'H0-Q0', 'run_id':'R0',
                'retrieval_id':'RET1', 'selected_memory_ids':['TM1'], 'target_memory_context':['synthetic private memory']}
    guard = BudgetedDispatchLedger(db.get_bind(), path, digest, '0.002', request_evidence=evidence)
    with patch('app.services.ac3_budget_guard.compile_mock', side_effect=fake_budget_compile):
        guard.begin('S', digest, 'req-1', 'b'*64, 'H0-Q0')
    pending = guard.record_pending_response('S', digest, 'req-1', 'synthetic', '0.001', response_metadata={'request_contract_sha256':'c'*64})
    assert not pending['metadata_verified']
    assert db.execute(text("SELECT response_text FROM ac3_attempt_receipts WHERE request_key='req-1'")).scalar_one() == 'synthetic'
    db.rollback()
    with pytest.raises(ValueError, match='metadata'):
        settle(prepared)
