"""Create and stage reviewed AC3 source and audits, without calling a model.

The full setup is bound by the prospective frozen protocol. Source and audit
identifiers are deterministic; existing unrelated records are never replaced.
"""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import AuditRunModel, TargetResponseModel
from app.schemas import AuditRun
from app.services.ac3_controlled_runner import _SETTINGS_FIELDS, target_settings_sha256
from app.services.ac3_reviewed_source_import import import_reviewed_ac3_sources
from app.services.ac3_staging import stage_reviewed_suite
from scripts.ac3_fixed_suite_adapter import compile_mock, sha


def prepare_staged_ac3(engine, *, frozen_path, frozen_sha256, reservation, ledger_scope=None):
    plan = compile_mock(frozen_path, frozen_sha256, reservation)
    cfg = plan['model_configuration']
    setup = cfg.get('audit_setup')
    if not isinstance(setup, dict) or set(setup) != _SETTINGS_FIELDS:
        raise ValueError('Frozen audit_setup must contain every target setting')
    for field, key in (('provider','target_provider'),('model','target_model'),
                       ('evaluator_provider','evaluator_provider'),('evaluator_model','evaluator_model'),
                       ('pipeline_provider','pipeline_provider'),('pipeline_model','pipeline_model'),
                       ('memory_strategy','target_strategy')):
        if setup[field] != cfg[key]: raise ValueError('Frozen audit setup differs from model configuration')
    if not isinstance(setup['target_memory_profile'], dict) or setup['target_memory_profile'].get('output_token_limit') != cfg.get('target_output_token_limit'):
        raise ValueError('Frozen memory profile and output limit must agree')
    if any(not isinstance(setup.get(key), str) or not setup[key].strip() for key in ('target_memory_writer_version','target_system_adapter_version')):
        raise ValueError('Frozen writer and adapter implementation versions are required')
    eligible = [row for row in plan['items'] if row['grounding_review'] == 'valid']
    history_ids = sorted({row['history_id'] for row in eligible})
    if not history_ids or len(eligible) != plan['eligible_question_count']:
        raise ValueError('Frozen suite has no eligible histories or mismatched count')
    runs = {history:'AC3R' + sha(f'{frozen_sha256}|{history}'.encode())[:32].upper() for history in history_ids}
    configs = {}
    for history in history_ids:
        count = sum(row['history_id'] == history for row in eligible)
        # A per-history budget is derived, rather than silently assuming four.
        values = {**setup, 'test_budget':count}
        model = AuditRun(run_id=runs[history], conversation_id='synthetic-placeholder', status='CREATED',
                         created_at=datetime.now(timezone.utc), **values)
        expected = cfg.get('target_settings_sha256')
        if isinstance(expected, dict): expected = expected.get(history)
        if target_settings_sha256(model) != expected:
            raise ValueError('Derived audit target settings differ from frozen settings hash')
        configs[history] = model.model_dump(mode='json', include=_SETTINGS_FIELDS)
    sources = import_reviewed_ac3_sources(engine, frozen_path=frozen_path, frozen_sha256=frozen_sha256, reservation=reservation)
    conversations = sources['history_conversations']
    if set(conversations) != set(history_ids):
        raise ValueError('Every imported history needs at least one eligible test')
    from app.api.routes import audit_run_locks, audit_schema
    with Session(engine) as db:
        with audit_run_locks(['ac3-prepare:' + frozen_sha256], db=db):
            with db.begin():
                saved = {row.id:row for row in db.scalars(select(AuditRunModel).where(AuditRunModel.id.in_(runs.values())).with_for_update())}
                if saved and len(saved) != len(runs):
                    raise ValueError('Partially created audit set requires investigation')
                if saved:
                    for history, run_id in runs.items():
                        row = saved[run_id]
                        actual = audit_schema(row)
                        expected_audit = AuditRun(run_id=run_id, conversation_id=conversations[history], status='CREATED', created_at=datetime.now(timezone.utc), **configs[history])
                        if row.conversation_id != conversations[history] or target_settings_sha256(actual) != target_settings_sha256(expected_audit):
                            actual_values = actual.model_dump(mode='json', include=_SETTINGS_FIELDS)
                            differing = sorted(key for key in _SETTINGS_FIELDS if actual_values[key] != configs[history][key])
                            raise ValueError('Existing audit differs from frozen configuration: ' + ', '.join(differing))
                else:
                    for history, run_id in runs.items():
                        values = dict(configs[history]); profile = values.pop('target_memory_profile')
                        db.add(AuditRunModel(id=run_id, conversation_id=conversations[history], status='CREATED',
                            reproducibility_metadata={'target_memory_profile':profile}, **values))
    with Session(engine) as db:
        has_outputs = db.scalar(select(TargetResponseModel.id).where(TargetResponseModel.run_id.in_(runs.values())).limit(1)) is not None
        db.rollback()
        if has_outputs:
            if not ledger_scope:
                raise ValueError('Resuming completed answers requires their ledger scope')
            from app.services.ac3_locked_preflight import locked_ac3_preflight
            with locked_ac3_preflight(db, frozen_path, frozen_sha256, reservation, conversations, runs, ledger_scope=ledger_scope):
                pass
            staged = {'status':'already_staged_with_answers'}
        else:
            staged = stage_reviewed_suite(db, frozen_path, frozen_sha256, reservation, conversations, runs)
    return {'status':'staged','history_conversations':conversations,'history_runs':runs,
            'history_count':len(runs),'test_count':len(eligible),'model_called':False,
            'staging_status':staged['status']}
