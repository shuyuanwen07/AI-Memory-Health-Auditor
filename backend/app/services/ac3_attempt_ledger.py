"""PostgreSQL durable attempt records for a future controlled AC3 adapter.

This primitive never calls providers and does not authorize an execution. The
schema is a manually reviewed draft outside Alembic, and no API uses it.
Callers must bind actual dispatch and reviewed frozen inputs under appropriate
locks. A missing/unverified cost or uncertain outcome blocks the whole scope;
there is intentionally no automated resolution or resending of uncertain calls.
"""
import re
from decimal import Decimal, InvalidOperation
from sqlalchemy import inspect, text

_HASH = re.compile(r'^[0-9a-f]{64}$')


def _id(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError('Invalid ledger identity')
    return value


def _digest(value):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError('Invalid digest')
    return value


class AttemptLedger:
    def __init__(self, engine):
        if engine.dialect.name != 'postgresql':
            raise ValueError('Attempt ledger requires PostgreSQL')
        self.engine = engine

    def register_reviewed_scope(self, scope, frozen_path, frozen_sha, mock_reservation):
        """Bind a ledger scope to a reviewed frozen package; never authorizes dispatch."""
        from scripts.ac3_fixed_suite_adapter import compile_mock
        _id(scope, 64); _digest(frozen_sha)
        result = compile_mock(frozen_path, frozen_sha, mock_reservation)
        if result.get('frozen_sha256') != frozen_sha or result.get('model_called') is not False:
            raise ValueError('Frozen verification failed')
        with self.engine.begin() as conn:
            current = conn.execute(text('SELECT frozen_sha256 FROM ac3_attempt_scopes WHERE scope_id = :scope FOR UPDATE'), {'scope': scope}).mappings().first()
            if current:
                if current['frozen_sha256'] != frozen_sha:
                    raise ValueError('Scope already bound to a different frozen suite')
                return {'state': 'already_registered', 'execution_authorized': False}
            conn.execute(text("INSERT INTO ac3_attempt_scopes (scope_id, frozen_sha256, status) VALUES (:scope, :sha, 'active')"), {'scope': scope, 'sha': frozen_sha})
        return {'state': 'registered', 'execution_authorized': False}

    def begin(self, scope, frozen_sha, request_key, contract_sha, test_id):
        _id(scope, 64); _digest(frozen_sha); _id(request_key, 120); _digest(contract_sha); _id(test_id, 120)
        budget_enabled = inspect(self.engine).has_table('ac3_budget_scopes')
        with self.engine.begin() as conn:
            row = conn.execute(text('SELECT frozen_sha256, status FROM ac3_attempt_scopes WHERE scope_id = :scope FOR UPDATE'), {'scope': scope}).mappings().first()
            if not row or row['frozen_sha256'] != frozen_sha:
                raise ValueError('Unknown scope or frozen suite')
            if budget_enabled and conn.execute(text('SELECT scope_id FROM ac3_budget_scopes WHERE scope_id=:scope'), {'scope':scope}).first():
                raise ValueError('Budgeted scope must dispatch through its cost reservation guard')
            previous = conn.execute(text('SELECT scope_id, contract_sha256, test_id, status, response_text, reported_cost_usd FROM ac3_attempt_receipts WHERE request_key = :key'), {'key': request_key}).mappings().first()
            if previous:
                if previous['scope_id'] != scope or previous['contract_sha256'] != contract_sha or previous['test_id'] != test_id:
                    raise ValueError('Attempt identity already bound to another request')
                if previous['status'] == 'settled':
                    return {'state': 'settled', 'duplicate': True, 'response': previous['response_text'], 'reported_cost_usd': previous['reported_cost_usd']}
                raise ValueError('Previous dispatch unresolved; no automatic retry')
            if row['status'] != 'active':
                raise ValueError('Scope has an unresolved attempt')
            # All attempts within a scope share this row lock. A crash after
            # this committed insert is conservatively treated as unresolved.
            conn.execute(text("INSERT INTO ac3_attempt_receipts (request_key, scope_id, contract_sha256, test_id, status) VALUES (:key, :scope, :contract, :test, 'dispatched')"), {'key': request_key, 'scope': scope, 'contract': contract_sha, 'test': test_id})
            conn.execute(text("UPDATE ac3_attempt_scopes SET status = 'unknown' WHERE scope_id = :scope"), {'scope': scope})
        return {'state': 'dispatched', 'duplicate': False}

    def settle(self, scope, frozen_sha, request_key, response, reported_cost_usd):
        _id(scope, 64); _digest(frozen_sha); _id(request_key, 120)
        if not isinstance(response, str) or not response.strip() or len(response) > 1_000_000:
            raise ValueError('Invalid response')
        if not isinstance(reported_cost_usd, str) or len(reported_cost_usd) > 64:
            raise ValueError('Provider-reported cost is missing or invalid; attempt remains unresolved')
        try:
            cost = Decimal(reported_cost_usd)
        except InvalidOperation as exc:
            raise ValueError('Invalid provider-reported cost') from exc
        if not cost.is_finite() or cost < 0 or cost > 1_000_000:
            raise ValueError('Invalid provider-reported cost')
        budget_enabled = inspect(self.engine).has_table('ac3_budget_reservations')
        with self.engine.begin() as conn:
            scope_row = conn.execute(text('SELECT frozen_sha256, status FROM ac3_attempt_scopes WHERE scope_id = :scope FOR UPDATE'), {'scope': scope}).mappings().first()
            row = conn.execute(text('SELECT scope_id, status FROM ac3_attempt_receipts WHERE request_key = :key FOR UPDATE'), {'key': request_key}).mappings().first()
            if budget_enabled and conn.execute(text('SELECT request_key FROM ac3_budget_reservations WHERE request_key=:key'), {'key':request_key}).first():
                raise ValueError('Budgeted response must use atomic response and cost settlement')
            if not scope_row or scope_row['frozen_sha256'] != frozen_sha or not row or row['scope_id'] != scope or row['status'] != 'dispatched' or scope_row['status'] != 'unknown':
                raise ValueError('Attempt is not awaiting settlement')
            conn.execute(text("UPDATE ac3_attempt_receipts SET status = 'settled', response_text = :response, reported_cost_usd = :cost WHERE request_key = :key"), {'response': response, 'cost': str(cost), 'key': request_key})
            conn.execute(text("UPDATE ac3_attempt_scopes SET status = 'active' WHERE scope_id = :scope"), {'scope': scope})
        return {'state': 'settled', 'reported_cost_usd': str(cost), 'cost_source': 'provider_report_unreconciled'}

    def export_settled(self, scope, frozen_path, frozen_sha, mock_reservation, output_path):
        """Export only complete receipts tied to a verified frozen question set.

        The export does not establish provider authenticity or independent
        billing, and cannot replace a completed blind human review.
        """
        from scripts.ac3_fixed_suite_adapter import compile_mock
        from scripts.ac3_rehearsal_workflow import _write_new_json
        _id(scope, 64); _digest(frozen_sha)
        plan = compile_mock(frozen_path, frozen_sha, mock_reservation)
        eligible = {item['test_id'] for item in plan['items'] if item['grounding_review'] == 'valid'}
        if not eligible or len(eligible) != plan['eligible_question_count']:
            raise ValueError('Invalid eligible frozen question set')
        with self.engine.begin() as conn:
            scoped = conn.execute(text('SELECT frozen_sha256, status FROM ac3_attempt_scopes WHERE scope_id = :scope FOR UPDATE'), {'scope': scope}).mappings().first()
            if not scoped or scoped['frozen_sha256'] != frozen_sha or scoped['status'] != 'active':
                raise ValueError('Scope is unknown, unfrozen or has unresolved attempts')
            rows = conn.execute(text('SELECT test_id, request_key, contract_sha256, status, response_text, reported_cost_usd, created_at FROM ac3_attempt_receipts WHERE scope_id = :scope ORDER BY test_id'), {'scope': scope}).mappings().all()
            if len(rows) != len(eligible) or {row['test_id'] for row in rows} != eligible or any(row['status'] != 'settled' or not row['response_text'] or row['reported_cost_usd'] is None for row in rows):
                raise ValueError('Not every eligible question has one settled response and reported cost')
            # Detect a frozen source changing during receipt collection.
            if compile_mock(frozen_path, frozen_sha, mock_reservation)['frozen_sha256'] != frozen_sha:
                raise ValueError('Frozen suite changed during export')
            data = {'format': 'ac3-settled-receipts-v1', 'frozen_sha256': frozen_sha,
                    'scope_id': scope, 'receipt_count': len(rows), 'human_outcome_reviewed': False,
                    'reported_cost_status': 'provider_report_unreconciled',
                    'responses': [{**{key: row[key] for key in ('test_id', 'request_key', 'contract_sha256', 'response_text', 'reported_cost_usd')},
                                   'dispatched_at_utc': row['created_at'].isoformat()} for row in rows]}
            digest = _write_new_json(output_path, data)
        return {'output_sha256': digest, 'receipt_count': len(rows), 'human_outcome_reviewed': False}
