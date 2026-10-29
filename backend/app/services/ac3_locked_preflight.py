"""Repeat staged AC3 checks while holding audit and input locks.

No production dispatch is enabled here. The caller may inspect the observation
only; a future live runner must also validate the frozen files immediately
before dispatch, bind the request, and reconcile the durable attempt ledger.
"""
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from decimal import Decimal, InvalidOperation
from sqlalchemy import select, text
from app.models import AuditRunModel, ConversationModel, MemoryModel, MemoryRelationshipModel, MessageModel, TestCaseModel, TargetResponseModel
from app.services.ac3_readiness import inspect_staged_ac3

_SEQUENCE = ContextVar('ac3_locked_sequence', default=None)


@contextmanager
def ac3_sequence_locks(db, history_runs):
    """Hold app stage locks across preflight, request and later settlement.

    Row locks belong to the shorter preflight transaction. This outer scope
    only protects cooperating application writers; the result must be checked
    again at settlement, and a returned answer must first be recorded in the
    durable pending receipt. It is not itself dispatch authorization.
    """
    from app.api.routes import audit_run_locks
    if _SEQUENCE.get() is not None:
        raise ValueError('Nested AC3 sequence locks are not supported')
    if not isinstance(history_runs, dict) or not history_runs:
        raise ValueError('Audit mapping is required')
    ids = list(history_runs.values())
    if any(not isinstance(x, str) or not x.strip() for x in ids) or len(ids) != len(set(ids)):
        raise ValueError('Audit identifiers must be distinct')
    scopes = sorted(set(ids) | {'suite:' + x for x in ids})
    with audit_run_locks(scopes, db=db):
        token = _SEQUENCE.set((db.get_bind(), frozenset(ids)))
        try:
            yield
        finally:
            _SEQUENCE.reset(token)


@contextmanager
def locked_ac3_preflight(db, frozen_path, frozen_sha256, reservation, history_conversations, history_runs, *, ledger_scope=None, ledger_write_handoff=False):
    from app.api.routes import audit_run_locks
    bind = db.get_bind()
    if db.in_transaction() or db.new or db.dirty or db.deleted:
        raise ValueError('A clean idle session is required')
    dialect = bind.url.get_backend_name()
    if dialect == 'postgresql':
        with bind.connect() as connection:
            if connection.get_isolation_level() != 'SERIALIZABLE':
                raise ValueError('Locked preflight requires SERIALIZABLE PostgreSQL')
    elif dialect != 'sqlite' or bind.url.database not in (None, ':memory:'):
        raise ValueError('Locked preflight requires SERIALIZABLE PostgreSQL or isolated in-memory SQLite')
    if not isinstance(history_runs, dict) or set(history_runs) != set(history_conversations):
        raise ValueError('Every history needs one audit')
    ids = list(history_runs.values())
    if any(not isinstance(x, str) or not x.strip() for x in ids) or len(ids) != len(set(ids)):
        raise ValueError('Audit identifiers must be distinct')
    scopes = sorted(set(ids) | {'suite:' + x for x in ids})
    outer = _SEQUENCE.get()
    externally_locked = outer == (db.get_bind(), frozenset(ids))
    if ledger_write_handoff and (not externally_locked or ledger_scope is None):
        raise ValueError('Ledger handoff requires the matching outer AC3 sequence locks')
    with (nullcontext() if externally_locked else audit_run_locks(scopes, db=db)):
        db.expire_all()
        with db.begin():
            conversation_ids = sorted(set(history_conversations.values()))
            list(db.scalars(select(AuditRunModel).where(AuditRunModel.id.in_(ids)).order_by(AuditRunModel.id).with_for_update()))
            list(db.scalars(select(ConversationModel).where(ConversationModel.id.in_(conversation_ids)).order_by(ConversationModel.id).with_for_update()))
            list(db.scalars(select(MessageModel).where(MessageModel.conversation_id.in_(conversation_ids)).order_by(MessageModel.id).with_for_update()))
            memories = list(db.scalars(select(MemoryModel).where(MemoryModel.conversation_id.in_(conversation_ids)).order_by(MemoryModel.id).with_for_update()))
            list(db.scalars(select(MemoryRelationshipModel).where(MemoryRelationshipModel.memory_id.in_([x.id for x in memories])).order_by(MemoryRelationshipModel.id).with_for_update()))
            list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id.in_(ids)).order_by(TestCaseModel.id).with_for_update()))
            list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id.in_(ids)).order_by(TargetResponseModel.id).with_for_update()))
            settled = None
            if ledger_scope is not None:
                if not isinstance(ledger_scope, str) or not ledger_scope.strip():
                    raise ValueError('Ledger scope is required')
                suffix = ' FOR UPDATE' if dialect == 'postgresql' and not ledger_write_handoff else ''
                scope = db.execute(text('SELECT frozen_sha256, status FROM ac3_attempt_scopes WHERE scope_id = :scope' + suffix), {'scope': ledger_scope}).mappings().first()
                if not scope or scope['frozen_sha256'] != frozen_sha256 or scope['status'] != 'active':
                    raise ValueError('Ledger scope has an unresolved attempt or does not match the frozen suite')
                records = db.execute(text('SELECT test_id, status, response_text, reported_cost_usd FROM ac3_attempt_receipts WHERE scope_id = :scope ORDER BY test_id' + suffix), {'scope': ledger_scope}).mappings().all()
                settled = {}
                for record in records:
                    try:
                        cost = Decimal(record['reported_cost_usd']) if isinstance(record['reported_cost_usd'], str) else Decimal('NaN')
                    except InvalidOperation as exc:
                        raise ValueError('Ledger has invalid reported cost') from exc
                    if (record['status'] != 'settled' or not isinstance(record['response_text'], str) or not record['response_text'].strip() or
                        not cost.is_finite() or cost < 0 or record['test_id'] in settled):
                        raise ValueError('Ledger has unresolved, duplicate or invalid receipts')
                    settled[record['test_id']] = dict(record)
            result = inspect_staged_ac3(db, frozen_path, frozen_sha256, reservation, history_conversations, history_runs,
                                        settled_receipts=settled)
            yield result
