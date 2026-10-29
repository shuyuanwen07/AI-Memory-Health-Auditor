-- Manual draft. Do not apply automatically to the application's database.
-- Reservation amounts are cost assumptions, not provider-enforced caps.
CREATE TABLE ac3_budget_scopes (
    scope_id VARCHAR(64) PRIMARY KEY REFERENCES ac3_attempt_scopes(scope_id) ON DELETE RESTRICT,
    max_new_usd VARCHAR(64) NOT NULL,
    reservation_usd VARCHAR(64) NOT NULL,
    spent_usd VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('active', 'overrun'))
);
CREATE TABLE ac3_budget_reservations (
    request_key VARCHAR(120) PRIMARY KEY REFERENCES ac3_attempt_receipts(request_key) ON DELETE RESTRICT,
    scope_id VARCHAR(64) NOT NULL REFERENCES ac3_budget_scopes(scope_id) ON DELETE RESTRICT,
    reserved_usd VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('reserved', 'settled', 'overrun'))
);
CREATE TABLE ac3_request_evidence (
    request_key VARCHAR(120) PRIMARY KEY REFERENCES ac3_attempt_receipts(request_key) ON DELETE RESTRICT,
    evidence_json TEXT NOT NULL,
    evidence_sha256 VARCHAR(64) NOT NULL,
    response_metadata_json TEXT
);
