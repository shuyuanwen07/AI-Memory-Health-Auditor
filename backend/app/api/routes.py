from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from io import StringIO
import csv
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.evaluator.factory import get_behaviour_evaluator
from app.extraction.factory import get_memory_extractor
from app.extraction.llm import configured_pipeline_model, pipeline_provider
from app.evaluator.factory import configured_evaluator
from app.memory_agent import SqlTargetMemoryStore, get_target_memory_writer
from app.metrics.service import MetricsService
from app.services.experiment_analytics import ExperimentAnalyticsService
from app.models import AuditRunModel, ConversationModel, EvaluationResultModel, ExperimentModel, MemoryModel, MemoryRelationshipModel, MessageModel, TargetAgentMemoryEventModel, TargetAgentMemoryModel, TargetAgentMemoryRelationshipModel, TargetAgentRetrievalModel, TargetResponseModel, TestCaseModel
from app.schemas import *
from app.target_ai.providers import HttpTargetAIConnector, PROVIDERS, configured
from app.test_generator.factory import get_test_generator
from app.test_generator.baselines import get_suite_generator
from app.test_generator.quality import RuleBasedTestQualityValidator

router = APIRouter(prefix="/api/v1")
def ident(prefix: str) -> str: return f"{prefix}{uuid4().hex[:8].upper()}"
def missing(kind: str): raise HTTPException(404, f"{kind} was not found.")
def conversation_schema(db, obj):
    messages = db.scalars(select(MessageModel).where(MessageModel.conversation_id == obj.id).order_by(MessageModel.timestamp)).all()
    return Conversation(conversation_id=obj.id, created_at=obj.created_at, authorised=obj.authorised, messages=[ConversationMessage(message_id=m.id, role=m.role, content=m.content, timestamp=m.timestamp) for m in messages])
def memory_schema(db, obj):
    rels = db.scalars(select(MemoryRelationshipModel).where(MemoryRelationshipModel.memory_id == obj.id)).all()
    return Memory(memory_id=obj.id, conversation_id=obj.conversation_id, canonical_value=obj.canonical_value, status=obj.status, source_message_ids=obj.source_message_ids, timestamp=obj.timestamp, relationships=[MemoryRelationship(relationship_id=r.id, type=r.relationship_type, target_memory_id=r.target_memory_id) for r in rels])
def audit_schema(obj):
    return AuditRun(run_id=obj.id, conversation_id=obj.conversation_id, experiment_id=obj.experiment_id, status=obj.status, target_configuration=obj.target_configuration, provider=obj.provider, model=obj.model, temperature=obj.temperature, random_seed=obj.random_seed, test_budget=obj.test_budget, prompt_template_version=obj.prompt_template_version, pipeline_provider=obj.pipeline_provider, pipeline_model=obj.pipeline_model, evaluator_provider=obj.evaluator_provider, evaluator_model=obj.evaluator_model, memory_strategy=obj.memory_strategy, created_at=obj.created_at, completed_at=obj.completed_at)
def experiment_schema(obj):
    return Experiment(experiment_id=obj.id, conversation_id=obj.conversation_id, label=obj.label, status=obj.status, test_suite_configuration=TestSuiteConfiguration.model_validate(obj.test_suite_configuration), test_suite_metadata=TestSuiteMetadata.model_validate(obj.test_suite_metadata), test_suite_source_run_id=obj.test_suite_source_run_id, created_at=obj.created_at, completed_at=obj.completed_at)
def test_schema(o): return TestCase(test_id=o.id, run_id=o.run_id, dimension=o.dimension, prompt=o.prompt, expected_behavior=o.expected_behavior, supporting_memory_ids=o.supporting_memory_ids, generator_version=o.generator_version, test_type=o.test_type, quality_status=o.quality_status, grounding_status=o.grounding_status, validation_notes=o.validation_notes, target_memory_context=o.target_memory_context)
def public_test_schema(o):
    return TestCasePublic(
        test_id=o.id if hasattr(o, "id") else o.test_id, run_id=o.run_id,
        dimension=o.dimension, prompt=o.prompt, expected_behavior=o.expected_behavior,
        supporting_memory_ids=o.supporting_memory_ids, generator_version=o.generator_version,
        test_type=o.test_type, quality_status=o.quality_status,
        grounding_status=o.grounding_status, validation_notes=o.validation_notes,
    )
def response_schema(o): return TargetResponse(response_id=o.id, test_id=o.test_id, run_id=o.run_id, response_text=o.response_text, model=o.model, temperature=o.temperature, created_at=o.created_at)
def eval_schema(o): return EvaluationResult(evaluation_id=o.id, test_id=o.test_id, response_id=o.response_id, passed=o.passed, failure_type=o.failure_type, reason=o.reason, evidence_memory_ids=o.evidence_memory_ids, evaluator=o.evaluator)
def require_state(run, allowed: set[AuditStatus]):
    if AuditStatus(run.status) not in allowed:
        raise HTTPException(status_code=409, detail=f"Audit is {run.status}; this action is not valid at this stage.")

