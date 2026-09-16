"""Contract tests for the private, persistent controlled-target memory store."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.memory_agent import SqlTargetMemoryStore
from app.models import (
    AuditRunModel,
    ConversationModel,
    TargetAgentMemoryEventModel,
    TargetAgentMemoryModel,
    TargetAgentRetrievalModel,
)
from app.schemas import (
    Conversation,
    ConversationMessage,
    Dimension,
    Memory,
    MemoryRelationship,
    MemoryStatus,
    MemoryStrategy,
    RelationshipType,
    TargetMemoryEventType,
    TargetMemoryLifecycleState,
    TestCase,
)


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False)()


def _conversation() -> Conversation:
    now = datetime.now(timezone.utc)
    return Conversation(
        conversation_id="C-TARGET", authorised=True, created_at=now,
        messages=[ConversationMessage(
            message_id="MSG001", role="user", timestamp=now,
            content=("I used MySQL before. The backend now uses PostgreSQL. "
                     "I generally prefer Python. This assignment currently requires Java."),
        )],
    )


def _run(db, conversation_id="C-TARGET"):
    db.add(ConversationModel(id=conversation_id, authorised=True))
    db.add(AuditRunModel(
        id="RUN-TARGET", conversation_id=conversation_id, status="CREATED",
        target_configuration="strong", provider="rule_based", model="rule-based-target-ai",
        temperature=0.0, random_seed=42, test_budget=4,
        prompt_template_version="rule-based-v1", pipeline_provider="rule_based",
        pipeline_model="rule-based-v2", evaluator_provider="rule_based",
        evaluator_model="rule-based-v2", memory_strategy="strong_rule_based",
    ))
    db.commit()


def test_ingestion_writes_an_independent_store_and_is_idempotent():
    db = _db()
    _run(db)
    store = SqlTargetMemoryStore(db)

    first = store.ingest("RUN-TARGET", _conversation())
    db.commit()
    second = store.ingest("RUN-TARGET", _conversation())

    records = db.scalars(select(TargetAgentMemoryModel).where(TargetAgentMemoryModel.run_id == "RUN-TARGET")).all()
    events = db.scalars(select(TargetAgentMemoryEventModel).where(TargetAgentMemoryEventModel.run_id == "RUN-TARGET")).all()
    assert len(first.records) == len(second.records) == len(records) >= 4
    assert all(record.source_message_ids == ["MSG001"] for record in first.records)
    assert any(record.lifecycle_state == TargetMemoryLifecycleState.SUPERSEDED for record in first.records)
    assert TargetMemoryEventType.INGESTED.value in {event.event_type for event in events}
    assert TargetMemoryEventType.WRITTEN.value in {event.event_type for event in events}
    assert TargetMemoryEventType.UPDATED.value in {event.event_type for event in events}
    # Retry returns the original evidence: it does not write a second timeline.
    assert len(events) == len(second.write_evidence)


def test_retrieval_is_persistent_traceable_and_keeps_evaluator_secret_out_of_context():
    db = _db()
    _run(db)
    store = SqlTargetMemoryStore(db)
    test = TestCase(
        test_id="T-FRESH", run_id="RUN-TARGET", dimension=Dimension.FRESHNESS,
        prompt="Which database should be used now?", supporting_memory_ids=["GROUND-TRUTH-ONLY"],
        expected_behavior="EVALUATOR_ONLY_SECRET: PostgreSQL", generator_version="test-v1",
    )

    weak = store.retrieve("RUN-TARGET", _conversation(), test, MemoryStrategy.WEAK_FIRST_HIT)
    strong = store.retrieve("RUN-TARGET", _conversation(), test, MemoryStrategy.STRONG_RULE_BASED)
    db.commit()

    assert "MySQL" in weak.context[0]
    assert "PostgreSQL" in strong.context[-1]
    assert all("EVALUATOR_ONLY_SECRET" not in value for value in weak.context + strong.context)
    assert all("GROUND-TRUTH-ONLY" not in value for value in weak.context + strong.context)
    traces = db.scalars(select(TargetAgentRetrievalModel).where(TargetAgentRetrievalModel.run_id == "RUN-TARGET")).all()
    assert len(traces) == 2
    assert weak.evidence.selected_memory_ids
    assert any(row["selected"] for row in strong.evidence.ranking_evidence)


class _ConflictExtractor:
    def extract(self, conversation: Conversation):
        moment = conversation.messages[0].timestamp
        return [
            Memory(memory_id="M1", conversation_id=conversation.conversation_id,
                   canonical_value="The deployment must use region A.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=moment),
            Memory(memory_id="M2", conversation_id=conversation.conversation_id,
                   canonical_value="The deployment must use region B.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=moment + timedelta(seconds=1),
                   relationships=[MemoryRelationship(type=RelationshipType.CONFLICT, target_memory_id="M1")]),
        ]


def test_conflicts_are_retained_as_two_records_with_lifecycle_evidence():
    db = _db()
    _run(db)
    result = SqlTargetMemoryStore(db, extractor=_ConflictExtractor()).ingest("RUN-TARGET", _conversation())

    assert {record.lifecycle_state for record in result.records} == {TargetMemoryLifecycleState.CONFLICTED}
    assert any(event.event_type == TargetMemoryEventType.CONFLICT_RECORDED for event in result.write_evidence)
