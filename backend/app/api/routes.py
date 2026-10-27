from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import os
import time
from contextlib import contextmanager
from threading import Lock
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO, StringIO
import csv
import hashlib
import json
import zipfile
from sqlalchemy import delete, select, text, update, func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from app.database.session import SessionLocal, get_db
from app.evaluator.factory import get_behaviour_evaluator
from app.extraction.factory import get_memory_extractor
from app.extraction.llm import configured_pipeline_model, pipeline_provider
from app.evaluator.factory import configured_evaluator
from app.memory_agent import default_target_memory_writer_kind, get_target_memory_writer
from app.metrics.service import MetricsService
from app.metrics.retrieval_quality import RetrievalQualityService
from app.services.audit_execution import AuditExecutionService, AuditExecutionSnapshot, RunArtifacts
from app.services.experiment_analytics import ExperimentAnalyticsService
from app.services.audit_comparison import compare_audit_evidence
from app.services.runtime_freeze import (
    audit_runtime_signature, assert_audit_runtime_frozen,
    refresh_failed_preexecution_generation, inherit_preexecution_runtime_refresh,
)
from app.services.stage_lock import database_stage_lock, database_stage_busy
from app.services.generation_coverage import assert_generation_coverage, saved_suite_observation
from app.services.reviewer_identity import reviewer_identity, distinct_reviewers, unique_independent_reviews
from app.models import AgentExecutionModel, AssessorComparisonModel, AuditRunModel, ConversationModel, EvaluationHumanReviewModel, EvaluationResultModel, ExperimentModel, MemoryModel, MemoryRelationshipModel, MessageModel, TargetAgentMemoryEventModel, TargetAgentMemoryModel, TargetAgentMemoryRelationshipModel, TargetAgentRetrievalModel, TargetResponseModel, TestCaseModel
from app.schemas.assessor_comparison import AssessorComparisonRequest
from app.schemas.generator_comparison import GeneratorComparisonRequest
from app.models import GeneratorComparisonModel
from app.models import ExtractionComparisonModel
from app.schemas.extraction_comparison import ExtractionComparisonRequest
from app.schemas.model_availability import ModelAvailabilityCheckRequest
from app.services.model_availability import options_and_checks, verified_options, check_model, credential_scope
from app.schemas import *
from app.target_ai.providers import PROVIDERS, configured
from app.target_systems import get_target_system_adapter
from app.target_systems.controlled import ControlledTargetSystemAdapter
from app.test_generator.factory import get_test_generator
from app.test_generator.baselines import get_suite_generator, HumanReviewedFixedTemplateGenerator
from app.test_generator.quality import RuleBasedTestQualityValidator

router = APIRouter(prefix="/api/v1")
_RUN_LOCKS: dict[str, Lock] = {}
_RUN_LOCKS_GUARD = Lock()

@contextmanager
def audit_run_lock(run_id: str, busy_message: str = "This audit stage is already running.", *, db: Session | None = None):
    """Reject duplicate work locally and across PostgreSQL API workers."""
    with _RUN_LOCKS_GUARD:
        lock = _RUN_LOCKS.setdefault(run_id, Lock())
    if not lock.acquire(blocking=False):
        raise HTTPException(409, busy_message)
    try:
        with database_stage_lock(db, run_id, busy_message):
            yield
    finally:
        lock.release()

@contextmanager
def audit_suite_lock(db: Session, run_id: str):
    """Serialise shared-suite edits and execution across PostgreSQL workers."""
    audit = db.get(AuditRunModel, run_id)
    if not audit:
        missing("Audit")
    suite_key = "suite:" + (audit.experiment_id or run_id)
    with audit_run_lock(suite_key, db=db):
        # The initial lookup may predate a peer's commit; re-read under lock.
        db.expire_all()
        yield

def ident(prefix: str) -> str: return f"{prefix}{uuid4().hex.upper()}"
def missing(kind: str): raise HTTPException(404, f"{kind} was not found.")
def ensure_supported_pipeline_role(provider: TargetProvider, role: str) -> None:
    """Keep structured pipeline role selection explicit at API boundaries."""
    if provider not in set(TargetProvider):
        raise HTTPException(422, f"The selected provider cannot perform {role}.")
def conversation_schema(db, obj):
    messages = db.scalars(select(MessageModel).where(MessageModel.conversation_id == obj.id).order_by(MessageModel.sequence, MessageModel.timestamp)).all()
    return Conversation(conversation_id=obj.id, created_at=obj.created_at, authorised=obj.authorised,
        source_origin=getattr(obj, "source_origin", "unknown"),
        extraction_provenance=getattr(obj, "extraction_provenance", None),
        messages=[ConversationMessage(message_id=getattr(m, "source_message_id", None) or m.id, role=m.role, content=m.content, timestamp=m.observation_timestamp, original_timestamp=m.original_timestamp) for m in messages])

_PASTED_ROLE = re.compile(r"^\s*\[(?P<role>[^\]]+)\]\s*(?P<content>.*)$")

def pasted_messages(text: str) -> list[ConversationMessageInput]:
    """Turn the documented one-message-per-line form into ordered records."""
    base = datetime.now(timezone.utc)
    messages: list[ConversationMessageInput] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        matched = _PASTED_ROLE.match(line)
        role = matched.group("role").strip() if matched else "user"
        content = (matched.group("content") if matched else line).strip()
        if content:
            messages.append(ConversationMessageInput(
                message_id=f"MSG{len(messages) + 1:03d}", role=role, content=content,
                timestamp=base + timedelta(microseconds=len(messages)),
            ))
    return messages
def memory_schema(db, obj):
    rels = db.scalars(select(MemoryRelationshipModel).where(MemoryRelationshipModel.memory_id == obj.id)).all()
    return Memory(memory_id=obj.id, conversation_id=obj.conversation_id, canonical_value=obj.canonical_value, status=obj.status, source_message_ids=obj.source_message_ids, timestamp=obj.timestamp, confidence=getattr(obj, "confidence", None), relationships=[MemoryRelationship(relationship_id=r.id, type=r.relationship_type, target_memory_id=r.target_memory_id, evidence_message_ids=getattr(r,"evidence_message_ids",None) or [], confidence=getattr(r,"confidence",None)) for r in rels])


def fingerprint(payload: dict) -> str:
    """Hash public configuration only; never include conversation or secrets."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def reproducibility_snapshot(*, provider: str, model: str, temperature: float, random_seed: int,
                             test_budget: int, prompt_template_version: str, pipeline_provider: str,
                             pipeline_model: str, evaluator_provider: str, evaluator_model: str,
                             semantic_review_provider: str | None = None,
                             semantic_review_model: str | None = None,
                             retrieval_mode: str = "fixed",
                             retrieval_provider: str | None = None,
                             retrieval_model: str | None = None,
                             memory_strategy: str, memory_maintenance_policy: str,
                             target_memory_writer: TargetMemoryWriterKind | str,
                             target_memory_capacity: int,
                             target_system_adapter: TargetSystemAdapterKind | str,
                             target_memory_profile: TargetMemoryProfile | None = None) -> dict:
    """Freeze safe reproducibility facts when a run is created."""
    profile = target_memory_profile or TargetMemoryProfile()
    semantic_review_provider = semantic_review_provider or pipeline_provider
    semantic_review_model = semantic_review_model or (pipeline_model if semantic_review_provider == pipeline_provider
                                                        else configured_pipeline_model(semantic_review_provider))
    if provider != "rule_based" and profile.output_token_limit is None:
        profile = profile.model_copy(update={"output_token_limit": 2048})
    adapter_version = "external-http-v1" if TargetSystemAdapterKind(target_system_adapter) == TargetSystemAdapterKind.EXTERNAL_HTTP else ControlledTargetSystemAdapter.version
    writer_kind = TargetMemoryWriterKind(target_memory_writer)
    writer = get_target_memory_writer(pipeline_provider, pipeline_model, writer_kind)
    writer_version = getattr(writer, "VERSION", writer.__class__.__name__)
    configuration = {
        "provider": provider, "model": model, "temperature": temperature,
        "random_seed": random_seed, "test_budget": test_budget,
        "pipeline_provider": pipeline_provider, "pipeline_model": pipeline_model,
        "semantic_review_provider": semantic_review_provider,
        "semantic_review_model": semantic_review_model,
        "evaluator_provider": evaluator_provider, "evaluator_model": evaluator_model,
        "retrieval_mode": retrieval_mode,
        "retrieval_provider": retrieval_provider,
        "retrieval_model": retrieval_model,
        "retrieval_agent_version": "target-memory-retrieval-agent-v1" if retrieval_mode == "agent" else None,
        "memory_strategy": memory_strategy,
        "memory_maintenance_policy": memory_maintenance_policy,
        "target_memory_capacity": target_memory_capacity,
        "target_memory_writer": writer_kind.value,
        "target_memory_writer_version": writer_version,
        "target_system_adapter": TargetSystemAdapterKind(target_system_adapter).value,
        "target_system_adapter_version": adapter_version,
        "target_memory_profile": profile.model_dump(),
    }
    return {
        "schema_version": "reproducibility-v1",
        "audit_runtime_signature": audit_runtime_signature(),
        "configuration_fingerprint": fingerprint(configuration),
        "prompt_template_fingerprint": fingerprint({
            "prompt_template_version": prompt_template_version,
            "pipeline_provider": pipeline_provider, "pipeline_model": pipeline_model,
            "semantic_review_provider": semantic_review_provider,
            "semantic_review_model": semantic_review_model,
            "evaluator_provider": evaluator_provider, "evaluator_model": evaluator_model,
            "retrieval_mode": retrieval_mode,
            "retrieval_provider": retrieval_provider,
            "retrieval_model": retrieval_model,
            "retrieval_agent_version": "target-memory-retrieval-agent-v1" if retrieval_mode == "agent" else None,
        }),
        "target_memory_writer_version": writer_version,
        "target_memory_writer": writer_kind.value,
        "retrieval_mode": retrieval_mode,
        "retrieval_provider": retrieval_provider,
        "retrieval_model": retrieval_model,
        "retrieval_agent_version": "target-memory-retrieval-agent-v1" if retrieval_mode == "agent" else None,
        "target_system_adapter": TargetSystemAdapterKind(target_system_adapter).value,
        "target_system_adapter_version": adapter_version,
        "target_memory_profile": profile.model_dump(),
        "memory_policy_version": "target-memory-policy-v43",
        # A seed is fully deterministic for the local baseline. Third-party
        # APIs do not share one portable seed contract, so retain it as a
        # configuration identifier rather than implying bit-for-bit replay.
        "seed_control": {
            "target": "deterministic_local" if provider == "rule_based" else "recorded_only",
            "pipeline": "deterministic_local" if pipeline_provider == "rule_based" else "recorded_only",
            "semantic_review": "deterministic_local" if semantic_review_provider == "rule_based" else "recorded_only",
            "evaluator": "deterministic_local" if evaluator_provider == "rule_based" else "recorded_only",
            "retrieval_agent": "recorded_only" if retrieval_mode == "agent" else "deterministic_local",
        },
        "target_retry_policy": {
            "max_attempts": 3, "timeout_seconds": 60.0,
            "retryable_status_codes": [408, 409, 425, 429, 500, 502, 503, 504],
        },
        "execution_budget": {
            "max_target_calls": max(1, int(os.getenv("MAX_AUDIT_TARGET_CALLS", "100"))),
            "max_execution_seconds": max(1, int(os.getenv("MAX_AUDIT_EXECUTION_SECONDS", "300"))),
        },
    }


def audit_schema(obj):
    metadata = getattr(obj, "reproducibility_metadata", {}) or {}
    # Rows created before migration 0011 are deterministic rule-based runs.
    # The fallback is intentional for durable backwards compatibility.
    writer_kind = getattr(obj, "target_memory_writer", None) or metadata.get("target_memory_writer") or "rule_based"
    writer_version = getattr(obj, "target_memory_writer_version", None) or metadata.get("target_memory_writer_version")
    adapter = getattr(obj, "target_system_adapter", None) or metadata.get("target_system_adapter") or "controlled-memory"
    adapter_version = getattr(obj, "target_system_adapter_version", None) or metadata.get("target_system_adapter_version")
    retrieval_mode = getattr(obj, "retrieval_mode", None) or metadata.get("retrieval_mode") or "fixed"
    retrieval_provider = getattr(obj, "retrieval_provider", None) or metadata.get("retrieval_provider")
    retrieval_model = getattr(obj, "retrieval_model", None) or metadata.get("retrieval_model")
    return AuditRun(run_id=obj.id, conversation_id=obj.conversation_id, experiment_id=obj.experiment_id, status=obj.status, target_configuration=obj.target_configuration, provider=obj.provider, model=obj.model, temperature=obj.temperature, random_seed=obj.random_seed, test_budget=obj.test_budget, prompt_template_version=obj.prompt_template_version, pipeline_provider=obj.pipeline_provider, pipeline_model=obj.pipeline_model, semantic_review_provider=getattr(obj, "semantic_review_provider", None), semantic_review_model=getattr(obj, "semantic_review_model", None), evaluator_provider=obj.evaluator_provider, evaluator_model=obj.evaluator_model, retrieval_mode=retrieval_mode, retrieval_provider=retrieval_provider, retrieval_model=retrieval_model, memory_strategy=obj.memory_strategy, memory_maintenance_policy=getattr(obj, "memory_maintenance_policy", "update_aware_consolidation"), target_memory_capacity=getattr(obj, "target_memory_capacity", 50), target_memory_writer=writer_kind, target_memory_writer_version=writer_version, target_system_adapter=adapter, target_system_adapter_version=adapter_version, reproducibility=metadata, target_memory_profile=metadata.get("target_memory_profile", {}), created_at=obj.created_at, completed_at=obj.completed_at)
def experiment_schema(obj, run_receipts=None):
    metadata = dict(obj.test_suite_metadata or {})
    if not metadata.get("study_role") and run_receipts:
        roles = {receipt.get("study_role") for receipt in run_receipts}
        recorded_roles = roles - {None, ""}
        if recorded_roles:
            metadata["study_role"] = next(iter(recorded_roles)) if len(roles) == 1 else "mixed_study"
            sources = {receipt.get("diagnostic_source_run_id") for receipt in run_receipts}
            if len(sources) == 1:
                metadata["diagnostic_source_run_id"] = next(iter(sources))
    return Experiment(experiment_id=obj.id, conversation_id=obj.conversation_id, label=obj.label, status=obj.status, test_suite_configuration=TestSuiteConfiguration.model_validate(obj.test_suite_configuration), test_suite_metadata=TestSuiteMetadata.model_validate(metadata), test_suite_source_run_id=obj.test_suite_source_run_id, created_at=obj.created_at, completed_at=obj.completed_at)
def test_schema(o): return TestCase(test_id=o.id, run_id=o.run_id, dimension=o.dimension, prompt=o.prompt, expected_behavior=o.expected_behavior, supporting_memory_ids=o.supporting_memory_ids, generator_version=o.generator_version, test_type=o.test_type, quality_status=o.quality_status, grounding_status=o.grounding_status, validation_notes=o.validation_notes, human_validity_status=getattr(o, "human_validity_status", "pending"), human_validity_reviewer=getattr(o, "human_validity_reviewer", None), human_validity_note=getattr(o, "human_validity_note", None), human_validity_reviewed_at=getattr(o, "human_validity_reviewed_at", None), probe_group_id=o.probe_group_id, probe_variant=o.probe_variant, target_memory_context=o.target_memory_context)
def public_test_schema(o):
    return TestCasePublic(
        test_id=o.id if hasattr(o, "id") else o.test_id, run_id=o.run_id,
        dimension=o.dimension, prompt=o.prompt, expected_behavior=o.expected_behavior,
        supporting_memory_ids=o.supporting_memory_ids, generator_version=o.generator_version,
        test_type=o.test_type, quality_status=o.quality_status,
        grounding_status=o.grounding_status, validation_notes=o.validation_notes, probe_group_id=o.probe_group_id, probe_variant=o.probe_variant,
        human_validity_status=getattr(o, "human_validity_status", "pending"),
        human_validity_reviewer=getattr(o, "human_validity_reviewer", None),
        human_validity_note=getattr(o, "human_validity_note", None),
        human_validity_reviewed_at=getattr(o, "human_validity_reviewed_at", None),
    )
def validate_memory_evidence(db: Session, conversation_id: str, source_message_ids: list[str], relationships: list[MemoryRelationship], memory_id: str | None = None):
    if len(source_message_ids) != len(set(source_message_ids)):
        raise HTTPException(422, "Source evidence IDs must not be repeated.")
    relationship_keys = [(relationship.type.value, relationship.target_memory_id) for relationship in relationships]
    if len(relationship_keys) != len(set(relationship_keys)):
        raise HTTPException(422, "A memory relationship must not be repeated.")
    source_ids = set(db.scalars(select(MessageModel.source_message_id).where(MessageModel.conversation_id == conversation_id)).all())
    unknown_sources = set(source_message_ids) - source_ids
    if unknown_sources:
        raise HTTPException(422, f"Source evidence references messages outside this conversation: {', '.join(sorted(unknown_sources))}.")
    target_rows = db.scalars(select(MemoryModel.id).where(MemoryModel.conversation_id == conversation_id)).all()
    target_ids = set(target_rows)
    for relationship in relationships:
        if relationship.target_memory_id == memory_id or relationship.target_memory_id not in target_ids:
            raise HTTPException(422, "A memory relationship must reference another memory in the same conversation.")
        cited = relationship.evidence_message_ids
        if len(cited) != len(set(cited)):
            raise HTTPException(422, "Relationship evidence IDs must not be repeated.")
        if not set(cited).issubset(source_ids):
            raise HTTPException(422, "Relationship evidence must reference messages in this conversation.")
        if relationship.confidence is not None and not cited:
            raise HTTPException(422, "A model confidence estimate requires cited relationship evidence.")
        target = db.get(MemoryModel, relationship.target_memory_id)
        endpoint_sources = set(source_message_ids) | set(target.source_message_ids if target else [])
        if cited and not set(cited).issubset(endpoint_sources):
            raise HTTPException(422, "Relationship evidence must support one of its two linked memories.")
    if memory_id is None:
        return

    # UPDATE edges express a version lineage. A cycle would make freshness
    # impossible to reason about (A supersedes B which supersedes A), so reject
    # it at the shared API boundary rather than leaving it to one retrieval
    # strategy to interpret differently.
    update_edges: dict[str, set[str]] = {}
    existing = db.execute(
        select(MemoryRelationshipModel.memory_id, MemoryRelationshipModel.target_memory_id)
        .join(MemoryModel, MemoryModel.id == MemoryRelationshipModel.memory_id)
        .where(MemoryModel.conversation_id == conversation_id, MemoryRelationshipModel.relationship_type == RelationshipType.UPDATE.value)
    ).all()
    for source_id, target_id in existing:
        if source_id != memory_id:
            update_edges.setdefault(source_id, set()).add(target_id)
    for relationship in relationships:
        if relationship.type == RelationshipType.UPDATE:
            update_edges.setdefault(memory_id, set()).add(relationship.target_memory_id)

    visiting: set[str] = set()
    visited: set[str] = set()

    def has_cycle(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(has_cycle(target) for target in update_edges.get(node, set())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    if any(has_cycle(node) for node in update_edges):
        raise HTTPException(422, "UPDATE relationships cannot form a cycle.")
def response_schema(o): return TargetResponse(response_id=o.id, test_id=o.test_id, run_id=o.run_id, response_text=o.response_text, model=o.model, temperature=o.temperature, execution_metadata=getattr(o, "execution_metadata", {}) or {}, created_at=o.created_at)
def eval_schema(o):
    classification = getattr(o, "failure_classification", None)
    # Historical labels inherited the test dimension. Preserve them in storage
    # but never present them as independently observed diagnoses/calibration.
    legacy = classification is None
    return EvaluationResult(evaluation_id=o.id, test_id=o.test_id, response_id=o.response_id,
        passed=o.passed, failure_type=o.failure_type if not legacy and classification.get("status") == "classified" else None,
        reason=o.reason, evidence_memory_ids=o.evidence_memory_ids, evaluator=o.evaluator,
        judge_execution=o.judge_execution,
        failure_classification=classification or {"status": "legacy_test_dimension", "method": "historical_label",
            "reason": "The historical category inherited the test dimension and is not an independently observed diagnosis."})
def human_review_schema(o): return EvaluationHumanReview(review_id=o.id, evaluation_id=o.evaluation_id, human_passed=o.human_passed, human_failure_type=o.human_failure_type, reviewer_label=o.reviewer_label, review_role=getattr(o, "review_role", "reference"), based_on_review_ids=getattr(o, "based_on_review_ids", []) or [], note=o.note, created_at=o.created_at, updated_at=o.updated_at)
def require_state(run, allowed: set[AuditStatus]):
    if AuditStatus(run.status) not in allowed:
        raise HTTPException(status_code=409, detail=f"Audit is {run.status}; this action is not valid at this stage.")


def transition_audit_status(
    db: Session,
    audit: AuditRunModel,
    expected: AuditStatus,
    target: AuditStatus,
    *,
    completed_at: datetime | None = None,
) -> None:
    """Advance one lifecycle step without reviving a concurrently cancelled run.

    Provider calls are intentionally sequential, but cancellation arrives on a
    separate request/session. A conditional database update is therefore the
    authority at each terminal boundary, not a stale ORM object in the worker
    request. Pending responses/evaluations are flushed first and remain
    traceable if the compare-and-set loses to cancellation.
    """
    changed = db.execute(
        update(AuditRunModel)
        .where(AuditRunModel.id == audit.id, AuditRunModel.status == expected.value)
        .values(status=target.value, completed_at=completed_at)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount == 1:
        db.expire(audit)
        return
    db.expire(audit)
    db.refresh(audit)
    if audit.status == AuditStatus.CANCELLED.value:
        raise HTTPException(409, "This audit was cancelled. Completed artifacts were retained for traceability.")
    raise HTTPException(409, f"Audit status changed to {audit.status} while this stage was running.")

@router.get("/health")
def health():
    """Readiness check: a healthy API must also reach its configured database."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        if revision != ScriptDirectory.from_config(config).get_current_head():
            raise RuntimeError("database migration revision is behind the application")
    except Exception as exc:
        raise HTTPException(503, "The Auditor database is not ready.") from exc
    return {"status": "ok", "service": "AI Memory Health Auditor", "database": "ready"}
