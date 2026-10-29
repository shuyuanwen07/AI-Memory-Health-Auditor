"""Quarantined import for a reviewed prospective AC3 suite.

This is deliberately not wired to an HTTP endpoint. It never executes a model,
unlocks an audit, or claims a real budget limit. PostgreSQL requires
SERIALIZABLE transactions; SQLite is restricted to an isolated in-memory
test database. Its staged status is blocked by both API and worker execution
paths. Existing results and prior evidence are never modified.
"""
from sqlalchemy import select

from app.models import AuditRunModel, ConversationModel, MemoryModel, MemoryRelationshipModel, MessageModel, TargetResponseModel, TestCaseModel
from app.schemas.domain import AuditStatus, Dimension
from app.services.formal_freeze import formal_input_signature


def stage_reviewed_suite(db, frozen_path, frozen_sha256, reservation,
                         history_conversations, history_runs):
    """Atomically stage an already frozen suite, without enabling execution.

    All source files, human attestations and mock budget are revalidated by
    compile_database_stage *inside* the audit locks and transaction. Repeating
    the same request is idempotent only when saved input fingerprints still
    match. Partial or altered states are rejected rather than repaired.
    """
    from app.api.routes import audit_run_locks
    from scripts.ac3_database_mapping import compile_database_stage
    from scripts.ac3_fixed_suite_adapter import sha

    bind = db.get_bind()
    if db.in_transaction() or db.new or db.dirty or db.deleted:
        raise ValueError('Use a clean idle session; caller-owned transactions are not supported.')
    dialect = bind.url.get_backend_name()
    if dialect == 'postgresql':
        with bind.connect() as connection:
            if connection.get_isolation_level() != 'SERIALIZABLE':
                raise ValueError('PostgreSQL staging requires SERIALIZABLE transaction isolation.')
    elif dialect != 'sqlite' or bind.url.database not in (None, ':memory:'):
        raise ValueError('Quarantined import requires SERIALIZABLE PostgreSQL or an in-memory SQLite test database.')
    if not isinstance(history_runs, dict) or set(history_runs) != set(history_conversations):
        raise ValueError('Every frozen history requires a separate audit.')
    run_ids = list(history_runs.values())
    if any(not isinstance(value, str) or not value.strip() for value in run_ids) or len(set(run_ids)) != len(run_ids):
        raise ValueError('Audit IDs must be distinct and non-empty.')

    # Identify shared-suite lock scopes, then discard the preflight transaction;
    # under the acquired locks every scope is re-read and compared.
    preflight = {run.id: (run.experiment_id or run.id) for run in
                 db.scalars(select(AuditRunModel).where(AuditRunModel.id.in_(run_ids)))}
    db.rollback()
    if set(preflight) != set(run_ids):
        raise ValueError('An audit was not found.')
    scopes = sorted({f'suite:{value}' for value in preflight.values()} | set(run_ids))
    with audit_run_locks(scopes, db=db):
        db.expire_all()
        with db.begin():
            runs = {run.id: run for run in db.scalars(select(AuditRunModel)
                    .where(AuditRunModel.id.in_(run_ids)).order_by(AuditRunModel.id).with_for_update())}
            if set(runs) != set(run_ids) or any((run.experiment_id or run.id) != preflight[run.id] for run in runs.values()):
                raise ValueError('Audit or shared-suite identity changed during staging.')
            # Lock parent rows before their children. INSERTs through ordinary
            # foreign keys must acquire a conflicting parent key-share lock,
            # preventing unnoticed additions while the checked snapshot is
            # staged. Serializable isolation also rejects incompatible writes.
            conversation_ids = sorted(set(history_conversations.values()))
            list(db.scalars(select(ConversationModel).where(ConversationModel.id.in_(conversation_ids))
                            .order_by(ConversationModel.id).with_for_update()))
            list(db.scalars(select(MessageModel).where(MessageModel.conversation_id.in_(conversation_ids))
                            .order_by(MessageModel.id).with_for_update()))
            memories = list(db.scalars(select(MemoryModel).where(MemoryModel.conversation_id.in_(conversation_ids))
                            .order_by(MemoryModel.id).with_for_update()))
            list(db.scalars(select(MemoryRelationshipModel).where(MemoryRelationshipModel.memory_id.in_([m.id for m in memories]))
                            .order_by(MemoryRelationshipModel.id).with_for_update()))
            plan = compile_database_stage(db, frozen_path, frozen_sha256, reservation, history_conversations)
            config = plan['model_configuration']
            eligible = [row for row in plan['items'] if row['grounding_review'] == 'valid']
            if len(eligible) != plan['eligible_question_count']:
                raise ValueError('Eligible test count differs from the reviewed plan.')
            valid_dimensions = {item.value for item in Dimension}
            previous = [runs[run_id].status == AuditStatus.RESEARCH_STAGED.value for run_id in run_ids]
            if any(previous) and not all(previous):
                raise ValueError('Partial staged state is not repaired automatically.')
            for history, run_id in history_runs.items():
                run = runs[run_id]
                if run.conversation_id != history_conversations[history]:
                    raise ValueError('Audit belongs to the wrong conversation.')
                if run.experiment_id is not None:
                    raise ValueError('Shared experiments are not supported by quarantined staging.')
                if any(getattr(run, key) != config[value] for key, value in (
                    ('provider', 'target_provider'), ('model', 'target_model'),
                    ('evaluator_provider', 'evaluator_provider'), ('evaluator_model', 'evaluator_model'),
                    ('pipeline_provider', 'pipeline_provider'), ('pipeline_model', 'pipeline_model'),
                    ('memory_strategy', 'target_strategy'))):
                    raise ValueError('Audit provider, model or strategy differs from the frozen configuration.')
                rows = [row for row in eligible if row['history_id'] == history]
                if not rows or run.test_budget != len(rows) or any(row['dimension'] not in valid_dimensions or not row['supporting_memory_ids'] for row in rows):
                    raise ValueError('Reviewed tests do not match the audit budget or memory evidence.')
                if db.scalar(select(TargetResponseModel.id).where(TargetResponseModel.run_id == run_id).limit(1)):
                    raise ValueError('An audit with target responses cannot be staged.')
                saved = list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id)))
                if all(previous):
                    metadata = (run.reproducibility_metadata or {}).get('ac3_staged_suite') or {}
                    if metadata.get('frozen_sha256') != frozen_sha256 or metadata.get('history_id') != history or metadata.get('test_count') != len(rows) or len(saved) != len(rows):
                        raise ValueError('Existing staged audit differs from the requested frozen suite.')
                    if metadata.get('input_sha256') != formal_input_signature(db, run):
                        raise ValueError('Existing staged audit inputs changed after staging.')
                elif run.status != AuditStatus.CREATED.value or saved:
                    raise ValueError('A new staged audit must be CREATED and contain no tests.')

            if all(previous):
                return {'status': 'already_staged', 'audit_count': len(run_ids), 'test_count': len(eligible),
                        'execution_supported': False, 'model_called': False}

            for row in eligible:
                run_id = history_runs[row['history_id']]
                test_id = 'AC3' + sha(f"{frozen_sha256}|{run_id}|{row['test_id']}".encode())[:32].upper()
                db.add(TestCaseModel(id=test_id, run_id=run_id, dimension=row['dimension'], prompt=row['question'],
                    expected_behavior=row['expected_behavior'], supporting_memory_ids=row['supporting_memory_ids'],
                    generator_version='ac3-quarantined-stage-v1', test_type='contextual',
                    quality_status='pending', grounding_status='pending',
                    validation_notes='Quarantined staging only; live execution is disabled.', target_memory_context=[]))
            db.flush()
            for history, run_id in history_runs.items():
                run = runs[run_id]
                metadata = dict(run.reproducibility_metadata or {})
                metadata['ac3_staged_suite'] = {'frozen_sha256': frozen_sha256, 'history_id': history,
                    'test_count': sum(row['history_id'] == history for row in eligible),
                    'execution_supported': False, 'budget_enforcement': 'not_implemented',
                    'relationship_semantics_verified': False}
                run.reproducibility_metadata = metadata
                run.status = AuditStatus.RESEARCH_STAGED.value
            db.flush()
            for run in runs.values():
                metadata = dict(run.reproducibility_metadata)
                stage = dict(metadata['ac3_staged_suite'])
                stage['input_sha256'] = formal_input_signature(db, run)
                metadata['ac3_staged_suite'] = stage
                run.reproducibility_metadata = metadata
            db.flush()
    return {'status': 'staged', 'audit_count': len(run_ids), 'test_count': len(eligible),
            'execution_supported': False, 'model_called': False,
            'notice': 'No API route, release mechanism, real budget guard or execution is enabled. PostgreSQL staging requires SERIALIZABLE isolation.'}


# Backwards-compatible name for isolated tests; the same function also admits
# PostgreSQL only under SERIALIZABLE isolation, without enabling execution.
stage_reviewed_suite_in_test_db = stage_reviewed_suite
