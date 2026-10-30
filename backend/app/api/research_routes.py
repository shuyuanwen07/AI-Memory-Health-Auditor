"""Ephemeral API endpoints for research artefact validation and reporting.

Analysis endpoints keep supplied annotation and benchmark payloads request-scoped.
Explicit matrix creation endpoints persist approved source histories and frozen
suites under separate synthetic or deidentified research permission gates.
"""
import asyncio
from datetime import timezone
from threading import Event
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session

from app.benchmarks.longmemeval import LongMemEvalAdapter
from app.benchmarks.runner import LongMemEvalDeterministicRunner
from app.benchmarks.live import LiveBenchmarkRunner
from app.benchmarks.semantic_review import SemanticReviewService
from app.schemas.semantic_review import SemanticReviewRequest, SemanticReviewReport
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
    LiveBenchmarkRequest, LiveBenchmarkResponse,
)
from app.schemas.research import (
    AnnotationImportReport,
    AnnotationImportRequest,
    ResearchValidityReport,
    ResearchValidityRequest,
    annotation_import_report,
)
from app.schemas.formal_experiment import (
    ExploratoryMatrixCreateRequest, FormalMatrixCreateRequest, FormalMatrixCreateResponse, ResearchFormalMatrixCreateRequest,
)
from app.schemas.scene_evidence import SceneEvidenceCheckRequest
from app.database.session import get_db
from app.services.formal_matrix import FormalSyntheticMatrixService
from app.research.ranking_agreement import RankingAgreementService, RepeatedRankingService
from app.schemas.ranking_agreement import RankingAgreementRequest, RankingAgreementReport, RepeatedRankingRequest, RepeatedRankingReport


from app.schemas.acceptance import AcceptanceCheckRequest, AcceptanceCheckReport, ReviewedSavedAcceptanceReport, SavedFormalRunPage, SavedFormalRunOption
from app.research.acceptance import AcceptanceCheckService


from app.schemas.benchmark_plan import BenchmarkPlanCreate, BenchmarkPlanResponse, PlannedBenchmarkRun, PlannedRankingAnalysis, BenchmarkHumanReviewImport
from app.services.benchmark_plan import BenchmarkPlanService

research_router = APIRouter(prefix="/api/v1/research", tags=["research-validation"])




@research_router.post('/benchmarks/longmemeval/plans', response_model=BenchmarkPlanResponse, status_code=201)
def create_benchmark_plan(payload: BenchmarkPlanCreate, db: Session = Depends(get_db)):
    try:
        return BenchmarkPlanService().create(db, payload)
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from error


@research_router.get('/benchmarks/longmemeval/plans', response_model=list[BenchmarkPlanResponse])
def list_benchmark_plans(db: Session = Depends(get_db)):
    from sqlalchemy import select
    from app.models import BenchmarkPlanModel
    ids = db.scalars(select(BenchmarkPlanModel.id).order_by(BenchmarkPlanModel.created_at.desc()).limit(50)).all()
    return [BenchmarkPlanService().view(db, identity) for identity in ids]


@research_router.get('/benchmarks/longmemeval/plans/{plan_id}', response_model=BenchmarkPlanResponse)
def get_benchmark_plan(plan_id: str, db: Session = Depends(get_db)):
    return BenchmarkPlanService().view(db, plan_id)


@research_router.post('/benchmarks/longmemeval/plans/{plan_id}/execute', response_model=LiveBenchmarkResponse)
def execute_planned_benchmark(plan_id: str, payload: PlannedBenchmarkRun, db: Session = Depends(get_db)):
    try:
        return BenchmarkPlanService().run(db, plan_id, payload)
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from error


@research_router.post('/benchmarks/longmemeval/plans/{plan_id}/analyse', response_model=RepeatedRankingReport)
def analyse_planned_rankings(plan_id: str, payload: PlannedRankingAnalysis, db: Session = Depends(get_db)):
    try:
        from uuid import uuid4
        from app.models import BenchmarkAnalysisModel
        report = BenchmarkPlanService().analyse(db, plan_id, payload)
        report.notice = report.notice.replace('This analysis creates no model calls, database records or human labels.', 'This analysis makes no model calls or human labels; its derived summary is saved for the dashboard.')
        db.add(BenchmarkAnalysisModel(id='BA' + uuid4().hex.upper(), plan_id=plan_id,
            report=report.model_dump(mode='json')))
        db.commit()
        return report
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from error