@router.get("/target-providers", response_model=list[ProviderOption])
def target_providers():
    return [ProviderOption(provider=provider, label=label, default_model=model, configured=configured(provider), description=description, default_pipeline_model=configured_pipeline_model("openrouter") if provider == TargetProvider.OPENROUTER else None, default_evaluator_model=configured_evaluator()[1] if provider == TargetProvider.OPENROUTER and configured_evaluator()[0] == "openrouter" else None) for provider, (label, model, description) in PROVIDERS.items()]

@router.get("/ollama-models")
def ollama_models():
    import httpx
    from app.target_ai.providers import ollama_base_url
    try:
        response = httpx.get(f"{ollama_base_url()}/api/tags", timeout=10.0)
        response.raise_for_status()
        return [{"value": item["name"], "label": item["name"]} for item in response.json()["models"]]
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, "The installed local model list could not be loaded. Please retry.") from None

@router.get("/openrouter-models")
def openrouter_models(db: Session = Depends(get_db)):
    """Only return models that passed a recent request using this backend key."""
    return verified_options(db)

@router.get("/openrouter-model-checks")
def openrouter_model_checks(db: Session = Depends(get_db)):
    """List eligible candidates and their current verification state; makes no model calls."""
    return options_and_checks(db)

@router.post("/openrouter-model-checks")
def run_openrouter_model_check(payload: ModelAvailabilityCheckRequest, db: Session = Depends(get_db)):
    """Explicitly verify one candidate with a minimal synthetic structured-output request."""
    scope = credential_scope()
    with audit_run_lock(f"model-check:{scope}:{payload.model}", "This model is already being checked.", db=db):
        return check_model(db, payload.model)

@router.post("/conversations", response_model=Conversation, status_code=201)
def create_conversation(payload: ConversationCreate, db: Session = Depends(get_db)):
    if not payload.authorised: raise HTTPException(422, "Authorisation is required before conversation data can be processed.")
    existing = existing_creation(db, ConversationModel, payload)
    if existing:
        return conversation_schema(db, existing)
    if not payload.pasted_text and not payload.messages: raise HTTPException(422, "Provide pasted conversation text or structured messages.")
    messages = payload.messages or pasted_messages(payload.pasted_text or "")
    if not messages:
        raise HTTPException(422, "Provide at least one non-empty conversation message.")
    source_ids = [message.message_id or f"MSG{index:03d}" for index, message in enumerate(messages, 1)]
    if len(source_ids) != len(set(source_ids)):
        raise HTTPException(422, "Conversation message IDs must be unique within the uploaded conversation.")
    c = ConversationModel(id=ident("C"), authorised=True, source_origin=payload.source_origin, creation_request_key=payload.creation_request_key,
        creation_request_fingerprint=creation_fingerprint(payload) if payload.creation_request_key else None)
    db.add(c)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = existing_creation(db, ConversationModel, payload)
        if existing:
            return conversation_schema(db, existing)
        raise
    fallback_time = datetime.now(timezone.utc)
    for i, (m, source_id) in enumerate(zip(messages, source_ids), 1):
        db.add(MessageModel(
            id=ident("MSG"), conversation_id=c.id, source_message_id=source_id, sequence=i,
            role=m.role.strip(), content=m.content.strip(),
            timestamp=MessageModel.timestamp_for_storage(m.timestamp or fallback_time + timedelta(microseconds=i)),
            original_timestamp=m.original_timestamp or (m.timestamp or fallback_time + timedelta(microseconds=i)).isoformat(),
        ))
    db.commit(); db.refresh(c); return conversation_schema(db, c)
@router.get("/conversations/{conversation_id}", response_model=Conversation)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    c = db.get(ConversationModel, conversation_id)
    if not c: missing("Conversation")
    return conversation_schema(db, c)


@router.get("/conversations/{conversation_id}/export")
def export_conversation_data(conversation_id: str, db: Session = Depends(get_db)):
    """Download authorised source data and its local audit records (never secrets)."""
    conversation = db.get(ConversationModel, conversation_id)
    if not conversation: missing("Conversation")
    memories = db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == conversation_id)).all()
    runs = db.scalars(select(AuditRunModel).where(AuditRunModel.conversation_id == conversation_id).order_by(AuditRunModel.created_at)).all()
    experiments = db.scalars(select(ExperimentModel).where(ExperimentModel.conversation_id == conversation_id).order_by(ExperimentModel.created_at)).all()
    audits = []
    receipts_by_group = {}
    for run in runs:
        if run.experiment_id:
            receipts_by_group.setdefault(run.experiment_id, []).append(run.reproducibility_metadata or {})
        tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run.id)).all()
        responses = db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == run.id)).all()
        evaluations = db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id == run.id)).all()
        human_reviews = db.scalars(select(EvaluationHumanReviewModel).where(EvaluationHumanReviewModel.run_id == run.id)).all()
        target_memories = db.scalars(select(TargetAgentMemoryModel).where(TargetAgentMemoryModel.run_id == run.id).order_by(TargetAgentMemoryModel.write_order)).all()
        target_relationships = db.scalars(select(TargetAgentMemoryRelationshipModel).where(TargetAgentMemoryRelationshipModel.run_id == run.id)).all()
        target_events = db.scalars(select(TargetAgentMemoryEventModel).where(TargetAgentMemoryEventModel.run_id == run.id).order_by(TargetAgentMemoryEventModel.created_at)).all()
        target_retrievals = db.scalars(select(TargetAgentRetrievalModel).where(TargetAgentRetrievalModel.run_id == run.id).order_by(TargetAgentRetrievalModel.created_at)).all()
        audits.append({"audit_run": audit_schema(run).model_dump(mode="json"),
                       "tests": [test_schema(row).model_dump(mode="json") for row in tests],
                       "target_responses": [response_schema(row).model_dump(mode="json") for row in responses],
                       "evaluations": [eval_schema(row).model_dump(mode="json") for row in evaluations],
                       "evaluation_human_reviews": [human_review_schema(row).model_dump(mode="json") for row in human_reviews],
                       "target_memory_records": [{"memory_id": row.id, "canonical_value": row.canonical_value,
                           "scope": row.scope, "lifecycle_state": row.lifecycle_state, "source_message_ids": row.source_message_ids,
                           "observed_at": row.observed_at, "write_order": row.write_order, "created_at": row.created_at} for row in target_memories],
                       "target_memory_relationships": [{"relationship_id": row.id, "memory_id": row.memory_id,
                           "relationship_type": row.relationship_type, "target_memory_id": row.target_memory_id} for row in target_relationships],
                       "target_memory_events": [{"event_id": row.id, "memory_id": row.memory_id, "event_type": row.event_type,
                           "source_message_ids": row.source_message_ids, "details": row.details, "created_at": row.created_at} for row in target_events],
                       "target_memory_retrievals": [{"retrieval_id": row.id, "test_id": row.test_id, "strategy": row.strategy,
                           "selected_memory_ids": row.selected_memory_ids, "ranking_evidence": row.ranking_evidence,
                           "created_at": row.created_at} for row in target_retrievals]})
    origin_notices = {
        "synthetic": "Synthetic source: this operational smoke data is not participant evidence and must not be used as human labels or held-out research evidence.",
        "authorised": "Authorised source origin was declared by the operator; this declaration does not establish research eligibility or independent labels.",
        "deidentified": "De-identified source origin was declared by the operator; this declaration does not establish research eligibility or independent labels.",
        "unknown": "Source origin was not recorded. Do not infer it from conversation content or treat it as research evidence.",
    }
    data = {"schema_version": "conversation-export-v1", "exported_at": datetime.now(timezone.utc),
            "notice": "Local authorised-data export. API keys and raw provider payloads are excluded.",
            "source_origin_notice": origin_notices.get(getattr(conversation, "source_origin", "unknown"), origin_notices["unknown"]),
            "conversation": conversation_schema(db, conversation).model_dump(mode="json"),
            "ground_truth_memories": [memory_schema(db, row).model_dump(mode="json") for row in memories],
            "experiments": [experiment_schema(row, receipts_by_group.get(row.id)).model_dump(mode="json") for row in experiments], "audits": audits,
            "assessor_comparisons": [{column.name:getattr(plan,column.name) for column in AssessorComparisonModel.__table__.columns}
                for plan in db.scalars(select(AssessorComparisonModel).where(AssessorComparisonModel.source_run_id.in_([run.id for run in runs])))],
            "generator_comparisons": [{column.name:getattr(plan,column.name) for column in GeneratorComparisonModel.__table__.columns}
                for plan in db.scalars(select(GeneratorComparisonModel).where(GeneratorComparisonModel.source_run_id.in_([run.id for run in runs])))],
            "extraction_comparisons": [{column.name:getattr(plan,column.name) for column in ExtractionComparisonModel.__table__.columns}
                for plan in db.scalars(select(ExtractionComparisonModel).where(ExtractionComparisonModel.source_run_id.in_([run.id for run in runs])))]}
    return StreamingResponse(iter([json.dumps(data, default=str, indent=2)]), media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="memory-health-{conversation_id}-export.json"'})


@router.delete("/conversations/{conversation_id}", response_model=ConversationDeletionReceipt)
def delete_conversation_data(conversation_id: str, payload: ConversationDeletionRequest, db: Session = Depends(get_db)):
    """Permanently erase one conversation and every operational record derived from it."""
    conversation = db.get(ConversationModel, conversation_id)
    if not conversation: missing("Conversation")
    if payload.confirmation != conversation_id:
        raise HTTPException(422, "To permanently delete local data, enter the exact conversation ID shown on this page.")
    runs = db.scalars(select(AuditRunModel).where(AuditRunModel.conversation_id == conversation_id)).all()
    run_ids = [run.id for run in runs]
    experiments = db.scalars(select(ExperimentModel).where(ExperimentModel.conversation_id == conversation_id)).all()
    memory_ids = list(db.scalars(select(MemoryModel.id).where(MemoryModel.conversation_id == conversation_id)).all())
    test_ids = list(db.scalars(select(TestCaseModel.id).where(TestCaseModel.run_id.in_(run_ids))).all()) if run_ids else []
    try:
        if test_ids:
            evaluation_ids = list(db.scalars(select(EvaluationResultModel.id).where(EvaluationResultModel.test_id.in_(test_ids))).all())
            if evaluation_ids:
                db.execute(delete(EvaluationHumanReviewModel).where(EvaluationHumanReviewModel.evaluation_id.in_(evaluation_ids)))
            db.execute(delete(EvaluationResultModel).where(EvaluationResultModel.test_id.in_(test_ids)))
            db.execute(delete(TargetAgentRetrievalModel).where(TargetAgentRetrievalModel.test_id.in_(test_ids)))
        if run_ids:
            db.execute(delete(AssessorComparisonModel).where(AssessorComparisonModel.source_run_id.in_(run_ids)))
            db.execute(delete(GeneratorComparisonModel).where(GeneratorComparisonModel.source_run_id.in_(run_ids)))
            db.execute(delete(ExtractionComparisonModel).where(ExtractionComparisonModel.source_run_id.in_(run_ids)))
            db.execute(delete(TargetAgentMemoryRelationshipModel).where(TargetAgentMemoryRelationshipModel.run_id.in_(run_ids)))
            db.execute(delete(TargetAgentMemoryEventModel).where(TargetAgentMemoryEventModel.run_id.in_(run_ids)))
            db.execute(delete(TargetAgentMemoryModel).where(TargetAgentMemoryModel.run_id.in_(run_ids)))
            db.execute(delete(TargetResponseModel).where(TargetResponseModel.run_id.in_(run_ids)))
            db.execute(delete(TestCaseModel).where(TestCaseModel.run_id.in_(run_ids)))
            db.execute(delete(AuditRunModel).where(AuditRunModel.id.in_(run_ids)))
        if memory_ids:
            db.execute(delete(MemoryRelationshipModel).where(MemoryRelationshipModel.memory_id.in_(memory_ids) | MemoryRelationshipModel.target_memory_id.in_(memory_ids)))
            db.execute(delete(MemoryModel).where(MemoryModel.id.in_(memory_ids)))
        db.execute(delete(ExperimentModel).where(ExperimentModel.conversation_id == conversation_id))
        db.execute(delete(MessageModel).where(MessageModel.conversation_id == conversation_id))
        db.delete(conversation)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ConversationDeletionReceipt(conversation_id=conversation_id, deleted_audit_runs=len(runs), deleted_experiments=len(experiments),
        message="The authorised conversation and all locally derived audit data were permanently deleted.")
@router.post("/conversations/{conversation_id}/extract", response_model=list[Memory])
def extract(conversation_id: str, payload: ExtractionRequest | None = None, db: Session = Depends(get_db)):
    message = "Memory extraction is still running. Wait, then continue to check the saved result."
    with audit_run_lock("extraction:" + conversation_id, message, db=db):
        # PostgreSQL protects the same conversation across API workers as well.
        try:
            conversation = db.scalar(select(ConversationModel).where(ConversationModel.id == conversation_id)
                .with_for_update(nowait=True).execution_options(populate_existing=True))
        except OperationalError as cause:
            db.rollback()
            if getattr(cause.orig, "pgcode", None) == "55P03" or getattr(cause.orig, "sqlstate", None) == "55P03":
                raise HTTPException(409, message) from None
            raise
        if not conversation:
            missing("Conversation")
        return extract_saved_conversation(conversation_id, payload, db)


def extract_saved_conversation(conversation_id: str, payload: ExtractionRequest | None, db: Session):
    c = db.get(ConversationModel, conversation_id)
    if not c: missing("Conversation")
    existing = db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == conversation_id)).all()
    prior_status = (c.extraction_provenance or {}).get("status")
    if existing or (c.extraction_provenance is not None and prior_status != "failed"):
        return [memory_schema(db, x) for x in existing]
    if payload and payload.provider:
        ensure_supported_pipeline_role(payload.provider, "memory extraction")
    selected_provider = payload.provider.value if payload and payload.provider else pipeline_provider()
    selected_model = payload.model if payload and payload.model else configured_pipeline_model(selected_provider)
    extractor = get_memory_extractor(selected_provider, selected_model)
    try:
        extracted = extractor.extract(conversation_schema(db, c))
    except Exception:
        stages = getattr(extractor, "last_agent_stages", []) or []
        execution_ids = _persist_agent_stages(db, stages, conversation_id=conversation_id)
        c.extraction_provenance = {
            "status": "failed", "provider": selected_provider, "model": selected_model,
            "version": getattr(extractor, "VERSION", type(extractor).__name__),
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "agent_execution_ids": execution_ids,
            "error": "Memory extraction did not complete. Correct the source or retry the selected service.",
        }
        db.commit()
        raise
    # Extractors may deliberately use short, conversation-local labels such
    # as M001 so their relationship output is easy to inspect.  Persisting
    # those labels directly made two independent conversations collide on the
    # global memories primary key.  Resolve every extractor-local reference to
    # a durable global identifier at this database boundary instead.
    source_ids = [memory.memory_id for memory in extracted]
    if len(source_ids) != len(set(source_ids)):
        raise HTTPException(502, "The memory extractor returned duplicate memory IDs.")
    durable_ids = {source_id: ident("M") for source_id in source_ids}
    try:
        stages = getattr(extractor, "last_agent_stages", []) or []
        stages = _remap_candidate_ids(stages, durable_ids)
        review_report = _remap_candidate_ids(getattr(extractor, "memory_review", None), durable_ids)
        execution_ids = _persist_agent_stages(
            db, stages, conversation_id=conversation_id,
        )
        c.extraction_provenance = {"status": "completed", "provider": selected_provider, "model": selected_model,
            "version": getattr(extractor, "VERSION", type(extractor).__name__),
            "extracted_at": datetime.now(timezone.utc).isoformat(), "candidate_count": len(extracted),
            "agent_execution_ids": execution_ids,
            "memory_review": review_report}
        execution=getattr(getattr(extractor,'client',None),'last_execution',None)
        if execution is not None:c.extraction_provenance['http_execution']=execution
        for memory in extracted:
            db.add(MemoryModel(
                id=durable_ids[memory.memory_id], conversation_id=conversation_id,
                canonical_value=memory.canonical_value, status=memory.status.value,
                source_message_ids=memory.source_message_ids, timestamp=memory.timestamp,
                confidence=memory.confidence,
            ))
        # Flush memory rows before inserting relationship FKs.  This also
        # keeps PostgreSQL and SQLite ordering behaviour identical.
        db.flush()
        for memory in extracted:
            for relationship in memory.relationships:
                target_id = durable_ids.get(relationship.target_memory_id)
                if target_id is None:
                    raise HTTPException(502, "The memory extractor returned a relationship to an unknown memory.")
                db.add(MemoryRelationshipModel(
                    id=ident("MR"), memory_id=durable_ids[memory.memory_id],
                    relationship_type=relationship.type.value, target_memory_id=target_id,
                    evidence_message_ids=relationship.evidence_message_ids or None,
                    confidence=relationship.confidence,
                ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return [memory_schema(db, x) for x in db.scalars(
        select(MemoryModel).where(MemoryModel.conversation_id == conversation_id)
    ).all()]


def _remap_candidate_ids(value, mapping: dict[str, str]):
    """Replace extractor-local IDs in persisted traces with durable memory IDs."""
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [_remap_candidate_ids(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: _remap_candidate_ids(item, mapping) for key, item in value.items()}
    return value


def _persist_agent_stages(db: Session, stages: list[dict], *, conversation_id: str | None = None,
                          run_id: str | None = None) -> list[str]:
    from app.services.agent_trace import record_agent_execution
    rows = []
    for stage in stages:
        row = record_agent_execution(
            db,
            role=stage.get("role") or "unknown_agent",
            provider=stage.get("provider") or "unknown",
            model=stage.get("model") or "unknown",
            prompt_template_version=stage.get("prompt_template_version") or "unversioned",
            instructions=stage.get("instructions") or "",
            prompt=stage.get("prompt") or "",
            schema=stage.get("schema"),
            input_payload=stage.get("input_payload") or {},
            input_refs=stage.get("input_refs") or {},
            output_data=stage.get("output_data"),
            status=stage.get("status") or "failed",
            execution=stage.get("execution"),
            error_code=stage.get("error_code"),
            error_summary=stage.get("error_summary"),
            error_diagnostics=stage.get("error_diagnostics"),
            conversation_id=conversation_id,
            run_id=run_id,
            handoff_from=rows[-1].id if rows else None,
        )
        if rows:
            rows[-1].handoff_to = row.id
        rows.append(row)
    return [row.id for row in rows]
@router.get("/conversations/{conversation_id}/memories", response_model=list[Memory])
def memories(conversation_id: str, db: Session = Depends(get_db)):
    return [memory_schema(db, x) for x in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == conversation_id)).all()]


@router.get("/conversations/{conversation_id}/agent-executions", response_model=list[AgentExecution])
def conversation_agent_executions(conversation_id: str, db: Session = Depends(get_db)):
    if not db.get(ConversationModel, conversation_id):
        missing("Conversation")
    from app.services.agent_trace import agent_execution_schema
    rows = db.scalars(select(AgentExecutionModel).where(
        AgentExecutionModel.conversation_id == conversation_id,
    ).order_by(AgentExecutionModel.created_at, AgentExecutionModel.id)).all()
    return [agent_execution_schema(row) for row in rows]


@router.get("/audits/{run_id}/agent-executions", response_model=list[AgentExecution])
def audit_agent_executions(run_id: str, db: Session = Depends(get_db)):
    if not db.get(AuditRunModel, run_id):
        missing("Audit")
    from app.services.agent_trace import agent_execution_schema
    rows = db.scalars(select(AgentExecutionModel).where(
        AgentExecutionModel.run_id == run_id,
    ).order_by(AgentExecutionModel.created_at, AgentExecutionModel.id)).all()
    return [agent_execution_schema(row) for row in rows]

@router.get("/conversations/{conversation_id}/test-coverage-preview", response_model=TestCoveragePreview)
def test_coverage_preview(conversation_id: str, test_budget: int = 20, db: Session = Depends(get_db)):
    """Preview the exact deterministic evidence slots before audit inputs freeze."""
    if not db.get(ConversationModel, conversation_id):
        missing("Conversation")
    if test_budget < 1 or test_budget > 100:
        raise HTTPException(422, "The requested test count must be between 1 and 100.")
    confirmed_memories = [memory_schema(db, row) for row in db.scalars(select(MemoryModel).where(
        MemoryModel.conversation_id == conversation_id,
        MemoryModel.status.in_(["confirmed", "edited"]),
    )).all()]
    from app.test_generator.agent import AgentTestGenerator
    coverage = AgentTestGenerator.preview_dimension_coverage(confirmed_memories, test_budget)
    minimum_met = test_budget >= len(Dimension) and all(
        item["available_question_count"] >= item["required_question_count"]
        for item in coverage
    )
    return TestCoveragePreview(
        requested_test_count=test_budget,
        minimum_met=minimum_met,
        dimensions=[TestDimensionCoverage.model_validate(item) for item in coverage],
    )

def ensure_ground_truth_editable(db: Session, conversation_id: str) -> None:
    if db.scalar(select(AuditRunModel.id).where(AuditRunModel.conversation_id == conversation_id).limit(1)):
        raise HTTPException(409, "Ground truth is frozen after an audit is created. Start a new conversation to revise the evidence.")

@router.post("/memories", response_model=Memory, status_code=201)
def add_memory(payload: MemoryCreate, db: Session = Depends(get_db)):
    if not db.get(ConversationModel, payload.conversation_id): missing("Conversation")
    ensure_ground_truth_editable(db, payload.conversation_id)
    validate_memory_evidence(db, payload.conversation_id, payload.source_message_ids, payload.relationships)
    timestamp = payload.timestamp
    if timestamp is None and payload.source_message_ids:
        timestamp = db.scalar(select(MessageModel.timestamp).where(MessageModel.conversation_id == payload.conversation_id, MessageModel.source_message_id.in_(payload.source_message_ids)).order_by(MessageModel.timestamp.desc()))
    m = MemoryModel(id=ident("M"), conversation_id=payload.conversation_id, canonical_value=payload.canonical_value, status="candidate", source_message_ids=payload.source_message_ids, timestamp=timestamp); db.add(m); db.flush()
    for r in payload.relationships: db.add(MemoryRelationshipModel(id=ident("MR"), memory_id=m.id, relationship_type=r.type.value, target_memory_id=r.target_memory_id, evidence_message_ids=r.evidence_message_ids or None, confidence=r.confidence))
    db.commit(); return memory_schema(db,m)
@router.patch("/memories/{memory_id}", response_model=Memory)
def patch_memory(memory_id: str, payload: MemoryUpdate, db: Session = Depends(get_db)):
    m=db.get(MemoryModel,memory_id)
    if not m: missing("Memory")
    ensure_ground_truth_editable(db, m.conversation_id)
    next_sources = payload.source_message_ids if payload.source_message_ids is not None else list(m.source_message_ids)
    next_relationships = payload.relationships if payload.relationships is not None else memory_schema(db, m).relationships
    validate_memory_evidence(db, m.conversation_id, next_sources, next_relationships, m.id)
    if payload.canonical_value is not None: m.canonical_value=payload.canonical_value
    if payload.status is not None: m.status=payload.status.value
    if payload.source_message_ids is not None: m.source_message_ids=payload.source_message_ids
    if "timestamp" in payload.model_fields_set: m.timestamp=payload.timestamp
    if payload.relationships is not None:
        for r in db.scalars(select(MemoryRelationshipModel).where(MemoryRelationshipModel.memory_id==m.id)).all(): db.delete(r)
        # Persist removals before replacements: the database enforces unique
        # relationship edges, and ORM inserts can otherwise precede deletes.
        db.flush()
        for r in payload.relationships: db.add(MemoryRelationshipModel(id=ident("MR"), memory_id=m.id, relationship_type=r.type.value, target_memory_id=r.target_memory_id, evidence_message_ids=r.evidence_message_ids or None, confidence=r.confidence))
    db.commit(); return memory_schema(db,m)
@router.delete("/memories/{memory_id}", status_code=204)
def reject_memory(memory_id: str, db: Session = Depends(get_db)):
    m=db.get(MemoryModel,memory_id)
    if not m: missing("Memory")
    ensure_ground_truth_editable(db, m.conversation_id)
    m.status="rejected"; db.commit()
@router.post("/conversations/{conversation_id}/confirm-ground-truth", response_model=list[Memory])
def confirm_ground_truth(conversation_id: str, payload: GroundTruthConfirm, db: Session = Depends(get_db)):
    ensure_ground_truth_editable(db, conversation_id)
    rows=db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==conversation_id)).all()
    if not rows: raise HTTPException(409, "Extract candidate memories before confirming ground truth.")
    for m in rows:
        if m.id in payload.confirmed_memory_ids and m.status == "candidate": m.status="confirmed"
    if not any(m.status in ("confirmed", "edited") for m in rows): raise HTTPException(422, "Confirm or edit at least one memory.")
    db.commit(); return [memory_schema(db,m) for m in rows]