@router.get("/health")
def health(): return {"status": "ok", "service": "AI Memory Health Auditor"}
@router.get("/target-providers", response_model=list[ProviderOption])
def target_providers():
    return [ProviderOption(provider=provider, label=label, default_model=model, configured=configured(provider), description=description) for provider, (label, model, description) in PROVIDERS.items()]

@router.post("/conversations", response_model=Conversation, status_code=201)
def create_conversation(payload: ConversationCreate, db: Session = Depends(get_db)):
    if not payload.authorised: raise HTTPException(422, "Authorisation is required before conversation data can be processed.")
    if not payload.pasted_text and not payload.messages: raise HTTPException(422, "Provide pasted conversation text or structured messages.")
    c = ConversationModel(id=ident("C"), authorised=True); db.add(c); db.flush()
    messages = payload.messages or [ConversationMessage(message_id="MSG001", role="user", content=payload.pasted_text or "", timestamp=datetime.now(timezone.utc))]
    for i, m in enumerate(messages, 1): db.add(MessageModel(id=m.message_id or f"MSG{i:03d}", conversation_id=c.id, role=m.role, content=m.content, timestamp=m.timestamp))
    db.commit(); db.refresh(c); return conversation_schema(db, c)
@router.get("/conversations/{conversation_id}", response_model=Conversation)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    c = db.get(ConversationModel, conversation_id)
    if not c: missing("Conversation")
    return conversation_schema(db, c)
@router.post("/conversations/{conversation_id}/extract", response_model=list[Memory])
def extract(conversation_id: str, db: Session = Depends(get_db)):
    c = db.get(ConversationModel, conversation_id)
    if not c: missing("Conversation")
    existing = db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == conversation_id)).all()
    if existing: return [memory_schema(db, x) for x in existing]
    for m in get_memory_extractor().extract(conversation_schema(db, c)):
        db.add(MemoryModel(id=m.memory_id, conversation_id=m.conversation_id, canonical_value=m.canonical_value, status=m.status.value, source_message_ids=m.source_message_ids, timestamp=m.timestamp))
        for r in m.relationships: db.add(MemoryRelationshipModel(id=ident("MR"), memory_id=m.memory_id, relationship_type=r.type.value, target_memory_id=r.target_memory_id))
    db.commit(); return [memory_schema(db, x) for x in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == conversation_id)).all()]
@router.get("/conversations/{conversation_id}/memories", response_model=list[Memory])
def memories(conversation_id: str, db: Session = Depends(get_db)):
    return [memory_schema(db, x) for x in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == conversation_id)).all()]
@router.post("/memories", response_model=Memory, status_code=201)
def add_memory(payload: MemoryCreate, db: Session = Depends(get_db)):
    if not db.get(ConversationModel, payload.conversation_id): missing("Conversation")
    m = MemoryModel(id=ident("M"), conversation_id=payload.conversation_id, canonical_value=payload.canonical_value, status="candidate", source_message_ids=payload.source_message_ids, timestamp=payload.timestamp); db.add(m); db.flush()
    for r in payload.relationships: db.add(MemoryRelationshipModel(id=ident("MR"), memory_id=m.id, relationship_type=r.type.value, target_memory_id=r.target_memory_id))
    db.commit(); return memory_schema(db,m)
@router.patch("/memories/{memory_id}", response_model=Memory)
def patch_memory(memory_id: str, payload: MemoryUpdate, db: Session = Depends(get_db)):
    m=db.get(MemoryModel,memory_id)
    if not m: missing("Memory")
    if payload.canonical_value is not None: m.canonical_value=payload.canonical_value
    if payload.status is not None: m.status=payload.status.value
    if payload.relationships is not None:
        for r in db.scalars(select(MemoryRelationshipModel).where(MemoryRelationshipModel.memory_id==m.id)).all(): db.delete(r)
        for r in payload.relationships: db.add(MemoryRelationshipModel(id=ident("MR"), memory_id=m.id, relationship_type=r.type.value, target_memory_id=r.target_memory_id))
    db.commit(); return memory_schema(db,m)
@router.delete("/memories/{memory_id}", status_code=204)
def reject_memory(memory_id: str, db: Session = Depends(get_db)):
    m=db.get(MemoryModel,memory_id)
    if not m: missing("Memory")
    m.status="rejected"; db.commit()
@router.post("/conversations/{conversation_id}/confirm-ground-truth", response_model=list[Memory])
def confirm_ground_truth(conversation_id: str, payload: GroundTruthConfirm, db: Session = Depends(get_db)):
    rows=db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==conversation_id)).all()
    if not rows: raise HTTPException(409, "Extract candidate memories before confirming ground truth.")
    for m in rows:
        if m.id in payload.confirmed_memory_ids and m.status == "candidate": m.status="confirmed"
    if not any(m.status in ("confirmed", "edited") for m in rows): raise HTTPException(422, "Confirm or edit at least one memory.")
    db.commit(); return [memory_schema(db,m) for m in rows]

