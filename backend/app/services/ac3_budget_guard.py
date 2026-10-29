"""Durable cost reservations for the AC3 connector.

A reservation is a declared per-request cost assumption, not a provider hard
limit. The caller must independently bound the provider request, price and
output length; a changed price or an unknown outcome stops further dispatch.
This module does not authorize or initiate a model call.
"""
from decimal import Decimal, InvalidOperation
import hashlib
import json
from sqlalchemy import text
from scripts.ac3_fixed_suite_adapter import compile_mock
from app.services.ac3_attempt_ledger import _digest, _id


def money(value, *, positive=False):
    try:
        if isinstance(value, bool): raise ValueError
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Invalid monetary value') from exc
    if not amount.is_finite() or amount < 0 or amount > 1000000 or (positive and amount == 0):
        raise ValueError('Invalid monetary value')
    return amount


class BudgetedDispatchLedger:
    """An AC3RequestBinding ledger with durable, serialized reservations."""
    def __init__(self, engine, frozen_path, frozen_sha256, reservation, *, request_evidence=None):
        url = engine.url
        if url.get_backend_name() != 'postgresql' and not (url.get_backend_name() == 'sqlite' and url.database in (None, ':memory:')):
            raise ValueError('PostgreSQL or isolated in-memory SQLite required')
        self.engine, self.frozen_path, self.frozen_sha256 = engine, frozen_path, frozen_sha256
        self.reservation = money(reservation, positive=True)
        self.request_evidence = None
        if request_evidence is not None:
            if (not isinstance(request_evidence, dict) or set(request_evidence) != {'format','frozen_test_id','run_id','retrieval_id','selected_memory_ids','target_memory_context'} or
                request_evidence.get('format') != 'ac3-private-request-evidence-v1' or
                any(not isinstance(request_evidence.get(k), str) or not request_evidence[k].strip() for k in ('frozen_test_id','run_id','retrieval_id')) or
                any(not isinstance(request_evidence.get(k), list) or any(not isinstance(x, str) for x in request_evidence[k]) for k in ('selected_memory_ids','target_memory_context')) or
                len(request_evidence['selected_memory_ids']) != len(request_evidence['target_memory_context'])):
                raise ValueError('Invalid private request evidence')
            self.request_evidence = json.dumps(request_evidence, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            if len(self.request_evidence.encode()) > 1_000_000:
                raise ValueError('Private request evidence is too large')

    def _compile_plan(self, frozen_sha):
        """Keep legacy frozen-suite verification as the default."""
        return compile_mock(self.frozen_path, frozen_sha, str(self.reservation))

    def register(self, scope):
        _id(scope, 64); _digest(self.frozen_sha256)
        plan = self._compile_plan(self.frozen_sha256)
        limit = money(plan['max_new_estimated_usd'], positive=True)
        eligible = {item['test_id'] for item in plan['items'] if item['grounding_review'] == 'valid'}
        if not eligible or self.reservation > limit:
            raise ValueError('Frozen plan has no eligible budgeted request')
        suffix = ' FOR UPDATE' if self.engine.dialect.name == 'postgresql' else ''
        with self.engine.begin() as conn:
            scoped = conn.execute(text('SELECT frozen_sha256,status FROM ac3_attempt_scopes WHERE scope_id=:scope' + suffix), {'scope':scope}).mappings().first()
            if not scoped or scoped['frozen_sha256'] != self.frozen_sha256 or scoped['status'] != 'active':
                raise ValueError('Scope is not active or bound to this frozen plan')
            existing = conn.execute(text('SELECT max_new_usd,reservation_usd FROM ac3_budget_scopes WHERE scope_id=:scope' + suffix), {'scope':scope}).mappings().first()
            if existing:
                if money(existing['max_new_usd']) != limit or money(existing['reservation_usd']) != self.reservation:
                    raise ValueError('Budget already bound to different assumptions')
                return {'state':'already_registered', 'limit_usd':str(limit)}
            if conn.execute(text('SELECT request_key FROM ac3_attempt_receipts WHERE scope_id=:scope LIMIT 1'), {'scope':scope}).first():
                raise ValueError('Budget cannot be added after dispatch')
            conn.execute(text('INSERT INTO ac3_budget_scopes (scope_id,max_new_usd,reservation_usd,spent_usd,status) VALUES (:scope,:limit,:reserve,:spent,:status)'),
                         {'scope':scope,'limit':str(limit),'reserve':str(self.reservation),'spent':'0','status':'active'})
        return {'state':'registered','limit_usd':str(limit),'cost_assumption_only':True}

    def begin(self, scope, frozen_sha, request_key, contract_sha, test_id):
        _id(scope,64); _id(request_key,120); _id(test_id,120); _digest(frozen_sha); _digest(contract_sha)
        if frozen_sha != self.frozen_sha256: raise ValueError('Frozen suite mismatch')
        if self.request_evidence is not None and json.loads(self.request_evidence)['frozen_test_id'] != test_id:
            raise ValueError('Private evidence is bound to another question')
        plan = self._compile_plan(frozen_sha)
        if test_id not in {item['test_id'] for item in plan['items'] if item['grounding_review'] == 'valid'}:
            raise ValueError('Test is not in frozen reviewed suite')
        limit = money(plan['max_new_estimated_usd'], positive=True)
        suffix = ' FOR UPDATE' if self.engine.dialect.name == 'postgresql' else ''
        with self.engine.begin() as conn:
            scope_row = conn.execute(text('SELECT frozen_sha256,status FROM ac3_attempt_scopes WHERE scope_id=:scope' + suffix), {'scope':scope}).mappings().first()
            budget = conn.execute(text('SELECT max_new_usd,reservation_usd,spent_usd,status FROM ac3_budget_scopes WHERE scope_id=:scope' + suffix), {'scope':scope}).mappings().first()
            if not scope_row or scope_row['frozen_sha256'] != frozen_sha or scope_row['status'] != 'active' or not budget or budget['status'] != 'active':
                raise ValueError('Unresolved scope or unregistered budget')
            spent, bound = money(budget['spent_usd']), money(budget['reservation_usd'], positive=True)
            if money(budget['max_new_usd']) != limit or bound != self.reservation:
                raise ValueError('Budget assumptions differ from frozen plan')
            if spent + bound > limit:
                raise ValueError('Remaining budget is below the request reservation')
            if conn.execute(text('SELECT request_key FROM ac3_attempt_receipts WHERE request_key=:key OR (scope_id=:scope AND test_id=:test)'), {'key':request_key,'scope':scope,'test':test_id}).first():
                raise ValueError('Request or question already dispatched; do not resend')
            conn.execute(text("INSERT INTO ac3_attempt_receipts (request_key,scope_id,contract_sha256,test_id,status) VALUES (:key,:scope,:contract,:test,'dispatched')"), {'key':request_key,'scope':scope,'contract':contract_sha,'test':test_id})
            conn.execute(text("INSERT INTO ac3_budget_reservations (request_key,scope_id,reserved_usd,status) VALUES (:key,:scope,:reserved,'reserved')"), {'key':request_key,'scope':scope,'reserved':str(bound)})
            if self.request_evidence is not None:
                conn.execute(text('INSERT INTO ac3_request_evidence (request_key,evidence_json,evidence_sha256) VALUES (:key,:evidence,:sha)'), {'key':request_key,'evidence':self.request_evidence,'sha':hashlib.sha256(self.request_evidence.encode()).hexdigest()})
            conn.execute(text("UPDATE ac3_attempt_scopes SET status='unknown' WHERE scope_id=:scope"), {'scope':scope})
        return {'state':'dispatched','duplicate':False, 'reserved_usd':str(bound), 'cost_assumption_only':True}

    def record_pending_response(self, scope, frozen_sha, request_key, response, reported_cost_usd, *, response_metadata=None):
        """Persist an obtained answer before releasing source locks or settling.

        This records evidence only. Missing cost is retained as unknown and
        blocks settlement and subsequent dispatch; it is not treated as zero.
        """
        _id(scope,64); _id(request_key,120); _digest(frozen_sha)
        if frozen_sha != self.frozen_sha256 or not isinstance(response, str) or not response.strip() or len(response) > 1_000_000:
            raise ValueError('Invalid response or frozen identity')
        try:
            cost = None if reported_cost_usd is None else str(money(reported_cost_usd))
        except ValueError:
            cost = None
        metadata = None
        if response_metadata is not None:
            if not isinstance(response_metadata, dict): raise ValueError('Invalid response metadata')
            metadata = json.dumps(response_metadata, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            if len(metadata.encode()) > 1_000_000: raise ValueError('Response metadata is too large')
        suffix = ' FOR UPDATE' if self.engine.dialect.name == 'postgresql' else ''
        with self.engine.begin() as conn:
            scoped = conn.execute(text('SELECT frozen_sha256,status FROM ac3_attempt_scopes WHERE scope_id=:scope' + suffix), {'scope':scope}).mappings().first()
            row = conn.execute(text('SELECT scope_id,status,contract_sha256,response_text,reported_cost_usd FROM ac3_attempt_receipts WHERE request_key=:key' + suffix), {'key':request_key}).mappings().first()
            reserved = conn.execute(text('SELECT scope_id,status FROM ac3_budget_reservations WHERE request_key=:key' + suffix), {'key':request_key}).mappings().first()
            if not scoped or scoped['frozen_sha256'] != frozen_sha or scoped['status'] != 'unknown' or not row or row['scope_id'] != scope or row['status'] != 'dispatched' or not reserved or reserved['scope_id'] != scope or reserved['status'] != 'reserved':
                raise ValueError('No unique pending budgeted dispatch')
            metadata_verified = True
            if self.request_evidence is not None:
                evidence = conn.execute(text('SELECT evidence_json,evidence_sha256,response_metadata_json FROM ac3_request_evidence WHERE request_key=:key' + suffix), {'key':request_key}).mappings().first()
                metadata_verified = bool(evidence and evidence['evidence_json'] == self.request_evidence and
                    evidence['evidence_sha256'] == hashlib.sha256(self.request_evidence.encode()).hexdigest() and
                    metadata is not None and response_metadata.get('request_contract_sha256') == row['contract_sha256'] and
                    (evidence['response_metadata_json'] is None or evidence['response_metadata_json'] == metadata))
            if row['response_text'] is not None:
                if row['response_text'] != response or row['reported_cost_usd'] != cost:
                    raise ValueError('Pending provider evidence differs from saved result')
                return {'state':'pending_settlement', 'duplicate':True, 'cost_unknown':cost is None, 'metadata_verified':metadata_verified}
            conn.execute(text('UPDATE ac3_attempt_receipts SET response_text=:response,reported_cost_usd=:cost WHERE request_key=:key'), {'response':response,'cost':cost,'key':request_key})
            if self.request_evidence is not None and evidence:
                conn.execute(text('UPDATE ac3_request_evidence SET response_metadata_json=:metadata WHERE request_key=:key'), {'metadata':metadata,'key':request_key})
        return {'state':'pending_settlement', 'duplicate':False, 'cost_unknown':cost is None, 'metadata_verified':metadata_verified}
