-- MANUAL DRAFT ONLY. Not in Alembic's automatically applied versions.
-- Apply only after review and an explicit migration decision.
CREATE TABLE ac3_attempt_scopes (
    scope_id VARCHAR(64) PRIMARY KEY,
    frozen_sha256 VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL CHECK (status IN ('active', 'unknown'))
);
CREATE TABLE ac3_attempt_receipts (
    request_key VARCHAR(120) PRIMARY KEY,
    scope_id VARCHAR(64) NOT NULL REFERENCES ac3_attempt_scopes(scope_id) ON DELETE RESTRICT,
    contract_sha256 VARCHAR(64) NOT NULL,
    test_id VARCHAR(120) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('dispatched', 'settled', 'unknown')),
    response_text TEXT,
    reported_cost_usd VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (scope_id, test_id)
);