@router.post("/experiments", response_model=Experiment, status_code=201)
def create_experiment(payload: ExperimentCreate, db: Session = Depends(get_db)):
    if not db.get(ConversationModel, payload.conversation_id): missing("Conversation")
    confirmed = db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == payload.conversation_id, MemoryModel.status.in_(["confirmed", "edited"]))).all()
    if not confirmed: raise HTTPException(409, "Confirm ground truth before creating an experiment.")
    experiment = ExperimentModel(
        id=ident("EXP"), conversation_id=payload.conversation_id, label=payload.label,
        status=ExperimentStatus.CREATED.value,
        test_suite_configuration=payload.test_suite_configuration.model_dump(mode="json"),
        test_suite_metadata=TestSuiteMetadata().model_dump(mode="json"),
    )
    db.add(experiment); db.commit(); db.refresh(experiment)
    return experiment_schema(experiment)

@router.get("/experiments", response_model=list[Experiment])
def list_experiments(db: Session = Depends(get_db)):
    """Return reproducible comparison groups, newest first.

    Individual audit runs stay available through ``/audits``; this endpoint is
    deliberately group-oriented so the UI never presents unrelated completed
    runs as a controlled experiment.
    """
    rows = db.scalars(select(ExperimentModel).order_by(ExperimentModel.created_at.desc())).all()
    return [experiment_schema(row) for row in rows]

@router.post("/audits", response_model=AuditRun, status_code=201)
def create_audit(payload: AuditCreate, db: Session = Depends(get_db)):
    if not db.get(ConversationModel,payload.conversation_id): missing("Conversation")
    experiment = db.get(ExperimentModel, payload.experiment_id) if payload.experiment_id else None
    if payload.experiment_id and not experiment: missing("Experiment")
    if experiment and experiment.conversation_id != payload.conversation_id:
        raise HTTPException(422, "An audit run must use the experiment's conversation.")
    confirmed=db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==payload.conversation_id, MemoryModel.status.in_(["confirmed","edited"]))).all()
    if not confirmed: raise HTTPException(409, "Confirm ground truth before creating an audit.")
    default_model=PROVIDERS[payload.provider][1]
    model=payload.model if payload.model not in ("", "rule-based-target-ai") or payload.provider == TargetProvider.RULE_BASED else default_model
    suite = TestSuiteConfiguration.model_validate(experiment.test_suite_configuration) if experiment else None
    selected_pipeline_provider = suite.pipeline_provider.value if suite else (payload.pipeline_provider.value if payload.pipeline_provider else pipeline_provider())
    selected_evaluator_provider, selected_evaluator_model = configured_evaluator(
        payload.evaluator_provider.value if payload.evaluator_provider else None, payload.evaluator_model,
    )
    selected_strategy = payload.memory_strategy or (MemoryStrategy.WEAK_FIRST_HIT if payload.target_configuration == TargetConfiguration.WEAK else MemoryStrategy.STRONG_RULE_BASED)
    a=AuditRunModel(id=ident("RUN"), conversation_id=payload.conversation_id, experiment_id=payload.experiment_id, status="CREATED", target_configuration=payload.target_configuration.value, provider=payload.provider.value, model=model, temperature=payload.temperature, random_seed=suite.random_seed if suite else payload.random_seed, test_budget=suite.test_budget if suite else payload.test_budget, prompt_template_version=suite.prompt_template_version if suite else payload.prompt_template_version, pipeline_provider=selected_pipeline_provider, pipeline_model=suite.pipeline_model if suite else (payload.pipeline_model or configured_pipeline_model(selected_pipeline_provider)), evaluator_provider=selected_evaluator_provider, evaluator_model=selected_evaluator_model, memory_strategy=selected_strategy.value)
    db.add(a); db.commit(); db.refresh(a); return audit_schema(a)
@router.get("/audits", response_model=list[AuditRun])
def list_audits(db: Session = Depends(get_db)): return [audit_schema(a) for a in db.scalars(select(AuditRunModel).order_by(AuditRunModel.created_at.desc())).all()]
@router.get("/audits/{run_id}", response_model=AuditRun)
def get_audit(run_id: str, db: Session = Depends(get_db)):
    a=db.get(AuditRunModel,run_id)
    if not a: missing("Audit")
    return audit_schema(a)

def persist_generated_tests(db: Session, run: AuditRunModel, generated: list[TestCaseModel | TestCase]) -> list[TestCaseModel]:
    """Persist a suite with globally unique IDs; generator-local IDs are not DB IDs."""
    rows: list[TestCaseModel] = []
    for test in generated:
        row = TestCaseModel(id=ident("T"), run_id=run.id, dimension=test.dimension.value if isinstance(test.dimension, Dimension) else test.dimension, prompt=test.prompt, expected_behavior=test.expected_behavior, supporting_memory_ids=test.supporting_memory_ids, generator_version=test.generator_version, test_type=test.test_type.value if isinstance(test.test_type, TestType) else test.test_type, quality_status=test.quality_status.value if isinstance(test.quality_status, TestQualityStatus) else test.quality_status, grounding_status=test.grounding_status.value if isinstance(test.grounding_status, GroundingStatus) else test.grounding_status, validation_notes=test.validation_notes, target_memory_context=test.target_memory_context)
        db.add(row); rows.append(row)
    db.flush()
    return rows