def creation_fingerprint(payload) -> str:
    data = payload.model_dump(mode="json", exclude={"creation_request_key"})
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def existing_creation(db: Session, model, payload):
    if not payload.creation_request_key:
        return None
    row = db.scalar(select(model).where(model.creation_request_key == payload.creation_request_key))
    if row and row.creation_request_fingerprint != creation_fingerprint(payload):
        raise HTTPException(409, "This creation request belongs to different settings. Resume the original request or start a separate audit.")
    return row


@router.post("/experiments", response_model=Experiment, status_code=201)
def create_experiment(payload: ExperimentCreate, db: Session = Depends(get_db)):
    existing = existing_creation(db, ExperimentModel, payload)
    if existing:
        return experiment_schema(existing)
    if not db.get(ConversationModel, payload.conversation_id): missing("Conversation")
    ensure_supported_pipeline_role(payload.test_suite_configuration.pipeline_provider, "memory-extraction and test-generation pipeline")
    confirmed = db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == payload.conversation_id, MemoryModel.status.in_(["confirmed", "edited"]))).all()
    if not confirmed: raise HTTPException(409, "Confirm ground truth before creating an experiment.")
    suite_configuration = payload.test_suite_configuration.model_dump(mode="json")
    generation_provider = payload.test_suite_configuration.pipeline_provider.value
    generation_model = payload.test_suite_configuration.pipeline_model or configured_pipeline_model(generation_provider)
    semantic_provider = (payload.test_suite_configuration.semantic_review_provider
                         or payload.test_suite_configuration.pipeline_provider)
    if generation_provider != TargetProvider.RULE_BASED.value and semantic_provider == TargetProvider.RULE_BASED:
        raise HTTPException(422, "Model-generated questions require a local or cloud semantic duplicate-review model.")
    semantic_model = (payload.test_suite_configuration.semantic_review_model
                      or (generation_model if semantic_provider == payload.test_suite_configuration.pipeline_provider
                          else configured_pipeline_model(semantic_provider.value)))
    suite_configuration["semantic_review_provider"] = semantic_provider.value
    suite_configuration["semantic_review_model"] = semantic_model
    suite_configuration["pipeline_model"] = generation_model
    if payload.test_suite_configuration.evaluator_provider == TargetProvider.RULE_BASED:
        suite_configuration["evaluator_model"] = configured_evaluator("rule_based")[1]
    experiment = ExperimentModel(
        id=ident("EXP"), conversation_id=payload.conversation_id, label=payload.label,
        creation_request_key=payload.creation_request_key,
        creation_request_fingerprint=creation_fingerprint(payload) if payload.creation_request_key else None,
        status=ExperimentStatus.CREATED.value,
        test_suite_configuration=suite_configuration,
        test_suite_metadata=TestSuiteMetadata().model_dump(mode="json"),
    )
    db.add(experiment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = existing_creation(db, ExperimentModel, payload)
        if existing:
            return experiment_schema(existing)
        raise
    db.refresh(experiment)
    return experiment_schema(experiment)

@router.get("/experiments", response_model=list[Experiment])
def list_experiments(db: Session = Depends(get_db)):
    """Return reproducible comparison groups, newest first.

    Individual audit runs stay available through ``/audits``; this endpoint is
    deliberately group-oriented so the UI never presents unrelated completed
    runs as a controlled experiment.
    """
    rows = db.scalars(select(ExperimentModel).order_by(ExperimentModel.created_at.desc())).all()
    receipts_by_group = {}
    if rows:
        receipts = db.execute(select(AuditRunModel.experiment_id, AuditRunModel.reproducibility_metadata)
                              .where(AuditRunModel.experiment_id.in_([row.id for row in rows]))).all()
        for group_id, receipt in receipts:
            receipts_by_group.setdefault(group_id, []).append(receipt or {})
    return [experiment_schema(row, receipts_by_group.get(row.id)) for row in rows]

@router.post("/audits", response_model=AuditRun, status_code=201)
def create_audit(payload: AuditCreate, db: Session = Depends(get_db)):
    existing = existing_creation(db, AuditRunModel, payload)
    if existing:
        return audit_schema(existing)
    try:
        result = build_audit(payload, db)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = existing_creation(db, AuditRunModel, payload)
        if existing:
            return audit_schema(existing)
        raise
    return result

def build_audit(payload: AuditCreate, db: Session):
    conversation = db.get(ConversationModel,payload.conversation_id)
    if not conversation: missing("Conversation")
    experiment = db.get(ExperimentModel, payload.experiment_id) if payload.experiment_id else None
    if payload.experiment_id and not experiment: missing("Experiment")
    if experiment and experiment.conversation_id != payload.conversation_id:
        raise HTTPException(422, "An audit run must use the experiment's conversation.")
    if experiment and experiment.status != ExperimentStatus.CREATED.value:
        raise HTTPException(
            409,
            "Experiment membership is frozen once its shared test suite has been generated or the experiment is terminal.",
        )
    confirmed=db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==payload.conversation_id, MemoryModel.status.in_(["confirmed","edited"]))).all()
    if not confirmed: raise HTTPException(409, "Confirm ground truth before creating an audit.")
    default_model=PROVIDERS[payload.provider][1]
    model=payload.model if payload.model not in ("", "rule-based-target-ai") or payload.provider == TargetProvider.RULE_BASED else default_model
    from app.target_ai.openrouter import validate_profile_reasoning
    try:
        validate_profile_reasoning(payload.provider.value, model, payload.target_memory_profile)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    suite = TestSuiteConfiguration.model_validate(experiment.test_suite_configuration) if experiment else None
    selected_pipeline_provider = suite.pipeline_provider.value if suite else (payload.pipeline_provider.value if payload.pipeline_provider else pipeline_provider())
    ensure_supported_pipeline_role(TargetProvider(selected_pipeline_provider), "memory-extraction and test-generation pipeline")
    if suite:
        if suite.compare_evaluators:
            selected_evaluator_provider, selected_evaluator_model = configured_evaluator(
                payload.evaluator_provider.value if payload.evaluator_provider else suite.evaluator_provider.value,
                payload.evaluator_model or suite.evaluator_model,
            )
        else:
            selected_evaluator_provider = suite.evaluator_provider.value
            selected_evaluator_model = configured_evaluator("rule_based")[1] if suite.evaluator_provider == TargetProvider.RULE_BASED else suite.evaluator_model
    else:
        selected_evaluator_provider, selected_evaluator_model = configured_evaluator(
            payload.evaluator_provider.value if payload.evaluator_provider else None, payload.evaluator_model,
        )
    selected_strategy = payload.memory_strategy or (MemoryStrategy.WEAK_FIRST_HIT if payload.target_configuration == TargetConfiguration.WEAK else MemoryStrategy.STRONG_RULE_BASED)
    selected_seed = suite.random_seed if suite else payload.random_seed
    selected_budget = suite.test_budget if suite else payload.test_budget
    selected_template = suite.prompt_template_version if suite else payload.prompt_template_version
    selected_pipeline_model = suite.pipeline_model if suite else (payload.pipeline_model or configured_pipeline_model(selected_pipeline_provider))
    if suite:
        selected_semantic_provider = suite.semantic_review_provider or TargetProvider(selected_pipeline_provider)
        selected_semantic_model = (suite.semantic_review_model
                                   or (selected_pipeline_model if selected_semantic_provider.value == selected_pipeline_provider
                                       else configured_pipeline_model(selected_semantic_provider.value)))
    else:
        selected_semantic_provider = payload.semantic_review_provider or TargetProvider(selected_pipeline_provider)
        selected_semantic_model = (payload.semantic_review_model
                                   or (selected_pipeline_model if selected_semantic_provider.value == selected_pipeline_provider
                                       else configured_pipeline_model(selected_semantic_provider.value)))
    if (selected_pipeline_provider != TargetProvider.RULE_BASED.value
            and selected_semantic_provider == TargetProvider.RULE_BASED):
        raise HTTPException(422, "Model-generated questions require a local or cloud semantic duplicate-review model.")
    selected_retrieval_mode = payload.retrieval_mode.value
    selected_retrieval_provider = None
    selected_retrieval_model = None
    if selected_retrieval_mode == TargetMemoryRetrievalMode.AGENT.value:
        if payload.target_system_adapter != TargetSystemAdapterKind.CONTROLLED_MEMORY:
            raise HTTPException(422, "Agent memory retrieval is available for the controlled-memory target system.")
        requested_provider = payload.retrieval_provider.value if payload.retrieval_provider else None
        provider_choice = requested_provider or (
            selected_pipeline_provider if selected_pipeline_provider != TargetProvider.RULE_BASED.value else None
        )
        if provider_choice is None:
            provider_choice = next((candidate.value for candidate in (
                TargetProvider.OPENROUTER, TargetProvider.OLLAMA, TargetProvider.OPENAI,
                TargetProvider.DEEPSEEK, TargetProvider.GEMINI,
            ) if configured(candidate)), None)
        if provider_choice is None or provider_choice == TargetProvider.RULE_BASED.value:
            raise HTTPException(422, "Agent memory retrieval needs a configured local or cloud model service.")
        retrieval_provider_enum = TargetProvider(provider_choice)
        ensure_supported_pipeline_role(retrieval_provider_enum, "target memory retrieval")
        if not configured(retrieval_provider_enum):
            raise HTTPException(422, "The selected memory retrieval model service is unavailable.")
        selected_retrieval_provider = retrieval_provider_enum.value
        selected_retrieval_model = (payload.retrieval_model.strip() if payload.retrieval_model and payload.retrieval_model.strip() else None) or (
            selected_pipeline_model if selected_retrieval_provider == selected_pipeline_provider
            else configured_pipeline_model(selected_retrieval_provider)
        )
    selected_maintenance_policy = payload.memory_maintenance_policy.value
    selected_memory_capacity = payload.target_memory_capacity
    # The environment is read exactly once here. Every later stage uses the
    # persisted writer kind/version below, even if .env changes meanwhile.
    selected_target_memory_writer = payload.target_memory_writer or default_target_memory_writer_kind()
    metadata = reproducibility_snapshot(
        provider=payload.provider.value, model=model, temperature=payload.temperature,
        random_seed=selected_seed, test_budget=selected_budget,
        prompt_template_version=selected_template, pipeline_provider=selected_pipeline_provider,
        pipeline_model=selected_pipeline_model, semantic_review_provider=selected_semantic_provider.value,
        semantic_review_model=selected_semantic_model,
        retrieval_mode=selected_retrieval_mode, retrieval_provider=selected_retrieval_provider,
        retrieval_model=selected_retrieval_model, evaluator_provider=selected_evaluator_provider,
        evaluator_model=selected_evaluator_model, memory_strategy=selected_strategy.value,
        memory_maintenance_policy=selected_maintenance_policy,
        target_memory_writer=selected_target_memory_writer,
        target_memory_capacity=selected_memory_capacity,
        target_system_adapter=payload.target_system_adapter,
        target_memory_profile=payload.target_memory_profile,
    )
    metadata["auditor_comparison_id"] = suite.auditor_comparison_id if suite else None
    metadata["retrieval_mode"] = selected_retrieval_mode
    metadata["retrieval_provider"] = selected_retrieval_provider
    metadata["retrieval_model"] = selected_retrieval_model
    metadata["extraction_provenance"] = conversation.extraction_provenance
    metadata["auditor_method"] = (
        "rules" if selected_pipeline_provider == selected_evaluator_provider == "rule_based" else
        "model_generation" if selected_pipeline_provider != "rule_based" and selected_evaluator_provider == "rule_based" else
        "hybrid" if selected_pipeline_provider != "rule_based" and selected_evaluator_provider != "rule_based" else "custom"
    )
    a=AuditRunModel(id=ident("RUN"), creation_request_key=payload.creation_request_key, creation_request_fingerprint=creation_fingerprint(payload) if payload.creation_request_key else None, conversation_id=payload.conversation_id, experiment_id=payload.experiment_id, status="CREATED", target_configuration=payload.target_configuration.value, provider=payload.provider.value, model=model, temperature=payload.temperature, random_seed=selected_seed, test_budget=selected_budget, prompt_template_version=selected_template, pipeline_provider=selected_pipeline_provider, pipeline_model=selected_pipeline_model, semantic_review_provider=selected_semantic_provider.value, semantic_review_model=selected_semantic_model, retrieval_mode=selected_retrieval_mode, retrieval_provider=selected_retrieval_provider, retrieval_model=selected_retrieval_model, evaluator_provider=selected_evaluator_provider, evaluator_model=selected_evaluator_model, memory_strategy=selected_strategy.value, memory_maintenance_policy=selected_maintenance_policy, target_memory_capacity=selected_memory_capacity, target_memory_writer=selected_target_memory_writer.value, target_memory_writer_version=metadata["target_memory_writer_version"], target_system_adapter=payload.target_system_adapter.value, target_system_adapter_version=metadata["target_system_adapter_version"], reproducibility_metadata=metadata)
    if payload.shared_answer_source_run_id:
        source = db.get(AuditRunModel, payload.shared_answer_source_run_id)
        if not source or not experiment or source.experiment_id != experiment.id or not suite.compare_evaluators:
            raise HTTPException(409, "Shared answers require a source in the same evaluator-ablation group.")
        from app.services.shared_answers import validate_shared_target
        validate_shared_target(source, a)
        a.reproducibility_metadata = {**metadata, "shared_answer_source_run_id": source.id}
    db.add(a); db.flush(); db.refresh(a); return audit_schema(a)
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
        row = TestCaseModel(id=ident("T"), run_id=run.id, dimension=test.dimension.value if isinstance(test.dimension, Dimension) else test.dimension, prompt=test.prompt, expected_behavior=test.expected_behavior, supporting_memory_ids=test.supporting_memory_ids, generator_version=test.generator_version, test_type=test.test_type.value if isinstance(test.test_type, TestType) else test.test_type, quality_status=test.quality_status.value if isinstance(test.quality_status, TestQualityStatus) else test.quality_status, grounding_status=test.grounding_status.value if isinstance(test.grounding_status, GroundingStatus) else test.grounding_status, validation_notes=test.validation_notes, probe_group_id=test.probe_group_id, probe_variant=test.probe_variant, target_memory_context=test.target_memory_context)
        db.add(row); rows.append(row)
    db.flush()
    return rows

def clone_shared_suite(db: Session, source_tests: list[TestCaseModel], run: AuditRunModel) -> list[TestCaseModel]:
    """Give a peer run an isolated copy of the exact canonical suite."""
    clones: list[TestCaseModel] = []
    for source in source_tests:
        clone = TestCaseModel(id=ident("T"), run_id=run.id, suite_test_id=source.id, comparison_test_id=source.comparison_test_id, dimension=source.dimension, prompt=source.prompt, expected_behavior=source.expected_behavior, supporting_memory_ids=list(source.supporting_memory_ids), generator_version=source.generator_version, test_type=source.test_type, quality_status=source.quality_status, grounding_status=source.grounding_status, validation_notes=source.validation_notes, human_validity_status=source.human_validity_status, human_validity_reviewer=source.human_validity_reviewer, human_validity_note=source.human_validity_note, human_validity_reviewed_at=source.human_validity_reviewed_at, probe_group_id=source.probe_group_id, probe_variant=source.probe_variant, target_memory_context=[])
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

def ensure_suite_editable(db: Session, run: AuditRunModel) -> None:
    """Freeze a shared suite as soon as any comparison condition starts.

    Reviewing or regenerating a canonical test after one peer has executed
    would make the comparison unfair: completed peers would answer an older
    version while later peers would answer the edited prompt.
    """
    if (run.reproducibility_metadata or {}).get('formal_matrix_version'):
        raise HTTPException(409, 'This formal reference suite is frozen. Create a newly reviewed dataset version to change its questions.')
    if run.status in {AuditStatus.TESTS_EXECUTED.value, AuditStatus.COMPLETED.value, AuditStatus.FAILED.value, AuditStatus.CANCELLED.value}:
        raise HTTPException(409, "The test suite is frozen once execution has started.")
    if not run.experiment_id:
        return
    experiment = db.get(ExperimentModel, run.experiment_id)
    if not experiment:
        raise HTTPException(409, "The comparison experiment is unavailable.")
    if experiment.status in {
        ExperimentStatus.RUNNING.value,
        ExperimentStatus.COMPLETED.value,
        ExperimentStatus.FAILED.value,
        ExperimentStatus.CANCELLED.value,
    }:
        raise HTTPException(409, "The shared test suite is frozen once an experiment condition has started.")
    started_statuses = {
        AuditStatus.TESTS_EXECUTED.value,
        AuditStatus.COMPLETED.value,
        AuditStatus.FAILED.value,
        AuditStatus.CANCELLED.value,
    }
    peer_started = db.scalar(select(AuditRunModel.id).where(
        AuditRunModel.experiment_id == run.experiment_id,
        AuditRunModel.id != run.id,
        AuditRunModel.status.in_(started_statuses),
    ).limit(1))
    if peer_started:
        raise HTTPException(409, "The shared test suite is frozen once an experiment condition has started.")

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
        peer.human_validity_status = source.human_validity_status
        peer.human_validity_reviewer = source.human_validity_reviewer
        peer.human_validity_note = source.human_validity_note
        peer.human_validity_reviewed_at = source.human_validity_reviewed_at
        peer.probe_group_id = source.probe_group_id
        peer.probe_variant = source.probe_variant
        # This must be empty before execution.  It is only ever computed by
        # the independent target store for the specific peer run.
        peer.target_memory_context = []
    return [source, *peers]

