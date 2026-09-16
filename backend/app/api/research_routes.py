"""Ephemeral API endpoints for research artefact validation and reporting.

No supplied annotation or benchmark payload is written to the operational audit
database.  This keeps research releases versioned in team-controlled files and
avoids mixing consent scopes with ordinary audit records.
"""
from fastapi import APIRouter, HTTPException

from app.benchmarks.longmemeval import LongMemEvalAdapter
from app.research.validity import ResearchValidityService
from app.schemas.benchmark import LongMemEvalImportRequest, LongMemEvalValidationResponse
from app.schemas.research import (
    AnnotationImportReport,
    AnnotationImportRequest,
    ResearchValidityReport,
    ResearchValidityRequest,
    annotation_import_report,
)


research_router = APIRouter(prefix="/api/v1/research", tags=["research-validation"])


@research_router.post("/annotations/validate", response_model=AnnotationImportReport)
def validate_annotation_dataset(payload: AnnotationImportRequest):
    """Validate a versioned human-label release and return its reproducible hash."""
    return annotation_import_report(payload.dataset)


@research_router.post("/validity/report", response_model=ResearchValidityReport)
def research_validity_report(payload: ResearchValidityRequest):
    """Compute explicit research metrics against supplied, frozen human labels."""
    try:
        return ResearchValidityService().calculate(payload.dataset, payload.predictions)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@research_router.post("/benchmarks/longmemeval/validate", response_model=LongMemEvalValidationResponse)
def validate_longmemeval_compatible(payload: LongMemEvalImportRequest):
    """Validate/normalise local LongMemEval-compatible JSON without execution."""
    try:
        cases, report = LongMemEvalAdapter().adapt(payload.payload)
        return LongMemEvalValidationResponse(report=report, cases=cases)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
