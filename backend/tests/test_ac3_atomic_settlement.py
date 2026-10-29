"""Synthetic atomic settlement tests: no model calls or human labels."""
from unittest.mock import patch
import pytest
from sqlalchemy import event, select, text
from app.models import TargetResponseModel
from app.services.ac3_atomic_settlement import settle_and_save
from test_ac3_database_mapping import fake_compile, saved_histories as saved_histories
from test_ac3_locked_resume import staged as staged


@pytest.fixture
def ready(staged):
    db, frozen, digest, mapping, runs = staged
    db.execute(text('ALTER TABLE ac3_attempt_receipts ADD COLUMN request_key TEXT'))
    db.execute(text('ALTER TABLE ac3_attempt_receipts ADD COLUMN contract_sha256 TEXT'))
    db.execute(text("UPDATE ac3_attempt_scopes SET status = 'unknown'"))
    db.execute(text("INSERT INTO ac3_attempt_receipts VALUES ('S','H0-Q0','dispatched',NULL,NULL,'request-1',:contract)"), {'contract':'b'*64})
    db.commit()
    return staged


def settle(ready, **overrides):
    db, frozen, digest, _, _ = ready
    args = dict(frozen_path=frozen, frozen_sha256=digest, reservation='0', scope='S', request_key='request-1',
                contract_sha256='b'*64, frozen_test_id='H0-Q0', run_id='R0', response='synthetic answer', reported_cost_usd='0.001')
    args.update(overrides)
    with patch('app.services.ac3_atomic_settlement.compile_mock', side_effect=fake_compile):
        return settle_and_save(db.get_bind(), **args)


def test_settlement_saves_once_and_retry_recovers(ready):
    result = settle(ready)
    assert result['state'] == 'settled' and result['duplicate'] is False
    assert settle(ready)['duplicate'] is True
    db = ready[0]; db.expire_all()
    assert len(list(db.scalars(select(TargetResponseModel)))) == 1
    assert db.execute(text("SELECT status FROM ac3_attempt_scopes WHERE scope_id='S'" )).scalar_one() == 'active'
    assert db.execute(text("SELECT status FROM ac3_attempt_receipts WHERE request_key='request-1'" )).scalar_one() == 'settled'


def test_failure_between_insert_and_settlement_rolls_back_both(ready):
    db = ready[0]; engine = db.get_bind()
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('UPDATE ac3_attempt_receipts SET status'):
            raise RuntimeError('simulated transaction failure')
    event.listen(engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='simulated'):
            settle(ready)
    finally:
        event.remove(engine, 'before_cursor_execute', fail)
    db.expire_all()
    assert len(list(db.scalars(select(TargetResponseModel)))) == 0
    assert db.execute(text("SELECT status FROM ac3_attempt_scopes WHERE scope_id='S'" )).scalar_one() == 'unknown'
    assert db.execute(text("SELECT status FROM ac3_attempt_receipts WHERE request_key='request-1'" )).scalar_one() == 'dispatched'
    db.rollback()
    assert settle(ready)['duplicate'] is False
    assert settle(ready)['duplicate'] is True


def test_bad_contract_and_changed_retry_blocked(ready):
    with pytest.raises(ValueError, match='identity'):
        settle(ready, contract_sha256='c'*64)
    settle(ready)
    with pytest.raises(ValueError, match='differs'):
        settle(ready, response='another answer')
