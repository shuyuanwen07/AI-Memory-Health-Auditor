"""Quarantined paired-retest staging; no model, release or public endpoint.

The live paired execution and billing path is not implemented. PostgreSQL
requires SERIALIZABLE isolation; SQLite is accepted only in memory for tests.
"""
import hashlib
from sqlalchemy import select
from app.models import AuditRunModel, ConversationModel, MemoryModel, MemoryRelationshipModel, MessageModel, TargetResponseModel, TestCaseModel
from app.schemas.domain import AuditStatus, Dimension
from app.services.ac3_retest_binding import verify_database_binding
from app.services.formal_freeze import formal_input_signature
from scripts.ac3_retest_paired_freeze import canonical
from scripts.ac3_retest_reference_stage import compile_reference_stage


def stage_paired_retest(db, frozen, source_raw, plan_raw, reviews, components, history_conversations, history_runs):
    from app.api.routes import audit_run_locks
    bind=db.get_bind()
    if db.in_transaction() or db.new or db.dirty or db.deleted:
        raise ValueError('Use a clean idle session')
    dialect=bind.url.get_backend_name()
    if dialect=='postgresql':
        with bind.connect() as connection:
            if connection.get_isolation_level()!='SERIALIZABLE':
                raise ValueError('PostgreSQL requires SERIALIZABLE isolation')
    elif dialect!='sqlite' or bind.url.database not in (None,':memory:'):
        raise ValueError('Only SERIALIZABLE PostgreSQL or in-memory SQLite is supported')
    if not isinstance(history_runs,dict) or set(history_runs)!=set(history_conversations):
        raise ValueError('Each history requires a separate audit')
    run_ids=list(history_runs.values())
    if not run_ids or any(not isinstance(x,str) or not x.strip() for x in run_ids) or len(set(run_ids))!=len(run_ids):
        raise ValueError('Audit IDs must be distinct')
    scopes={row.id:(row.experiment_id or row.id) for row in db.scalars(select(AuditRunModel).where(AuditRunModel.id.in_(run_ids)))}
    db.rollback()
    if set(scopes)!=set(run_ids): raise ValueError('Audit missing')
    with audit_run_locks(sorted(set(run_ids)|{f'suite:{s}' for s in scopes.values()}),db=db):
        db.expire_all()
        with db.begin():
            runs={r.id:r for r in db.scalars(select(AuditRunModel).where(AuditRunModel.id.in_(run_ids)).order_by(AuditRunModel.id).with_for_update())}
            if set(runs)!=set(run_ids) or any((r.experiment_id or r.id)!=scopes[r.id] for r in runs.values()):
                raise ValueError('Audit scope changed')
            cids=sorted(set(history_conversations.values()))
            list(db.scalars(select(ConversationModel).where(ConversationModel.id.in_(cids)).order_by(ConversationModel.id).with_for_update()))
            list(db.scalars(select(MessageModel).where(MessageModel.conversation_id.in_(cids)).order_by(MessageModel.id).with_for_update()))
            memories=list(db.scalars(select(MemoryModel).where(MemoryModel.conversation_id.in_(cids)).order_by(MemoryModel.id).with_for_update()))
            list(db.scalars(select(MemoryRelationshipModel).where(MemoryRelationshipModel.memory_id.in_([m.id for m in memories])).order_by(MemoryRelationshipModel.id).with_for_update()))
            verify_database_binding(db,frozen,source_raw,plan_raw,reviews,components,history_conversations)
            stage=compile_reference_stage(frozen,source_raw,plan_raw,reviews,components)
            target=frozen['protocol']['target'];questions=stage['questions']
            frozen_sha=hashlib.sha256(canonical(frozen)).hexdigest()
            previous=[runs[run_id].status==AuditStatus.RESEARCH_STAGED.value for run_id in run_ids]
            if any(previous) and not all(previous):raise ValueError('Partial staged state requires investigation')
            valid_dimensions={d.value for d in Dimension}
            for history,run_id in history_runs.items():
                run=runs[run_id];items=[q for q in questions if q['history_id']==history]
                if (run.conversation_id!=history_conversations[history] or run.experiment_id is not None
                        or (not all(previous) and run.status!=AuditStatus.CREATED.value) or not items or run.test_budget!=len(items)
                        or run.provider!=target['provider'] or run.model!=target['model']
                        or run.memory_strategy!=target['strategy'] or run.prompt_template_version!=target['prompt_template_version']
                        or any(q['dimension'] not in valid_dimensions for q in items)):
                    raise ValueError('Audit does not match the frozen target and questions')
                if db.scalar(select(TargetResponseModel.id).where(TargetResponseModel.run_id==run_id).limit(1)):
                    raise ValueError('Audit already has target responses')
                saved=list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==run_id)))
                if all(previous):
                    metadata=(run.reproducibility_metadata or {}).get('ac3_paired_retest') or {}
                    if (metadata.get('frozen_sha256')!=frozen_sha or metadata.get('history_id')!=history
                            or metadata.get('execution_supported') is not False or len(saved)!=len(items)
                            or metadata.get('input_sha256')!=formal_input_signature(db,run)):
                        raise ValueError('Existing staged audit differs from the frozen inputs')
                    by_id={row.id:row for row in saved}
                    for item in items:
                        identity='AC3'+hashlib.sha256(f"{frozen_sha}|{run_id}|{item['test_id']}".encode()).hexdigest()[:32].upper()
                        row=by_id.get(identity)
                        if (row is None or row.prompt!=item['question'] or row.expected_behavior!=item['expected_behavior']
                                or row.dimension!=item['dimension'] or row.supporting_memory_ids!=item['supporting_memory_ids']):
                            raise ValueError('Existing staged question differs from frozen material')
                elif saved:
                    raise ValueError('A new audit already contains questions')
            if all(previous):
                return {'status':'already_quarantined','audit_count':len(run_ids),'test_count':len(questions),
                        'model_called':False,'execution_supported':False,'budget_enforced':False}
            for q in questions:
                run_id=history_runs[q['history_id']]
                identity='AC3'+hashlib.sha256(f"{frozen_sha}|{run_id}|{q['test_id']}".encode()).hexdigest()[:32].upper()
                db.add(TestCaseModel(id=identity,run_id=run_id,dimension=q['dimension'],prompt=q['question'],
                    expected_behavior=q['expected_behavior'],supporting_memory_ids=q['supporting_memory_ids'],
                    generator_version='ac3-paired-quarantine-v1',test_type='contextual',quality_status='pending',
                    grounding_status='pending',validation_notes='Quarantined: no live execution is enabled.',target_memory_context=[]))
            db.flush()
            for history,run_id in history_runs.items():
                run=runs[run_id];metadata=dict(run.reproducibility_metadata or {})
                metadata['ac3_paired_retest']={'frozen_sha256':frozen_sha,'history_id':history,
                    'execution_supported':False,'budget_enforced':False}
                run.reproducibility_metadata=metadata;run.status=AuditStatus.RESEARCH_STAGED.value
            db.flush()
            for run in runs.values():
                metadata=dict(run.reproducibility_metadata);stage_metadata=dict(metadata['ac3_paired_retest'])
                stage_metadata['input_sha256']=formal_input_signature(db,run)
                metadata['ac3_paired_retest']=stage_metadata;run.reproducibility_metadata=metadata
            db.flush()
    return {'status':'quarantined','audit_count':len(run_ids),'test_count':len(questions),
            'model_called':False,'execution_supported':False,'budget_enforced':False}