def clone_shared_suite(db: Session, source_tests: list[TestCaseModel], run: AuditRunModel) -> list[TestCaseModel]:
    """Give a peer run an isolated copy of the exact canonical suite."""
    clones: list[TestCaseModel] = []
    for source in source_tests:
        clone = TestCaseModel(id=ident("T"), run_id=run.id, suite_test_id=source.id, dimension=source.dimension, prompt=source.prompt, expected_behavior=source.expected_behavior, supporting_memory_ids=list(source.supporting_memory_ids), generator_version=source.generator_version, test_type=source.test_type, quality_status=source.quality_status, grounding_status=source.grounding_status, validation_notes=source.validation_notes, target_memory_context=[])
        db.add(clone); clones.append(clone)
    db.flush()
    return clones

def canonical_test_for_review(db: Session, run: AuditRunModel, test_id: str) -> TestCaseModel:
    """Resolve a test to an experiment's canonical suite member.

    Reviewer edits always target that canonical row and are then copied to its
    peer-run clones.  This prevents one model condition from receiving a
    different question after the experiment suite has been frozen.
    """
    test = db.get(TestCaseModel, test_id)
    if not test:
        missing("Test case")
    if test.run_id != run.id:
        experiment = db.get(ExperimentModel, run.experiment_id) if run.experiment_id else None
        if not experiment or test.run_id != experiment.test_suite_source_run_id:
            missing("Test case")
    source = db.get(TestCaseModel, test.suite_test_id) if test.suite_test_id else test
    if not source:
        raise HTTPException(409, "The canonical test suite record is unavailable.")
    return source

def sync_canonical_test(db: Session, source: TestCaseModel) -> list[TestCaseModel]:
    """Copy the source test's review/revision to every cloned peer row."""
    peers = db.scalars(select(TestCaseModel).where(TestCaseModel.suite_test_id == source.id)).all()
    for peer in peers:
        peer.dimension = source.dimension
        peer.prompt = source.prompt
        peer.expected_behavior = source.expected_behavior
        peer.supporting_memory_ids = list(source.supporting_memory_ids)
        peer.generator_version = source.generator_version
        peer.test_type = source.test_type
        peer.quality_status = source.quality_status
        peer.grounding_status = source.grounding_status
        peer.validation_notes = source.validation_notes
        # This must be empty before execution.  It is only ever computed by
        # the independent target store for the specific peer run.
        peer.target_memory_context = []
    return [source, *peers]

def generated_candidate_for_review(db: Session, source: TestCaseModel) -> TestCase:
    """Produce a replacement candidate using the frozen suite configuration."""
    source_run = db.get(AuditRunModel, source.run_id)
    if not source_run:
        raise HTTPException(409, "The source audit run is unavailable.")
    experiment = db.get(ExperimentModel, source_run.experiment_id) if source_run.experiment_id else None
    memories = [memory_schema(db, row) for row in db.scalars(select(MemoryModel).where(
        MemoryModel.conversation_id == source_run.conversation_id,
        MemoryModel.status.in_(["confirmed", "edited"]),
    )).all()]
    if not memories:
        raise HTTPException(409, "Ground truth is empty.")
    suite_mode = TestSuiteConfiguration.model_validate(experiment.test_suite_configuration).suite_mode if experiment else TestSuiteMode.BEHAVIOURAL
    generator = get_suite_generator(suite_mode, get_test_generator(source_run.pipeline_provider, source_run.pipeline_model))
    candidates = generator.generate(memories, audit_schema(source_run))
    matching = [candidate for candidate in candidates if candidate.dimension.value == source.dimension and candidate.test_type.value == source.test_type]
    # A deterministic baseline can legitimately reproduce the same wording;
    # the review history still records that the reviewer asked for a new pass.
    candidate = next((item for item in matching if item.prompt != source.prompt), None) or (matching[0] if matching else None)
    if not candidate:
        raise HTTPException(422, "The generator could not produce a compatible replacement test.")
    assessment = RuleBasedTestQualityValidator().validate(candidate, memories)
    if assessment.quality_status == TestQualityStatus.REJECTED:
        raise HTTPException(422, f"The replacement test was rejected by the quality gate: {assessment.reason}")
    return candidate.model_copy(update={
        "quality_status": TestQualityStatus.PENDING,
        "grounding_status": assessment.grounding_status,
        "validation_notes": f"{assessment.validator_version}: regenerated for human review — {assessment.reason}",
        "target_memory_context": [],
    })

