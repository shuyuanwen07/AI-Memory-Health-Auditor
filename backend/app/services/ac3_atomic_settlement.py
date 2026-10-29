"""Atomically settle an AC3 receipt and save its target response; never dispatches.

The only supported non-PostgreSQL database is disposable in-memory SQLite for
isolated tests. Provider receipt authenticity and billing are not established.
The real connector remains fail-closed; no route exposes this function.
"""
from decimal import Decimal, InvalidOperation
import hashlib
import json
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
from app.models import AuditRunModel, TestCaseModel, TargetResponseModel
from app.services.formal_freeze import formal_input_signature
from scripts.ac3_fixed_suite_adapter import compile_mock, sha


def settle_and_save(engine, *, frozen_path, frozen_sha256, reservation, scope, request_key,
                    contract_sha256, frozen_test_id, run_id, response, reported_cost_usd, budgeted=False):
    for value in (scope, request_key, frozen_test_id, run_id):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('All identities are required')
    if not isinstance(response, str) or not response.strip() or len(response) > 1_000_000:
        raise ValueError('Invalid provider response')
    if not isinstance(reported_cost_usd, str) or len(reported_cost_usd) > 64:
        raise ValueError('Provider-reported cost is missing')
    try:
        cost = Decimal(reported_cost_usd)
    except InvalidOperation as exc:
        raise ValueError('Invalid provider-reported cost') from exc
    if not cost.is_finite() or cost < 0 or cost > 1_000_000:
        raise ValueError('Invalid provider-reported cost')
    url = engine.url
    dialect = url.get_backend_name()
    if dialect == 'postgresql':
        with engine.connect() as connection:
            if connection.get_isolation_level() != 'SERIALIZABLE':
                raise ValueError('Atomic settlement requires SERIALIZABLE PostgreSQL')
    elif dialect != 'sqlite' or url.database not in (None, ':memory:'):
        raise ValueError('Only SERIALIZABLE PostgreSQL or isolated SQLite is supported')
    # Revalidating the frozen package does not authenticate the provider output.
    plan = compile_mock(frozen_path, frozen_sha256, reservation)
    tests = [item for item in plan['items'] if item['grounding_review'] == 'valid' and item['test_id'] == frozen_test_id]
    if len(tests) != 1:
        raise ValueError('Unknown or duplicate frozen question')
    item, cfg = tests[0], plan['model_configuration']
    local_test_id = 'AC3' + sha(f'{frozen_sha256}|{run_id}|{frozen_test_id}'.encode())[:32].upper()
    response_id = 'ACR' + sha(f'{scope}|{request_key}'.encode())[:32].upper()
    suffix = ' FOR UPDATE' if dialect == 'postgresql' else ''
    budget_tables_exist = inspect(engine).has_table('ac3_budget_reservations')
    evidence_table_exists = inspect(engine).has_table('ac3_request_evidence')
    with Session(engine) as db, db.begin():
        audit = db.scalar(select(AuditRunModel).where(AuditRunModel.id == run_id).with_for_update())
        test = db.scalar(select(TestCaseModel).where(TestCaseModel.id == local_test_id).with_for_update())
        if not audit or audit.status != 'RESEARCH_STAGED' or not test or test.run_id != run_id:
            raise ValueError('Expected staged audit and test are missing')
        if any(getattr(audit, attr) != cfg[key] for attr, key in (
            ('provider','target_provider'), ('model','target_model'), ('evaluator_provider','evaluator_provider'),
            ('evaluator_model','evaluator_model'), ('pipeline_provider','pipeline_provider'),
            ('pipeline_model','pipeline_model'), ('memory_strategy','target_strategy'))):
            raise ValueError('Audit configuration differs from frozen protocol')
        metadata = (audit.reproducibility_metadata or {}).get('ac3_staged_suite') or {}
        if (metadata.get('frozen_sha256') != frozen_sha256 or metadata.get('history_id') != item['history_id'] or
            metadata.get('input_sha256') != formal_input_signature(db, audit) or test.prompt != item['question'] or
            test.expected_behavior != item['expected_behavior'] or test.dimension != item['dimension']):
            raise ValueError('Staged evidence differs from frozen question')
        scoped = db.execute(text('SELECT frozen_sha256, status FROM ac3_attempt_scopes WHERE scope_id = :scope' + suffix), {'scope':scope}).mappings().first()
        receipt = db.execute(text('SELECT scope_id, test_id, contract_sha256, status, response_text, reported_cost_usd FROM ac3_attempt_receipts WHERE request_key = :key' + suffix), {'key':request_key}).mappings().first()
        if (not scoped or scoped['frozen_sha256'] != frozen_sha256 or not receipt or receipt['scope_id'] != scope or
            receipt['test_id'] != frozen_test_id or receipt['contract_sha256'] != contract_sha256):
            raise ValueError('Ledger identity does not match request')
        if not budgeted and budget_tables_exist and db.execute(text('SELECT request_key FROM ac3_budget_reservations WHERE request_key=:key'), {'key':request_key}).first():
            raise ValueError('Budgeted request requires budget-aware settlement')
        previous = list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.test_id == local_test_id).with_for_update()))
        if receipt['status'] == 'settled' and scoped['status'] == 'active':
            if (len(previous) != 1 or previous[0].id != response_id or previous[0].run_id != run_id or
                previous[0].response_text != response or previous[0].model != cfg['target_model'] or
                receipt['response_text'] != response or Decimal(receipt['reported_cost_usd']) != cost):
                raise ValueError('Existing settled response differs from request')
            if budgeted:
                from app.services.ac3_budget_guard import money
                saved_budget = db.execute(text('SELECT max_new_usd,reservation_usd,spent_usd,status FROM ac3_budget_scopes WHERE scope_id=:scope' + suffix), {'scope':scope}).mappings().first()
                saved_reservation = db.execute(text('SELECT scope_id,reserved_usd,status FROM ac3_budget_reservations WHERE request_key=:key' + suffix), {'key':request_key}).mappings().first()
                if (not saved_budget or saved_budget['status'] != 'active' or not saved_reservation or
                    saved_reservation['scope_id'] != scope or saved_reservation['status'] != 'settled' or
                    money(saved_budget['max_new_usd']) != money(plan['max_new_estimated_usd']) or
                    money(saved_budget['reservation_usd']) != money(reservation) or
                    money(saved_reservation['reserved_usd']) != money(reservation) or money(saved_budget['spent_usd']) < cost):
                    raise ValueError('Existing settled response has inconsistent budget record')
            if compile_mock(frozen_path, frozen_sha256, reservation)['frozen_sha256'] != frozen_sha256:
                raise ValueError('Frozen evidence changed during recovery')
            return {'state':'settled', 'duplicate':True, 'response_id':response_id, 'provider_called':False}
        if scoped['status'] != 'unknown' or receipt['status'] != 'dispatched' or previous:
            raise ValueError('Attempt is not uniquely awaiting settlement')
        if receipt['response_text'] is not None and (
                receipt['response_text'] != response or receipt['reported_cost_usd'] is None or
                Decimal(receipt['reported_cost_usd']) != cost):
            raise ValueError('Pending provider evidence differs or has unknown cost')
        budget_overrun = False
        if budgeted:
            from app.services.ac3_budget_guard import money
            budget = db.execute(text('SELECT max_new_usd,reservation_usd,spent_usd,status FROM ac3_budget_scopes WHERE scope_id=:scope' + suffix), {'scope':scope}).mappings().first()
            reserved = db.execute(text('SELECT scope_id,reserved_usd,status FROM ac3_budget_reservations WHERE request_key=:key' + suffix), {'key':request_key}).mappings().first()
            if not budget or budget['status'] != 'active' or not reserved or reserved['scope_id'] != scope or reserved['status'] != 'reserved':
                raise ValueError('A matching outstanding budget reservation is required')
            maximum = money(budget['max_new_usd'], positive=True)
            assumed = money(budget['reservation_usd'], positive=True)
            old_spent = money(budget['spent_usd'])
            if maximum != money(plan['max_new_estimated_usd'], positive=True) or assumed != money(reserved['reserved_usd'], positive=True) or assumed != money(reservation, positive=True):
                raise ValueError('Budget differs from frozen assumptions')
            budget_overrun = cost > assumed or old_spent + cost > maximum
        stored_metadata = {'ac3_request_key':request_key, 'ac3_frozen_sha256':frozen_sha256,
                           'reported_cost_usd':str(cost), 'cost_source':'provider_report_unreconciled'}
        if budgeted and evidence_table_exists:
            evidence = db.execute(text('SELECT evidence_json,evidence_sha256,response_metadata_json FROM ac3_request_evidence WHERE request_key=:key' + suffix), {'key':request_key}).mappings().first()
            if evidence:
                if (hashlib.sha256(evidence['evidence_json'].encode()).hexdigest() != evidence['evidence_sha256'] or
                    not evidence['response_metadata_json']):
                    raise ValueError('Pending private request evidence or response metadata is incomplete')
                metadata = json.loads(evidence['response_metadata_json'])
                if (not isinstance(metadata, dict) or metadata.get('request_contract_sha256') != contract_sha256 or
                    metadata.get('reported_cost_usd') is None or Decimal(str(metadata['reported_cost_usd'])) != cost):
                    raise ValueError('Response metadata differs from the pending request')
                stored_metadata = {**metadata, **stored_metadata, 'ac3_request_evidence_sha256':evidence['evidence_sha256']}
        db.add(TargetResponseModel(id=response_id, test_id=local_test_id, run_id=run_id,
              response_text=response, model=cfg['target_model'], temperature=audit.temperature,
              execution_metadata=stored_metadata))
        db.flush()
        changed = db.execute(text("UPDATE ac3_attempt_receipts SET status = 'settled', response_text = :response, reported_cost_usd = :cost WHERE request_key = :key AND status = 'dispatched'"), {'response':response,'cost':str(cost),'key':request_key}).rowcount
        if changed != 1:
            raise ValueError('Attempt changed while settling')
        if budgeted:
            status = 'overrun' if budget_overrun else 'settled'
            changed_budget = db.execute(text('UPDATE ac3_budget_reservations SET status=:status WHERE request_key=:key AND status=\'reserved\''), {'status':status, 'key':request_key}).rowcount
            changed_scope = db.execute(text('UPDATE ac3_budget_scopes SET spent_usd=:spent,status=:status WHERE scope_id=:scope AND status=\'active\''), {'spent':str(old_spent + cost), 'status':'overrun' if budget_overrun else 'active', 'scope':scope}).rowcount
            if changed_budget != 1 or changed_scope != 1:
                raise ValueError('Budget changed while settling')
        changed = db.execute(text("UPDATE ac3_attempt_scopes SET status = :status WHERE scope_id = :scope AND status = 'unknown'"), {'scope':scope, 'status':'unknown' if budget_overrun else 'active'}).rowcount
        if changed != 1:
            raise ValueError('Ledger scope changed while settling')
        if compile_mock(frozen_path, frozen_sha256, reservation)['frozen_sha256'] != frozen_sha256:
            raise ValueError('Frozen evidence changed during settlement')
    return {'state':'budget_overrun' if budget_overrun else 'settled', 'duplicate':False, 'response_id':response_id, 'provider_called':False}
