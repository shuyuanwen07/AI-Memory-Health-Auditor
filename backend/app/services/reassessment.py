"""New assessment records over exact saved answers; original evidence is immutable."""
import hashlib
import json
from copy import deepcopy
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.evaluator.factory import configured_evaluator
from app.models import AuditRunModel, EvaluationResultModel, TargetResponseModel, TestCaseModel
from app.schemas import ReassessmentRequest, TargetProvider
from app.target_ai.providers import configured
from app.services.runtime_freeze import audit_runtime_signature
from app.services.formal_freeze import formal_input_signature


def saved_answer_signature(db, source):
    db.refresh(source)
    def serial(value):
        if isinstance(value, datetime):
            return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
        raise TypeError('Unsupported source input value.')
    answers = db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == source.id).order_by(TargetResponseModel.id).execution_options(populate_existing=True)).all()
    payload = {'reference':formal_input_signature(db, source),
               'answers':[{column.name:getattr(answer,column.name) for column in TargetResponseModel.__table__.columns} for answer in answers]}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,default=serial).encode()).hexdigest()


def assert_saved_assessment_inputs(db, audit):
    metadata = audit.reproducibility_metadata or {}
    expected = metadata.get('assessment_input_signature') or metadata.get('comparison_input_signature')
    if not expected:
        return
    source = db.get(AuditRunModel, metadata.get('assessment_source_run_id') or metadata.get('comparison_source_run_id'))
    if not source or saved_answer_signature(db, source) != expected:
        raise HTTPException(409, 'The saved answers or reference data changed. Existing assessments are preserved; start a new comparison with verified inputs.')
    copied = metadata.get('assessment_copy_signature')
    if metadata.get('assessment_source_run_id') and not copied:
        raise HTTPException(409, 'This historical assessment has no saved question and answer verification. Existing results are preserved; start a new comparison.')
    if copied and assessment_copy_signature(db, audit) != copied:
        raise HTTPException(409, 'The questions or saved answers in this assessment changed. Existing results are preserved; start a new comparison with verified inputs.')


def assessment_copy_signature(db, audit):
    """Bind the actual destination inputs, not just the original audit.

    Evaluation results and human decisions remain independent outputs. Fresh
    reads detect edits committed by another session while a judge is running.
    """
    def serial(value):
        if isinstance(value, datetime):
            return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
        raise TypeError('Unsupported assessment input value.')
    payload = {}
    for name, model in (('questions', TestCaseModel), ('answers', TargetResponseModel)):
        payload[name] = [{column.name: getattr(row, column.name)
                          for column in model.__table__.columns}
                         for row in db.scalars(select(model).where(model.run_id == audit.id)
                             .order_by(model.id).execution_options(populate_existing=True))]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=serial).encode()).hexdigest()