@router.post("/audits/{run_id}/generate-tests", response_model=list[TestCasePublic])
def generate(run_id: str, db: Session=Depends(get_db)):
    a=db.get(AuditRunModel,run_id)
    if not a: missing("Audit")
    if a.status == AuditStatus.TESTS_GENERATED.value:
        return [public_test_schema(test) for test in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id)).all()]
    require_state(a,{AuditStatus.CREATED})
    experiment = db.get(ExperimentModel, a.experiment_id) if a.experiment_id else None
    if experiment and experiment.test_suite_source_run_id:
        source_tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == experiment.test_suite_source_run_id).order_by(TestCaseModel.id)).all()
        cloned = clone_shared_suite(db, source_tests, a)
        a.status = "TESTS_GENERATED"; db.commit()
        return [public_test_schema(test) for test in cloned]
    memories=[memory_schema(db,m) for m in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==a.conversation_id,MemoryModel.status.in_(["confirmed","edited"]))).all()]
    if not memories: raise HTTPException(409,"Ground truth is empty.")
    # Baseline suites and behavioural suites share the same persisted contract.
    # The selected mode was frozen at experiment creation, before any model run.
    suite_mode = TestSuiteConfiguration.model_validate(experiment.test_suite_configuration).suite_mode if experiment else TestSuiteMode.BEHAVIOURAL
    generator = get_suite_generator(suite_mode, get_test_generator(a.pipeline_provider, a.pipeline_model))
    generated = generator.generate(memories, audit_schema(a))
    validator = RuleBasedTestQualityValidator()
    tests: list[TestCase] = []
    for test in generated:
        assessment = validator.validate(test, memories)
        if assessment.quality_status == TestQualityStatus.REJECTED:
            raise HTTPException(422, f"Generated test {test.test_id} was rejected by the quality gate: {assessment.reason}")
        tests.append(test.model_copy(update={
            "quality_status": assessment.quality_status,
            "grounding_status": assessment.grounding_status,
            "validation_notes": f"{assessment.validator_version}: {assessment.reason}",
        }))
    persisted = persist_generated_tests(db, a, tests)
    a.status="TESTS_GENERATED"
    if experiment:
        experiment.test_suite_source_run_id = a.id
        experiment.status = ExperimentStatus.TEST_SUITE_GENERATED.value
        experiment.test_suite_metadata = TestSuiteMetadata(
            test_count=len(persisted), dimensions=list(dict.fromkeys(Dimension(test.dimension) for test in persisted)),
            generator_version=persisted[0].generator_version if persisted else None, generated_at=datetime.now(timezone.utc),
        ).model_dump(mode="json")
        peers = db.scalars(select(AuditRunModel).where(AuditRunModel.experiment_id == experiment.id, AuditRunModel.id != a.id, AuditRunModel.status == "CREATED")).all()
        for peer in peers:
            clone_shared_suite(db, persisted, peer)
            peer.status = "TESTS_GENERATED"
    db.commit(); return [public_test_schema(test) for test in persisted]
@router.get("/audits/{run_id}/tests", response_model=list[TestCasePublic])
def tests(run_id:str,db:Session=Depends(get_db)):
    if not db.get(AuditRunModel, run_id): missing("Audit")
    return [public_test_schema(t) for t in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==run_id)).all()]

@router.get("/audits/{run_id}/test-review", response_model=TestReviewSuite)
def test_review_suite(run_id: str, db: Session = Depends(get_db)):
    """Expose the frozen test suite for researcher review before execution.

    A peer audit points at the same canonical source suite, so this route
    always returns source test IDs.  It never includes target-memory context.
    """
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    require_state(audit, {AuditStatus.TESTS_GENERATED})
    experiment = db.get(ExperimentModel, audit.experiment_id) if audit.experiment_id else None
    source_run_id = experiment.test_suite_source_run_id if experiment and experiment.test_suite_source_run_id else run_id
    source_tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == source_run_id).order_by(TestCaseModel.id)).all()
    return TestReviewSuite(run_id=run_id, canonical_run_id=source_run_id, tests=[public_test_schema(test) for test in source_tests])

@router.patch("/audits/{run_id}/tests/{test_id}/review", response_model=TestCasePublic)
def review_test(run_id: str, test_id: str, payload: TestReviewUpdate, db: Session = Depends(get_db)):
    """Accept or reject a canonical test and synchronise every peer copy."""
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    require_state(audit, {AuditStatus.TESTS_GENERATED})
    if payload.quality_status == TestQualityStatus.PENDING:
        raise HTTPException(422, "Choose accepted or rejected for a test review decision.")
    source = canonical_test_for_review(db, audit, test_id)
    source.quality_status = payload.quality_status.value
    review_note = payload.note.strip() if payload.note else "No reviewer note provided."
    source.validation_notes = f"Human review: {payload.quality_status.value}. {review_note}"
    sync_canonical_test(db, source)
    db.commit(); db.refresh(source)
    return public_test_schema(source)

@router.post("/audits/{run_id}/tests/{test_id}/regenerate", response_model=TestCasePublic)
def regenerate_test(run_id: str, test_id: str, db: Session = Depends(get_db)):
    """Replace one canonical test, then keep every comparison condition equal."""
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    require_state(audit, {AuditStatus.TESTS_GENERATED})
    source = canonical_test_for_review(db, audit, test_id)
    replacement = generated_candidate_for_review(db, source)
    source.dimension = replacement.dimension.value
    source.prompt = replacement.prompt
    source.expected_behavior = replacement.expected_behavior
    source.supporting_memory_ids = list(replacement.supporting_memory_ids)
    source.generator_version = replacement.generator_version
    source.test_type = replacement.test_type.value
    source.quality_status = replacement.quality_status.value
    source.grounding_status = replacement.grounding_status.value
    source.validation_notes = replacement.validation_notes
    source.target_memory_context = []
    sync_canonical_test(db, source)
    db.commit(); db.refresh(source)
    return public_test_schema(source)