def generated_candidate_for_review(db: Session, source: TestCaseModel) -> TestCase:
    """Produce a replacement candidate using the frozen suite configuration."""
    source_run = db.get(AuditRunModel, source.run_id)
    if not source_run:
        raise HTTPException(409, "The source audit run is unavailable.")
    assert_audit_runtime_frozen(source_run)
    experiment = db.get(ExperimentModel, source_run.experiment_id) if source_run.experiment_id else None
    memories = [memory_schema(db, row) for row in db.scalars(select(MemoryModel).where(
        MemoryModel.conversation_id == source_run.conversation_id,
        MemoryModel.status.in_(["confirmed", "edited"]),
    )).all()]
    if not memories:
        raise HTTPException(409, "Ground truth is empty.")
    suite_mode = TestSuiteConfiguration.model_validate(experiment.test_suite_configuration).suite_mode if experiment else TestSuiteMode.BEHAVIOURAL
    generator = get_suite_generator(suite_mode, get_test_generator(
        source_run.pipeline_provider, source_run.pipeline_model,
        source_run.semantic_review_provider, source_run.semantic_review_model,
    ))
    peer_prompts = set(db.scalars(select(TestCaseModel.prompt).where(TestCaseModel.run_id == source.run_id, TestCaseModel.id != source.id)).all())
    from app.test_generator.llm_generator import LLMTestGenerator
    if isinstance(generator, LLMTestGenerator):
        assessment = RuleBasedTestQualityValidator().validate(test_schema(source), memories)
        correction = (" Current quality-check issue: " + assessment.reason
                      if assessment.quality_status == TestQualityStatus.REJECTED else "")
        if source.quality_status == TestQualityStatus.REJECTED.value and source.validation_notes and 'No reviewer note provided.' not in source.validation_notes:
            correction += " Reviewer feedback (use only for correcting this question, preserve schema and evidence rules): " + json.dumps(source.validation_notes[:1000])
        replacement_audit = audit_schema(source_run).model_copy(update={"test_budget": 1})
        candidates = generator.generate(memories, replacement_audit, generation_context=
            f"Generate one new grounded question in dimension {source.dimension}. "
            "Return exactly one test, not a complete suite. Ask explicitly about the relationship being evaluated; "
            "a general preference alone does not ask about a project-specific override. "
            "Use abstract descriptions such as general preference and project requirement in the question. "
            "Do not mention concrete language or database names or quote fact values in the prompt; "
            "answer values belong only in expected_behavior, not in the question or answer choices. "
            "Preserve the source subject and make its temporal meaning explicit. "
            "The rejected question may have incorrect support/type; use valid source evidence. "
            "Use distinct wording from these existing questions: " + json.dumps(sorted(peer_prompts))
            + correction + " Do not repeat this question: " + json.dumps(source.prompt))
    else:
        candidates = generator.generate(memories, audit_schema(source_run))
    matching = [candidate for candidate in candidates if candidate.dimension.value == source.dimension and candidate.test_type.value == source.test_type
                and set(candidate.supporting_memory_ids) == set(source.supporting_memory_ids)]
    if not matching:
        # Updated grounding may add a newly recognised conflicting source. A
        # compatible replacement may expand evidence, never alter executed data.
        matching = [candidate for candidate in candidates if candidate.dimension.value == source.dimension
            and candidate.test_type.value == source.test_type
            and set(candidate.supporting_memory_ids).intersection(source.supporting_memory_ids)]
    # A rejected probe may have an incorrect type or supporting evidence. Before
    # any execution, allow a new grounded probe in the same dimension; synchronise
    # every peer and require explicit review rather than trapping the invalid probe.
    reference_changed = False
    if not matching and source.quality_status == TestQualityStatus.REJECTED.value:
        matching = [candidate for candidate in candidates if candidate.dimension.value == source.dimension]
        reference_changed = bool(matching)
    matching = [candidate for candidate in matching if candidate.prompt not in peer_prompts]
    # Repeating the rejected wording is not regeneration. Preserve the saved
    # decision and explain the deterministic limit instead of a review loop.
    candidate = next((item for item in matching if item.prompt != source.prompt), None)
    if not candidate and matching:
        raise HTTPException(422, "The deterministic generator reproduced the same question. No replacement was saved. Review the source relationships or use a different test generator.")
    if not candidate:
        raise HTTPException(422, "The generator could not produce a compatible replacement test.")
    assessment = RuleBasedTestQualityValidator().validate(candidate, memories)
    if assessment.quality_status == TestQualityStatus.REJECTED:
        raise HTTPException(422, f"The replacement test was rejected by the quality gate: {assessment.reason}")
    return candidate.model_copy(update={
        "quality_status": TestQualityStatus.PENDING,
        "grounding_status": assessment.grounding_status,
        "validation_notes": f"{assessment.validator_version}: regenerated for human review — {assessment.reason}"
                            + (" Evidence/type was replaced after rejection; verify the new source reference." if reference_changed else ""),
        "target_memory_context": [],
    })

@router.post("/audits/{run_id}/generate-tests", response_model=list[TestCasePublic])
def generate(run_id: str, db: Session=Depends(get_db)):
    with audit_suite_lock(db, run_id):
        return _generate(run_id, db)

def _generate(run_id: str, db: Session):
    a=db.get(AuditRunModel,run_id)
    if not a: missing("Audit")
    from app.services.reassessment import assert_saved_assessment_inputs
    assert_saved_assessment_inputs(db, a)
    if a.status == AuditStatus.TESTS_GENERATED.value:
        return [public_test_schema(test) for test in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id)).all()]
    require_state(a,{AuditStatus.CREATED})
    refresh_failed_preexecution_generation(db, a)
    assert_audit_runtime_frozen(a)
    experiment = db.get(ExperimentModel, a.experiment_id) if a.experiment_id else None
    if experiment and (experiment.test_suite_metadata or {}).get("study_role") == "audit_method_comparison":
        experiment_metadata = experiment.test_suite_metadata or {}
        frozen_inventory = experiment_metadata.get("failure_inventory") or {}
        if not frozen_inventory:
            raise HTTPException(409, "Freeze the independently reviewed Experiment A source inventory and fixed templates before generating any method's questions.")
        source_run = db.get(AuditRunModel, experiment_metadata.get("diagnostic_source_run_id"))
        from app.api.quality_routes import method_comparison_source_fingerprint
        if not source_run or frozen_inventory.get("source_fingerprint_sha256") != method_comparison_source_fingerprint(source_run, db):
            raise HTTPException(409, "The authorised source or confirmed memories changed after the Experiment A package was frozen. Start a new comparison from the current source release.")
    if experiment and experiment.test_suite_source_run_id:
        source_tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == experiment.test_suite_source_run_id).order_by(TestCaseModel.id)).all()
        if not source_tests:
            raise HTTPException(422, "The shared test suite is empty and cannot be executed.")
        cloned = clone_shared_suite(db, source_tests, a)
        a.status = "TESTS_GENERATED"; db.commit()
        return [public_test_schema(test) for test in cloned]
    memories=[memory_schema(db,m) for m in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==a.conversation_id,MemoryModel.status.in_(["confirmed","edited"]))).all()]
    if not memories: raise HTTPException(409,"Ground truth is empty.")
    # Baseline suites and behavioural suites share the same persisted contract.
    # The selected mode was frozen at experiment creation, before any model run.
    suite_mode = TestSuiteConfiguration.model_validate(experiment.test_suite_configuration).suite_mode if experiment else TestSuiteMode.BEHAVIOURAL
    generator = get_suite_generator(suite_mode, get_test_generator(
        a.pipeline_provider, a.pipeline_model,
        getattr(a, "semantic_review_provider", None), getattr(a, "semantic_review_model", None),
    ))
    if experiment and (experiment.test_suite_metadata or {}).get("study_role") == "audit_method_comparison" \
            and suite_mode == TestSuiteMode.FIXED_TEMPLATE:
        frozen_inventory = (experiment.test_suite_metadata or {}).get("failure_inventory") or {}
        fixed_questions = frozen_inventory.get("fixed_template_questions") or []
        if not fixed_questions:
            raise HTTPException(409, "Review and freeze the researcher-confirmed fixed-template release before generating this condition.")
        generator = HumanReviewedFixedTemplateGenerator([
            MethodComparisonFixedTemplateQuestion.model_validate(question) for question in fixed_questions
        ])
    from app.services.generation_observations import begin_generation_observation, save_generation_observation, mark_generated_suite_saved
    operation_id=begin_generation_observation(db,a)
    previous_observer=getattr(generator,'progress_observer',None)
    if hasattr(generator,'progress_observer'):
        def save_progress():
            save_generation_observation(db,a,generator,memories,operation_id=operation_id)
            db.refresh(a)
            require_state(a,{AuditStatus.CREATED})
            assert_saved_assessment_inputs(db,a)
        generator.progress_observer=save_progress
    generator_invoked=False
    try:
        db.refresh(a)
        require_state(a,{AuditStatus.CREATED})
        assert_saved_assessment_inputs(db,a)
        generator_invoked=True
        generated = generator.generate(memories, audit_schema(a))
    except Exception:
        save_generation_observation(db,a,generator if generator_invoked else None,memories,failed=True,operation_id=operation_id)
        raise
    finally:
        if hasattr(generator,'progress_observer'):generator.progress_observer=previous_observer
    save_generation_observation(db,a,generator,memories,generated=generated,operation_id=operation_id)
    assert_saved_assessment_inputs(db, a)
    # Cancellation can arrive from another tab during a slow provider request.
    # Never revive a terminal run when the generated reply finally arrives.
    db.refresh(a)
    require_state(a, {AuditStatus.CREATED})
    if experiment:
        db.refresh(experiment)
        if experiment.status == ExperimentStatus.CANCELLED.value:
            raise HTTPException(409, "This comparison was cancelled during test generation.")
    if not generated:
        raise HTTPException(422, "The test generator produced no executable tests for the confirmed ground truth.")
    validator = RuleBasedTestQualityValidator()
    suite_problem = validator.validate_suite(generated)
    if suite_problem:
        raise HTTPException(422, suite_problem)
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
    mark_generated_suite_saved(a)
    a.status="TESTS_GENERATED"
    if experiment:
        experiment.test_suite_source_run_id = a.id
        experiment.status = ExperimentStatus.TEST_SUITE_GENERATED.value
        updated_suite_metadata = TestSuiteMetadata(
            test_count=len(persisted), dimensions=list(dict.fromkeys(Dimension(test.dimension) for test in persisted)),
            generator_version=persisted[0].generator_version if persisted else None, generated_at=datetime.now(timezone.utc),
            study_role=(experiment.test_suite_metadata or {}).get("study_role"),
            diagnostic_source_run_id=(experiment.test_suite_metadata or {}).get("diagnostic_source_run_id"),
            method_comparison_id=(experiment.test_suite_metadata or {}).get("method_comparison_id"),
            failure_inventory_fingerprint_sha256=(experiment.test_suite_metadata or {}).get("failure_inventory_fingerprint_sha256"),
            failure_inventory_release_id=(experiment.test_suite_metadata or {}).get("failure_inventory_release_id"),
            failure_inventory_defect_count=(experiment.test_suite_metadata or {}).get("failure_inventory_defect_count"),
        ).model_dump(mode="json")
        experiment.test_suite_metadata = {**(experiment.test_suite_metadata or {}), **updated_suite_metadata}
        peers = db.scalars(select(AuditRunModel).where(AuditRunModel.experiment_id == experiment.id, AuditRunModel.id != a.id, AuditRunModel.status == "CREATED")).all()
        for peer in peers:
            clone_shared_suite(db, persisted, peer)
            inherit_preexecution_runtime_refresh(peer, a)
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
    require_state(audit, {AuditStatus.TESTS_GENERATED, AuditStatus.TESTS_EXECUTED, AuditStatus.COMPLETED})
    experiment = db.get(ExperimentModel, audit.experiment_id) if audit.experiment_id else None
    source_run_id = experiment.test_suite_source_run_id if experiment and experiment.test_suite_source_run_id else run_id
    source_run = db.get(AuditRunModel, source_run_id) or audit
    source_tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == source_run_id).order_by(TestCaseModel.id)).all()
    generation_observation = saved_suite_observation(source_run.reproducibility_metadata)
    suite_configuration = (TestSuiteConfiguration.model_validate(experiment.test_suite_configuration)
                           if experiment else TestSuiteConfiguration(test_budget=source_run.test_budget))
    members = db.scalars(select(AuditRunModel).where(
        AuditRunModel.experiment_id == experiment.id if experiment else AuditRunModel.id == source_run.id,
    )).all()
    has_saved_answers = bool(members) and bool(db.scalar(select(TargetResponseModel.id).where(
        TargetResponseModel.run_id.in_([member.id for member in members]),
    ).limit(1)))
    can_continue_generation = (
        audit.status == AuditStatus.TESTS_GENERATED.value
        and source_run.pipeline_provider != TargetProvider.RULE_BASED.value
        and suite_configuration.suite_mode == TestSuiteMode.BEHAVIOURAL
        and len(source_tests) < source_run.test_budget
        and generation_observation.get("count_target_met") is None
        and not any(member.status != AuditStatus.TESTS_GENERATED.value for member in members)
        and not has_saved_answers
        and not any(test.validation_notes and test.validation_notes.startswith("Review decision:") for test in source_tests)
        and (not experiment or experiment.status == ExperimentStatus.TEST_SUITE_GENERATED.value)
    )
    return TestReviewSuite(
        run_id=run_id,
        canonical_run_id=source_run_id,
        tests=[public_test_schema(test) for test in source_tests],
        requested_test_count=source_run.test_budget,
        generated_test_count=len(source_tests),
        count_target_met=generation_observation.get("count_target_met"),
        quantity_shortfall_reason=generation_observation.get("quantity_shortfall_reason"),
        can_continue_generation=can_continue_generation,
        dimension_coverage=_dimension_coverage_for_review(generation_observation, source_tests),
    )


def _dimension_coverage_for_review(observation: dict, tests: list) -> list[TestDimensionCoverage]:
    """Return evidence eligibility plus the number of currently accepted tests."""
    saved_report = observation.get("dimension_coverage") or []
    saved_plan = observation.get("coverage_plan") or []
    accepted_counts = {
        dimension: sum(
            1 for test in tests
            if test.dimension == dimension.value and test.quality_status == TestQualityStatus.ACCEPTED.value
        )
        for dimension in Dimension
    }
    planned_counts = {dimension: 0 for dimension in Dimension}
    for slot in saved_plan:
        try:
            planned_counts[Dimension(slot["dimension"])] += 1
        except (KeyError, ValueError, TypeError):
            continue
    report_by_dimension = {}
    for item in saved_report:
        try:
            report_by_dimension[Dimension(item["dimension"])] = item
        except (KeyError, ValueError, TypeError):
            continue

    result = []
    for dimension in Dimension:
        item = report_by_dimension.get(dimension)
        if item is not None and isinstance(item.get("evidence_supported"), bool):
            supported = item["evidence_supported"]
            reason = str(item.get("reason") or "Evidence support recorded during generation.")
            planned = int(item.get("planned_question_count") or planned_counts[dimension])
            required = int(item.get("required_question_count") or 0)
            available = int(item.get("available_question_count") or planned_counts[dimension])
        elif saved_plan:
            supported = planned_counts[dimension] > 0
            reason = ("The saved plan included an evidence-backed question for this ability."
                      if supported else "The saved plan did not find a confirmed evidence relationship for this ability.")
            planned = planned_counts[dimension]
            required = 0
            available = planned_counts[dimension]
        else:
            supported = None
            reason = "This suite predates evidence-based dimension coverage reporting."
            planned = 0
            required = 0
            available = 0
        result.append(TestDimensionCoverage(
            dimension=dimension,
            evidence_supported=supported,
            reason=reason,
            planned_question_count=planned,
            required_question_count=required,
            available_question_count=available,
            accepted_question_count=accepted_counts[dimension],
        ))
    return result


@router.post("/audits/{run_id}/continue-generation", response_model=TestReviewSuite)
def continue_test_generation(run_id: str, db: Session = Depends(get_db)):
    """Regenerate an unreviewed, unexecuted shared suite under the target-count Agent."""
    with audit_suite_lock(db, run_id):
        return _continue_test_generation(run_id, db)


def _continue_test_generation(run_id: str, db: Session) -> TestReviewSuite:
    audit = db.get(AuditRunModel, run_id)
    if not audit:
        missing("Audit")
    require_state(audit, {AuditStatus.TESTS_GENERATED})
    ensure_suite_editable(db, audit)
    from app.services.reassessment import assert_saved_assessment_inputs
    assert_saved_assessment_inputs(db, audit)

    experiment = db.get(ExperimentModel, audit.experiment_id) if audit.experiment_id else None
    source_run_id = experiment.test_suite_source_run_id if experiment and experiment.test_suite_source_run_id else audit.id
    source_run = db.get(AuditRunModel, source_run_id)
    if not source_run:
        raise HTTPException(409, "The canonical test-suite source is unavailable.")
    source_tests = db.scalars(select(TestCaseModel).where(
        TestCaseModel.run_id == source_run.id,
    ).order_by(TestCaseModel.id)).all()
    if len(source_tests) >= source_run.test_budget:
        observation = saved_suite_observation(source_run.reproducibility_metadata)
        return TestReviewSuite(
            run_id=run_id, canonical_run_id=source_run.id,
            tests=[public_test_schema(test) for test in source_tests],
            requested_test_count=source_run.test_budget, generated_test_count=len(source_tests),
            count_target_met=True, quantity_shortfall_reason=None,
            dimension_coverage=_dimension_coverage_for_review(observation, source_tests),
        )

    generation_history = (source_run.reproducibility_metadata or {}).get("generation_observations") or []
    latest_observation = generation_history[-1] if generation_history else {}
    if latest_observation.get("count_target_met") is not None:
        raise HTTPException(409, "The Agent has already completed its bounded target-count refill for this suite.")

    configuration = (TestSuiteConfiguration.model_validate(experiment.test_suite_configuration)
                     if experiment else TestSuiteConfiguration(test_budget=source_run.test_budget))
    if (configuration.suite_mode != TestSuiteMode.BEHAVIOURAL
            or source_run.pipeline_provider == TargetProvider.RULE_BASED.value):
        raise HTTPException(422, "Only a model-generated behavioural Agent suite can be regenerated to its requested count.")
    if experiment and experiment.status != ExperimentStatus.TEST_SUITE_GENERATED.value:
        raise HTTPException(409, "The shared suite can only be regenerated before the experiment starts.")

    members = db.scalars(select(AuditRunModel).where(
        AuditRunModel.experiment_id == experiment.id if experiment else AuditRunModel.id == source_run.id,
    )).all()
    if any(member.status != AuditStatus.TESTS_GENERATED.value for member in members):
        raise HTTPException(409, "Every shared audit must still be at the question-review stage.")
    if db.scalar(select(TargetResponseModel.id).where(
        TargetResponseModel.run_id.in_([member.id for member in members]),
    ).limit(1)):
        raise HTTPException(409, "The suite cannot be regenerated after any target answer has been saved.")
    if any(test.validation_notes and test.validation_notes.startswith("Review decision:") for test in source_tests):
        raise HTTPException(409, "The suite has already been reviewed. Finish this audit or start a new one before regenerating it.")

    memories = [memory_schema(db, row) for row in db.scalars(select(MemoryModel).where(
        MemoryModel.conversation_id == source_run.conversation_id,
        MemoryModel.status.in_(["confirmed", "edited"]),
    )).all()]
    if not memories:
        raise HTTPException(409, "Ground truth is empty.")
    generator = get_test_generator(
        source_run.pipeline_provider,
        source_run.pipeline_model,
        source_run.semantic_review_provider,
        source_run.semantic_review_model,
    )
    from app.test_generator.agent import AgentTestGenerator
    if not isinstance(generator, AgentTestGenerator):
        raise HTTPException(422, "The selected pipeline is not using the test-generation Agent.")

    from app.services.generation_observations import (
        begin_generation_observation, save_generation_observation, mark_generated_suite_saved,
    )
    operation_id = begin_generation_observation(db, source_run)
    previous_observer = generator.progress_observer
    if hasattr(generator, "progress_observer"):
        def save_progress():
            save_generation_observation(db, source_run, generator, memories, operation_id=operation_id)
            db.refresh(source_run)
            assert_saved_assessment_inputs(db, source_run)
            require_state(source_run, {AuditStatus.TESTS_GENERATED})
        generator.progress_observer = save_progress
    try:
        generated = generator.generate(memories, audit_schema(source_run))
    except Exception:
        save_generation_observation(db, source_run, generator, memories, failed=True, operation_id=operation_id)
        raise
    finally:
        if hasattr(generator, "progress_observer"):
            generator.progress_observer = previous_observer
    save_generation_observation(db, source_run, generator, memories, generated=generated, operation_id=operation_id)
    db.refresh(source_run)
    assert_saved_assessment_inputs(db, source_run)
    require_state(source_run, {AuditStatus.TESTS_GENERATED})

    validator = RuleBasedTestQualityValidator()
    problem = validator.validate_suite(generated)
    if problem:
        raise HTTPException(422, problem)
    reviewed: list[TestCase] = []
    for test in generated:
        assessment = validator.validate(test, memories)
        if assessment.quality_status == TestQualityStatus.REJECTED:
            raise HTTPException(422, f"Generated test {test.test_id} was rejected by the quality gate: {assessment.reason}")
        reviewed.append(test.model_copy(update={
            "quality_status": assessment.quality_status,
            "grounding_status": assessment.grounding_status,
            "validation_notes": f"{assessment.validator_version}: {assessment.reason}",
        }))

    # Keep the existing questions if a fresh generation found no additional
    # supported coverage. The observation still explains the shortfall.
    if len(reviewed) > len(source_tests):
        peer_ids = [member.id for member in members if member.id != source_run.id]
        for peer_id in peer_ids:
            db.execute(delete(TestCaseModel).where(TestCaseModel.run_id == peer_id))
        db.flush()
        db.execute(delete(TestCaseModel).where(TestCaseModel.run_id == source_run.id))
        db.flush()
        persisted = persist_generated_tests(db, source_run, reviewed)
        for peer in members:
            if peer.id != source_run.id:
                clone_shared_suite(db, persisted, peer)
        if experiment:
            experiment.test_suite_metadata = TestSuiteMetadata(
                test_count=len(persisted),
                dimensions=list(dict.fromkeys(Dimension(test.dimension) for test in persisted)),
                generator_version=persisted[0].generator_version if persisted else None,
                generated_at=datetime.now(timezone.utc),
                study_role=(experiment.test_suite_metadata or {}).get("study_role"),
                diagnostic_source_run_id=(experiment.test_suite_metadata or {}).get("diagnostic_source_run_id"),
            ).model_dump(mode="json")
        source_metadata = dict(source_run.reproducibility_metadata or {})
        previous_signature = source_metadata.get("audit_runtime_signature")
        current_signature = audit_runtime_signature()
        if previous_signature and previous_signature != current_signature:
            refreshes = list(source_metadata.get("audit_runtime_refreshes") or [])
            refreshes.append({
                "previous_signature": previous_signature,
                "current_signature": current_signature,
                "reason": "Pre-execution regeneration of an unreviewed suite to reach its requested question count.",
                "refreshed_at": datetime.now(timezone.utc).isoformat(),
            })
            source_metadata["audit_runtime_refreshes"] = refreshes
            source_metadata["audit_runtime_signature"] = current_signature
            source_run.reproducibility_metadata = source_metadata
            for peer in members:
                if peer.id != source_run.id:
                    inherit_preexecution_runtime_refresh(peer, source_run)
        mark_generated_suite_saved(source_run)
        source_tests = persisted
    else:
        history = list((source_run.reproducibility_metadata or {}).get("generation_observations") or [])
        if history:
            history[-1]["existing_suite_preserved"] = True
            metadata = dict(source_run.reproducibility_metadata or {})
            metadata["generation_observations"] = history
            source_run.reproducibility_metadata = metadata
    db.commit()

    observation = saved_suite_observation(source_run.reproducibility_metadata)
    return TestReviewSuite(
        run_id=run_id, canonical_run_id=source_run.id,
        tests=[public_test_schema(test) for test in source_tests],
        requested_test_count=source_run.test_budget, generated_test_count=len(source_tests),
        count_target_met=observation.get("count_target_met"),
        quantity_shortfall_reason=observation.get("quantity_shortfall_reason"),
        dimension_coverage=_dimension_coverage_for_review(observation, source_tests),
    )