@research_router.get('/benchmarks/longmemeval/analyses')
def list_benchmark_analyses(db: Session = Depends(get_db)):
    """Saved derived analyses; source text and raw benchmark replies are not retained."""
    from sqlalchemy import select
    from app.models import BenchmarkAnalysisModel
    rows = db.scalars(select(BenchmarkAnalysisModel).order_by(BenchmarkAnalysisModel.created_at.desc(), BenchmarkAnalysisModel.id.desc()).limit(100)).all()
    return [{'id': row.id, 'plan_id': row.plan_id, 'created_at': row.created_at.isoformat(), 'report': row.report} for row in rows]


@research_router.post('/benchmarks/longmemeval/plans/{plan_id}/trials/{trial_id}/human-review', status_code=201)
def import_benchmark_human_review(plan_id: str, trial_id: str, payload: BenchmarkHumanReviewImport, db: Session = Depends(get_db)):
    """Bind independently declared human judgments to a saved benchmark receipt."""
    from uuid import uuid4
    from datetime import datetime, timezone
    from app.services.benchmark_plan import checked_plan
    from app.services.stage_lock import database_stage_lock
    with database_stage_lock(db, 'benchmark-plan:' + plan_id, 'This benchmark plan is already in use.'):
        plan = checked_plan(db, plan_id)
        execution = plan.executions.get(trial_id)
        if not execution or execution.get('status') != 'COMPLETED' or not execution.get('dashboard_summary'):
            raise HTTPException(409, 'This trial has no saved case-bound dashboard summary.')
        if execution.get('evidence_fingerprint_sha256') != payload.evidence_fingerprint_sha256:
            raise HTTPException(409, 'Review evidence fingerprint does not match the saved trial.')
        allowed = {(row['strategy'], case_id) for row in execution['dashboard_summary']['conditions'] for case_id in row.get('case_ids', [])}
        if any((j.strategy, j.case_id) not in allowed for reviewer in payload.reviewers for j in reviewer.judgments):
            raise HTTPException(422, 'A review refers to a case or strategy outside this trial.')
        version = {'review_id': 'HR' + uuid4().hex.upper(), 'created_at': datetime.now(timezone.utc).isoformat(),
                   **payload.model_dump(mode='json')}
        updated = {**execution, 'human_reviews': [*execution.get('human_reviews', []), version]}
        plan.executions = {**plan.executions, trial_id: updated}
        db.commit()
        return {'review_id': version['review_id'], 'plan_id': plan_id, 'trial_id': trial_id,
                'notice': 'Reviewer independence is declared, not authenticated; prior versions remain saved.'}


@research_router.post("/benchmarks/longmemeval/ranking-agreement", response_model=RankingAgreementReport)
def compare_policy_rankings(payload: RankingAgreementRequest, db: Session = Depends(get_db)):
    """Read saved audits and validate both original benchmark assessment files."""
    _require_authorised_source(payload.reference_benchmark.source_authorised, "longmemeval")
    _require_authorised_source(payload.candidate_benchmark.source_authorised, "longmemeval")
    try:
        return RankingAgreementService().analyse(db, payload)
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from error


@research_router.post("/benchmarks/longmemeval/ranking-agreement/repeated", response_model=RepeatedRankingReport)
def compare_repeated_policy_rankings(payload: RepeatedRankingRequest, db: Session = Depends(get_db)):
    for trial in payload.trials:
        if trial.comparison is not None:
            _require_authorised_source(trial.comparison.reference_benchmark.source_authorised, "longmemeval")
            _require_authorised_source(trial.comparison.candidate_benchmark.source_authorised, "longmemeval")
    try:
        return RepeatedRankingService().analyse(db, payload)
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from error


@research_router.post("/benchmarks/longmemeval/semantic-review", response_model=SemanticReviewReport)
def import_semantic_review(payload: SemanticReviewRequest):
    """Validate imported automated scores against frozen source and replies."""
    _require_authorised_source(payload.source_authorised, "longmemeval")
    try:
        return SemanticReviewService().analyse(payload)
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from error


@research_router.post("/benchmarks/longmemeval/live", response_model=LiveBenchmarkResponse)
async def run_live_longmemeval(payload: LiveBenchmarkRequest, request: Request):
    cancelled = Event()
    task = asyncio.create_task(asyncio.to_thread(LiveBenchmarkRunner().run, payload, cancelled))
    try:
        while not task.done():
            if await request.is_disconnected():
                cancelled.set()
            await asyncio.sleep(0.1)
        return await task
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from error
    finally:
        cancelled.set()