@router.post("/audits/{run_id}/execute", response_model=list[TargetResponse])
def execute(run_id:str,db:Session=Depends(get_db)):
    a=db.get(AuditRunModel,run_id)
    if not a: missing("Audit")
    require_state(a,{AuditStatus.TESTS_GENERATED})
    review_rows = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id)).all()
    if any(test.quality_status == TestQualityStatus.REJECTED.value for test in review_rows):
        raise HTTPException(409, "Resolve rejected tests by regenerating or accepting them before execution.")
    if any(test.quality_status == TestQualityStatus.PENDING.value for test in review_rows):
        raise HTTPException(409, "Review each regenerated test before execution.")
    outputs=[]
    try:
        # The controlled target independently ingests the authorised source
        # conversation into its private persistent store.  It never receives
        # reviewer-confirmed ground truth as retrieval context.
        conversation = conversation_schema(db, db.get(ConversationModel, a.conversation_id))
        target_store = SqlTargetMemoryStore(db, extractor=get_target_memory_writer(a.pipeline_provider, a.pipeline_model))
        completed_test_ids = set(db.scalars(select(TargetResponseModel.test_id).where(TargetResponseModel.run_id == run_id)).all())
        for t in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==run_id)).all():
            if t.id in completed_test_ids:
                continue
            retrieval = target_store.retrieve(run_id, conversation, test_schema(t), MemoryStrategy(a.memory_strategy))
            private_test = test_schema(t).model_copy(update={"target_memory_context": retrieval.context})
            t.target_memory_context = private_test.target_memory_context
            r=HttpTargetAIConnector().execute(private_test,audit_schema(a)); outputs.append(r); db.add(TargetResponseModel(id=r.response_id,test_id=r.test_id,run_id=r.run_id,response_text=r.response_text,model=r.model,temperature=r.temperature,created_at=r.created_at))
    except HTTPException:
        a.status="FAILED"; db.commit()
        raise
    a.status="TESTS_EXECUTED"; db.commit(); return outputs
@router.post("/audits/{run_id}/evaluate", response_model=list[EvaluationResult])
def evaluate(run_id:str,db:Session=Depends(get_db)):
    a=db.get(AuditRunModel,run_id)
    if not a: missing("Audit")
    require_state(a,{AuditStatus.TESTS_EXECUTED})
    mems=[memory_schema(db,m) for m in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==a.conversation_id)).all()]; outputs=[]
    try:
        completed_test_ids = set(db.scalars(select(EvaluationResultModel.test_id).join(TestCaseModel).where(TestCaseModel.run_id == run_id)).all())
        for t in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==run_id)).all():
            if t.id in completed_test_ids:
                continue
            r=db.scalar(select(TargetResponseModel).where(TargetResponseModel.test_id==t.id)); e=get_behaviour_evaluator(a.evaluator_provider, a.evaluator_model).evaluate(test_schema(t),response_schema(r),mems); outputs.append(e); db.add(EvaluationResultModel(id=e.evaluation_id,test_id=e.test_id,response_id=e.response_id,passed=e.passed,failure_type=e.failure_type.value if e.failure_type else None,reason=e.reason,evidence_memory_ids=e.evidence_memory_ids,evaluator=e.evaluator))
    except HTTPException:
        a.status="FAILED"; db.commit()
        raise
    a.status="COMPLETED"; a.completed_at=datetime.now(timezone.utc)
    if a.experiment_id:
        experiment = db.get(ExperimentModel, a.experiment_id)
        if experiment:
            statuses = db.scalars(select(AuditRunModel.status).where(AuditRunModel.experiment_id == experiment.id)).all()
            if statuses and all(item in {"COMPLETED", "FAILED"} for item in statuses):
                experiment.status = ExperimentStatus.COMPLETED.value
                experiment.completed_at = datetime.now(timezone.utc)
    db.commit(); return outputs

@router.get("/audits/{run_id}/retry-plan")
def retry_plan(run_id: str, db: Session = Depends(get_db)):
    """Report the next idempotent recovery stage without exposing provider details."""
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    tests_count = len(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id)).all())
    responses_count = len(db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == run_id)).all())
    evaluations_count = len(db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id == run_id)).all())
    if tests_count == 0:
        return {"run_id": run_id, "next_stage": "generate_tests", "pending": 0, "retryable": audit.status != "COMPLETED"}
    if responses_count < tests_count:
        return {"run_id": run_id, "next_stage": "execute_tests", "pending": tests_count - responses_count, "retryable": True}
    if evaluations_count < tests_count:
        return {"run_id": run_id, "next_stage": "evaluate_responses", "pending": tests_count - evaluations_count, "retryable": True}
    return {"run_id": run_id, "next_stage": None, "pending": 0, "retryable": False}

