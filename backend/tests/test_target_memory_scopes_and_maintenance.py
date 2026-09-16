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
    Dimension,
    Memory,
    MemoryRelationship,
    MemoryStatus,
    RelationshipType,
    TargetMemoryEventType,
    TargetMemoryLifecycleState,
    TargetMemoryMaintenancePolicy,
    TargetMemoryScope,
    MemoryStrategy,
    TestCase,
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


class _NearDuplicateExtractor:
    def extract(self, conversation: Conversation):
        now = conversation.messages[0].timestamp
        return [
            Memory(memory_id="M1", conversation_id=conversation.conversation_id,
                   canonical_value="The user is based in Sydney.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=now),
            Memory(memory_id="M2", conversation_id=conversation.conversation_id,
                   canonical_value="User is based in Sydney.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG002"], timestamp=now + timedelta(seconds=1)),
        ]


def test_update_aware_policy_merges_only_conservative_near_duplicates():
    db = _db()
    _run(db)
    result = SqlTargetMemoryStore(
        db, extractor=_NearDuplicateExtractor(),
        maintenance_policy=TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION,
    ).ingest("RUN-SCOPES", _conversation())

    assert len(result.records) == 1
    assert result.records[0].source_message_ids == ["MSG001", "MSG002"]
    event = next(item for item in result.write_evidence if item.event_type == TargetMemoryEventType.MAINTENANCE_APPLIED)
    assert event.details["maintenance_action"] == "merged_conservative_near_duplicate"
    assert event.details["content_signature"] == ["based", "in", "is", "sydney"]


class _CapacityExtractor:
    def extract(self, conversation: Conversation):
        now = conversation.messages[0].timestamp
        return [
            Memory(memory_id="M-EP", conversation_id=conversation.conversation_id,
                   canonical_value="The user attended a workshop in Canberra.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=now),
            Memory(memory_id="M-PREF", conversation_id=conversation.conversation_id,
                   canonical_value="The user generally prefers Python.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG002"], timestamp=now + timedelta(seconds=1)),
            Memory(memory_id="M-REQ", conversation_id=conversation.conversation_id,
                   canonical_value="This assignment requires Java.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG003"], timestamp=now + timedelta(seconds=2)),
        ]


class _ConflictCapacityExtractor:
    def extract(self, conversation: Conversation):
        now = conversation.messages[0].timestamp
        return [
            Memory(memory_id="M-A", conversation_id=conversation.conversation_id,
                   canonical_value="The deployment must use region A.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=now),
            Memory(memory_id="M-B", conversation_id=conversation.conversation_id,
                   canonical_value="The deployment must use region B.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG002"], timestamp=now + timedelta(seconds=1),
                   relationships=[MemoryRelationship(type=RelationshipType.CONFLICT, target_memory_id="M-A")]),
        ]


def test_capacity_evicts_low_retention_record_and_excludes_it_from_every_retrieval_policy():
    db = _db()
    _run(db)
    store = SqlTargetMemoryStore(db, extractor=_CapacityExtractor(), capacity=2)
    result = store.ingest("RUN-SCOPES", _conversation())

    evicted = next(record for record in result.records if record.canonical_value.endswith("Canberra."))
    assert evicted.lifecycle_state == TargetMemoryLifecycleState.EVICTED
    event = next(item for item in result.write_evidence if item.details.get("maintenance_action") == "capacity_evicted_record")
    assert event.details["evicted_memory_id"] == evicted.memory_id
    assert event.details["exclusion"] == "all_retrieval_strategies"

    test = TestCase(
        test_id="T-CAPACITY", run_id="RUN-SCOPES", dimension=Dimension.ACCURACY,
        prompt="Which workshop did the user attend in Canberra?", expected_behavior="Canberra.",
        supporting_memory_ids=[], generator_version="test-v1",
    )
    retrieval = store.retrieve("RUN-SCOPES", _conversation(), test, MemoryStrategy.WEAK_FIRST_HIT)
    assert retrieval.context == []
    evidence = next(row for row in retrieval.evidence.ranking_evidence if row["memory_id"] == evicted.memory_id)
    assert evidence["eligible"] is False
    assert "capacity_evicted_excluded" in evidence["reason"]


def test_capacity_soft_limit_never_discards_an_unresolved_conflict_pair():
    db = _db()
    _run(db)
    result = SqlTargetMemoryStore(db, extractor=_ConflictCapacityExtractor(), capacity=1).ingest("RUN-SCOPES", _conversation())

    assert len(result.records) == 2
    assert {record.lifecycle_state for record in result.records} == {TargetMemoryLifecycleState.CONFLICTED}
    event = next(item for item in result.write_evidence if item.details.get("maintenance_action") == "capacity_soft_limit_preserved_conflict")
    assert event.details["max_active_records"] == 1
    assert len(event.details["protected_conflicted_memory_ids"]) == 2
