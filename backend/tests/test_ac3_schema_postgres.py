"""Create/check the dedicated schema only in a disposable PostgreSQL."""
import pytest
from sqlalchemy import inspect, text
from app.services.ac3_schema import ac3_schema_migration_sha256, ensure_ac3_ledger_schema
from test_ac3_atomic_settlement_postgres import prepared as prepared, pytestmark as pytestmark


def test_install_is_idempotent_and_rejects_digest_drift(prepared):
    engine, _, _ = prepared
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE ac3_attempt_receipts'))
        conn.execute(text('DROP TABLE ac3_attempt_scopes'))
    digest=ac3_schema_migration_sha256()
    assert ensure_ac3_ledger_schema(engine,digest)['status']=='verified'
    assert ensure_ac3_ledger_schema(engine,digest)['status']=='verified'
    with pytest.raises(ValueError, match='differs'):
        ensure_ac3_ledger_schema(engine,'a'*64)
    assert 'ac3_request_evidence' in inspect(engine).get_table_names()
