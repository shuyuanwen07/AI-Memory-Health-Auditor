-- Research-only draft. Never applied by the application automatically.
CREATE TABLE ac3_paired_budget_scopes (
  scope_id VARCHAR(64) PRIMARY KEY,
  frozen_sha256 VARCHAR(64) NOT NULL UNIQUE,
  budget_sha256 VARCHAR(64) NOT NULL,
  max_usd VARCHAR(64) NOT NULL,
  prior_upper_usd VARCHAR(64) NOT NULL,
  target_reserve_usd VARCHAR(64) NOT NULL,
  scorer_reserve_usd VARCHAR(64) NOT NULL,
  spent_usd VARCHAR(64) NOT NULL,
  status VARCHAR(20) NOT NULL CHECK (status IN ('active', 'unknown', 'overrun'))
);
CREATE TABLE ac3_paired_budget_receipts (
  request_key VARCHAR(120) PRIMARY KEY,
  scope_id VARCHAR(64) NOT NULL REFERENCES ac3_paired_budget_scopes(scope_id),
  test_id VARCHAR(120) NOT NULL,
  role VARCHAR(20) NOT NULL CHECK (role IN ('target', 'scorer')),
  contract_sha256 VARCHAR(64) NOT NULL,
  target_answer_sha256 VARCHAR(64),
  request_evidence_json TEXT,
  request_evidence_sha256 VARCHAR(64),
  reserved_usd VARCHAR(64) NOT NULL,
  status VARCHAR(20) NOT NULL CHECK (status IN ('dispatched', 'pending', 'settled', 'overrun')),
  response_text TEXT,
  response_metadata_json TEXT,
  reported_cost_usd VARCHAR(64),
  UNIQUE (scope_id, test_id, role)
);
