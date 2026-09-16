"""Ephemeral API endpoints for research artefact validation and reporting.

No supplied annotation or benchmark payload is written to the operational audit
database.  This keeps research releases versioned in team-controlled files and
avoids mixing consent scopes with ordinary audit records.
"""
from fastapi import APIRouter, HTTPException

from app.benchmarks.longmemeval import LongMemEvalAdapter
from app.benchmarks.runner import LongMemEvalDeterministicRunner
from app.benchmarks.local_compatible import BEAMAdapter, LoCoMoAdapter
from app.benchmarks.local_runner import BEAMDeterministicRunner, LoCoMoDeterministicRunner
from app.research.validity import ResearchValidityService
from app.research.pilot import PilotAnnotationService
from app.evaluator.calibration import (
    EvaluatorCalibrationReport,
    EvaluatorCalibrationRequest,
    EvaluatorCalibrationService,
)
from app.schemas.pilot import PilotAnalysisRequest, PilotReadinessReport
from app.schemas.benchmark import (
    LocalCompatibleImportRequest,
    LocalCompatibleRunRequest,
    LocalCompatibleRunResponse,
    LocalCompatibleValidationResponse,
    LongMemEvalImportRequest,
    LongMemEvalRunRequest,
    LongMemEvalRunResponse,
    LongMemEvalValidationResponse,
)
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


@research_router.post("/pilot/analyse", response_model=PilotReadinessReport)
def analyse_annotation_pilot(payload: PilotAnalysisRequest):
    """Calculate double-annotation agreement and formal-study readiness.

    The complete package is request-scoped: it is never written to PostgreSQL.
    It must contain the two independent label sets and separate adjudication or
    external-reference labels, allowing disagreements to remain auditable.
    """
    return PilotAnnotationService().analyse(payload)


@research_router.post("/evaluator-calibration/analyse", response_model=EvaluatorCalibrationReport)
def analyse_evaluator_calibration(payload: EvaluatorCalibrationRequest):
    """Compare automated verdicts against de-identified human review labels.

    The release is analysed only for this request. It is separate from the
    optional per-audit calibration notes in the operational workflow.
    """
    return EvaluatorCalibrationService().analyse(payload)


@research_router.post("/benchmarks/longmemeval/validate", response_model=LongMemEvalValidationResponse)
def validate_longmemeval_compatible(payload: LongMemEvalImportRequest):
    """Validate/normalise local LongMemEval-compatible JSON without execution."""
    try:
        cases, report = LongMemEvalAdapter().adapt(payload.payload)
        return LongMemEvalValidationResponse(report=report, cases=cases)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@research_router.post("/benchmarks/longmemeval/run", response_model=LongMemEvalRunResponse)
def run_longmemeval_compatible(payload: LongMemEvalRunRequest):
    """Run an uploaded compatible source in isolated, local in-memory stores.

    This endpoint is intentionally provider-free and ephemeral.  It is a
    reproducible policy baseline, not an official benchmark implementation.
    """
    if not payload.source_authorised:
        raise HTTPException(
            status_code=422,
            detail=(
                "Confirm source_authorised=true only when you may process this local "
                "benchmark source and comply with its licence, citation and privacy terms."
            ),
        )
    try:
        return LongMemEvalDeterministicRunner().run(payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _require_authorised_source(authorised: bool, family: str) -> None:
    if not authorised:
        raise HTTPException(
            status_code=422,
            detail=(
                "Confirm source_authorised=true only when you may process this local "
                f"{family.upper()}-compatible source and comply with its licence, citation and privacy terms."
            ),
        )


@research_router.post("/benchmarks/locomo/validate", response_model=LocalCompatibleValidationResponse)
def validate_locomo_compatible(payload: LocalCompatibleImportRequest):
    """Validate caller-supplied local LoCoMo-style JSON without execution."""
    try:
        cases, report = LoCoMoAdapter().adapt(payload.payload)
        return LocalCompatibleValidationResponse(report=report, cases=cases)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@research_router.post("/benchmarks/beam/validate", response_model=LocalCompatibleValidationResponse)
def validate_beam_compatible(payload: LocalCompatibleImportRequest):
    """Validate caller-supplied local BEAM-style JSON without execution."""
    try:
        cases, report = BEAMAdapter().adapt(payload.payload)
        return LocalCompatibleValidationResponse(report=report, cases=cases)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@research_router.post("/benchmarks/locomo/run", response_model=LocalCompatibleRunResponse)
def run_locomo_compatible(payload: LocalCompatibleRunRequest):
    """Run isolated local LoCoMo-style cases; never an official score."""
    _require_authorised_source(payload.source_authorised, "locomo")
    try:
        return LoCoMoDeterministicRunner().run(payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@research_router.post("/benchmarks/beam/run", response_model=LocalCompatibleRunResponse)
def run_beam_compatible(payload: LocalCompatibleRunRequest):
    """Run isolated local BEAM-style cases; never an official score."""
    _require_authorised_source(payload.source_authorised, "beam")
    try:
        return BEAMDeterministicRunner().run(payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