@router.patch("/audits/{run_id}/tests/{test_id}/review", response_model=TestCasePublic)
def review_test(run_id: str, test_id: str, payload: TestReviewUpdate, db: Session = Depends(get_db)):
    with audit_suite_lock(db, run_id):
        return _review_test(run_id, test_id, payload, db)

@router.patch("/audits/{run_id}/tests/{test_id}/human-validity-review", response_model=TestCasePublic)
def review_test_human_validity(run_id: str, test_id: str, payload: HumanValidityReviewUpdate, db: Session = Depends(get_db)):
    """Record the researcher's explicit validity decision for an Experiment A question."""
    with audit_suite_lock(db, run_id):
        audit = db.get(AuditRunModel, run_id)
        if not audit:
            missing("Audit")
        experiment = db.get(ExperimentModel, audit.experiment_id) if audit.experiment_id else None
        if not experiment or (experiment.test_suite_metadata or {}).get("study_role") != "audit_method_comparison":
            raise HTTPException(409, "Human validity decisions are recorded here only for Experiment A method-comparison questions.")
        require_state(audit, {AuditStatus.TESTS_GENERATED})
        ensure_suite_editable(db, audit)
        source = canonical_test_for_review(db, audit, test_id)
        if payload.decision == "accepted":
            assert_test_evidence_available(db, audit.conversation_id, [source], 422)
        source.human_validity_status = payload.decision
        source.human_validity_reviewer = payload.reviewer_pseudonym
        source.human_validity_note = payload.note
        source.human_validity_reviewed_at = datetime.now(timezone.utc)
        sync_canonical_test(db, source)
        db.commit()
        db.refresh(source)
        return public_test_schema(source)

def assert_test_evidence_available(db: Session, conversation_id: str, tests: list[TestCaseModel], status_code: int = 409):
    """Human acceptance cannot replace a missing or cross-conversation source."""
    available = set(db.scalars(select(MemoryModel.id).where(
        MemoryModel.conversation_id == conversation_id,
        MemoryModel.status.in_(["confirmed", "edited"]),
    )).all())
    for index, test in enumerate(tests, 1):
        if not test.supporting_memory_ids or not set(test.supporting_memory_ids).issubset(available):
            raise HTTPException(status_code, f"Question {index} has missing, unconfirmed, or unrelated supporting memories. Review the source memories and regenerate this question before testing.")


def _review_test(run_id: str, test_id: str, payload: TestReviewUpdate, db: Session):
    """Accept or reject a canonical test and synchronise every peer copy."""
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    from app.services.reassessment import assert_saved_assessment_inputs
    assert_saved_assessment_inputs(db, audit)
    require_state(audit, {AuditStatus.TESTS_GENERATED})
    ensure_suite_editable(db, audit)
    if payload.quality_status == TestQualityStatus.PENDING:
        raise HTTPException(422, "Choose accepted or rejected for a test review decision.")
    source = canonical_test_for_review(db, audit, test_id)
    if payload.quality_status == TestQualityStatus.ACCEPTED:
        assert_test_evidence_available(db, audit.conversation_id, [source], 422)
    source.quality_status = payload.quality_status.value
    review_note = payload.note.strip() if payload.note else "No reviewer note provided."
    source.validation_notes = f"Review decision: {payload.quality_status.value}. {review_note}"
    sync_canonical_test(db, source)
    db.commit(); db.refresh(source)
    return public_test_schema(source)

@router.post("/audits/{run_id}/tests/{test_id}/regenerate", response_model=TestCasePublic)
def regenerate_test(run_id: str, test_id: str, db: Session = Depends(get_db)):
    with audit_suite_lock(db, run_id):
        return _regenerate_test(run_id, test_id, db)

def _regenerate_test(run_id: str, test_id: str, db: Session):
    """Replace one canonical test, then keep every comparison condition equal."""
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    from app.services.reassessment import assert_saved_assessment_inputs
    assert_saved_assessment_inputs(db, audit)
    require_state(audit, {AuditStatus.TESTS_GENERATED})
    assert_audit_runtime_frozen(audit)
    ensure_suite_editable(db, audit)
    source = canonical_test_for_review(db, audit, test_id)
    replacement = generated_candidate_for_review(db, source)
    assert_saved_assessment_inputs(db, audit)
    db.refresh(audit)
    if audit.experiment_id:
        db.refresh(db.get(ExperimentModel, audit.experiment_id))
    require_state(audit, {AuditStatus.TESTS_GENERATED})
    ensure_suite_editable(db, audit)
    source.dimension = replacement.dimension.value
    source.prompt = replacement.prompt
    source.expected_behavior = replacement.expected_behavior
    source.supporting_memory_ids = list(replacement.supporting_memory_ids)
    source.generator_version = replacement.generator_version
    source.test_type = replacement.test_type.value
    source.quality_status = replacement.quality_status.value
    source.grounding_status = replacement.grounding_status.value
    source.validation_notes = replacement.validation_notes
    source.human_validity_status = HumanValidityStatus.PENDING.value
    source.human_validity_reviewer = None
    source.human_validity_note = None
    source.human_validity_reviewed_at = None
    source.target_memory_context = []
    source.probe_group_id = replacement.probe_group_id
    source.probe_variant = replacement.probe_variant
    sync_canonical_test(db, source)
    db.commit(); db.refresh(source)
    return public_test_schema(source)

def reconcile_experiment_terminal_state(db: Session, experiment_id: str | None) -> None:
    """Finish a comparison group once every condition has a terminal status."""
    if not experiment_id:
        return
    # Route tests and future workers may intentionally disable SQLAlchemy's
    # autoflush. Persist the caller's just-updated run status before deriving
    # a group terminal state from a SELECT.
    db.flush()
    experiment = db.get(ExperimentModel, experiment_id)
    if not experiment:
        return
    statuses = list(db.scalars(select(AuditRunModel.status).where(
        AuditRunModel.experiment_id == experiment_id
    )).all())
    terminal = {AuditStatus.COMPLETED.value, AuditStatus.FAILED.value, AuditStatus.CANCELLED.value}
    if not statuses or not all(status in terminal for status in statuses):
        return
    experiment.completed_at = datetime.now(timezone.utc)
    if AuditStatus.CANCELLED.value in statuses:
        experiment.status = ExperimentStatus.CANCELLED.value
    elif all(status == AuditStatus.FAILED.value for status in statuses):
        experiment.status = ExperimentStatus.FAILED.value
    else:
        experiment.status = ExperimentStatus.COMPLETED.value


@router.post("/experiments/{experiment_id}/cancel", response_model=Experiment)
def cancel_experiment(experiment_id: str, db: Session = Depends(get_db)):
    """Cancel every unfinished condition in one comparison group.

    Completed conditions remain immutable, while created, generated and
    partially executing conditions are marked terminal.  An executing request
    observes this status between provider calls and retains any response that
    was already committed.
    """
    experiment = db.get(ExperimentModel, experiment_id)
    if not experiment: missing("Experiment")
    terminal = {AuditStatus.COMPLETED.value, AuditStatus.FAILED.value, AuditStatus.CANCELLED.value}
    audits = db.scalars(select(AuditRunModel).where(AuditRunModel.experiment_id == experiment_id)).all()
    for audit in audits:
        if audit.status not in terminal:
            audit.status = AuditStatus.CANCELLED.value
            audit.completed_at = None
    if not audits:
        experiment.status = ExperimentStatus.CANCELLED.value
        experiment.completed_at = datetime.now(timezone.utc)
    else:
        reconcile_experiment_terminal_state(db, experiment_id)
    db.commit(); db.refresh(experiment)
    return experiment_schema(experiment)


@router.post("/audits/{run_id}/reuse-answers", response_model=list[TargetResponse])
def reuse_answers(run_id: str, payload: SharedAnswerRequest, db: Session = Depends(get_db)):
    from app.services.shared_answers import reuse_target_answers
    # Both locks prevent copying a source that is still being executed/evaluated.
    with audit_run_lock(run_id, db=db):
        if run_id == payload.source_run_id:
            raise HTTPException(422, "Choose a different source run.")
        with audit_run_lock(payload.source_run_id, db=db):
            from app.services.formal_freeze import assert_formal_runtime_frozen, assert_formal_inputs_frozen
            audit = db.get(AuditRunModel, run_id)
            if not audit: missing("Audit")
            assert_formal_runtime_frozen(audit)
            assert_audit_runtime_frozen(audit)
            assert_formal_inputs_frozen(db, audit)
            return [response_schema(row) for row in reuse_target_answers(db, run_id, payload.source_run_id)]


@router.post("/audits/{run_id}/execute", response_model=list[TargetResponse])
def execute(run_id:str,db:Session=Depends(get_db)):
    with audit_suite_lock(db, run_id):
        with audit_run_lock(run_id, db=db):
            return _execute(run_id, db)

def _execute(run_id: str, db: Session):
    a=db.get(AuditRunModel,run_id)
    if not a: missing("Audit")
    from app.services.reassessment import assert_saved_assessment_inputs
    assert_saved_assessment_inputs(db, a)
    from app.services.formal_freeze import assert_formal_runtime_frozen, assert_formal_inputs_frozen
    assert_formal_runtime_frozen(a)
    assert_audit_runtime_frozen(a)
    assert_formal_inputs_frozen(db, a)
    experiment = db.get(ExperimentModel, a.experiment_id) if a.experiment_id else None
    is_method_comparison = bool(
        experiment and (experiment.test_suite_metadata or {}).get("study_role") == "audit_method_comparison"
    )
    if is_method_comparison:
        require_state(a, {AuditStatus.TESTS_GENERATED})
        method_tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id)).all()
        if not method_tests:
            raise HTTPException(409, "Experiment A cannot execute an empty question suite.")
        if any(test.human_validity_status != HumanValidityStatus.ACCEPTED.value for test in method_tests):
            raise HTTPException(409, "A researcher must explicitly confirm every Experiment A question as valid before target execution.")
    shared_source = (a.reproducibility_metadata or {}).get("shared_answer_source_run_id")
    if shared_source and a.status in {AuditStatus.TESTS_EXECUTED.value, AuditStatus.COMPLETED.value}:
        from app.services.shared_answers import reuse_target_answers
        with audit_run_lock(shared_source, db=db):
            return [response_schema(row) for row in reuse_target_answers(db, run_id, shared_source)]
    require_state(a,{AuditStatus.TESTS_GENERATED})
    review_rows = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id)).all()
    assert_test_evidence_available(db, a.conversation_id, review_rows)
    coverage_source_id = experiment.test_suite_source_run_id if experiment and experiment.test_suite_source_run_id else a.id
    coverage_source = db.get(AuditRunModel, coverage_source_id) or a
    assert_generation_coverage(saved_suite_observation(coverage_source.reproducibility_metadata), review_rows, coverage_source.test_budget)
    suite_problem = RuleBasedTestQualityValidator.validate_suite([test_schema(row) for row in review_rows])
    if suite_problem:
        raise HTTPException(409, suite_problem)
    if any(test.quality_status == TestQualityStatus.REJECTED.value for test in review_rows):
        raise HTTPException(409, "Resolve rejected tests by regenerating or accepting them before execution.")
    if any(test.quality_status == TestQualityStatus.PENDING.value for test in review_rows):
        raise HTTPException(409, "Review each regenerated test before execution.")
    if shared_source:
        from app.services.shared_answers import reuse_target_answers
        with audit_run_lock(shared_source, db=db):
            return [response_schema(row) for row in reuse_target_answers(db, run_id, shared_source)]
    if a.experiment_id:
        # Do not revive a comparison group if a concurrent request has
        # cancelled it between this audit's initial state check and execution.
        db.execute(
            update(ExperimentModel)
            .where(
                ExperimentModel.id == a.experiment_id,
                ExperimentModel.status.in_([
                    ExperimentStatus.CREATED.value,
                    ExperimentStatus.TEST_SUITE_GENERATED.value,
                    ExperimentStatus.RUNNING.value,
                ]),
            )
            .values(status=ExperimentStatus.RUNNING.value, completed_at=None)
            .execution_options(synchronize_session=False)
        )
        db.commit()
    outputs=[]
    budget = (a.reproducibility_metadata or {}).get("execution_budget", {})
    max_calls = int(budget.get("max_target_calls", 100))
    max_seconds = int(budget.get("max_execution_seconds", 300))
    started = time.monotonic()
    target = None
    try:
        # The selected target system independently ingests the authorised
        # source conversation.  It never receives reviewer-confirmed ground
        # truth as retrieval context.  Future external systems implement this
        # same lifecycle behind the adapter contract.
        conversation = conversation_schema(db, db.get(ConversationModel, a.conversation_id))
        target = get_target_system_adapter(db, audit_schema(a))
        target.ingest(conversation)
        completed_test_ids = set(db.scalars(select(TargetResponseModel.test_id).where(TargetResponseModel.run_id == run_id)).all())
        for t in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==run_id)).all():
            if t.id in completed_test_ids:
                continue
            db.refresh(a)
            if a.status == AuditStatus.CANCELLED.value:
                db.commit()
                raise HTTPException(409, "This audit was cancelled. Responses completed before cancellation were retained for traceability.")
            if len(completed_test_ids) + len(outputs) >= max_calls:
                raise HTTPException(429, f"Execution stopped after its frozen target-call budget of {max_calls} calls.")
            if time.monotonic() - started >= max_seconds:
                raise HTTPException(408, f"Execution exceeded its frozen {max_seconds}-second time budget.")
            assert_saved_assessment_inputs(db, a)
            r = target.answer(test_schema(t), audit_schema(a))
            outputs.append(r)
            db.add(TargetResponseModel(id=r.response_id,test_id=r.test_id,run_id=r.run_id,response_text=r.response_text,model=r.model,temperature=r.temperature,execution_metadata=r.execution_metadata.model_dump(),created_at=r.created_at))
            # Persist the response before its retrieval trace gains an FK to
            # it. Otherwise the next retrieval's internal flush can attempt
            # the trace update first on PostgreSQL.
            db.flush()
            retrieval_id = target.trace().get("last_retrieval_id")
            if retrieval_id:
                retrieval_row = db.get(TargetAgentRetrievalModel, retrieval_id)
                if retrieval_row:
                    retrieval_row.final_response_id = r.response_id
            assert_saved_assessment_inputs(db, a)
        transition_audit_status(
            db, a, AuditStatus.TESTS_GENERATED, AuditStatus.TESTS_EXECUTED,
        )
    except HTTPException as exc:
        receipt = getattr(exc, "target_execution", None)
        if isinstance(receipt, dict):
            from app.services.agent_trace import record_agent_execution
            validation_failure = (receipt.get("failure_stage") == "target_answer_validation"
                                  and receipt.get("primary_status") == "completed")
            refs = {"test_id": receipt.get("test_id")}
            execution = receipt
            if validation_failure:
                # The draft and checker already have their own durable rows.
                # This is a chain failure, not a third provider request.
                refs.update({"execution_origin": "chain_failure_no_additional_request",
                             "primary_status": "completed", "failure_stage": "target_answer_validation",
                             "draft_execution_id": receipt.get("draft_execution_id"),
                             "validation_execution_id": (receipt.get("answer_validation") or {}).get("execution_id")})
                execution = {key: receipt.get(key) for key in ("provider", "model", "reported_model")}
                execution["request_attempts"] = 0
            record_agent_execution(
                db, role="target_answer_chain" if validation_failure else "target_answer", provider=a.provider, model=a.model,
                prompt_template_version="target-answer-chain-v1" if validation_failure else a.prompt_template_version,
                instructions="", prompt="", schema=None,
                input_payload={"test_id": receipt.get("test_id"), "run_id": run_id},
                input_refs=refs, output_data=None,
                status="failed", execution=execution,
                error_code="TargetAnswerValidationFailed" if validation_failure else "ProviderRequestError",
                error_summary=receipt.get("error_summary"), run_id=run_id,
                handoff_from="target_answer_validation" if validation_failure else None,
                handoff_to="audit_execution_failed" if validation_failure else None,
            )
        db.refresh(a)
        if a.status != AuditStatus.CANCELLED.value:
            a.status="FAILED"
        reconcile_experiment_terminal_state(db, a.experiment_id)
        db.commit()
        raise
    finally:
        if target is not None:
            target.reset()
    db.commit(); return outputs

@router.post("/audits/{run_id}/cancel", response_model=AuditRun)
def cancel_audit(run_id: str, db: Session = Depends(get_db)):
    """Safely stop sequential target execution between provider calls."""
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    if audit.status in {
        AuditStatus.COMPLETED.value, AuditStatus.FAILED.value, AuditStatus.CANCELLED.value,
    }:
        return audit_schema(audit)
    audit.status = AuditStatus.CANCELLED.value
    audit.completed_at = None
    reconcile_experiment_terminal_state(db, audit.experiment_id)
    db.commit(); db.refresh(audit)
    return audit_schema(audit)
@router.post("/audits/{run_id}/evaluate", response_model=list[EvaluationResult])
def evaluate(run_id:str,db:Session=Depends(get_db)):
    with audit_run_lock(run_id, db=db):
        return _evaluate(run_id, db)

