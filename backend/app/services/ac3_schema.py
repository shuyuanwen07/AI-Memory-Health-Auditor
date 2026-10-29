"""Install the dedicated AC3 research ledger from the frozen reviewed schema.

This only creates new AC3 tables. Existing or partially present unmanaged
schemas are never modified. No provider request or user data is touched.
"""
import hashlib
from pathlib import Path
from sqlalchemy import inspect, text

_MIGRATIONS = ('ac3_attempt_ledger.sql','ac3_budget_guard.sql')
_EXPECTED = {
    'ac3_attempt_scopes': {'scope_id','frozen_sha256','status'},
    'ac3_attempt_receipts': {'request_key','scope_id','contract_sha256','test_id','status','response_text','reported_cost_usd','created_at'},
    'ac3_budget_scopes': {'scope_id','max_new_usd','reservation_usd','spent_usd','status'},
    'ac3_budget_reservations': {'request_key','scope_id','reserved_usd','status'},
    'ac3_request_evidence': {'request_key','evidence_json','evidence_sha256','response_metadata_json'},
    'ac3_schema_installation': {'singleton','schema_sha256'},
}


def _migration_bytes():
    folder = Path(__file__).resolve().parents[2] / 'research_migrations'
    return [(name, (folder / name).read_bytes()) for name in _MIGRATIONS]


def ac3_schema_migration_sha256():
    digest = hashlib.sha256()
    for name, content in _migration_bytes():
        digest.update(len(name.encode()).to_bytes(8,'big')); digest.update(name.encode())
        digest.update(len(content).to_bytes(8,'big')); digest.update(content)
    return digest.hexdigest()


def ensure_ac3_ledger_schema(engine, expected_sha256):
    if engine.dialect.name != 'postgresql': raise ValueError('AC3 ledger installation requires PostgreSQL')
    actual = ac3_schema_migration_sha256()
    if not isinstance(expected_sha256, str) or expected_sha256 != actual:
        raise ValueError('Ledger schema differs from the frozen protocol')
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('memory-auditor-ac3-schema-v1'))"))
        names = set(inspect(conn).get_table_names())
        present = set(_EXPECTED) & names
        if present and present != set(_EXPECTED):
            raise ValueError('A partial or unmanaged AC3 ledger exists; no schema was changed')
        if not present:
            for _name, content in _migration_bytes():
                for statement in content.decode('utf-8').split(';'):
                    if statement.strip(): conn.execute(text(statement))
            conn.execute(text('CREATE TABLE ac3_schema_installation (singleton BOOLEAN PRIMARY KEY CHECK (singleton), schema_sha256 VARCHAR(64) NOT NULL)'))
            conn.execute(text('INSERT INTO ac3_schema_installation (singleton,schema_sha256) VALUES (true,:sha)'), {'sha':actual})
        marker = conn.execute(text('SELECT schema_sha256 FROM ac3_schema_installation WHERE singleton = true')).scalar_one_or_none()
        if marker != actual:
            raise ValueError('Existing AC3 ledger was installed with a different schema')
        inspector = inspect(conn)
        for name, expected in _EXPECTED.items():
            if {column['name'] for column in inspector.get_columns(name)} != expected:
                raise ValueError('Existing AC3 ledger columns differ from reviewed schema')
    return {'status':'verified','schema_sha256':actual,'provider_called':False}
