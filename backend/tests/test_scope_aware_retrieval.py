"""Contracts for the scope-aware controlled retrieval condition."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.memory_agent.store import SqlTargetMemoryStore
from app.models import AuditRunModel, ConversationModel
from app.schemas import (
    Conversation,
    ConversationMessage,
    Dimension,
    Memory,
    MemoryStatus,
    MemoryStrategy,
    AuditCreate,
    TargetConfiguration,
    TargetMemoryMaintenancePolicy,
    TestCase,
)


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False)()


def _conversation() -> Conversation:
    now = datetime.now(timezone.utc)
    return Conversation(
        conversation_id="C-SCOPE-RETRIEVAL", authorised=True, created_at=now,
        messages=[ConversationMessage(
            message_id="MSG001", role="user", timestamp=now,
            content="The user generally prefers Python. This assignment currently requires Java.",
        )],
    )


def _run(db):
    db.add(ConversationModel(id="C-SCOPE-RETRIEVAL", authorised=True))
    db.add(AuditRunModel(
        id="RUN-SCOPE-RETRIEVAL", conversation_id="C-SCOPE-RETRIEVAL", status="CREATED",
        target_configuration="strong", provider="rule_based", model="rule-based-target-ai",
        temperature=0.0, random_seed=42, test_budget=4, prompt_template_version="rule-based-v1",
        pipeline_provider="rule_based", pipeline_model="rule-based-v2",
        evaluator_provider="rule_based", evaluator_model="rule-based-v2",
        memory_strategy="scope_aware",
    ))
    db.commit()


class _ScopedExtractor:
    def extract(self, conversation: Conversation):
        now = conversation.messages[0].timestamp
        return [
            Memory(memory_id="M-PREF", conversation_id=conversation.conversation_id,
                   canonical_value="The user generally prefers Python.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=now),
            Memory(memory_id="M-REQ", conversation_id=conversation.conversation_id,
                   canonical_value="This assignment currently requires Java.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=now + timedelta(seconds=1)),
            Memory(memory_id="M-PROFILE", conversation_id=conversation.conversation_id,
                   canonical_value="The user is based in Sydney.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=now + timedelta(seconds=2)),
        ]


def test_scope_aware_prefers_requirement_and_excludes_general_preference_for_current_task():
    db = _db()
    _run(db)
    store = SqlTargetMemoryStore(db, extractor=_ScopedExtractor())
    test = TestCase(
        test_id="T-SCOPE-REQ", run_id="RUN-SCOPE-RETRIEVAL", dimension=Dimension.APPROPRIATE_USE,
        prompt="Which language is required for this current assignment?",
        expected_behavior="Use Java.", supporting_memory_ids=[], generator_version="test-v1",
    )

    result = store.retrieve("RUN-SCOPE-RETRIEVAL", _conversation(), test, MemoryStrategy.SCOPE_AWARE)

    assert result.context[-1] == "This assignment currently requires Java."
    assert "The user generally prefers Python." not in result.context
    requirement = next(row for row in result.evidence.ranking_evidence if row["scope"] == "project_requirement")
    assert "intent=current_project_requirement" in requirement["reason"]
    assert "scope_bonus=80" in requirement["reason"]


def test_audit_contract_accepts_scope_aware_as_a_controlled_strategy():
    audit = AuditCreate.model_validate({
        "conversation_id": "C-SCOPE-RETRIEVAL",
        "target_configuration": TargetConfiguration.STRONG,
        "memory_strategy": "scope_aware",
    })
    assert audit.memory_strategy == MemoryStrategy.SCOPE_AWARE


def test_scope_aware_uses_preference_only_for_explicit_preference_question():
    db = _db()
    _run(db)
    store = SqlTargetMemoryStore(db, extractor=_ScopedExtractor())
    test = TestCase(
        test_id="T-SCOPE-PREF", run_id="RUN-SCOPE-RETRIEVAL", dimension=Dimension.ACCURACY,
        prompt="Which programming language does the user prefer?",
        expected_behavior="Python.", supporting_memory_ids=[], generator_version="test-v1",
    )

    result = store.retrieve("RUN-SCOPE-RETRIEVAL", _conversation(), test, MemoryStrategy.SCOPE_AWARE)

    assert result.context == ["The user generally prefers Python."]
    assert "intent=general_preference" in result.evidence.ranking_evidence[0]["reason"]


class _DuplicateExtractor:
    def extract(self, conversation: Conversation):
        now = conversation.messages[0].timestamp
        return [
            Memory(memory_id="M1", conversation_id=conversation.conversation_id,
                   canonical_value="The user is based in Sydney.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=now),
            Memory(memory_id="M2", conversation_id=conversation.conversation_id,
                   canonical_value="the user is based in Sydney!", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG002"], timestamp=now + timedelta(seconds=1)),
        ]


def test_update_aware_maintenance_merges_only_exact_normalised_duplicates():
    db = _db()
    _run(db)
    result = SqlTargetMemoryStore(
        db, extractor=_DuplicateExtractor(),
        maintenance_policy=TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION,
    ).ingest("RUN-SCOPE-RETRIEVAL", _conversation())

    assert len(result.records) == 1
    assert result.records[0].source_message_ids == ["MSG001", "MSG002"]
    merged = next(event for event in result.write_evidence if event.event_type.value == "MAINTENANCE_APPLIED")
    assert merged.details["maintenance_action"] == "merged_exact_duplicate"


def test_append_only_retains_same_text_as_two_independent_observations():
    db = _db()
    _run(db)
    result = SqlTargetMemoryStore(
        db, extractor=_DuplicateExtractor(),
        maintenance_policy=TargetMemoryMaintenancePolicy.APPEND_ONLY,
    ).ingest("RUN-SCOPE-RETRIEVAL", _conversation())

    assert len(result.records) == 2