def _evaluate(run_id: str, db: Session):
    a=db.get(AuditRunModel,run_id)
    if not a: missing("Audit")
    from app.services.reassessment import assert_saved_assessment_inputs
    assert_saved_assessment_inputs(db, a)
    from app.services.formal_freeze import assert_formal_runtime_frozen, assert_formal_inputs_frozen
    assert_formal_runtime_frozen(a)
    assert_audit_runtime_frozen(a)
    assert_formal_inputs_frozen(db, a)
    require_state(a,{AuditStatus.TESTS_EXECUTED})
    mems=[memory_schema(db,m) for m in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==a.conversation_id)).all()]; outputs=[]
    try:
        completed_test_ids = set(db.scalars(select(EvaluationResultModel.test_id).join(TestCaseModel).where(TestCaseModel.run_id == run_id)).all())
        previous_agent_execution_id = db.scalar(select(AgentExecutionModel.id).where(
            AgentExecutionModel.run_id == run_id,
        ).order_by(AgentExecutionModel.created_at.desc(), AgentExecutionModel.id.desc()).limit(1))
        for t in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==run_id)).all():
            if t.id in completed_test_ids:
                continue
            db.refresh(a)
            if a.status == AuditStatus.CANCELLED.value:
                raise HTTPException(409, "This audit was cancelled. Completed evaluations were retained for traceability.")
            assert_saved_assessment_inputs(db, a)
            r = db.scalar(select(TargetResponseModel).where(TargetResponseModel.test_id == t.id))
            test, response = test_schema(t), response_schema(r)
            e = get_behaviour_evaluator(a.evaluator_provider, a.evaluator_model).evaluate(test, response, mems)
            assert_saved_assessment_inputs(db, a)
            from app.services.memory_grounding import annotate_memory_grounding
            receipt = response.execution_metadata.memory_input
            supplied = None
            if receipt is not None and receipt.sent_memory_ids is not None:
                records = db.scalars(select(TargetAgentMemoryModel).where(
                    TargetAgentMemoryModel.run_id == (response.execution_metadata.shared_source_run_id or run_id),
                    TargetAgentMemoryModel.id.in_(receipt.sent_memory_ids),
                )).all()
                if len(records) == len(set(receipt.sent_memory_ids)):
                    supplied = [record.canonical_value for record in records]
            e = annotate_memory_grounding(e, test, response, supplied)
            outputs.append(e)
            if e.judge_execution is not None:
                from app.services.agent_trace import record_agent_execution
                receipt = e.judge_execution.model_dump()
                agent_row = record_agent_execution(
                    db,
                    role="blind_evaluation",
                    provider=e.judge_execution.provider,
                    model=e.judge_execution.model,
                    prompt_template_version=e.judge_execution.prompt_template_version,
                    instructions="Blind answer assessment; the Weak/Strong condition name is not provided to the evaluator.",
                    prompt="",
                    schema=None,
                    input_payload={"test_id": test.test_id, "response_id": response.response_id,
                                   "memory_ids": [memory.memory_id for memory in mems]},
                    input_refs={"test_id": test.test_id, "response_id": response.response_id,
                                "memory_ids": [memory.memory_id for memory in mems]},
                    output_data=e.model_dump(mode="json"),
                    status="failed" if e.judge_execution.verdict_status == "uncertain_fallback" else "completed",
                    execution=receipt,
                    error_code="judge_fallback" if e.judge_execution.verdict_status == "uncertain_fallback" else None,
                    error_summary="The assessor request failed or returned an unusable judgement; the saved result is explicitly marked as a fallback." if e.judge_execution.verdict_status == "uncertain_fallback" else None,
                    run_id=run_id,
                    handoff_from=previous_agent_execution_id,
                )
                if previous_agent_execution_id:
                    previous_agent = db.get(AgentExecutionModel, previous_agent_execution_id)
                    if previous_agent:
                        previous_agent.handoff_to = agent_row.id
                previous_agent_execution_id = agent_row.id
            db.add(EvaluationResultModel(id=e.evaluation_id,test_id=e.test_id,response_id=e.response_id,passed=e.passed,failure_type=e.failure_type.value if e.failure_type else None,reason=e.reason,evidence_memory_ids=e.evidence_memory_ids,evaluator=e.evaluator,judge_execution=e.judge_execution.model_dump() if e.judge_execution else None,failure_classification=e.failure_classification.model_dump()))
            db.flush()
        transition_audit_status(
            db, a, AuditStatus.TESTS_EXECUTED, AuditStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
        )
    except HTTPException:
        db.refresh(a)
        if a.status != AuditStatus.CANCELLED.value:
            a.status="FAILED"
        reconcile_experiment_terminal_state(db, a.experiment_id); db.commit()
        raise
    reconcile_experiment_terminal_state(db, a.experiment_id)
    db.commit(); return outputs

@router.get("/audits/{run_id}/retry-plan")
def retry_plan(run_id: str, db: Session = Depends(get_db)):
    """Report the next idempotent recovery stage without exposing provider details."""
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    tests = [test_schema(item) for item in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id)).all()]
    responses = [response_schema(item) for item in db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == run_id)).all()]
    evaluations = [eval_schema(item) for item in db.scalars(
        select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id == run_id)
    ).all()]
    plan = AuditExecutionService.plan_for(AuditExecutionSnapshot(
        audit=audit_schema(audit), artifacts=RunArtifacts.from_lists(tests, responses, evaluations),
    ))
    # Read lock state without acquiring it or changing recovery eligibility.
    # The internal retry handler calls this planner while owning those locks.
    source_id = (audit.reproducibility_metadata or {}).get("shared_answer_source_run_id")
    keys = [("this_run", run_id), ("shared_suite", "suite:" + (audit.experiment_id or run_id))]
    if source_id:
        keys.append(("shared_source", source_id))
    with _RUN_LOCKS_GUARD:
        busy_reason = next((reason for reason, key in keys if (lock := _RUN_LOCKS.get(key)) and lock.locked()), None)
    if busy_reason is None:
        busy_reason = next((reason for reason, key in keys if database_stage_busy(db, key)), None)
    # Inspect compatibility without mutating artifacts or making provider calls.
    # Keep the unfinished stage visible, but do not promise a resumable audit
    # that the engine guard will immediately reject.
    resume_blocked_reason = None
    if plan.retryable:
        from app.services.formal_freeze import assert_formal_runtime_frozen, assert_formal_inputs_frozen
        try:
            assert_formal_runtime_frozen(audit)
            assert_audit_runtime_frozen(audit)
            assert_formal_inputs_frozen(db, audit)
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
            resume_blocked_reason = str(exc.detail)
    return {
        "run_id": run_id, "next_stage": plan.next_stage.value if plan.next_stage else None,
        "pending": len(plan.pending_test_ids), "retryable": plan.retryable and resume_blocked_reason is None,
        "resume_blocked_reason": resume_blocked_reason,
        "busy": busy_reason is not None, "busy_reason": busy_reason,
        "status": audit.status,
        "completed_at": audit.completed_at.isoformat() if audit.completed_at else None,
    }

@router.post("/audits/{run_id}/retry", response_model=AuditRun)
def retry_audit(run_id: str, db: Session = Depends(get_db)):
    with audit_suite_lock(db, run_id):
        with audit_run_lock(run_id, db=db):
            return _retry_audit(run_id, db)

def _retry_audit(run_id: str, db: Session):
    """Resume only the incomplete durable stage of an interrupted audit."""
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    from app.services.formal_freeze import assert_formal_runtime_frozen, assert_formal_inputs_frozen
    assert_formal_runtime_frozen(audit)
    assert_audit_runtime_frozen(audit)
    assert_formal_inputs_frozen(db, audit)
    plan = retry_plan(run_id, db)
    if not plan["retryable"]:
        # A provider/database interruption can occur after the final durable
        # evaluation was written but before the public COMPLETED transition.
        # The shared planner has proved every artifact exists, so repair that
        # final state without re-running a model call.
        if audit.status == AuditStatus.FAILED.value and plan["next_stage"] is None:
            audit.status = AuditStatus.COMPLETED.value
            audit.completed_at = datetime.now(timezone.utc)
            reconcile_experiment_terminal_state(db, audit.experiment_id)
            db.commit(); db.refresh(audit)
        return audit_schema(audit)
    if plan["next_stage"] == "generate_tests":
        audit.status = "CREATED"; db.commit(); _generate(run_id, db)
    elif plan["next_stage"] == "execute_tests":
        audit.status = "TESTS_GENERATED"; db.commit(); _execute(run_id, db)
    else:
        audit.status = "TESTS_EXECUTED"; db.commit(); _evaluate(run_id, db)
    db.refresh(audit)
    return audit_schema(audit)
def result_for(run_id,db):
    a=db.get(AuditRunModel,run_id)
    if not a: missing("Audit")
    if a.status != "COMPLETED": raise HTTPException(409,"Results are available after evaluation is complete.")
    from collections import Counter
    ts={t.id: test_schema(t) for t in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==run_id)).all()}
    response_rows=db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id==run_id)).all()
    rs={r.id: response_schema(r) for r in response_rows}
    raw_evaluations=db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id==run_id)).all()
    counts=Counter(row.test_id for row in raw_evaluations)
    es=[eval_schema(row) for row in raw_evaluations if counts[row.test_id]==1 and row.response_id in rs and rs[row.response_id].test_id==row.test_id and rs[row.response_id].run_id==run_id]
    excluded=len(ts)-len(es)
    overall, dimensions=MetricsService().calculate(es,{k:v.dimension for k,v in ts.items()}); failures=[]; uncertain_answers=[]
    source_messages = db.scalars(select(MessageModel).where(MessageModel.conversation_id == a.conversation_id).order_by(MessageModel.sequence, MessageModel.timestamp)).all()
    valid_evaluations_by_response = {evaluation.response_id: evaluation for evaluation in es}

    def evidence_for(memory_ids):
        if not memory_ids:
            return []
        return [memory_schema(db, memory) for memory in db.scalars(
            select(MemoryModel).where(
                MemoryModel.id.in_(memory_ids),
                MemoryModel.conversation_id == a.conversation_id,
            )
        ).all()]

    def sources_for(evidence):
        source_ids = {source for memory in evidence for source in memory.source_message_ids}
        return [SourceStatement(role=message.role, content=message.content, timestamp=message.observation_timestamp)
                for message in source_messages if (message.source_message_id or message.id) in source_ids]

    # Keep a portable per-response record for every saved response attached to
    # a test in this run. Ambiguous or missing assessments remain explicitly
    # unassessed; they are never promoted into the score.
    answers = []
    for response in sorted(rs.values(), key=lambda item: (item.test_id, item.response_id)):
        test = ts.get(response.test_id)
        if test is None or response.run_id != run_id:
            continue
        evaluation = valid_evaluations_by_response.get(response.response_id)
        outcome = (
            "pass" if evaluation is not None and evaluation.passed is True else
            "fail" if evaluation is not None and evaluation.passed is False else
            "uncertain" if evaluation is not None else
            "unassessed"
        )
        # The portable answer record includes the question's reference memories
        # and any memories cited by the evaluator. The evaluator's own citations
        # remain separately identifiable in evaluation.evidence_memory_ids.
        memory_ids = set(test.supporting_memory_ids)
        if evaluation is not None:
            memory_ids.update(evaluation.evidence_memory_ids)
        answer_evidence = evidence_for(memory_ids)
        answers.append(AuditAnswerDetail(
            test=TestCasePublic(**test.model_dump(exclude={"target_memory_context"})),
            response=response,
            outcome=outcome,
            evaluation=evaluation,
            reason=evaluation.reason if evaluation is not None else "No unique valid assessment is linked to this saved response.",
            evidence=answer_evidence,
            source_statements=sources_for(answer_evidence),
        ))

    for e in es:
        if e.passed is not True:
            # Early uncertainty (e.g. truncated output) may precede any judge
            # evidence check. Expose the question's reference memories for
            # review without claiming the evaluator actually checked them.
            review_ids = set(e.evidence_memory_ids)
            if e.passed is None:
                review_ids.update(ts[e.test_id].supporting_memory_ids)
            evidence=evidence_for(review_ids)
            detail = dict(test=TestCasePublic(**ts[e.test_id].model_dump(exclude={"target_memory_context"})),response=rs[e.response_id],evaluation=e,evidence=evidence,source_statements=sources_for(evidence))
            if e.passed is False:
                failures.append(FailureDetail(failure_id=e.evaluation_id, **detail))
            else:
                uncertain_answers.append(AssessmentDetail(**detail))
    fallback_count = sum(1 for evaluation in es if evaluation.evaluator.startswith("fallback-"))
    warnings = [
        f"{fallback_count} evaluation(s) remain uncertain because the configured LLM judge did not return a valid decision; advisory fallback decisions are excluded from scores."
    ] if fallback_count else []
    from app.services.assessment_versions import assessment_version_warnings
    warnings.extend(assessment_version_warnings(es))
    if excluded:
        warnings.append(f"{excluded} of {len(ts)} saved questions have missing or inconsistent assessment evidence and are excluded from scores. Excluded questions are neither passes nor failures.")
    disagreements = sum(e.judge_execution is not None and e.judge_execution.verdict_status == "review_disagreement" for e in es)
    if disagreements:
        warnings.append(f"{disagreements} local semantic judgment(s) disagree with the evidence-rule check; both automated judgments are advisory and these answers remain excluded from scoring until independent review.")
    source_uncertainties = sum(e.judge_execution is not None and e.judge_execution.verdict_status == "review_source_uncertainty" for e in es)
    if source_uncertainties:
        warnings.append(f"{source_uncertainties} local semantic judgment(s) cannot resolve source-check uncertainty; the original explanations are retained and these answers remain excluded from scoring until independent review.")
    return AuditResult(run_id=run_id,overall_score=overall,tests_passed=sum(e.passed is True for e in es),tests_total=sum(e.passed is not None for e in es),dimensions=dimensions,failures=failures,answers=answers,uncertain_count=sum(e.passed is None for e in es),uncertain_answers=uncertain_answers,evaluated_count=len(es),expected_tests=len(ts),excluded_evidence_count=excluded,evaluation_warnings=warnings,retrieval_quality=RetrievalQualityService().calculate((a.reproducibility_metadata or {}).get("shared_answer_source_run_id") or run_id, db),reproducibility=getattr(a, "reproducibility_metadata", {}) or {})
@router.get("/audits/{run_id}/results", response_model=AuditResult)
def results(run_id:str,db:Session=Depends(get_db)): return result_for(run_id,db)


def evaluation_review_items_for(run_id: str, db: Session) -> list[EvaluationReviewItem]:
    """Join verdicts to independent labels and an explicit resolved label."""
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    if audit.status != AuditStatus.COMPLETED.value:
        raise HTTPException(409, "Evaluation review is available after the audit is complete.")
    return evaluation_review_batches_for([run_id], db)[run_id]


def evaluation_review_batches_for(run_ids: list[str], db: Session, integrity: dict | None = None) -> dict[str, list[EvaluationReviewItem]]:
    """Bulk-load completed runs; bind each verdict to its exact response receipt.

    Callers validate completion before entering. Bounded chunks also respect
    SQLite parameter limits while avoiding one query for every answer/run.
    """
    from collections import Counter
    batches: dict[str, list[EvaluationReviewItem]] = {key: [] for key in run_ids}
    if integrity is not None:
        integrity.update({key: {'expected_questions': 0, 'eligible_questions': 0, 'excluded_questions': 0, 'discarded_review_labels': 0, 'reasons': {}} for key in run_ids})
    for offset in range(0, len(run_ids), 200):
        chunk = run_ids[offset:offset + 200]
        tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id.in_(chunk)).order_by(TestCaseModel.id)).all()
        evaluations = db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id.in_(chunk))).all()
        responses = db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id.in_(chunk))).all()
        reviews = db.scalars(select(EvaluationHumanReviewModel).where(EvaluationHumanReviewModel.run_id.in_(chunk))).all()
        # A verdict and its exact reply must be unique and belong to this
        # condition. Never choose a duplicate according to database row order.
        verdict_counts = Counter(row.test_id for row in evaluations)
        evaluation_by_test = {row.test_id: row for row in evaluations}
        response_by_id = {row.id: row for row in responses}
        review_by_evaluation: dict[str, list[EvaluationHumanReviewModel]] = {}
        for review in reviews:
            review_by_evaluation.setdefault(review.evaluation_id, []).append(review)
        for test in tests:
            automated = evaluation_by_test.get(test.id)
            response = response_by_id.get(automated.response_id) if automated else None
            reason = ('multiple_assessments' if verdict_counts[test.id] > 1 else
                      'missing_assessment' if not automated else
                      'missing_answer' if not response else
                      'answer_belongs_elsewhere' if response.test_id != test.id or response.run_id != test.run_id else None)
            if integrity is not None:
                counts = integrity[test.run_id]
                counts['expected_questions'] += 1
                counts['excluded_questions' if reason else 'eligible_questions'] += 1
                if reason:
                    counts['reasons'][reason] = counts['reasons'].get(reason, 0) + 1
            if reason:
                continue
            matching_reviews = [row for row in review_by_evaluation.get(automated.id, []) if row.run_id == test.run_id]
            if integrity is not None:
                integrity[test.run_id]['discarded_review_labels'] += len(review_by_evaluation.get(automated.id, [])) - len(matching_reviews)
            all_reviews = sorted(matching_reviews, key=lambda row: (row.created_at, row.id))
            resolved = None
            for role in (HumanReviewRole.ADJUDICATION.value, HumanReviewRole.REFERENCE.value):
                found = [row for row in all_reviews if getattr(row, "review_role", "reference") == role]
                if found:
                    candidate = max(found, key=lambda row: (row.updated_at, row.id))
                    if role == HumanReviewRole.ADJUDICATION.value:
                        cited_ids = set(candidate.based_on_review_ids or [])
                        cited = [row for row in all_reviews if row.id in cited_ids and row.review_role == HumanReviewRole.INDEPENDENT.value]
                        # Changing an independent judgement invalidates its old
                        # resolution. Preserve all labels, but require explicit
                        # renewed adjudication before using the reference again.
                        independent_ids = {row.id for row in all_reviews if row.review_role == HumanReviewRole.INDEPENDENT.value}
                        if (cited_ids != independent_ids or len(cited) != len(cited_ids) or len(distinct_reviewers(cited)) < 2
                                or any(row.updated_at > candidate.updated_at for row in cited)):
                            break
                    resolved = candidate
                    break
            batches[test.run_id].append(EvaluationReviewItem(
                test=public_test_schema(test), response=response_schema(response),
                automated=eval_schema(automated),
                human_review=human_review_schema(resolved) if resolved else None,
                human_reviews=[human_review_schema(row) for row in all_reviews],
                independent_reviewer_count=len(distinct_reviewers([row for row in all_reviews if row.review_role == HumanReviewRole.INDEPENDENT.value])),
            ))
    return batches


@router.post("/audits/{run_id}/reassessment", response_model=AuditRun, status_code=201)
def create_reassessment(run_id: str, selection: ReassessmentRequest | None = None, db: Session = Depends(get_db)):
    from app.services.reassessment import prepare_reassessment
    with audit_run_lock(run_id, db=db):
        return audit_schema(prepare_reassessment(db, run_id, selection))


def assessor_comparison_payload(row, db):
    from app.services.reassessment import saved_answer_signature, assessment_copy_signature
    from app.services.assessor_observations import assessor_observations
    source = db.get(AuditRunModel, row.source_run_id)
    entries = []
    copies_match = True
    for entry in row.entries:
        run = db.get(AuditRunModel, entry['run_id']) if entry.get('run_id') else None
        if entry.get('run_id'):
            expected = (run.reproducibility_metadata or {}).get('assessment_copy_signature') if run else None
            copies_match = copies_match and bool(expected and assessment_copy_signature(db, run) == expected)
        entries.append({'selection':entry['selection'], 'run':audit_schema(run) if run else None,
                        'observations':assessor_observations(db, run) if run else None,
                        'result':result_for(run.id, db) if run and run.status == 'COMPLETED' else None})
    return {'comparison_id':row.id, 'source':audit_schema(source), 'created_at':row.created_at,
            'inputs_match':bool(copies_match and source and row.input_fingerprint and row.input_fingerprint == saved_answer_signature(db, source)),
            'runtime_matches':row.runtime_signature == audit_runtime_signature(), 'entries':entries}




@router.post('/assessor-comparisons', status_code=201)
def create_assessor_comparison(request: AssessorComparisonRequest, db: Session = Depends(get_db)):
    from app.services.assessor_comparison import create_comparison
    with audit_run_lock('assessor-'+request.creation_request_key, db=db):
        return assessor_comparison_payload(create_comparison(db, request), db)


def generator_comparison_payload(plan, db):
    from app.services.reassessment import saved_answer_signature
    from app.services.generator_usage import generator_usage
    source=db.get(AuditRunModel,plan.source_run_id)
    entries=[]
    for entry in plan.entries:
        run=db.get(AuditRunModel,entry['run_id']) if entry.get('run_id') else None
        tests=db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==run.id)).all() if run else []
        accepted=sum(test.quality_status=='accepted' for test in tests)
        history=(run.reproducibility_metadata or {}).get('generation_observations') or [] if run else []
        first=(history[0].get('attempts') or [None])[0] if history else None
        measured=bool(first and first.get('schema_valid') is True and type(first.get('local_accepted')) is int and type(first.get('candidate_count')) is int)
        count=first.get('candidate_count') if measured else None
        entries.append({'selection':entry['selection'],'run':audit_schema(run) if run else None,
            'usage':generator_usage(run) if run else None,
            'generation':{'operation_count':len(history),'repair_passes':sum(bool(attempt.get('repair_requested')) for operation in history for attempt in operation.get('attempts') or []),
                'latest_status':('saved' if history[-1].get('saved_suite') else 'unfinished' if history[-1].get('status')=='started' else 'failed' if history[-1].get('status')=='failed' else 'not_saved') if history else None,
                'initial_status':first.get('status') if first else None,
                'initial_candidates':count,'initial_local_check_percentage':100*first['local_accepted']/count if measured and count else None,
                'initial_leak_percentage':100*first['leaked_candidates']/count if measured and count and type(first.get('leaked_candidates')) is int else None,
                'initial_suite_contract_valid':first.get('suite_contract_valid') if first else None},
            'quality':{'saved_questions':len(tests),'accepted':accepted,
                'rejected':sum(test.quality_status=='rejected' for test in tests),
                'pending':sum(test.quality_status=='pending' for test in tests),
                'accepted_percentage':100*accepted/len(tests) if tests else None,
                'dimensions':{dimension.value:sum(test.dimension==dimension.value for test in tests if test.quality_status=='accepted') for dimension in Dimension},
                'initial_candidates_measured':measured},
            'result':result_for(run.id,db) if run and run.status=='COMPLETED' else None})
    return {'comparison_id':plan.id,'source':audit_schema(source),'created_at':plan.created_at,
        'runtime_matches':plan.runtime_signature==audit_runtime_signature(),
        'inputs_match':bool(source and saved_answer_signature(db,source)==plan.input_fingerprint),'entries':entries}


@router.post('/generator-comparisons',status_code=201)
def create_generator_comparison(request:GeneratorComparisonRequest,db:Session=Depends(get_db)):
    from app.services.generator_comparison import create_generator_plan
    with audit_run_lock('generator-'+request.creation_request_key,db=db):
        return generator_comparison_payload(create_generator_plan(db,request),db)


@router.get('/generator-comparisons')
def list_generator_comparisons(db:Session=Depends(get_db)):
    plans=db.scalars(select(GeneratorComparisonModel).order_by(GeneratorComparisonModel.created_at.desc())).all()
    return [generator_comparison_payload(plan,db) for plan in plans]