@router.post("/audits/{run_id}/retry", response_model=AuditRun)
def retry_audit(run_id: str, db: Session = Depends(get_db)):
    """Resume only the incomplete durable stage of an interrupted audit."""
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    plan = retry_plan(run_id, db)
    if not plan["retryable"]:
        return audit_schema(audit)
    if plan["next_stage"] == "generate_tests":
        audit.status = "CREATED"; db.commit(); generate(run_id, db)
    elif plan["next_stage"] == "execute_tests":
        audit.status = "TESTS_GENERATED"; db.commit(); execute(run_id, db)
    else:
        audit.status = "TESTS_EXECUTED"; db.commit(); evaluate(run_id, db)
    db.refresh(audit)
    return audit_schema(audit)
def result_for(run_id,db):
    a=db.get(AuditRunModel,run_id)
    if not a: missing("Audit")
    if a.status != "COMPLETED": raise HTTPException(409,"Results are available after evaluation is complete.")
    ts={t.id: test_schema(t) for t in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==run_id)).all()}; rs={r.id: response_schema(r) for r in db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id==run_id)).all()}; es=[eval_schema(e) for e in db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id==run_id)).all()]
    overall, dimensions=MetricsService().calculate(es,{k:v.dimension for k,v in ts.items()}); failures=[]
    for e in es:
        if not e.passed:
            evidence=[memory_schema(db,m) for m in db.scalars(select(MemoryModel).where(MemoryModel.id.in_(e.evidence_memory_ids))).all()]
            failures.append(FailureDetail(failure_id=e.evaluation_id,test=TestCasePublic(**ts[e.test_id].model_dump(exclude={"target_memory_context"})),response=rs[e.response_id],evaluation=e,evidence=evidence))
    return AuditResult(run_id=run_id,overall_score=overall,tests_passed=sum(e.passed for e in es),tests_total=len(es),dimensions=dimensions,failures=failures)
@router.get("/audits/{run_id}/results", response_model=AuditResult)
def results(run_id:str,db:Session=Depends(get_db)): return result_for(run_id,db)

def target_trace_record_schema(db: Session, record: TargetAgentMemoryModel) -> TargetMemoryTraceRecord:
    relationships = db.scalars(select(TargetAgentMemoryRelationshipModel).where(
        TargetAgentMemoryRelationshipModel.memory_id == record.id
    )).all()
    return TargetMemoryTraceRecord(
        memory_id=record.id, canonical_value=record.canonical_value,
        lifecycle_state=record.lifecycle_state,
        source_message_ids=list(record.source_message_ids), observed_at=record.observed_at,
        write_order=record.write_order,
        relationships=[MemoryRelationship(
            relationship_id=item.id, type=item.relationship_type,
            target_memory_id=item.target_memory_id,
        ) for item in relationships],
    )

def safe_trace_event_schema(event: TargetAgentMemoryEventModel) -> TargetMemoryTraceEvent:
    """Remove raw private values from event payloads; records carry values post-audit."""
    allowed = {
        "conversation_id", "message_count", "write_order", "supersedes_memory_id",
        "overrides_memory_id", "conflicts_with_memory_id", "test_id", "strategy",
        "selected_memory_ids", "writer_version",
    }
    details = {key: value for key, value in (event.details or {}).items() if key in allowed}
    return TargetMemoryTraceEvent(
        event_id=event.id, event_type=event.event_type, memory_id=event.memory_id,
        source_message_ids=list(event.source_message_ids), details=details,
        created_at=event.created_at,
    )

@router.get("/audits/{run_id}/target-memory-trace", response_model=TargetMemoryTrace)
def target_memory_trace(run_id: str, db: Session = Depends(get_db)):
    """Show the controlled agent's independent store only after audit completion.

    This is intentionally distinct from ground truth and omits evaluator-only
    expected behaviour and target runtime context.  It is unavailable while a
    target can still use the test suite, avoiding premature leakage.
    """
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    if audit.status != AuditStatus.COMPLETED.value:
        raise HTTPException(409, "Target memory evidence is available after the audit is complete.")
    records = db.scalars(select(TargetAgentMemoryModel).where(
        TargetAgentMemoryModel.run_id == run_id
    ).order_by(TargetAgentMemoryModel.write_order)).all()
    events = db.scalars(select(TargetAgentMemoryEventModel).where(
        TargetAgentMemoryEventModel.run_id == run_id
    ).order_by(TargetAgentMemoryEventModel.created_at, TargetAgentMemoryEventModel.id)).all()
    retrievals = db.scalars(select(TargetAgentRetrievalModel).where(
        TargetAgentRetrievalModel.run_id == run_id
    ).order_by(TargetAgentRetrievalModel.created_at, TargetAgentRetrievalModel.id)).all()
    return TargetMemoryTrace(
        run_id=run_id, memory_strategy=audit.memory_strategy,
        records=[target_trace_record_schema(db, record) for record in records],
        events=[safe_trace_event_schema(event) for event in events],
        retrievals=[TargetMemoryTraceRetrieval(
            retrieval_id=item.id, test_id=item.test_id, strategy=item.strategy,
            selected_memory_ids=list(item.selected_memory_ids),
            ranking_evidence=list(item.ranking_evidence), created_at=item.created_at,
        ) for item in retrievals],
    )

