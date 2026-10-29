"""Locked, read-only validation of quarantined paired AC3 inputs.

This is not permission to dispatch: billing, request binding and a live
coordinator must still be checked separately. Locks last only inside the scope.
"""
from contextlib import contextmanager, nullcontext
import hashlib

from sqlalchemy import select
from app.models import AuditRunModel, ConversationModel, MemoryModel, MemoryRelationshipModel, MessageModel, TargetResponseModel, TestCaseModel
from app.services.ac3_controlled_runner import target_settings_sha256
from app.services.ac3_retest_binding import verify_database_binding
from app.services.ac3_locked_preflight import _SEQUENCE
from app.services.formal_freeze import formal_input_signature
from scripts.ac3_retest_paired_freeze import canonical
from scripts.ac3_retest_reference_stage import compile_reference_stage


@contextmanager
def locked_paired_preflight(db, frozen, source_raw, plan_raw, reviews, components, history_conversations, history_runs):
    from app.api.routes import audit_run_locks, audit_schema
    if db.in_transaction() or db.new or db.dirty or db.deleted:
        raise ValueError('A clean idle session is required')
    bind = db.get_bind()
    dialect = bind.url.get_backend_name()
    if dialect == 'postgresql':
        with bind.connect() as connection:
            if connection.get_isolation_level() != 'SERIALIZABLE':
                raise ValueError('SERIALIZABLE isolation is required')
    elif dialect != 'sqlite' or bind.url.database not in (None, ':memory:'):
        raise ValueError('Only isolated in-memory SQLite or SERIALIZABLE PostgreSQL is supported')
    if not isinstance(history_conversations, dict) or not isinstance(history_runs, dict) or set(history_runs) != set(history_conversations):
        raise ValueError('Each history needs one conversation and audit')
    ids, cids = list(history_runs.values()), list(history_conversations.values())
    if not ids or any(not isinstance(x, str) or not x.strip() for x in ids + cids) or len(set(ids)) != len(ids) or len(set(cids)) != len(cids):
        raise ValueError('Audit and conversation identifiers must be distinct and nonempty')
    sha = hashlib.sha256(canonical(frozen)).hexdigest()
    externally_locked = _SEQUENCE.get() == (bind, frozenset(ids))
    with (nullcontext() if externally_locked else audit_run_locks(sorted(set(ids) | {'suite:' + x for x in ids}), db=db)):
        db.expire_all()
        with db.begin():
            runs = {r.id: r for r in db.scalars(select(AuditRunModel).where(AuditRunModel.id.in_(ids)).order_by(AuditRunModel.id).with_for_update())}
            if set(runs) != set(ids):
                raise ValueError('A staged audit is missing')
            list(db.scalars(select(ConversationModel).where(ConversationModel.id.in_(cids)).order_by(ConversationModel.id).with_for_update()))
            list(db.scalars(select(MessageModel).where(MessageModel.conversation_id.in_(cids)).order_by(MessageModel.id).with_for_update()))
            memories = list(db.scalars(select(MemoryModel).where(MemoryModel.conversation_id.in_(cids)).order_by(MemoryModel.id).with_for_update()))
            list(db.scalars(select(MemoryRelationshipModel).where(MemoryRelationshipModel.memory_id.in_([m.id for m in memories])).order_by(MemoryRelationshipModel.id).with_for_update()))
            tests = list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id.in_(ids)).order_by(TestCaseModel.id).with_for_update()))
            list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id.in_(ids)).order_by(TargetResponseModel.id).with_for_update()))
            verify_database_binding(db, frozen, source_raw, plan_raw, reviews, components, history_conversations)
            stage = compile_reference_stage(frozen, source_raw, plan_raw, reviews, components)
            target = frozen['protocol']['target']
            for history, run_id in history_runs.items():
                run = runs[run_id]
                metadata = (run.reproducibility_metadata or {}).get('ac3_paired_retest') or {}
                items = [q for q in stage['questions'] if q['history_id'] == history]
                saved = {row.id: row for row in tests if row.run_id == run_id}
                if (run.status != 'RESEARCH_STAGED' or run.experiment_id is not None or run.conversation_id != history_conversations[history]
                        or not items or run.test_budget != len(items) or len(saved) != len(items)
                        or metadata.get('history_id') != history or metadata.get('frozen_sha256') != sha
                        or metadata.get('execution_supported') is not False
                        or metadata.get('input_sha256') != formal_input_signature(db, run)
                        or target_settings_sha256(audit_schema(run)) != target['memory_configuration_sha256']):
                    raise ValueError('Staged audit, configuration or fingerprint differs from frozen inputs')
                for item in items:
                    identity = 'AC3' + hashlib.sha256(f"{sha}|{run_id}|{item['test_id']}".encode()).hexdigest()[:32].upper()
                    row = saved.get(identity)
                    if (row is None or row.prompt != item['question'] or row.expected_behavior != item['expected_behavior']
                            or row.dimension != item['dimension'] or row.supporting_memory_ids != item['supporting_memory_ids']):
                        raise ValueError('Staged question differs from reviewed material')
            yield {'history_count': len(ids), 'question_count': len(tests), 'frozen_sha256': sha,
                   'model_called': False, 'execution_supported': False}
