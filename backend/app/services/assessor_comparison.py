"""Recoverable preparation of controlled assessor comparisons; no paid calls."""
import hashlib
import json
from copy import deepcopy
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import AssessorComparisonModel, AuditRunModel
from app.schemas import ReassessmentRequest
from app.schemas.assessor_comparison import AssessorComparisonRequest
from app.services.reassessment import prepare_reassessment, saved_answer_signature, assessment_copy_signature
from app.services.runtime_freeze import audit_runtime_signature


def create_comparison(db, request: AssessorComparisonRequest):
    fingerprint = hashlib.sha256(json.dumps(request.model_dump(exclude={'creation_request_key'}), sort_keys=True).encode()).hexdigest()
    existing = db.scalar(select(AssessorComparisonModel).where(
        AssessorComparisonModel.creation_request_key == request.creation_request_key))
    if existing:
        if existing.fingerprint != fingerprint:
            raise HTTPException(409, 'This saved comparison request has different settings. Start a new comparison.')
        return existing
    source = db.get(AuditRunModel, request.source_run_id)
    if not source or source.status != 'COMPLETED':
        raise HTTPException(409, 'Choose a completed source audit.')
    original = (source.reproducibility_metadata or {}).get('assessment_source_run_id')
    if original:
        source = db.get(AuditRunModel, original)
        if not source or source.status != 'COMPLETED':
            raise HTTPException(409, 'The original saved source audit is unavailable.')
    row = AssessorComparisonModel(id='AC'+uuid4().hex.upper(), creation_request_key=request.creation_request_key,
        fingerprint=fingerprint, source_run_id=source.id, runtime_signature=audit_runtime_signature(),
        input_fingerprint=saved_answer_signature(db, source),
        entries=[{'selection': item.model_dump(), 'run_id':None} for item in request.assessors])
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(AssessorComparisonModel).where(
            AssessorComparisonModel.creation_request_key == request.creation_request_key))
        if not existing or existing.fingerprint != fingerprint:
            raise HTTPException(409, 'The comparison could not be saved with these settings.') from None
        return existing
    db.refresh(row)
    return row


def prepare_comparison(db, row):
    if row.runtime_signature != audit_runtime_signature():
        raise HTTPException(409, 'The software changed since this comparison was saved. Its results remain available; start a new comparison to use current software.')
    source = db.get(AuditRunModel, row.source_run_id)
    if not row.input_fingerprint or not source or saved_answer_signature(db, source) != row.input_fingerprint:
        raise HTTPException(409, 'The reference data or saved answers cannot be verified against this plan. Existing results remain available; start a new comparison.')
    for index, entry in enumerate(row.entries):
        if entry.get('run_id'):
            run = db.get(AuditRunModel, entry['run_id'])
            expected = (run.reproducibility_metadata or {}).get('assessment_copy_signature') if run else None
            if not expected or assessment_copy_signature(db, run) != expected:
                raise HTTPException(409, 'The saved comparison questions or answers cannot be verified. Existing results remain available; start a new comparison.')
            continue
        run = prepare_reassessment(db, row.source_run_id, ReassessmentRequest(**entry['selection']))
        entries = deepcopy(row.entries)
        entries[index]['run_id'] = run.id
        row.entries = entries
        db.commit()
    db.refresh(row)
    return row