@research_router.post("/annotations/validate", response_model=AnnotationImportReport)
def validate_annotation_dataset(payload: AnnotationImportRequest):
    """Validate a versioned human-label release and return its reproducible hash."""
    _require_authorised_research_source(payload.source_authorised)
    return annotation_import_report(payload.dataset)


@research_router.post("/validity/report", response_model=ResearchValidityReport)
def research_validity_report(payload: ResearchValidityRequest):
    """Compute explicit research metrics against supplied, frozen human labels."""
    _require_authorised_research_source(payload.source_authorised)
    try:
        return ResearchValidityService().calculate(payload.dataset, payload.predictions)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@research_router.get('/formal/saved-runs', response_model=SavedFormalRunPage)
def list_saved_formal_runs(offset: int = Query(0, ge=0, le=100000), limit: int = Query(25, ge=1, le=50), db: Session = Depends(get_db)):
    from sqlalchemy import select, func
    from pydantic import ValidationError
    from app.models import AuditRunModel
    from app.schemas.formal_experiment import FormalAcceptanceProtocol
    predicate = AuditRunModel.reproducibility_metadata['formal_matrix_version'].as_string().is_not(None)
    total = db.scalar(select(func.count()).select_from(AuditRunModel).where(predicate))
    rows = db.scalars(select(AuditRunModel).where(predicate).order_by(AuditRunModel.created_at.desc(), AuditRunModel.id.desc()).offset(offset).limit(limit))
    items = []
    for row in rows:
        metadata = row.reproducibility_metadata or {}
        repetition_index = metadata.get('formal_repetition_index')
        repetition_count = metadata.get('formal_repetition_count')
        if not (type(repetition_index) is int and type(repetition_count) is int
                and 1 <= repetition_index <= repetition_count <= 5):
            repetition_index = repetition_count = None
        valid = False
        try:
            parsed_protocol = FormalAcceptanceProtocol.model_validate((row.reproducibility_metadata or {}).get('formal_acceptance_protocol'))
            valid = (parsed_protocol.study_mode != 'formal_experiment_b'
                     or (parsed_protocol.reader_control == 'fixed_strong_reader'
                         and row.target_configuration == 'strong'))
        except ValidationError:
            pass
        protocol = (row.reproducibility_metadata or {}).get('formal_acceptance_protocol') or {}
        declared_mode = protocol.get('study_mode') if isinstance(protocol, dict) else None
        mode = declared_mode if declared_mode in {'formal_experiment_b', 'exploratory'} else 'exploratory'
        items.append(SavedFormalRunOption(run_id=row.id, study_mode=mode, provider=row.provider, model=row.model, memory_strategy=row.memory_strategy,
                                         created_at=row.created_at.replace(tzinfo=row.created_at.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat(), status=row.status, has_frozen_criteria=valid,
                                         repetition_index=repetition_index, repetition_count=repetition_count))
    return SavedFormalRunPage(items=items, total=total, offset=offset, limit=limit)


@research_router.get('/formal/{run_id}/plan', response_model=FormalMatrixCreateResponse)
def restore_saved_formal_plan(run_id: str, db: Session = Depends(get_db)):
    return FormalSyntheticMatrixService().restore(db, run_id)


@research_router.get('/formal/{run_id}/study-summary')
def saved_formal_study_summary(run_id: str, db: Session = Depends(get_db)):
    from app.services.formal_study_summary import study_summary
    return study_summary(db, run_id)


@research_router.post('/formal/{run_id}/verify-summary')
def verify_saved_scene_export(run_id: str, payload: SceneEvidenceCheckRequest, db: Session = Depends(get_db)):
    from app.services.formal_study_summary import verify_study_export
    return verify_study_export(db, run_id, payload.summary)


@research_router.get('/formal/{run_id}/reviewed-acceptance', response_model=ReviewedSavedAcceptanceReport)
def check_reviewed_saved_thresholds(run_id: str, db: Session = Depends(get_db)):
    from app.research.reviewed_acceptance import ReviewedSavedAcceptanceService
    return ReviewedSavedAcceptanceService().calculate(db, run_id)


@research_router.post("/formal/acceptance-check", response_model=AcceptanceCheckReport)
def check_frozen_thresholds(payload: AcceptanceCheckRequest, db: Session = Depends(get_db)):
    """Read saved criteria; supplied evidence remains request-scoped."""
    try:
        return AcceptanceCheckService().calculate(db, payload)
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from error


@research_router.post("/pilot/analyse", response_model=PilotReadinessReport)
def analyse_annotation_pilot(payload: PilotAnalysisRequest):
    """Calculate double-annotation agreement and formal-study readiness.

    The complete package is request-scoped: it is never written to PostgreSQL.
    It must contain the two independent label sets and separate adjudication or
    external-reference labels, allowing disagreements to remain auditable.
    """
    _require_authorised_research_source(payload.source_authorised)
    return PilotAnnotationService().analyse(payload)


def _require_authorised_research_source(authorised: bool) -> None:
    if not authorised:
        raise HTTPException(422, 'Confirm that you are authorised to process these research files and their conversation histories. Saving histories and calling a model require separate permission.')


@research_router.post("/formal/synthetic-matrix", response_model=FormalMatrixCreateResponse, status_code=201)
def create_formal_synthetic_matrix(
    payload: FormalMatrixCreateRequest, db: Session = Depends(get_db),
):
    """Create Experiment B runs from an authorised frozen *synthetic* release.

    This is one explicit persistence exception in the research API.
    It requires a frozen analysis plan, a development split, at least three
    repetitions, paired Weak/Strong policies, and a matching ready human
    double-annotation package before operational audit rows can be created.
    """
    pilot_report = PilotAnnotationService().analyse(PilotAnalysisRequest(package=payload.pilot))
    if not pilot_report.ready_for_formal_evaluation:
        raise HTTPException(422, detail="The matching double-annotation pilot is not ready for formal evaluation.")
    return FormalSyntheticMatrixService().create(db, payload, study_mode="formal_experiment_b")


@research_router.post("/exploratory/synthetic-matrix", response_model=FormalMatrixCreateResponse, status_code=201)
def create_exploratory_synthetic_matrix(
    payload: ExploratoryMatrixCreateRequest, db: Session = Depends(get_db),
):
    """Create explicitly exploratory synthetic runs outside formal Experiment B."""
    pilot_report = PilotAnnotationService().analyse(PilotAnalysisRequest(package=payload.pilot))
    if not pilot_report.ready_for_formal_evaluation:
        raise HTTPException(422, detail="The matching double-annotation package is not ready for this synthetic matrix.")
    return FormalSyntheticMatrixService().create(db, payload, study_mode="exploratory")


@research_router.post("/formal/research-matrix", response_model=FormalMatrixCreateResponse, status_code=201)
def create_formal_research_matrix(payload: ResearchFormalMatrixCreateRequest, db: Session = Depends(get_db)):
    """Persist an authorised deidentified release after the same formal B gates."""
    pilot_report = PilotAnnotationService().analyse(PilotAnalysisRequest(package=payload.pilot))
    if not pilot_report.ready_for_formal_evaluation:
        raise HTTPException(422, detail="The matching double-annotation pilot is not ready for formal evaluation.")
    return FormalSyntheticMatrixService().create(db, payload, study_mode="formal_experiment_b")


@research_router.post("/evaluator-calibration/analyse", response_model=EvaluatorCalibrationReport)
def analyse_evaluator_calibration(payload: EvaluatorCalibrationRequest):
    """Compare automated verdicts against de-identified human review labels.

    The release is analysed only for this request. It is separate from the
    optional per-audit calibration notes in the operational workflow.
    """
    return EvaluatorCalibrationService().analyse(payload)


@research_router.post("/benchmarks/longmemeval/validate", response_model=LongMemEvalValidationResponse)
def validate_longmemeval_compatible(payload: LongMemEvalImportRequest):
    """Validate/normalise local LongMemEval-compatible JSON after consent."""
    _require_authorised_source(payload.source_authorised, "longmemeval")
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
    _require_authorised_source(payload.source_authorised, "locomo")
    try:
        cases, report = LoCoMoAdapter().adapt(payload.payload)
        return LocalCompatibleValidationResponse(report=report, cases=cases)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@research_router.post("/benchmarks/beam/validate", response_model=LocalCompatibleValidationResponse)
def validate_beam_compatible(payload: LocalCompatibleImportRequest):
    """Validate caller-supplied local BEAM-style JSON without execution."""
    _require_authorised_source(payload.source_authorised, "beam")
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
