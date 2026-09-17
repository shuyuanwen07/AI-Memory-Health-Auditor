from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import os
import time
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO, StringIO
import csv
import hashlib
import json
import zipfile
from sqlalchemy import delete, select, text, update
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
from app.models import AuditRunModel, ConversationModel, EvaluationHumanReviewModel, EvaluationResultModel, ExperimentModel, MemoryModel, MemoryRelationshipModel, MessageModel, TargetAgentMemoryEventModel, TargetAgentMemoryModel, TargetAgentMemoryRelationshipModel, TargetAgentRetrievalModel, TargetResponseModel, TestCaseModel
from app.schemas import *
from app.target_ai.providers import PROVIDERS, configured
from app.target_systems import get_target_system_adapter
from app.test_generator.factory import get_test_generator
from app.test_generator.baselines import get_suite_generator
from app.test_generator.quality import RuleBasedTestQualityValidator

router = APIRouter(prefix="/api/v1")
def ident(prefix: str) -> str: return f"{prefix}{uuid4().hex.upper()}"
def missing(kind: str): raise HTTPException(404, f"{kind} was not found.")
def ensure_supported_pipeline_role(provider: TargetProvider, role: str) -> None:
    """Keep a target-only provider out of structured pipeline/judge roles."""
    if provider == TargetProvider.OLLAMA:
        raise HTTPException(
            422,
            f"Ollama is currently supported only as the controlled target AI, not as the {role}. "
            "Choose rule_based, openai, deepseek, or gemini for that role.",
        )
def conversation_schema(db, obj):
    messages = db.scalars(select(MessageModel).where(MessageModel.conversation_id == obj.id).order_by(MessageModel.sequence, MessageModel.timestamp)).all()
    return Conversation(conversation_id=obj.id, created_at=obj.created_at, authorised=obj.authorised, messages=[ConversationMessage(message_id=getattr(m, "source_message_id", None) or m.id, role=m.role, content=m.content, timestamp=m.timestamp) for m in messages])

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
    return Memory(memory_id=obj.id, conversation_id=obj.conversation_id, canonical_value=obj.canonical_value, status=obj.status, source_message_ids=obj.source_message_ids, timestamp=obj.timestamp, relationships=[MemoryRelationship(relationship_id=r.id, type=r.relationship_type, target_memory_id=r.target_memory_id) for r in rels])


