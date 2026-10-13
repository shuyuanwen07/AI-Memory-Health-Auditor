"""Freeze generator variants while target and assessment controls stay fixed."""
from copy import deepcopy
import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.models import AuditRunModel, GeneratorComparisonModel
from app.schemas import AuditCreate, ReassessmentRequest, TargetProvider
from app.services.reassessment import saved_answer_signature
from app.services.runtime_freeze import audit_runtime_signature
from app.target_ai.providers import configured


def assert_generator_plan(db, plan):
    if plan.runtime_signature != audit_runtime_signature():
        raise HTTPException(409,'Software changed. Saved generator results remain available; start a new comparison.')
    source = db.get(AuditRunModel,plan.source_run_id)
    if not source or saved_answer_signature(db,source) != plan.input_fingerprint:
        raise HTTPException(409,'Reference data changed. Saved generator results remain available; start a new comparison.')
    return source


def create_generator_plan(db, request):
    fingerprint=hashlib.sha256(json.dumps(request.model_dump(exclude={'creation_request_key'}),sort_keys=True).encode()).hexdigest()
    existing=db.scalar(select(GeneratorComparisonModel).where(GeneratorComparisonModel.creation_request_key==request.creation_request_key))
    if existing:
        if existing.fingerprint != fingerprint:
            raise HTTPException(409,'This saved request has different generator settings. Start a new comparison.')
        return existing
    source=db.get(AuditRunModel,request.source_run_id)
    if not source or source.status != 'COMPLETED':
        raise HTTPException(409,'Choose a completed source audit.')
    original=(source.reproducibility_metadata or {}).get('assessment_source_run_id')
    if original:source=db.get(AuditRunModel,original)
    if not source or source.status != 'COMPLETED':
        raise HTTPException(409,'The original completed audit is unavailable.')
    if source.target_memory_writer != 'rule_based' or source.target_system_adapter != 'controlled-memory':
        raise HTTPException(422,'Choose a controlled-memory audit with a rule-based memory writer. Otherwise changing the generator would also change target memory construction.')
    try:
        ReassessmentRequest(evaluator_provider=source.provider,evaluator_model=source.model)
        ReassessmentRequest(evaluator_provider=source.evaluator_provider,evaluator_model=source.evaluator_model)
    except ValidationError:
        raise HTTPException(422,'Choose a source with fixed target and assessor model names.') from None
    plan=GeneratorComparisonModel(id='GC'+uuid4().hex.upper(),creation_request_key=request.creation_request_key,
        fingerprint=fingerprint,source_run_id=source.id,input_fingerprint=saved_answer_signature(db,source),
        runtime_signature=audit_runtime_signature(),entries=[{'selection':item.model_dump(),'run_id':None} for item in request.generators])
    db.add(plan);db.commit();db.refresh(plan)
    return plan


def prepare_generator_plan(db, plan, builder):
    source=assert_generator_plan(db,plan)
    for index,entry in enumerate(plan.entries):
        if entry['run_id']:continue
        selection=entry['selection']
        if not configured(TargetProvider(selection['provider'])):
            raise HTTPException(422,'The selected test generation service is unavailable. Earlier preparation is saved.')
        key='generator_'+hashlib.sha256(f'{plan.id}:{index}'.encode()).hexdigest()
        run=db.scalar(select(AuditRunModel).where(AuditRunModel.creation_request_key==key))
        if not run:
            fields=('conversation_id','target_configuration','provider','model','temperature','random_seed','test_budget',
                'prompt_template_version','semantic_review_provider','semantic_review_model',
                'evaluator_provider','evaluator_model','memory_strategy','memory_maintenance_policy',
                'target_memory_capacity','target_memory_writer','target_system_adapter',
                'retrieval_mode','retrieval_provider','retrieval_model')
            values={field:getattr(source,field) for field in fields}
            values.update(creation_request_key=key,pipeline_provider=selection['provider'],pipeline_model=selection['model'],
                target_memory_profile=deepcopy((source.reproducibility_metadata or {}).get('target_memory_profile') or {}))
            created=builder(AuditCreate(**values),db)
            run=db.get(AuditRunModel,created.run_id)
            if not run:
                raise HTTPException(409,'The prepared generator run is unavailable. Saved earlier progress is retained.')
            metadata=deepcopy(run.reproducibility_metadata or {})
            metadata.update(study_role='generator_comparison',comparison_source_run_id=source.id,
                comparison_input_signature=plan.input_fingerprint,generator_comparison_id=plan.id)
            run.reproducibility_metadata=metadata
        entries=deepcopy(plan.entries);entries[index]['run_id']=run.id;plan.entries=entries
        db.commit();db.refresh(plan)
    return plan