@router.get('/generator-comparisons/{comparison_id}')
def get_generator_comparison(comparison_id:str,db:Session=Depends(get_db)):
    plan=db.get(GeneratorComparisonModel,comparison_id)
    if not plan:missing('Test generator comparison')
    return generator_comparison_payload(plan,db)


@router.post('/generator-comparisons/{comparison_id}/prepare')
def prepare_generator_comparison(comparison_id:str,db:Session=Depends(get_db)):
    from app.services.generator_comparison import prepare_generator_plan
    with audit_run_lock('generator-'+comparison_id,db=db):
        plan=db.get(GeneratorComparisonModel,comparison_id)
        if not plan:missing('Test generator comparison')
        return generator_comparison_payload(prepare_generator_plan(db,plan,build_audit),db)


@router.get('/assessor-comparisons')
def list_assessor_comparisons(db: Session = Depends(get_db)):
    rows = db.scalars(select(AssessorComparisonModel).order_by(AssessorComparisonModel.created_at.desc())).all()
    return [assessor_comparison_payload(row, db) for row in rows]


@router.get('/assessor-comparisons/{comparison_id}')
def get_assessor_comparison(comparison_id: str, db: Session = Depends(get_db)):
    row = db.get(AssessorComparisonModel, comparison_id)
    if not row: missing('Assessor comparison')
    return assessor_comparison_payload(row, db)


@router.post('/assessor-comparisons/{comparison_id}/prepare')
def prepare_assessor_comparison(comparison_id: str, db: Session = Depends(get_db)):
    from app.services.assessor_comparison import prepare_comparison
    with audit_run_lock('assessor-'+comparison_id, db=db):
        row = db.get(AssessorComparisonModel, comparison_id)
        if not row: missing('Assessor comparison')
        return assessor_comparison_payload(prepare_comparison(db, row), db)


@router.get("/audits/{run_id}/source-history", response_model=list[SourceStatement])
def audit_source_history(run_id: str, db: Session = Depends(get_db)):
    """Read original review evidence once, independently of verdicts and receipts."""
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    messages = db.scalars(select(MessageModel).where(
        MessageModel.conversation_id == audit.conversation_id
    ).order_by(MessageModel.sequence, MessageModel.timestamp, MessageModel.id)).all()
    return [SourceStatement(role=message.role, content=message.content, timestamp=message.observation_timestamp)
            for message in messages]


@router.get("/audits/{run_id}/evaluation-review", response_model=list[EvaluationReviewItem])
def evaluation_review_items(run_id: str, db: Session = Depends(get_db)):
    """Return completed answers and verdicts for explicit human calibration."""
    return evaluation_review_items_for(run_id, db)


@router.patch("/audits/{run_id}/evaluations/{evaluation_id}/review", response_model=EvaluationHumanReview)
def review_evaluation(run_id: str, evaluation_id: str, payload: EvaluationHumanReviewUpdate, db: Session = Depends(get_db)):
    with audit_run_lock(run_id, db=db):
        return _review_evaluation(run_id, evaluation_id, payload, db)


def _review_evaluation(run_id: str, evaluation_id: str, payload: EvaluationHumanReviewUpdate, db: Session):
    """Upsert one independent, reference, or adjudication label.

    The default ``reference`` role deliberately keeps the original single
    reviewer endpoint behaviour.  Supplying ``review_role=independent`` lets
    multiple pseudonymous researchers label the same response without
    overwriting each other.
    """
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    if audit.status != AuditStatus.COMPLETED.value:
        raise HTTPException(409, "Evaluation review is available after the audit is complete.")
    evaluation = db.get(EvaluationResultModel, evaluation_id)
    if not evaluation or not db.scalar(select(TestCaseModel.id).where(TestCaseModel.id == evaluation.test_id, TestCaseModel.run_id == run_id)):
        missing("Evaluation")
    response = db.get(TargetResponseModel, evaluation.response_id)
    verdict_count = db.scalar(select(func.count()).select_from(EvaluationResultModel).where(EvaluationResultModel.test_id == evaluation.test_id))
    if (verdict_count != 1 or not response or response.test_id != evaluation.test_id or response.run_id != run_id):
        raise HTTPException(409, 'This assessment cannot be reviewed because its saved answer is missing, belongs to another question or audit, or has conflicting assessments. Existing evidence has been preserved.')
    role = payload.review_role.value
    # Old clients never sent a role and historically upserted the single row
    # even when their displayed pseudonym changed.  Retain that narrow
    # behaviour while requiring role-aware callers to avoid overwriting an
    # explicit reference/adjudication owned by another reviewer.
    legacy_payload = "review_role" not in payload.model_fields_set
    if payload.based_on_review_ids:
        cited = db.scalars(select(EvaluationHumanReviewModel).where(
            EvaluationHumanReviewModel.evaluation_id == evaluation_id,
            EvaluationHumanReviewModel.id.in_(payload.based_on_review_ids),
        )).all()
        if len(cited) != len(set(payload.based_on_review_ids)) or any(
            row.review_role != HumanReviewRole.INDEPENDENT.value for row in cited
        ):
            raise HTTPException(422, "An adjudication may cite only independent reviews for this evaluation.")
        if len(distinct_reviewers(cited)) < 2:
            raise HTTPException(422, "Adjudication requires two independently named reviewers for this evaluation.")
        if role == HumanReviewRole.ADJUDICATION.value:
            independent_ids = set(db.scalars(select(EvaluationHumanReviewModel.id).where(
                EvaluationHumanReviewModel.evaluation_id == evaluation_id,
                EvaluationHumanReviewModel.review_role == HumanReviewRole.INDEPENDENT.value,
            )).all())
            if set(payload.based_on_review_ids) != independent_ids:
                raise HTTPException(409, "The independent review set changed or is incomplete. Refresh the review evidence and consider every independent label before submitting your final decision.")
        def utc_review_version(value: datetime) -> datetime:
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        if role == HumanReviewRole.ADJUDICATION.value and any(
            utc_review_version(row.updated_at) != utc_review_version(payload.based_on_review_versions[row.id])
            for row in cited
        ):
            raise HTTPException(409, "An independent review changed while this page was open. Refresh the review evidence, check the updated labels, then submit your final decision again.")
    if role == HumanReviewRole.INDEPENDENT.value:
        existing = db.scalars(select(EvaluationHumanReviewModel).where(
            EvaluationHumanReviewModel.evaluation_id == evaluation_id,
            EvaluationHumanReviewModel.review_role == role,
        )).all()
        matching = [row for row in existing if reviewer_identity(row.reviewer_label) == reviewer_identity(payload.reviewer_label)]
        if len(matching) > 1:
            raise HTTPException(409, "This reviewer pseudonym matches multiple legacy reviews. Reconcile the duplicate records before editing this label.")
        review = matching[0] if matching else None
    else:
        review = db.scalar(select(EvaluationHumanReviewModel).where(
            EvaluationHumanReviewModel.evaluation_id == evaluation_id,
            EvaluationHumanReviewModel.review_role == role,
        ))
        if review is not None and reviewer_identity(review.reviewer_label) != reviewer_identity(payload.reviewer_label) and not legacy_payload:
            raise HTTPException(409, f"This evaluation already has a {role} label. Update it using its existing reviewer pseudonym.")
    if review is None:
        review = EvaluationHumanReviewModel(
            id=ident("HR"), run_id=run_id, evaluation_id=evaluation_id,
            human_passed=payload.human_passed, human_failure_type=payload.human_failure_type.value if payload.human_failure_type else None,
            reviewer_label=payload.reviewer_label.strip(), review_role=role,
            based_on_review_ids=list(payload.based_on_review_ids), note=payload.note.strip() if payload.note else None,
        )
        db.add(review)
    else:
        review.human_passed = payload.human_passed
        review.human_failure_type = payload.human_failure_type.value if payload.human_failure_type else None
        if legacy_payload:
            review.reviewer_label = payload.reviewer_label.strip()
        review.based_on_review_ids = list(payload.based_on_review_ids)
        review.note = payload.note.strip() if payload.note else None
        # An explicit re-adjudication may reaffirm unchanged values after a
        # cited label changed. It must still record a new resolution time.
        review.updated_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(review)
    return human_review_schema(review)


@router.get("/audits/{run_id}/evaluation-calibration", response_model=EvaluationCalibrationSummary)
def evaluation_calibration(run_id: str, db: Session = Depends(get_db)):
    """Calibrate automated labels against explicit resolution labels only.

    Independent labels measure inter-rater reliability.  They are *not*
    silently majority-voted into the automated-evaluator calibration set.
    """
    items = evaluation_review_items_for(run_id, db)
    reviewed = [item for item in items if item.human_review and item.automated.passed is not None]
    automated_failures = sum(item.automated.passed is False for item in items)
    agreements = sum(item.automated.passed == item.human_review.human_passed for item in reviewed if item.human_review)
    true_positive = sum((not item.automated.passed) and (not item.human_review.human_passed) for item in reviewed if item.human_review)
    false_positive = sum((not item.automated.passed) and item.human_review.human_passed for item in reviewed if item.human_review)
    false_negative = sum(item.automated.passed and (not item.human_review.human_passed) for item in reviewed if item.human_review)
    precision = round(true_positive / (true_positive + false_positive) * 100, 1) if true_positive + false_positive else None
    recall = round(true_positive / (true_positive + false_negative) * 100, 1) if true_positive + false_negative else None
    f1_denominator = 2 * true_positive + false_positive + false_negative
    f1 = round(2 * true_positive / f1_denominator * 100, 1) if f1_denominator else None
    by_dimension: dict[str, dict[str, int]] = {}
    for item in reviewed:
        bucket = by_dimension.setdefault(item.test.dimension.value, {"reviewed": 0, "agreement": 0, "automated_failures": 0, "human_failures": 0})
        bucket["reviewed"] += 1
        bucket["agreement"] += int(item.automated.passed == item.human_review.human_passed)
        bucket["automated_failures"] += int(not item.automated.passed)
        bucket["human_failures"] += int(not item.human_review.human_passed)

    independent_groups: dict[str, list[EvaluationHumanReview]] = {}
    for item in items:
        labels = unique_independent_reviews(item.human_reviews)
        if labels:
            independent_groups[item.automated.evaluation_id] = labels
    independently_reviewed = [labels for labels in independent_groups.values() if len(labels) >= 2]
    consensus_count = sum(len({label.human_passed for label in labels}) == 1 for labels in independently_reviewed)
    conflict_count = len(independently_reviewed) - consensus_count
    failure_groups = [labels for labels in independently_reviewed if all(label.human_passed is False for label in labels)]
    typed_groups = [labels for labels in failure_groups if all(label.human_failure_type is not None for label in labels)]
    category_agreement = sum(len({label.human_failure_type for label in labels}) == 1 for labels in typed_groups)
    pairs: list[tuple[bool, bool]] = []
    for labels in independently_reviewed:
        ordered = sorted(labels, key=lambda label: (label.reviewer_label, label.review_id))
        for left_index, left in enumerate(ordered):
            for right in ordered[left_index + 1:]:
                pairs.append((left.human_passed, right.human_passed))
    pair_agreement = sum(left == right for left, right in pairs)
    pair_percentage = round(pair_agreement / len(pairs) * 100, 1) if pairs else None
    if pairs:
        left_pass_rate = sum(left for left, _ in pairs) / len(pairs)
        right_pass_rate = sum(right for _, right in pairs) / len(pairs)
        expected_agreement = left_pass_rate * right_pass_rate + (1 - left_pass_rate) * (1 - right_pass_rate)
        observed_agreement = pair_agreement / len(pairs)
        pair_kappa = round((observed_agreement - expected_agreement) / (1 - expected_agreement), 3) if expected_agreement < 1 else None
    else:
        pair_kappa = None
    return EvaluationCalibrationSummary(
        run_id=run_id, automated_failure_count=automated_failures, human_reviewed_count=len(reviewed),
        agreement_count=agreements, disagreement_count=len(reviewed) - agreements,
        agreement_percentage=round(agreements / len(reviewed) * 100, 1) if reviewed else None,
        failure_precision=precision, failure_recall=recall, failure_f1=f1, by_dimension=by_dimension,
        independent_review_count=sum(len(labels) for labels in independent_groups.values()),
        independently_reviewed_evaluation_count=len(independently_reviewed),
        independent_consensus_count=consensus_count, independent_conflict_count=conflict_count,
        independent_failure_category_compared_count=len(typed_groups),
        independent_failure_category_agreement_count=category_agreement,
        independent_failure_category_conflict_count=len(typed_groups)-category_agreement,
        independent_failure_category_missing_count=len(failure_groups)-len(typed_groups),
        independent_pair_count=len(pairs), independent_pair_agreement_percentage=pair_percentage,
        independent_pair_kappa=pair_kappa,
    )

def target_trace_record_schema(db: Session, record: TargetAgentMemoryModel) -> TargetMemoryTraceRecord:
    relationships = db.scalars(select(TargetAgentMemoryRelationshipModel).where(
        TargetAgentMemoryRelationshipModel.memory_id == record.id
    )).all()
    return TargetMemoryTraceRecord(
        memory_id=record.id, canonical_value=record.canonical_value,
        scope=record.scope,
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
        "selected_memory_ids", "writer_version", "scope", "maintenance_policy",
        "retrieval_mode", "retrieval_agent_version", "retrieval_provider", "retrieval_model",
        "candidate_count", "candidate_count_sent", "candidate_input_limit",
        "hierarchy_rounds", "model_calls",
        "request_attempts", "elapsed_ms", "reported_input_tokens", "reported_output_tokens",
        "maintenance_action", "target_memory_capacity", "max_active_records",
        "retained_record_count", "protected_conflicted_memory_ids",
        "evicted_memory_id", "duplicate_of_memory_id", "content_signature", "exclusion",
    }
    details = {key: value for key, value in (event.details or {}).items() if key in allowed}
    return TargetMemoryTraceEvent(
        event_id=event.id, event_type=event.event_type, memory_id=event.memory_id,
        source_message_ids=list(event.source_message_ids), details=details,
        created_at=event.created_at,
    )

def target_retrieval_trace_schema(db: Session, item: TargetAgentRetrievalModel) -> TargetMemoryTraceRetrieval:
    test = db.get(TestCaseModel, item.test_id)
    response = db.get(TargetResponseModel, item.final_response_id) if item.final_response_id else None
    receipt = ExecutionMetadata.model_validate(response.execution_metadata or {}).memory_input if response else None
    return TargetMemoryTraceRetrieval(
        question=getattr(test, "prompt", None),
        retrieval_id=item.id, test_id=item.test_id, strategy=item.strategy,
        selected_memory_ids=list(item.selected_memory_ids), ranking_evidence=list(item.ranking_evidence),
        final_response_id=item.final_response_id, memory_input=receipt, created_at=item.created_at,
    )


def target_memory_trace_payload(audit: AuditRunModel, db: Session) -> TargetMemoryTrace:
    """Build terminal target-memory evidence without evaluator-only material."""
    run_id = audit.id
    evidence_run_id = (audit.reproducibility_metadata or {}).get("shared_answer_source_run_id") or run_id
    records = db.scalars(select(TargetAgentMemoryModel).where(
        TargetAgentMemoryModel.run_id == evidence_run_id
    ).order_by(TargetAgentMemoryModel.write_order)).all()
    events = db.scalars(select(TargetAgentMemoryEventModel).where(
        TargetAgentMemoryEventModel.run_id == evidence_run_id
    ).order_by(TargetAgentMemoryEventModel.created_at, TargetAgentMemoryEventModel.id)).all()
    retrievals = db.scalars(select(TargetAgentRetrievalModel).where(
        TargetAgentRetrievalModel.run_id == evidence_run_id
    ).order_by(TargetAgentRetrievalModel.created_at, TargetAgentRetrievalModel.id)).all()
    return TargetMemoryTrace(
        run_id=run_id, memory_strategy=audit.memory_strategy,
        retrieval_mode=getattr(audit, "retrieval_mode", None) or (audit.reproducibility_metadata or {}).get("retrieval_mode") or "fixed",
        retrieval_provider=getattr(audit, "retrieval_provider", None) or (audit.reproducibility_metadata or {}).get("retrieval_provider"),
        retrieval_model=getattr(audit, "retrieval_model", None) or (audit.reproducibility_metadata or {}).get("retrieval_model"),
        shared_answer_source_run_id=(audit.reproducibility_metadata or {}).get("shared_answer_source_run_id"),
        target_system_adapter=getattr(audit, "target_system_adapter", None) or "controlled-memory",
        target_system_adapter_version=(getattr(audit, "target_system_adapter_version", None)
                                       or (audit.reproducibility_metadata or {}).get("target_system_adapter_version")),
        memory_maintenance_policy=audit.memory_maintenance_policy,
        target_memory_capacity=getattr(audit, "target_memory_capacity", 50),
        target_memory_writer=getattr(audit, "target_memory_writer", None) or "rule_based",
        target_memory_writer_version=(getattr(audit, "target_memory_writer_version", None)
                                      or (audit.reproducibility_metadata or {}).get("target_memory_writer_version")),
        records=[target_trace_record_schema(db, record) for record in records],
        events=[safe_trace_event_schema(event) for event in events],
        retrievals=[target_retrieval_trace_schema(db, item) for item in retrievals],
    )


@router.get("/audits/{run_id}/target-memory-trace", response_model=TargetMemoryTrace)
def target_memory_trace(run_id: str, db: Session = Depends(get_db)):
    """Show the controlled agent's independent store after a terminal audit.

    This is intentionally distinct from ground truth and omits evaluator-only
    expected behaviour and target runtime context. It is unavailable while a
    target can still use the test suite, avoiding premature leakage.
    """
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    if audit.status not in {AuditStatus.COMPLETED.value, AuditStatus.CANCELLED.value}:
        raise HTTPException(409, "Target memory evidence is available after an audit is complete or cancelled.")
    return target_memory_trace_payload(audit, db)


@router.get("/audits/{run_id}/cancelled-evidence", response_model=CancelledAuditEvidence)
def cancelled_audit_evidence(run_id: str, db: Session = Depends(get_db)):
    """Expose retained responses and safe retrieval trace for a cancelled run."""
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    if audit.status != AuditStatus.CANCELLED.value:
        raise HTTPException(409, "Cancelled-run evidence is available only after cancellation.")
    responses = db.scalars(select(TargetResponseModel).where(
        TargetResponseModel.run_id == run_id
    ).order_by(TargetResponseModel.created_at, TargetResponseModel.id)).all()
    return CancelledAuditEvidence(
        audit=audit_schema(audit), completed_responses=[response_schema(item) for item in responses],
        trace=target_memory_trace_payload(audit, db),
    )

@router.get("/audit-comparisons")
def audit_comparison(before: str, after: str, db: Session = Depends(get_db)):
    if before == after:
        raise HTTPException(422, "Choose two different audits.")
    audits = [db.get(AuditRunModel, run_id) for run_id in (before, after)]
    if any(audit is None for audit in audits):
        missing("Audit")
    if any(audit.status != AuditStatus.COMPLETED.value for audit in audits):
        raise HTTPException(409, "Both audits must be complete before comparison.")
    return {
        "before": {"run": audit_schema(audits[0]), "result": result_for(before, db)},
        "after": {"run": audit_schema(audits[1]), "result": result_for(after, db)},
        **compare_audit_evidence(db, audits[0], audits[1]),
    }


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
    answers_by_run = {
        run.run_id: experiment_answer_reports_for(run.run_id, db)
        for run in runs if run.status == AuditStatus.COMPLETED
    }
    response_metadata_by_run = {
        run.id: [dict(response.execution_metadata or {}) for response in db.scalars(
            select(TargetResponseModel).where(TargetResponseModel.run_id == run.id)
        ).all()]
        for run in run_models
    }
    service = ExperimentAnalyticsService()
    return ExperimentAnalytics(
        experiment=experiment_schema(experiment, [run.reproducibility_metadata or {} for run in run_models]),
        runs=[ExperimentRunReport(run=run, result=results_by_run.get(run.run_id),
                                  answers=answers_by_run.get(run.run_id, [])) for run in runs],
        conditions=service.condition_summaries(runs, results_by_run, response_metadata_by_run),
        paired_comparisons=service.paired_comparisons(db, runs),
    )