def fingerprint(payload: dict) -> str:
    """Hash public configuration only; never include conversation or secrets."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def reproducibility_snapshot(*, provider: str, model: str, temperature: float, random_seed: int,
                             test_budget: int, prompt_template_version: str, pipeline_provider: str,
                             pipeline_model: str, evaluator_provider: str, evaluator_model: str,
                             memory_strategy: str, memory_maintenance_policy: str,
                             target_memory_writer: TargetMemoryWriterKind | str,
                             target_memory_capacity: int,
                             target_system_adapter: TargetSystemAdapterKind | str) -> dict:
    """Freeze safe reproducibility facts when a run is created."""
    writer_kind = TargetMemoryWriterKind(target_memory_writer)
    writer = get_target_memory_writer(pipeline_provider, pipeline_model, writer_kind)
    writer_version = getattr(writer, "VERSION", writer.__class__.__name__)
    configuration = {
        "provider": provider, "model": model, "temperature": temperature,
        "random_seed": random_seed, "test_budget": test_budget,
        "pipeline_provider": pipeline_provider, "pipeline_model": pipeline_model,
        "evaluator_provider": evaluator_provider, "evaluator_model": evaluator_model,
        "memory_strategy": memory_strategy,
        "memory_maintenance_policy": memory_maintenance_policy,
        "target_memory_capacity": target_memory_capacity,
        "target_memory_writer": writer_kind.value,
        "target_memory_writer_version": writer_version,
        "target_system_adapter": TargetSystemAdapterKind(target_system_adapter).value,
        "target_system_adapter_version": "controlled-memory-v1",
    }
    return {
        "schema_version": "reproducibility-v1",
        "configuration_fingerprint": fingerprint(configuration),
        "prompt_template_fingerprint": fingerprint({
            "prompt_template_version": prompt_template_version,
            "pipeline_provider": pipeline_provider, "pipeline_model": pipeline_model,
            "evaluator_provider": evaluator_provider, "evaluator_model": evaluator_model,
        }),
        "target_memory_writer_version": writer_version,
        "target_memory_writer": writer_kind.value,
        "target_system_adapter": TargetSystemAdapterKind(target_system_adapter).value,
        "target_system_adapter_version": "controlled-memory-v1",
        "memory_policy_version": "target-memory-policy-v1",
        # A seed is fully deterministic for the local baseline. Third-party
        # APIs do not share one portable seed contract, so retain it as a
        # configuration identifier rather than implying bit-for-bit replay.
        "seed_control": {
            "target": "deterministic_local" if provider == "rule_based" else "recorded_only",
            "pipeline": "deterministic_local" if pipeline_provider == "rule_based" else "recorded_only",
            "evaluator": "deterministic_local" if evaluator_provider == "rule_based" else "recorded_only",
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
    return AuditRun(run_id=obj.id, conversation_id=obj.conversation_id, experiment_id=obj.experiment_id, status=obj.status, target_configuration=obj.target_configuration, provider=obj.provider, model=obj.model, temperature=obj.temperature, random_seed=obj.random_seed, test_budget=obj.test_budget, prompt_template_version=obj.prompt_template_version, pipeline_provider=obj.pipeline_provider, pipeline_model=obj.pipeline_model, evaluator_provider=obj.evaluator_provider, evaluator_model=obj.evaluator_model, memory_strategy=obj.memory_strategy, memory_maintenance_policy=getattr(obj, "memory_maintenance_policy", "update_aware_consolidation"), target_memory_capacity=getattr(obj, "target_memory_capacity", 50), target_memory_writer=writer_kind, target_memory_writer_version=writer_version, target_system_adapter=adapter, target_system_adapter_version=adapter_version, reproducibility=metadata, created_at=obj.created_at, completed_at=obj.completed_at)
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
def eval_schema(o): return EvaluationResult(evaluation_id=o.id, test_id=o.test_id, response_id=o.response_id, passed=o.passed, failure_type=o.failure_type, reason=o.reason, evidence_memory_ids=o.evidence_memory_ids, evaluator=o.evaluator)
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
    return [ProviderOption(provider=provider, label=label, default_model=model, configured=configured(provider), description=description) for provider, (label, model, description) in PROVIDERS.items()]

@router.post("/conversations", response_model=Conversation, status_code=201)
def create_conversation(payload: ConversationCreate, db: Session = Depends(get_db)):
    if not payload.authorised: raise HTTPException(422, "Authorisation is required before conversation data can be processed.")
    if not payload.pasted_text and not payload.messages: raise HTTPException(422, "Provide pasted conversation text or structured messages.")
    messages = payload.messages or pasted_messages(payload.pasted_text or "")
    if not messages:
        raise HTTPException(422, "Provide at least one non-empty conversation message.")
    source_ids = [message.message_id or f"MSG{index:03d}" for index, message in enumerate(messages, 1)]
    if len(source_ids) != len(set(source_ids)):
        raise HTTPException(422, "Conversation message IDs must be unique within the uploaded conversation.")
    c = ConversationModel(id=ident("C"), authorised=True); db.add(c); db.flush()
    fallback_time = datetime.now(timezone.utc)
    for i, (m, source_id) in enumerate(zip(messages, source_ids), 1):
        db.add(MessageModel(
            id=ident("MSG"), conversation_id=c.id, source_message_id=source_id, sequence=i,
            role=m.role.strip(), content=m.content.strip(),
            timestamp=m.timestamp or fallback_time + timedelta(microseconds=i),
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
    for run in runs:
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
    data = {"schema_version": "conversation-export-v1", "exported_at": datetime.now(timezone.utc),
            "notice": "Local authorised-data export. API keys and raw provider payloads are excluded.",
            "conversation": conversation_schema(db, conversation).model_dump(mode="json"),
            "ground_truth_memories": [memory_schema(db, row).model_dump(mode="json") for row in memories],
            "experiments": [experiment_schema(row).model_dump(mode="json") for row in experiments], "audits": audits}
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
def extract(conversation_id: str, db: Session = Depends(get_db)):
    c = db.get(ConversationModel, conversation_id)
    if not c: missing("Conversation")
    existing = db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == conversation_id)).all()
    if existing: return [memory_schema(db, x) for x in existing]
    extracted = get_memory_extractor().extract(conversation_schema(db, c))
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
        for memory in extracted:
            db.add(MemoryModel(
                id=durable_ids[memory.memory_id], conversation_id=conversation_id,
                canonical_value=memory.canonical_value, status=memory.status.value,
                source_message_ids=memory.source_message_ids, timestamp=memory.timestamp,
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
                ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return [memory_schema(db, x) for x in db.scalars(
        select(MemoryModel).where(MemoryModel.conversation_id == conversation_id)
    ).all()]
@router.get("/conversations/{conversation_id}/memories", response_model=list[Memory])
def memories(conversation_id: str, db: Session = Depends(get_db)):
    return [memory_schema(db, x) for x in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == conversation_id)).all()]
@router.post("/memories", response_model=Memory, status_code=201)
def add_memory(payload: MemoryCreate, db: Session = Depends(get_db)):
    if not db.get(ConversationModel, payload.conversation_id): missing("Conversation")
    validate_memory_evidence(db, payload.conversation_id, payload.source_message_ids, payload.relationships)
    m = MemoryModel(id=ident("M"), conversation_id=payload.conversation_id, canonical_value=payload.canonical_value, status="candidate", source_message_ids=payload.source_message_ids, timestamp=payload.timestamp); db.add(m); db.flush()
    for r in payload.relationships: db.add(MemoryRelationshipModel(id=ident("MR"), memory_id=m.id, relationship_type=r.type.value, target_memory_id=r.target_memory_id))
    db.commit(); return memory_schema(db,m)
@router.patch("/memories/{memory_id}", response_model=Memory)
def patch_memory(memory_id: str, payload: MemoryUpdate, db: Session = Depends(get_db)):
    m=db.get(MemoryModel,memory_id)
    if not m: missing("Memory")
    next_sources = payload.source_message_ids if payload.source_message_ids is not None else list(m.source_message_ids)
    next_relationships = payload.relationships if payload.relationships is not None else memory_schema(db, m).relationships
    validate_memory_evidence(db, m.conversation_id, next_sources, next_relationships, m.id)
    if payload.canonical_value is not None: m.canonical_value=payload.canonical_value
    if payload.status is not None: m.status=payload.status.value
    if payload.source_message_ids is not None: m.source_message_ids=payload.source_message_ids
    if "timestamp" in payload.model_fields_set: m.timestamp=payload.timestamp
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
    ensure_supported_pipeline_role(payload.test_suite_configuration.pipeline_provider, "memory-extraction and test-generation pipeline")
    ensure_supported_pipeline_role(payload.test_suite_configuration.evaluator_provider, "behaviour evaluator")
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
    if experiment and experiment.status != ExperimentStatus.CREATED.value:
        raise HTTPException(
            409,
            "Experiment membership is frozen once its shared test suite has been generated or the experiment is terminal.",
        )
    confirmed=db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==payload.conversation_id, MemoryModel.status.in_(["confirmed","edited"]))).all()
    if not confirmed: raise HTTPException(409, "Confirm ground truth before creating an audit.")
    default_model=PROVIDERS[payload.provider][1]
    model=payload.model if payload.model not in ("", "rule-based-target-ai") or payload.provider == TargetProvider.RULE_BASED else default_model
    suite = TestSuiteConfiguration.model_validate(experiment.test_suite_configuration) if experiment else None
    selected_pipeline_provider = suite.pipeline_provider.value if suite else (payload.pipeline_provider.value if payload.pipeline_provider else pipeline_provider())
    ensure_supported_pipeline_role(TargetProvider(selected_pipeline_provider), "memory-extraction and test-generation pipeline")
    if suite:
        selected_evaluator_provider = suite.evaluator_provider.value
        selected_evaluator_model = suite.evaluator_model
    else:
        selected_evaluator_provider, selected_evaluator_model = configured_evaluator(
            payload.evaluator_provider.value if payload.evaluator_provider else None, payload.evaluator_model,
        )
    ensure_supported_pipeline_role(TargetProvider(selected_evaluator_provider), "behaviour evaluator")
    selected_strategy = payload.memory_strategy or (MemoryStrategy.WEAK_FIRST_HIT if payload.target_configuration == TargetConfiguration.WEAK else MemoryStrategy.STRONG_RULE_BASED)
    selected_seed = suite.random_seed if suite else payload.random_seed
    selected_budget = suite.test_budget if suite else payload.test_budget
    selected_template = suite.prompt_template_version if suite else payload.prompt_template_version
    selected_pipeline_model = suite.pipeline_model if suite else (payload.pipeline_model or configured_pipeline_model(selected_pipeline_provider))
    selected_maintenance_policy = payload.memory_maintenance_policy.value
    selected_memory_capacity = payload.target_memory_capacity
    # The environment is read exactly once here. Every later stage uses the
    # persisted writer kind/version below, even if .env changes meanwhile.
    selected_target_memory_writer = payload.target_memory_writer or default_target_memory_writer_kind()
    metadata = reproducibility_snapshot(
        provider=payload.provider.value, model=model, temperature=payload.temperature,
        random_seed=selected_seed, test_budget=selected_budget,
        prompt_template_version=selected_template, pipeline_provider=selected_pipeline_provider,
        pipeline_model=selected_pipeline_model, evaluator_provider=selected_evaluator_provider,
        evaluator_model=selected_evaluator_model, memory_strategy=selected_strategy.value,
        memory_maintenance_policy=selected_maintenance_policy,
        target_memory_writer=selected_target_memory_writer,
        target_memory_capacity=selected_memory_capacity,
        target_system_adapter=payload.target_system_adapter,
    )
    a=AuditRunModel(id=ident("RUN"), conversation_id=payload.conversation_id, experiment_id=payload.experiment_id, status="CREATED", target_configuration=payload.target_configuration.value, provider=payload.provider.value, model=model, temperature=payload.temperature, random_seed=selected_seed, test_budget=selected_budget, prompt_template_version=selected_template, pipeline_provider=selected_pipeline_provider, pipeline_model=selected_pipeline_model, evaluator_provider=selected_evaluator_provider, evaluator_model=selected_evaluator_model, memory_strategy=selected_strategy.value, memory_maintenance_policy=selected_maintenance_policy, target_memory_capacity=selected_memory_capacity, target_memory_writer=selected_target_memory_writer.value, target_memory_writer_version=metadata["target_memory_writer_version"], target_system_adapter=payload.target_system_adapter.value, target_system_adapter_version=metadata["target_system_adapter_version"], reproducibility_metadata=metadata)
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
        transition_audit_status(
            db, a, AuditStatus.TESTS_GENERATED, AuditStatus.TESTS_EXECUTED,
        )
    except HTTPException:
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
    a=db.get(AuditRunModel,run_id)
    if not a: missing("Audit")
    require_state(a,{AuditStatus.TESTS_EXECUTED})
    mems=[memory_schema(db,m) for m in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==a.conversation_id)).all()]; outputs=[]
    try:
        completed_test_ids = set(db.scalars(select(EvaluationResultModel.test_id).join(TestCaseModel).where(TestCaseModel.run_id == run_id)).all())
        for t in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==run_id)).all():
            if t.id in completed_test_ids:
                continue
            db.refresh(a)
            if a.status == AuditStatus.CANCELLED.value:
                raise HTTPException(409, "This audit was cancelled. Completed evaluations were retained for traceability.")
            r=db.scalar(select(TargetResponseModel).where(TargetResponseModel.test_id==t.id)); e=get_behaviour_evaluator(a.evaluator_provider, a.evaluator_model).evaluate(test_schema(t),response_schema(r),mems); outputs.append(e); db.add(EvaluationResultModel(id=e.evaluation_id,test_id=e.test_id,response_id=e.response_id,passed=e.passed,failure_type=e.failure_type.value if e.failure_type else None,reason=e.reason,evidence_memory_ids=e.evidence_memory_ids,evaluator=e.evaluator)); db.flush()
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
    return {
        "run_id": run_id, "next_stage": plan.next_stage.value if plan.next_stage else None,
        "pending": len(plan.pending_test_ids), "retryable": plan.retryable,
    }

@router.post("/audits/{run_id}/retry", response_model=AuditRun)
def retry_audit(run_id: str, db: Session = Depends(get_db)):
    """Resume only the incomplete durable stage of an interrupted audit."""
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
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
    return AuditResult(run_id=run_id,overall_score=overall,tests_passed=sum(e.passed for e in es),tests_total=len(es),dimensions=dimensions,failures=failures,retrieval_quality=RetrievalQualityService().calculate(run_id, db),reproducibility=getattr(a, "reproducibility_metadata", {}) or {})
@router.get("/audits/{run_id}/results", response_model=AuditResult)
def results(run_id:str,db:Session=Depends(get_db)): return result_for(run_id,db)


def evaluation_review_items_for(run_id: str, db: Session) -> list[EvaluationReviewItem]:
    """Join verdicts to independent labels and an explicit resolved label."""
    audit = db.get(AuditRunModel, run_id)
    if not audit: missing("Audit")
    if audit.status != AuditStatus.COMPLETED.value:
        raise HTTPException(409, "Evaluation review is available after the audit is complete.")
    tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id).order_by(TestCaseModel.id)).all()
    evaluations = db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id == run_id)).all()
    evaluation_by_test = {row.test_id: row for row in evaluations}
    reviews = db.scalars(select(EvaluationHumanReviewModel).where(EvaluationHumanReviewModel.run_id == run_id)).all()
    review_by_evaluation: dict[str, list[EvaluationHumanReviewModel]] = {}
    for review in reviews:
        review_by_evaluation.setdefault(review.evaluation_id, []).append(review)

    def resolved_review(rows: list[EvaluationHumanReviewModel]) -> EvaluationHumanReviewModel | None:
        # Adjudication deliberately wins over a reference label.  Routes allow
        # at most one record in each resolved role, so this is deterministic.
        for role in (HumanReviewRole.ADJUDICATION.value, HumanReviewRole.REFERENCE.value):
            found = [row for row in rows if getattr(row, "review_role", "reference") == role]
            if found:
                return sorted(found, key=lambda row: (row.updated_at, row.id), reverse=True)[0]
        return None
    items: list[EvaluationReviewItem] = []
    for test in tests:
        automated = evaluation_by_test.get(test.id)
        response = db.scalar(select(TargetResponseModel).where(TargetResponseModel.test_id == test.id))
        if automated and response:
            all_reviews = sorted(review_by_evaluation.get(automated.id, []), key=lambda row: (row.created_at, row.id))
            resolved = resolved_review(all_reviews)
            items.append(EvaluationReviewItem(
                test=public_test_schema(test), response=response_schema(response),
                automated=eval_schema(automated),
                human_review=human_review_schema(resolved) if resolved else None,
                human_reviews=[human_review_schema(row) for row in all_reviews],
            ))
    return items


@router.get("/audits/{run_id}/evaluation-review", response_model=list[EvaluationReviewItem])
def evaluation_review_items(run_id: str, db: Session = Depends(get_db)):
    """Return completed answers and verdicts for explicit human calibration."""
    return evaluation_review_items_for(run_id, db)


@router.patch("/audits/{run_id}/evaluations/{evaluation_id}/review", response_model=EvaluationHumanReview)
def review_evaluation(run_id: str, evaluation_id: str, payload: EvaluationHumanReviewUpdate, db: Session = Depends(get_db)):
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
    if role == HumanReviewRole.INDEPENDENT.value:
        review = db.scalar(select(EvaluationHumanReviewModel).where(
            EvaluationHumanReviewModel.evaluation_id == evaluation_id,
            EvaluationHumanReviewModel.reviewer_label == payload.reviewer_label.strip(),
            EvaluationHumanReviewModel.review_role == role,
        ))
    else:
        review = db.scalar(select(EvaluationHumanReviewModel).where(
            EvaluationHumanReviewModel.evaluation_id == evaluation_id,
            EvaluationHumanReviewModel.review_role == role,
        ))
        if review is not None and review.reviewer_label != payload.reviewer_label.strip() and not legacy_payload:
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
        review.reviewer_label = payload.reviewer_label.strip()
        review.based_on_review_ids = list(payload.based_on_review_ids)
        review.note = payload.note.strip() if payload.note else None
    db.commit(); db.refresh(review)
    return human_review_schema(review)


@router.get("/audits/{run_id}/evaluation-calibration", response_model=EvaluationCalibrationSummary)
def evaluation_calibration(run_id: str, db: Session = Depends(get_db)):
    """Calibrate automated labels against explicit resolution labels only.

    Independent labels measure inter-rater reliability.  They are *not*
    silently majority-voted into the automated-evaluator calibration set.
    """
    items = evaluation_review_items_for(run_id, db)
    reviewed = [item for item in items if item.human_review]
    automated_failures = sum(not item.automated.passed for item in items)
    agreements = sum(item.automated.passed == item.human_review.human_passed for item in reviewed if item.human_review)
    true_positive = sum((not item.automated.passed) and (not item.human_review.human_passed) for item in reviewed if item.human_review)
    false_positive = sum((not item.automated.passed) and item.human_review.human_passed for item in reviewed if item.human_review)
    false_negative = sum(item.automated.passed and (not item.human_review.human_passed) for item in reviewed if item.human_review)
    precision = round(true_positive / (true_positive + false_positive) * 100, 1) if true_positive + false_positive else None
    recall = round(true_positive / (true_positive + false_negative) * 100, 1) if true_positive + false_negative else None
    f1 = round(2 * precision * recall / (precision + recall), 1) if precision is not None and recall is not None and precision + recall else None
    by_dimension: dict[str, dict[str, int]] = {}
    for item in reviewed:
        bucket = by_dimension.setdefault(item.test.dimension.value, {"reviewed": 0, "agreement": 0, "automated_failures": 0, "human_failures": 0})
        bucket["reviewed"] += 1
        bucket["agreement"] += int(item.automated.passed == item.human_review.human_passed)
        bucket["automated_failures"] += int(not item.automated.passed)
        bucket["human_failures"] += int(not item.human_review.human_passed)

    independent_groups: dict[str, list[EvaluationHumanReview]] = {}
    for item in items:
        labels = [review for review in item.human_reviews if review.review_role == HumanReviewRole.INDEPENDENT]
        if labels:
            independent_groups[item.automated.evaluation_id] = labels
    independently_reviewed = [labels for labels in independent_groups.values() if len(labels) >= 2]
    consensus_count = sum(len({label.human_passed for label in labels}) == 1 for labels in independently_reviewed)
    conflict_count = len(independently_reviewed) - consensus_count
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

def target_memory_trace_payload(audit: AuditRunModel, db: Session) -> TargetMemoryTrace:
    """Build terminal target-memory evidence without evaluator-only material."""
    run_id = audit.id
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
        retrievals=[TargetMemoryTraceRetrieval(
            retrieval_id=item.id, test_id=item.test_id, strategy=item.strategy,
            selected_memory_ids=list(item.selected_memory_ids),
            ranking_evidence=list(item.ranking_evidence), final_response_id=item.final_response_id,
            created_at=item.created_at,
        ) for item in retrievals],
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
            }
            for report in analytics.runs
        ],
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
    records = db.scalars(select(TargetAgentMemoryModel).where(
        TargetAgentMemoryModel.run_id == run_id
    ).order_by(TargetAgentMemoryModel.write_order)).all()
    events = db.scalars(select(TargetAgentMemoryEventModel).where(
        TargetAgentMemoryEventModel.run_id == run_id
    ).order_by(TargetAgentMemoryEventModel.created_at, TargetAgentMemoryEventModel.id)).all()
    retrievals = db.scalars(select(TargetAgentRetrievalModel).where(
        TargetAgentRetrievalModel.run_id == run_id
    ).order_by(TargetAgentRetrievalModel.created_at, TargetAgentRetrievalModel.id)).all()
    return {
        "records": [target_trace_record_schema(db, record).model_dump(mode="json") for record in records],
        "events": [safe_trace_event_schema(event).model_dump(mode="json") for event in events],
        "retrievals": [TargetMemoryTraceRetrieval(
            retrieval_id=item.id, test_id=item.test_id, strategy=item.strategy,
            selected_memory_ids=list(item.selected_memory_ids),
            ranking_evidence=list(item.ranking_evidence), final_response_id=item.final_response_id,
            created_at=item.created_at,
        ).model_dump(mode="json") for item in retrievals],
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
        "schema_version": "memory-health-experiment-artifact-v1",
        "experiment_id": experiment_id,
        "notice": "Frozen audit artifact. It excludes raw authorised conversation text, credentials and raw provider payloads.",
        "code_revision": os.getenv("AUDITOR_CODE_REVISION", "unknown"),
        "dataset_hash_sha256": hashlib.sha256(suite_bytes).hexdigest(),
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