def prepare_reassessment(db, source_id, selection: ReassessmentRequest | None = None):
    source = db.get(AuditRunModel, source_id)
    if not source:
        raise HTTPException(404, 'Audit not found.')
    original_id = (source.reproducibility_metadata or {}).get('assessment_source_run_id')
    if original_id:
        original = db.get(AuditRunModel, original_id)
        if not original:
            raise HTTPException(409, 'The original saved assessment is unavailable. Existing results are preserved.')
        source = original
        source_id = original.id
    if source.status != 'COMPLETED':
        raise HTTPException(409, 'Open a completed audit before reassessing its saved answers.')
    provider, model = configured_evaluator(
        selection.evaluator_provider if selection else source.evaluator_provider,
        selection.evaluator_model if selection else source.evaluator_model,
    )
    # An explicit unavailable service must not silently become a rule result.
    # Historical same-assessor reassessment preserves its existing behaviour.
    if selection and not configured(TargetProvider(provider)):
        raise HTTPException(422, 'The selected evaluation service is unavailable. Configure it before comparing assessors.')
    runtime = audit_runtime_signature()
    input_signature = saved_answer_signature(db, source)
    key = 'reassessment_' + hashlib.sha256(json.dumps(
        [source_id, provider, model, runtime, input_signature, 'saved-copy-v1'], sort_keys=True).encode()).hexdigest()
    existing = db.scalar(select(AuditRunModel).where(AuditRunModel.creation_request_key == key))
    if existing:
        return existing
    tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == source_id).order_by(TestCaseModel.id)).all()
    evaluations = {e.test_id: e for e in db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id == source_id)).all()}
    answers = []
    for test in tests:
        evaluation = evaluations.get(test.id)
        answer = db.get(TargetResponseModel, evaluation.response_id) if evaluation else None
        if not answer or answer.run_id != source_id or answer.test_id != test.id:
            raise HTTPException(409, 'The original assessment is missing its exact saved answer. Existing evidence is preserved.')
        if test.quality_status != 'accepted':
            raise HTTPException(409, 'Some original questions lack a saved acceptance decision. Start a new reviewed audit rather than changing historical questions.')
        answers.append(answer)
    if not tests:
        raise HTTPException(409, 'There are no assessed answers to reassess.')
    values = {c.name: deepcopy(getattr(source, c.name)) for c in AuditRunModel.__table__.columns
              if c.name not in {'id', 'experiment_id', 'creation_request_key', 'creation_request_fingerprint', 'created_at', 'completed_at', 'status', 'reproducibility_metadata'}}
    values.update(evaluator_provider=provider, evaluator_model=model)
    # Target settings describe the original execution, not a new memory write.
    # Formal labels/signatures and human attestations cannot be inherited by a
    # development reassessment. Keep only ordinary target provenance.
    metadata = {k: deepcopy(v) for k, v in (source.reproducibility_metadata or {}).items()
                if not k.startswith('formal_') and k not in {'auditor_comparison_id', 'human_validation', 'configuration_fingerprint'}}
    metadata.update(audit_runtime_signature=runtime, assessment_source_run_id=source_id,
                    assessment_input_signature=input_signature,
                    shared_answer_source_run_id=metadata.get('shared_answer_source_run_id') or source_id,
                    study_role='saved_answer_reassessment', auditor_method='custom',
                    configuration_fingerprint=hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest())
    target = AuditRunModel(id='RUN'+uuid4().hex.upper(), creation_request_key=key,
                           status='TESTS_EXECUTED', reproducibility_metadata=metadata, **values)
    db.add(target)
    try:
        db.flush()
        for original, answer in zip(tests, answers, strict=True):
            fields = {c.name: deepcopy(getattr(original, c.name)) for c in TestCaseModel.__table__.columns
                      if c.name not in {'id', 'run_id', 'suite_test_id', 'comparison_test_id', 'target_memory_context'}}
            test = TestCaseModel(id='T'+uuid4().hex.upper(), run_id=target.id,
                                 suite_test_id=original.suite_test_id or original.id,
                                 comparison_test_id=original.comparison_test_id or original.suite_test_id or original.id,
                                 target_memory_context=[], **fields)
            db.add(test); db.flush()
            receipt = answer.execution_metadata or {}
            db.add(TargetResponseModel(id='R'+uuid4().hex.upper(), run_id=target.id, test_id=test.id,
                response_text=answer.response_text, model=answer.model, temperature=answer.temperature,
                execution_metadata={'request_attempts': 0, 'latency_ms': 0,
                    'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0,
                    'response_source': 'shared_target_answer',
                    'shared_source_run_id': receipt.get('shared_source_run_id') or source_id,
                    'shared_source_response_id': receipt.get('shared_source_response_id') or answer.id,
                    'memory_input': deepcopy(receipt.get('memory_input')),
                    'requested_output_token_limit': receipt.get('requested_output_token_limit'),
                    'completion_status': receipt.get('completion_status'),
                    'finish_reason': receipt.get('finish_reason')}))
        db.flush()
        target.reproducibility_metadata = {
            **target.reproducibility_metadata,
            'assessment_copy_signature': assessment_copy_signature(db, target),
        }
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(AuditRunModel).where(AuditRunModel.creation_request_key == key))
        if not existing:
            raise
        return existing
    db.refresh(target)
    return target