@router.get("/audits/{run_id}/failures/{failure_id}", response_model=FailureDetail)
def failure(run_id:str,failure_id:str,db:Session=Depends(get_db)):
    item=next((f for f in result_for(run_id,db).failures if f.failure_id==failure_id),None)
    if not item: missing("Failure")
    return item

def experiment_analytics_for(experiment_id: str, db: Session) -> ExperimentAnalytics:
    """Return a completed/pending group without conflating unrelated audits."""
    experiment = db.get(ExperimentModel, experiment_id)
    if not experiment:
        missing("Experiment")
    run_models = db.scalars(
        select(AuditRunModel)
        .where(AuditRunModel.experiment_id == experiment_id)
        .order_by(AuditRunModel.created_at, AuditRunModel.id)
    ).all()
    runs = [audit_schema(run) for run in run_models]
    results_by_run = {run.run_id: result_for(run.run_id, db) for run in runs if run.status == AuditStatus.COMPLETED}
    service = ExperimentAnalyticsService()
    return ExperimentAnalytics(
        experiment=experiment_schema(experiment),
        runs=[ExperimentRunReport(run=run, result=results_by_run.get(run.run_id)) for run in runs],
        conditions=service.condition_summaries(runs, results_by_run),
        paired_comparisons=service.paired_comparisons(db, runs),
    )

@router.get("/experiments/{experiment_id}/results", response_model=ExperimentAnalytics)
def experiment_results(experiment_id: str, db: Session = Depends(get_db)):
    """Fair-comparison history with per-condition reports and paired outcomes."""
    return experiment_analytics_for(experiment_id, db)

@router.get("/experiments/{experiment_id}/export.csv")
def export_experiment_csv(experiment_id: str, db: Session = Depends(get_db)):
    """Download a portable group-level report without exposing private memory traces."""
    analytics = experiment_analytics_for(experiment_id, db)
    content = StringIO()
    writer = csv.writer(content)
    writer.writerow(["record_type", "experiment_id", "condition", "run_id", "dimension", "metric", "value", "detail"])
    for condition in analytics.conditions:
        writer.writerow(["condition", experiment_id, condition.label, "", "", "planned_runs", condition.planned_runs, ""])
        writer.writerow(["condition", experiment_id, condition.label, "", "", "completed_runs", condition.completed_runs, ""])
        writer.writerow(["condition", experiment_id, condition.label, "", "", "failed_runs", condition.failed_runs, ""])
        writer.writerow(["condition", experiment_id, condition.label, "", "", "overall_mean", condition.overall_mean, ""])
        writer.writerow(["condition", experiment_id, condition.label, "", "", "overall_standard_deviation", condition.overall_standard_deviation, ""])
        for score in condition.dimensions:
            writer.writerow(["dimension", experiment_id, condition.label, "", score.dimension.value, "mean_percentage", score.mean_percentage, f"{score.passed}/{score.total} over {score.measured_runs} run(s)"])
    for report in analytics.runs:
        run, result = report.run, report.result
        writer.writerow(["run", experiment_id, "", run.run_id, "", "status", run.status.value, ""])
        if result:
            writer.writerow(["run", experiment_id, "", run.run_id, "", "overall_score", result.overall_score, f"{result.tests_passed}/{result.tests_total} tests passed"])
            for failed in result.failures:
                writer.writerow(["failure", experiment_id, "", run.run_id, failed.test.dimension.value, "detected_failure", "FAIL", failed.evaluation.reason])
    for pair in analytics.paired_comparisons:
        detail = f"reference={pair.reference_run_id}; both_passed={pair.both_passed}; both_failed={pair.both_failed}; reference_only={pair.reference_only_passed}; candidate_only={pair.candidate_only_passed}; bootstrap_95_ci=[{pair.candidate_delta_confidence_interval_low}, {pair.candidate_delta_confidence_interval_high}]; exact_sign_p={pair.two_sided_sign_test_p_value}"
        writer.writerow(["paired_comparison", experiment_id, pair.candidate_label, pair.candidate_run_id, "", "delta_percentage_points", pair.candidate_delta_percentage_points, detail])
    filename = f"experiment-{experiment_id}-results.csv"
    return StreamingResponse(iter([content.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@router.get("/experiments/summary", response_model=list[ExperimentResult])
def experiments(db: Session = Depends(get_db)):
    runs = db.scalars(select(AuditRunModel).where(AuditRunModel.status == "COMPLETED")).all()
    grouped: dict[str, list[float]] = {"weak": [], "strong": []}
    for run in runs:
        tests = {t.id: Dimension(t.dimension) for t in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run.id)).all()}
        evaluations = [eval_schema(e) for e in db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id == run.id)).all()]
        score, _ = MetricsService().calculate(evaluations, tests)
        if score is not None: grouped[run.target_configuration].append(score)
    if not grouped["weak"] or not grouped["strong"]: return []
    return [ExperimentResult(experiment_id="EXP-COMPLETED", label="Completed controlled-run comparison", weak_score=round(sum(grouped["weak"]) / len(grouped["weak"]), 1), strong_score=round(sum(grouped["strong"]) / len(grouped["strong"]), 1), notes="Average Memory Health across completed weak and strong controlled runs.")]
