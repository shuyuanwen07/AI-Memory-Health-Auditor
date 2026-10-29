"""Prepare paired-retest source and quarantined audits, without model calls.

This is an internal setup path, not a release or live execution mechanism.
Failures may leave source/audits prepared but never launch target requests.
"""
import hashlib
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import AuditRunModel
from app.schemas import AuditRun
from app.services.ac3_controlled_runner import _SETTINGS_FIELDS, target_settings_sha256
from app.services.ac3_retest_source_import import import_paired_sources
from app.services.ac3_retest_staging import stage_paired_retest
from scripts.ac3_retest_paired_freeze import canonical
from scripts.ac3_retest_reference_stage import compile_reference_stage


def prepare_paired_retest(engine, frozen, source_raw, plan_raw, reviews, components, audit_setup):
    stage=compile_reference_stage(frozen,source_raw,plan_raw,reviews,components)
    target=frozen['protocol']['target']
    if not isinstance(audit_setup,dict) or set(audit_setup)!=_SETTINGS_FIELDS:
        raise ValueError('Every target audit setting must be explicitly frozen')
    if hashlib.sha256(canonical(audit_setup)).hexdigest()!=target['memory_configuration_sha256']:
        raise ValueError('Audit configuration differs from the frozen target fingerprint')
    for field,key in (('provider','provider'),('model','model'),('memory_strategy','strategy'),('prompt_template_version','prompt_template_version')):
        if audit_setup[field]!=target[key]:raise ValueError('Audit setup differs from the frozen target')
    for field in ('temperature','random_seed'):
        if target[field] is not None and audit_setup[field]!=target[field]:
            raise ValueError('Audit sampling setting differs from the frozen target')
    if audit_setup['target_memory_profile'].get('output_token_limit')!=target['output_token_limit']:
        raise ValueError('Output token limit differs from the frozen target')
    if any(not isinstance(audit_setup.get(field),str) or not audit_setup[field].strip()
           for field in ('target_memory_writer_version','target_system_adapter_version')):
        raise ValueError('Writer and adapter implementation versions must be explicit')
    sha=hashlib.sha256(canonical(frozen)).hexdigest()
    history_ids=[h['history_id'] for h in stage['histories']]
    run_ids={hid:'AC3R'+hashlib.sha256(f'{sha}|{hid}'.encode()).hexdigest()[:32].upper() for hid in history_ids}
    # Validate all Pydantic settings before creating source records.
    audits={}
    for hid in history_ids:
        count=sum(q['history_id']==hid for q in stage['questions'])
        if audit_setup['test_budget']!=count:
            raise ValueError('Frozen test budget does not match the reviewed history')
        audit=AuditRun(run_id=run_ids[hid],conversation_id='synthetic-placeholder',status='CREATED',
                       created_at=datetime.now(timezone.utc),**audit_setup)
        if audit.model_dump(mode='json',include=_SETTINGS_FIELDS)!=audit_setup:
            raise ValueError('Audit configuration is not in canonical product form')
        audits[hid]=audit
    imported=import_paired_sources(engine,frozen,source_raw,plan_raw,reviews,components)
    conversations=imported['history_conversations']
    from app.api.routes import audit_run_locks, audit_schema
    with Session(engine) as db:
        with audit_run_locks(['ac3-paired-prepare:'+sha],db=db):
            with db.begin():
                saved={row.id:row for row in db.scalars(select(AuditRunModel).where(AuditRunModel.id.in_(run_ids.values())).with_for_update())}
                if saved and len(saved)!=len(run_ids):raise ValueError('Partial prepared audit set requires investigation')
                if saved:
                    for hid,run_id in run_ids.items():
                        row=saved[run_id]
                        if row.conversation_id!=conversations[hid] or target_settings_sha256(audit_schema(row))!=target_settings_sha256(audits[hid]):
                            raise ValueError('Existing audit differs from frozen settings')
                else:
                    for hid,run_id in run_ids.items():
                        values=dict(audit_setup);profile=values.pop('target_memory_profile')
                        db.add(AuditRunModel(id=run_id,conversation_id=conversations[hid],status='CREATED',
                            reproducibility_metadata={'target_memory_profile':profile},**values))
    with Session(engine) as db:
        staged=stage_paired_retest(db,frozen,source_raw,plan_raw,reviews,components,conversations,run_ids)
    return {'format':'ac3-paired-preparation-v1','source_status':imported['status'],'staging_status':staged['status'],
            'history_count':len(history_ids),'test_count':len(stage['questions']),
            'model_called':False,'execution_supported':False,'budget_enforced':False}
