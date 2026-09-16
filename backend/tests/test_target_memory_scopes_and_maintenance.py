"""Focused contracts for typed target memories and write-side policies."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.memory_agent.store import SqlTargetMemoryStore, infer_target_memory_scope
from app.models import AuditRunModel, ConversationModel, TargetAgentMemoryModel
from app.schemas import (
    Conversation,
    ConversationMessage,
    Memory,
    MemoryRelationship,
    MemoryStatus,
    RelationshipType,
    TargetMemoryEventType,
    TargetMemoryLifecycleState,
    TargetMemoryMaintenancePolicy,
    TargetMemoryScope,
)


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False)()


def _conversation() -> Conversation:
    now = datetime.now(timezone.utc)
    return Conversation(
        conversation_id="C-SCOPES", authorised=True, created_at=now,
        messages=[ConversationMessage(
            message_id="MSG001", role="user", timestamp=now,
            content="I previously used MySQL. I now use PostgreSQL for the backend.",
        )],
    )


def _run(db, run_id="RUN-SCOPES"):
    db.add(ConversationModel(id="C-SCOPES", authorised=True))
    db.add(AuditRunModel(
        id=run_id, conversation_id="C-SCOPES", status="CREATED",
        target_configuration="strong", provider="rule_based", model="rule-based-target-ai",
        temperature=0.0, random_seed=42, test_budget=4,
        prompt_template_version="rule-based-v1", pipeline_provider="rule_based",
        pipeline_model="rule-based-v2", evaluator_provider="rule_based",
        evaluator_model="rule-based-v2", memory_strategy="strong_rule_based",
    ))
    db.commit()


def test_scope_inference_uses_small_stable_domain_labels():
    assert infer_target_memory_scope("I am based in Sydney.") == TargetMemoryScope.PROFILE
    assert infer_target_memory_scope("I generally prefer Python.") == TargetMemoryScope.PREFERENCE
    assert infer_target_memory_scope("This assignment requires Java.") == TargetMemoryScope.PROJECT_REQUIREMENT
    assert infer_target_memory_scope("I attended a workshop yesterday.") == TargetMemoryScope.EPISODIC


class _UpdateExtractor:
    def extract(self, conversation: Conversation):
        then = conversation.messages[0].timestamp
        return [
            Memory(memory_id="M001", conversation_id=conversation.conversation_id,
                   canonical_value="The backend used MySQL.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=then),
            Memory(memory_id="M002", conversation_id=conversation.conversation_id,
                   canonical_value="The backend now uses PostgreSQL.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=then + timedelta(seconds=1),
                   relationships=[MemoryRelationship(type=RelationshipType.UPDATE, target_memory_id="M001")]),
        ]


def test_update_aware_policy_supersedes_prior_record_and_records_scope():
    db = _db()
    _run(db)
    result = SqlTargetMemoryStore(
        db, extractor=_UpdateExtractor(),
        maintenance_policy=TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION,
    ).ingest("RUN-SCOPES", _conversation())

    old, current = result.records
    assert old.scope == TargetMemoryScope.PROFILE
    assert current.scope == TargetMemoryScope.PROFILE
    assert old.lifecycle_state == TargetMemoryLifecycleState.SUPERSEDED
    updated = next(event for event in result.write_evidence if event.event_type == TargetMemoryEventType.UPDATED)
    assert updated.details["maintenance_action"] == "supersede_prior_record"
    assert updated.details["maintenance_policy"] == "update_aware_consolidation"


def test_append_only_policy_keeps_prior_record_active_and_makes_decision_traceable():
    db = _db()
    _run(db)
    result = SqlTargetMemoryStore(
        db, extractor=_UpdateExtractor(),
        maintenance_policy=TargetMemoryMaintenancePolicy.APPEND_ONLY,
    ).ingest("RUN-SCOPES", _conversation())

    records = db.scalars(select(TargetAgentMemoryModel).where(TargetAgentMemoryModel.run_id == "RUN-SCOPES")).all()
    assert [record.lifecycle_state for record in records] == ["ACTIVE", "ACTIVE"]
    maintained = next(event for event in result.write_evidence if event.event_type == TargetMemoryEventType.MAINTENANCE_APPLIED)
    assert maintained.details["maintenance_action"] == "retained_prior_record"
    assert maintained.details["maintenance_policy"] == "append_only"