def experiment_answer_reports_for(run_id: str, db: Session) -> list[ExperimentAnswerReport]:
    """Expose every unique saved test/response pair and its assessment if available."""
    audit = db.get(AuditRunModel, run_id)
    if not audit or audit.status != AuditStatus.COMPLETED.value:
        return []
    tests = db.scalars(select(TestCaseModel).where(
        TestCaseModel.run_id == run_id,
    ).order_by(TestCaseModel.id)).all()
    responses = db.scalars(select(TargetResponseModel).where(
        TargetResponseModel.run_id == run_id,
        TargetResponseModel.test_id.in_([test.id for test in tests]),
    ).order_by(TargetResponseModel.test_id, TargetResponseModel.id)).all() if tests else []
    evaluations = db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(
        TestCaseModel.run_id == run_id,
    ).order_by(EvaluationResultModel.test_id, EvaluationResultModel.id)).all()
    responses_by_test: dict[str, list[TargetResponseModel]] = {}
    for response in responses:
        responses_by_test.setdefault(response.test_id, []).append(response)
    evaluations_by_test: dict[str, list[EvaluationResultModel]] = {}
    for evaluation in evaluations:
        evaluations_by_test.setdefault(evaluation.test_id, []).append(evaluation)
    # The shared review join verifies that evaluated pairs point to a response
    # from this exact run/test. It deliberately drops duplicate or cross-run
    # assessment bindings; we never repair one by selecting a database row.
    reviewed_items = {
        item.test.test_id: item for item in evaluation_review_batches_for([run_id], db)[run_id]
    }
    memory_ids = {memory_id for test in tests for memory_id in (test.supporting_memory_ids or [])}
    memory_ids.update(memory_id for item in reviewed_items.values()
                      for memory_id in item.automated.evidence_memory_ids)
    memories = db.scalars(select(MemoryModel).where(
        MemoryModel.conversation_id == audit.conversation_id,
        MemoryModel.id.in_(memory_ids),
    ).order_by(MemoryModel.id)).all() if memory_ids else []
    memories_by_id = {memory.id: memory for memory in memories}
    source_ids = {source_id for memory in memories for source_id in (memory.source_message_ids or [])}
    source_messages = db.scalars(select(MessageModel).where(
        MessageModel.conversation_id == audit.conversation_id,
        MessageModel.source_message_id.in_(source_ids),
    ).order_by(MessageModel.sequence, MessageModel.id)).all() if source_ids else []
    statements_by_id = {
        message.source_message_id: SourceStatement(
            role=message.role, content=message.content, timestamp=message.observation_timestamp,
        ) for message in source_messages
    }
    answer_rows = []
    for test in tests:
        response_candidates = responses_by_test.get(test.id, [])
        assessment_candidates = evaluations_by_test.get(test.id, [])
        # Include only unique test/response pairs. A duplicate response or
        # assessment makes the answer ambiguous; cross-run bindings are also
        # omitted even if a row happens to share one of the identifiers.
        if len(response_candidates) != 1:
            continue
        response = response_candidates[0]
        if response.run_id != run_id or response.test_id != test.id:
            continue
        item = reviewed_items.get(test.id)
        if item is not None:
            if item.response.response_id != response.id or len(assessment_candidates) != 1:
                continue
            evaluation = item.automated
        else:
            if assessment_candidates:
                continue
            evaluation = None
        supporting_ids = list(test.supporting_memory_ids or [])
        evidence_ids = set(supporting_ids) | set(evaluation.evidence_memory_ids if evaluation else [])
        evidence = [memories_by_id[memory_id] for memory_id in sorted(evidence_ids)
                    if memory_id in memories_by_id]
        linked_source_ids = sorted({source_id for memory in evidence
                                    for source_id in (memory.source_message_ids or [])})
        answer_rows.append(ExperimentAnswerReport(
            run_id=run_id,
            test_id=test.id,
            response_id=response.id,
            evaluation_id=evaluation.evaluation_id if evaluation else None,
            dimension=test.dimension,
            prompt=test.prompt,
            expected_behavior=test.expected_behavior,
            answer=response.response_text,
            outcome=("unassessed" if evaluation is None else
                     "pass" if evaluation.passed is True else
                     "fail" if evaluation.passed is False else "uncertain"),
            observed_category=evaluation.failure_type if evaluation else None,
            failure_classification=evaluation.failure_classification if evaluation else None,
            evaluation_reason=evaluation.reason if evaluation else None,
            supporting_memory_ids=supporting_ids,
            source_evidence=[ExperimentAnswerSourceEvidence(
                memory_id=memory.id, canonical_value=memory.canonical_value,
                source_message_ids=list(memory.source_message_ids or []),
            ) for memory in evidence],
            source_statements=[statements_by_id[source_id] for source_id in linked_source_ids
                               if source_id in statements_by_id],
        ))
    return answer_rows

@router.get("/experiments/{experiment_id}/results", response_model=ExperimentAnalytics)
def experiment_results(experiment_id: str, db: Session = Depends(get_db)):
    """Fair-comparison history with per-condition reports and paired outcomes."""
    return experiment_analytics_for(experiment_id, db)


@router.get("/experiments/{experiment_id}/reproducibility-bundle.json")
def export_experiment_reproducibility_bundle(experiment_id: str, db: Session = Depends(get_db)):
    """Export the frozen suite, safe configurations and completed outcomes.

    It purposefully excludes the authorised conversation, provider credentials,
    raw provider payloads and target-agent private-memory context.  Those can
    be exported through the explicit conversation-data control when authorised.
    """
    analytics = experiment_analytics_for(experiment_id, db)
    experiment = db.get(ExperimentModel, experiment_id)
    source_run_id = experiment.test_suite_source_run_id if experiment else None
    suite = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == source_run_id).order_by(TestCaseModel.id)).all() if source_run_id else []
    bundle = {
        "schema_version": "experiment-reproducibility-bundle-v1",
        "exported_at": datetime.now(timezone.utc),
        "notice": "Safe experiment bundle. Source conversation, secrets, raw provider payloads and private target-memory context are excluded.",
        "experiment": analytics.experiment.model_dump(mode="json"),
        "frozen_test_suite": [public_test_schema(test).model_dump(mode="json") for test in suite],
        "runs": [
            {
                "configuration": report.run.model_dump(mode="json"),
                "result": report.result.model_dump(mode="json") if report.result else None,
                "answers": [answer.model_dump(mode="json") for answer in report.answers],
            }
            for report in analytics.runs
        ],
        "analysis_metadata": ExperimentAnalyticsService.analysis_metadata(),
        "condition_summaries": [condition.model_dump(mode="json") for condition in analytics.conditions],
        "paired_comparisons": [pair.model_dump(mode="json") for pair in analytics.paired_comparisons],
    }
    filename = f"experiment-{experiment_id}-reproducibility-bundle.json"
    return StreamingResponse(iter([json.dumps(bundle, default=str, indent=2)]), media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _canonical_json(value: object) -> bytes:
    """Stable JSON bytes so the frozen artefact records exact input hashes."""
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _safe_artifact_trace(run_id: str, db: Session) -> dict:
    """Trace data already exposed after completion, without source conversation text."""
    audit = db.get(AuditRunModel, run_id)
    evidence_run_id = (audit.reproducibility_metadata or {}).get("shared_answer_source_run_id") or run_id
    records = db.scalars(select(TargetAgentMemoryModel).where(
        TargetAgentMemoryModel.run_id == evidence_run_id
    ).order_by(TargetAgentMemoryModel.write_order)).all()
    events = db.scalars(select(TargetAgentMemoryEventModel).where(
        TargetAgentMemoryEventModel.run_id == evidence_run_id
    ).order_by(TargetAgentMemoryEventModel.created_at, TargetAgentMemoryEventModel.id)).all()
    retrievals = db.scalars(select(TargetAgentRetrievalModel).where(
        TargetAgentRetrievalModel.run_id == evidence_run_id
    ).order_by(TargetAgentRetrievalModel.created_at, TargetAgentRetrievalModel.id)).all()
    return {
        "shared_answer_source_run_id": evidence_run_id if evidence_run_id != run_id else None,
        "records": [target_trace_record_schema(db, record).model_dump(mode="json") for record in records],
        "events": [safe_trace_event_schema(event).model_dump(mode="json") for event in events],
        "retrievals": [target_retrieval_trace_schema(db, item).model_dump(mode="json") for item in retrievals],
    }


@router.get("/experiments/{experiment_id}/artifact.zip")
def export_experiment_artifact(experiment_id: str, db: Session = Depends(get_db)):
    """Download the immutable experiment inputs, outputs, and retrieval evidence.

    The archive is derived exclusively from the frozen test suite and completed
    run records.  It excludes the raw authorised transcript, secrets and raw
    provider payloads.  Its manifest hashes every contained research file.
    """
    analytics = experiment_analytics_for(experiment_id, db)
    experiment = db.get(ExperimentModel, experiment_id)
    if experiment is None:  # Kept for type checkers; analytics already checks.
        missing("Experiment")
    source_run_id = experiment.test_suite_source_run_id
    suite = db.scalars(select(TestCaseModel).where(
        TestCaseModel.run_id == source_run_id
    ).order_by(TestCaseModel.id)).all() if source_run_id else []
    files: dict[str, object] = {
        "frozen-test-suite.json": [public_test_schema(test).model_dump(mode="json") for test in suite],
        "experiment.json": analytics.experiment.model_dump(mode="json"),
        "condition-summaries.json": [item.model_dump(mode="json") for item in analytics.conditions],
        "paired-comparisons.json": [item.model_dump(mode="json") for item in analytics.paired_comparisons],
        "analysis-metadata.json": ExperimentAnalyticsService.analysis_metadata(),
    }
    for report in analytics.runs:
        run_id = report.run.run_id
        prefix = f"runs/{run_id}"
        files[f"{prefix}/configuration.json"] = report.run.model_dump(mode="json")
        if report.result is not None:
            files[f"{prefix}/result.json"] = report.result.model_dump(mode="json")
            responses = db.scalars(select(TargetResponseModel).where(
                TargetResponseModel.run_id == run_id
            ).order_by(TargetResponseModel.test_id)).all()
            evaluations = db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(
                TestCaseModel.run_id == run_id
            ).order_by(EvaluationResultModel.test_id)).all()
            files[f"{prefix}/responses.json"] = [response_schema(row).model_dump(mode="json") for row in responses]
            files[f"{prefix}/evaluations.json"] = [eval_schema(row).model_dump(mode="json") for row in evaluations]
            files[f"{prefix}/retrieval-trace.json"] = _safe_artifact_trace(run_id, db)
    encoded_files = {name: _canonical_json(content) for name, content in files.items()}
    suite_bytes = encoded_files["frozen-test-suite.json"]
    manifest = {
        "schema_version": "memory-health-experiment-artifact-v2",
        "experiment_id": experiment_id,
        "notice": "Frozen audit artifact. It excludes raw authorised conversation text, credentials and raw provider payloads.",
        "code_revision": os.getenv("AUDITOR_CODE_REVISION", "unknown"),
        "frozen_test_suite_sha256": hashlib.sha256(suite_bytes).hexdigest(),
        "configuration_fingerprints": {
            report.run.run_id: report.run.reproducibility.configuration_fingerprint
            for report in analytics.runs if report.run.reproducibility
        },
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in encoded_files.items()},
    }
    # Fixed timestamps make a frozen artifact byte-stable when the stored
    # experiment is unchanged.  Manifest is last because it describes data,
    # not its own mutable archive container.
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(encoded_files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, encoded_files[name])
        info = zipfile.ZipInfo("manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, _canonical_json(manifest))
    output.seek(0)
    filename = f"experiment-{experiment_id}-artifact.zip"
    return StreamingResponse(output, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@router.get("/experiments/{experiment_id}/export.csv")
def export_experiment_csv(experiment_id: str, db: Session = Depends(get_db)):
    """Download a portable group-level report without exposing private memory traces."""
    analytics = experiment_analytics_for(experiment_id, db)
    content = StringIO()
    from app.services.csv_export import VERSION as csv_encoding_version, spreadsheet_csv_value
    writer = csv.writer(content, quoting=csv.QUOTE_ALL)
    answer_columns = ["test_id", "response_id", "evaluation_id", "prompt", "expected_behavior", "answer",
                      "outcome", "observed_category", "failure_classification", "evaluation_reason",
                      "supporting_memory_ids", "source_evidence", "source_statements"]
    writer.writerow(["record_type", "experiment_id", "condition", "run_id", "dimension", "metric", "value", "detail", "condition_id", *answer_columns])
    def write_record(fields, condition_id="", answer=None):
        answer_values = []
        if answer is not None:
            answer_values = [
                answer.test_id, answer.response_id, answer.evaluation_id, answer.prompt, answer.expected_behavior,
                answer.answer, answer.outcome, answer.observed_category.value if answer.observed_category else "",
                json.dumps(answer.failure_classification.model_dump(mode="json"), sort_keys=True)
                    if answer.failure_classification else "",
                answer.evaluation_reason, json.dumps(answer.supporting_memory_ids),
                json.dumps([item.model_dump(mode="json") for item in answer.source_evidence], sort_keys=True),
                json.dumps([item.model_dump(mode="json") for item in answer.source_statements], sort_keys=True),
            ]
        writer.writerow([spreadsheet_csv_value(value) for value in [*fields, condition_id, *answer_values,
                        *("" for _ in range(len(answer_columns) - len(answer_values))) ]])
    condition_by_run = {run_id: item.condition_id for item in analytics.conditions for run_id in item.run_ids}
    write_record(["analysis_metadata", experiment_id, "", "", "", "analysis_version", ExperimentAnalyticsService.VERSION,
                  json.dumps(ExperimentAnalyticsService.analysis_metadata(), sort_keys=True)])
    write_record(["serialization_metadata", experiment_id, "", "", "", "csv_text_encoding", csv_encoding_version,
                  "Formula-like text has a leading tab in this spreadsheet CSV. JSON evidence preserves original text."])
    for condition in analytics.conditions:
        write_record(["condition", experiment_id, condition.label, "", "", "planned_runs", condition.planned_runs, ""], condition.condition_id)
        write_record(["condition", experiment_id, condition.label, "", "", "completed_runs", condition.completed_runs, ""], condition.condition_id)
        write_record(["condition", experiment_id, condition.label, "", "", "failed_runs", condition.failed_runs, ""], condition.condition_id)
        write_record(["condition", experiment_id, condition.label, "", "", "overall_mean", condition.overall_mean, ""], condition.condition_id)
        write_record(["condition", experiment_id, condition.label, "", "", "overall_standard_deviation", condition.overall_standard_deviation, ""], condition.condition_id)
        write_record(["condition", experiment_id, condition.label, "", "", "mean_latency_ms", condition.mean_latency_ms, "Known response timings only; local deterministic calls may not report tokens."], condition.condition_id)
        write_record(["condition", experiment_id, condition.label, "", "", "total_input_tokens", condition.total_input_tokens, ""], condition.condition_id)
        write_record(["condition", experiment_id, condition.label, "", "", "total_output_tokens", condition.total_output_tokens, ""], condition.condition_id)
        write_record(["condition", experiment_id, condition.label, "", "", "total_tokens", condition.total_tokens, ""], condition.condition_id)
        for score in condition.dimensions:
            write_record(["dimension", experiment_id, condition.label, "", score.dimension.value, "mean_percentage", score.mean_percentage, f"{score.passed}/{score.total} over {score.measured_runs} run(s)"], condition.condition_id)
            state = ("partial" if score.uncertain_count or score.excluded_evidence_count else "measured") if score.mean_percentage is not None else (
                "evidence_unavailable" if score.excluded_evidence_count else "awaiting_review" if score.uncertain_count else "not_tested")
            for metric, value in (("answers_passed", score.passed), ("answers_decided", score.total),
                                  ("pending_judgments", score.uncertain_count), ("excluded_evidence", score.excluded_evidence_count),
                                  ("expected_questions", score.expected_tests), ("score_state", state)):
                write_record(["dimension", experiment_id, condition.label, "", score.dimension.value, metric, value,
                              "Unknown expected count is blank; excluded evidence and pending judgments are neither passes nor failures."], condition.condition_id)
        pending = sum((report.result.uncertain_count or 0) for report in analytics.runs
                      if report.run.run_id in condition.run_ids and report.result is not None)
        write_record(["condition", experiment_id, condition.label, "", "", "answers_passed", condition.tests_passed, "Among completed assessed runs."], condition.condition_id)
        write_record(["condition", experiment_id, condition.label, "", "", "answers_decided", condition.tests_total, "Excludes pending judgments."], condition.condition_id)
        write_record(["condition", experiment_id, condition.label, "", "", "pending_judgments", pending, "Among completed runs with available assessments; unfinished runs are reported separately."], condition.condition_id)
    for report in analytics.runs:
        run, result = report.run, report.result
        condition_id = condition_by_run.get(run.run_id, "")
        write_record(["run", experiment_id, "", run.run_id, "", "status", run.status.value, ""], condition_id)
        if result:
            write_record(["run", experiment_id, "", run.run_id, "", "overall_score", result.overall_score, f"{result.tests_passed}/{result.tests_total} tests passed"], condition_id)
            write_record(["run", experiment_id, "", run.run_id, "", "answers_passed", result.tests_passed, ""], condition_id)
            write_record(["run", experiment_id, "", run.run_id, "", "answers_decided", result.tests_total, "Excludes pending judgments."], condition_id)
            write_record(["run", experiment_id, "", run.run_id, "", "pending_judgments", result.uncertain_count or 0, "Not a pass or failure."], condition_id)
            for failed in result.failures:
                write_record(["failure", experiment_id, "", run.run_id, failed.test.dimension.value, "detected_failure", "FAIL", failed.evaluation.reason], condition_id)
        for answer in report.answers:
            write_record(["answer", experiment_id, "", run.run_id, answer.dimension.value, "observed_outcome",
                          answer.outcome.upper(), "One uniquely paired saved test, response and evaluation."],
                         condition_id, answer)
    for pair in analytics.paired_comparisons:
        detail = f"reference={pair.reference_run_id}; both_passed={pair.both_passed}; both_failed={pair.both_failed}; reference_only={pair.reference_only_passed}; candidate_only={pair.candidate_only_passed}; bootstrap_95_ci=[{pair.candidate_delta_confidence_interval_low}, {pair.candidate_delta_confidence_interval_high}]; exact_sign_p={pair.two_sided_sign_test_p_value}"
        write_record(["paired_comparison", experiment_id, pair.candidate_label, pair.candidate_run_id, "", "delta_percentage_points", pair.candidate_delta_percentage_points, detail], condition_by_run.get(pair.candidate_run_id, ""))
        for metric, value in (("shared_questions", pair.shared_question_count), ("comparable_decided_questions", pair.shared_tests),
                              ("pending_comparisons", pair.excluded_uncertain_count), ("excluded_assessments", pair.excluded_assessment_count)):
            write_record(["paired_comparison", experiment_id, pair.candidate_label, pair.candidate_run_id, "", metric, value,
                          "reference=" + pair.reference_run_id + "; pending and excluded pairs do not contribute to the delta."], condition_by_run.get(pair.candidate_run_id, ""))
    filename = f"experiment-{experiment_id}-results.csv"
    return StreamingResponse(iter([content.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@router.get("/experiments/summary", response_model=list[ExperimentResult])
def experiments(db: Session = Depends(get_db)):
    """Return legacy weak/strong summaries per comparison group.

    This endpoint predates the richer experiment analytics route.  Keep it
    backwards compatible, but never average unrelated conversations or
    experiments into one misleading global score.
    """
    runs = db.scalars(select(AuditRunModel).where(AuditRunModel.status == "COMPLETED")).all()
    grouped: dict[str, dict[str, list[float]]] = {}
    labels: dict[str, str] = {}
    for run in runs:
        key = run.experiment_id or f"standalone:{run.conversation_id}"
        grouped.setdefault(key, {"weak": [], "strong": []})
        if key not in labels:
            experiment = db.get(ExperimentModel, run.experiment_id) if run.experiment_id else None
            labels[key] = experiment.label if experiment else "Standalone controlled-run comparison"
        tests = {t.id: Dimension(t.dimension) for t in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run.id)).all()}
        evaluations = [eval_schema(e) for e in db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id == run.id)).all()]
        score, _ = MetricsService().calculate(evaluations, tests)
        if score is not None and run.target_configuration in {"weak", "strong"}:
            grouped[key][run.target_configuration].append(score)
    summaries: list[ExperimentResult] = []
    for key, scores in grouped.items():
        if not scores["weak"] or not scores["strong"]:
            continue
        summaries.append(ExperimentResult(
            experiment_id=key,
            label=labels[key],
            weak_score=round(sum(scores["weak"]) / len(scores["weak"]), 1),
            strong_score=round(sum(scores["strong"]) / len(scores["strong"]), 1),
            notes="Average Memory Health for this comparison group only.",
        ))
    return summaries


def extraction_comparison_payload(plan, db):
    from app.services.extraction_comparison import exact_reference_checks, extraction_usage
    from app.services.reassessment import saved_answer_signature
    source = db.get(AuditRunModel,plan.source_run_id)
    references = [Memory.model_validate(item) for item in plan.reference_snapshot]
    return {'comparison_id':plan.id,'source':audit_schema(source) if source else None,'created_at':plan.created_at,
        'inputs_match':bool(source and saved_answer_signature(db,source)==plan.input_fingerprint),
        'runtime_matches':plan.runtime_signature==audit_runtime_signature(),'reference_memories':references,
        'entries':[{**entry,'usage':extraction_usage(entry),
            'checks':exact_reference_checks(entry['candidates'],references)} for entry in plan.entries]}


@router.post('/extraction-comparisons',status_code=201)
def create_extraction_comparison(request:ExtractionComparisonRequest,db:Session=Depends(get_db)):
    from app.services.extraction_comparison import create_extraction_plan
    with audit_run_lock('extractor-'+request.creation_request_key,db=db):
        return extraction_comparison_payload(create_extraction_plan(db,request),db)


@router.get('/extraction-comparisons')
def list_extraction_comparisons(db:Session=Depends(get_db)):
    plans=db.scalars(select(ExtractionComparisonModel).order_by(ExtractionComparisonModel.created_at.desc())).all()
    return [extraction_comparison_payload(plan,db) for plan in plans]


@router.get('/extraction-comparisons/{comparison_id}')
def get_extraction_comparison(comparison_id:str,db:Session=Depends(get_db)):
    plan=db.get(ExtractionComparisonModel,comparison_id)
    if not plan:missing('Memory extraction comparison')
    return extraction_comparison_payload(plan,db)


@router.post('/extraction-comparisons/{comparison_id}/entries/{index}/extract')
def execute_extraction_comparison(comparison_id:str,index:int,db:Session=Depends(get_db)):
    from app.services.extraction_comparison import extract_entry, source_for_plan
    with audit_run_lock('extractor-'+comparison_id,db=db):
        plan=db.get(ExtractionComparisonModel,comparison_id)
        if not plan:missing('Memory extraction comparison')
        source=source_for_plan(db,plan)
        conversation=db.get(ConversationModel,source.conversation_id)
        try:
            result=extract_entry(db,plan,index,conversation_schema(db,conversation),get_memory_extractor)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502,'Extraction could not complete. Saved progress is retained; check the service and retry.') from None
        return extraction_comparison_payload(result,db)
