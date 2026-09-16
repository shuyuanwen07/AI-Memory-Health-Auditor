"""Regression contracts for the relative-chronology target memory policy."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.memory_agent.store import SqlTargetMemoryStore
from app.models import AuditRunModel, ConversationModel
from app.schemas import (
    AuditCreate,
    Conversation,
    ConversationMessage,
    Dimension,
    Memory,
    MemoryStatus,
    MemoryStrategy,
    TargetConfiguration,
    TestCase,
)


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False)()


def _run(db, run_id: str = "RUN-TEMPORAL"):
    db.add(ConversationModel(id="C-TEMPORAL", authorised=True))
    db.add(AuditRunModel(
        id=run_id, conversation_id="C-TEMPORAL", status="CREATED",
        target_configuration="strong", provider="rule_based", model="rule-based-target-ai",
        temperature=0.0, random_seed=42, test_budget=4, prompt_template_version="rule-based-v1",
        pipeline_provider="rule_based", pipeline_model="rule-based-v2",
        evaluator_provider="rule_based", evaluator_model="rule-based-v2",
        memory_strategy=MemoryStrategy.TEMPORAL_IMPORTANCE.value,
    ))
    db.commit()


def _conversation(year: int = 2026) -> Conversation:
    # The intentionally inverted absolute timestamps prove that the policy
    # consumes authorised message *position*, rather than timestamp values.
    return Conversation(
        conversation_id="C-TEMPORAL", authorised=True,
        created_at=datetime(year, 6, 1, tzinfo=timezone.utc),
        messages=[
            ConversationMessage(
                message_id="MSG-OLD", role="user",
                content="The database selected is MySQL.",
                timestamp=datetime(year + 10, 1, 1, tzinfo=timezone.utc),
            ),
            ConversationMessage(
                message_id="MSG-NEW", role="user",
                content="The database selected is PostgreSQL.",
                timestamp=datetime(year - 10, 1, 1, tzinfo=timezone.utc),
            ),
        ],
    )


class _ChronologyExtractor:
    def extract(self, conversation: Conversation):
        # Invert memory timestamps too: neither these nor the audit wall-clock
        # may affect temporal_importance ranking.
        first, second = conversation.messages
        return [
            Memory(
                memory_id="M-OLD", conversation_id=conversation.conversation_id,
                canonical_value="The database selected is MySQL.", status=MemoryStatus.CANDIDATE,
                source_message_ids=[first.message_id], timestamp=first.timestamp,
            ),
            Memory(
                memory_id="M-NEW", conversation_id=conversation.conversation_id,
                canonical_value="The database selected is PostgreSQL.", status=MemoryStatus.CANDIDATE,
                source_message_ids=[second.message_id], timestamp=second.timestamp,
            ),
        ]


class _ImportanceExtractor:
    def extract(self, conversation: Conversation):
        first, second = conversation.messages
        return [
            Memory(
                memory_id="M-REQUIREMENT", conversation_id=conversation.conversation_id,
                canonical_value="This project must use PostgreSQL database.", status=MemoryStatus.CANDIDATE,
                source_message_ids=[first.message_id], timestamp=first.timestamp,
            ),
            Memory(
                memory_id="M-EPISODIC", conversation_id=conversation.conversation_id,
                canonical_value="The database selected is SQLite.", status=MemoryStatus.CANDIDATE,
                source_message_ids=[second.message_id], timestamp=second.timestamp + timedelta(seconds=1),
            ),
        ]


def _database_test() -> TestCase:
    return TestCase(
        test_id="T-TEMPORAL", run_id="RUN-TEMPORAL", dimension=Dimension.FRESHNESS,
        prompt="Which database should we use?", expected_behavior="PostgreSQL.",
        supporting_memory_ids=[], generator_version="test-v1",
    )


def test_temporal_importance_uses_source_message_order_not_absolute_timestamps():
    db = _db()
    _run(db)
    result = SqlTargetMemoryStore(db, extractor=_ChronologyExtractor()).retrieve(
        "RUN-TEMPORAL", _conversation(), _database_test(), MemoryStrategy.TEMPORAL_IMPORTANCE,
    )

    assert result.context[-1] == "The database selected is PostgreSQL."
    rows = {row["memory_id"]: row for row in result.evidence.ranking_evidence}
    assert rows[next(key for key in rows if rows[key]["relative_chronology"] == 0.5)]["chronology_basis"] == "authorised_conversation_message_order"
    assert sorted(row["recency_factor"] for row in rows.values()) == [15.0, 30.0]
    assert all(row["importance_components"] == ["scope:episodic=10"] for row in rows.values())
    assert all(row["temporal_importance_score"] is not None for row in rows.values())


def test_temporal_importance_is_invariant_when_only_calendar_values_change():
    def score_rows(year: int, run_id: str):
        db = _db()
        _run(db, run_id)
        test = _database_test().model_copy(update={"run_id": run_id})
        output = SqlTargetMemoryStore(db, extractor=_ChronologyExtractor()).retrieve(
            run_id, _conversation(year), test, MemoryStrategy.TEMPORAL_IMPORTANCE,
        )
        return output.context, [
            (row["relative_chronology"], row["recency_factor"], row["importance_factor"], row["temporal_importance_score"])
            for row in output.evidence.ranking_evidence
        ]

    assert score_rows(2026, "RUN-TEMPORAL-A") == score_rows(2088, "RUN-TEMPORAL-B")


def test_temporal_importance_can_prioritise_requirement_importance_over_small_recency_gain():
    db = _db()
    _run(db)
    result = SqlTargetMemoryStore(db, extractor=_ImportanceExtractor()).retrieve(
        "RUN-TEMPORAL", _conversation(), _database_test(), MemoryStrategy.TEMPORAL_IMPORTANCE,
    )

    assert result.context[-1] == "This project must use PostgreSQL database."
    evidence = {row["scope"]: row for row in result.evidence.ranking_evidence}
    assert evidence["project_requirement"]["importance_factor"] == 45.0
    assert evidence["episodic"]["recency_factor"] > evidence["project_requirement"]["recency_factor"]
    assert evidence["project_requirement"]["temporal_importance_score"] > evidence["episodic"]["temporal_importance_score"]


def test_audit_contract_accepts_temporal_importance_as_a_controlled_strategy():
    audit = AuditCreate.model_validate({
        "conversation_id": "C-TEMPORAL",
        "target_configuration": TargetConfiguration.STRONG,
        "memory_strategy": "temporal_importance",
    })
    assert audit.memory_strategy == MemoryStrategy.TEMPORAL_IMPORTANCE
