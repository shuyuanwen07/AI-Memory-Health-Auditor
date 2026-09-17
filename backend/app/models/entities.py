from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base


def utc_now() -> datetime:
    """Timezone-aware replacement for the deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc)

class ConversationModel(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    authorised: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

class MessageModel(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "source_message_id",
            name="uq_messages_conversation_source_message_id",
        ),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    # ``id`` is an internal globally unique database key.  The source ID is
    # deliberately stored separately because common exports reuse identifiers
    # such as MSG001 in every conversation.
    source_message_id: Mapped[str] = mapped_column(String(160), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime)

class MemoryModel(Base):
    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    canonical_value: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="candidate")
    source_message_ids: Mapped[list] = mapped_column(JSON, default=list)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class MemoryRelationshipModel(Base):
    __tablename__ = "memory_relationships"
    __table_args__ = (UniqueConstraint("memory_id", "relationship_type", "target_memory_id", name="uq_memory_relationships_edge"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    memory_id: Mapped[str] = mapped_column(ForeignKey("memories.id", ondelete="CASCADE"))
    relationship_type: Mapped[str] = mapped_column(String(30))
    target_memory_id: Mapped[str] = mapped_column(ForeignKey("memories.id", ondelete="CASCADE"))


class ExperimentModel(Base):
    """A reproducible comparison group sharing one generated test suite.

    ``test_suite_source_run_id`` identifies the run which generated the
    canonical test cases.  Peer runs retain their own cloned test-case rows so
    target responses and evaluations remain isolated, while the experiment
    records the immutable source used for comparison.
    """

    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="CREATED")
    test_suite_configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    test_suite_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    test_suite_source_run_id: Mapped[str | None] = mapped_column(
        # This is the deliberate nullable edge in the experiment/run cycle.
        # ``use_alter`` gives SQLAlchemy a deterministic metadata ordering for
        # Alembic drift checks while retaining the existing PostgreSQL FK.
        ForeignKey(
            "audit_runs.id", ondelete="SET NULL", use_alter=True,
            name="experiments_test_suite_source_run_id_fkey",
        ),
        nullable=True, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditRunModel(Base):
    __tablename__ = "audit_runs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    experiment_id: Mapped[str | None] = mapped_column(
        ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(40), default="CREATED")
    target_configuration: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(30), default="rule_based")
    model: Mapped[str] = mapped_column(String(100))
    temperature: Mapped[float] = mapped_column(Float)
    random_seed: Mapped[int] = mapped_column(Integer)
    test_budget: Mapped[int] = mapped_column(Integer)
    prompt_template_version: Mapped[str] = mapped_column(String(40))
    pipeline_provider: Mapped[str] = mapped_column(String(30), default="rule_based")
    pipeline_model: Mapped[str] = mapped_column(String(100), default="rule-based-v2")
    evaluator_provider: Mapped[str] = mapped_column(String(30), default="rule_based")
    evaluator_model: Mapped[str] = mapped_column(String(100), default="rule-based-v4")
    memory_strategy: Mapped[str] = mapped_column(String(40), default="strong_rule_based")
    memory_maintenance_policy: Mapped[str] = mapped_column(
        String(40), default="update_aware_consolidation"
    )
    # A small, explicit capacity lets experiments compare retention pressure
    # without relying on an environment default that could change mid-study.
    target_memory_capacity: Mapped[int] = mapped_column(
        Integer, default=50, server_default="50"
    )
    # Frozen at creation. TARGET_MEMORY_WRITER is only used to choose this
    # default; execution must never depend on a subsequently changed env var.
    target_memory_writer: Mapped[str] = mapped_column(
        String(40), default="rule_based", server_default="rule_based"
    )
    target_memory_writer_version: Mapped[str | None] = mapped_column(
        String(100), nullable=True, server_default="rule-based-memory-extractor-v1"
    )
    # Adapter identity is frozen with the run so an external target system can
    # later be replayed or compared without changing route contracts.
    target_system_adapter: Mapped[str] = mapped_column(
        String(60), default="controlled-memory", server_default="controlled-memory"
    )
    target_system_adapter_version: Mapped[str | None] = mapped_column(
        String(100), nullable=True, server_default="controlled-memory-v1"
    )
    # This is a safe, immutable-at-creation snapshot: no credentials, prompts,
    # source conversation text, or provider response bodies belong here.
    reproducibility_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class TestCaseModel(Base):
    __tablename__ = "test_cases"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("audit_runs.id", ondelete="CASCADE"), index=True)
    # Populated only on peer runs cloned from an experiment's canonical suite.
    # Keeping this link makes per-test comparisons possible even though each
    # run owns its responses and evaluation rows.
    suite_test_id: Mapped[str | None] = mapped_column(
        ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dimension: Mapped[str] = mapped_column(String(30))
    prompt: Mapped[str] = mapped_column(Text)
    expected_behavior: Mapped[str] = mapped_column(Text)
    supporting_memory_ids: Mapped[list] = mapped_column(JSON, default=list)
    generator_version: Mapped[str] = mapped_column(String(40))
    test_type: Mapped[str] = mapped_column(String(20), default="contextual")
    quality_status: Mapped[str] = mapped_column(String(20), default="pending")
    grounding_status: Mapped[str] = mapped_column(String(20), default="pending")
    validation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_memory_context: Mapped[list] = mapped_column(JSON, default=list)

class TargetResponseModel(Base):
    __tablename__ = "target_responses"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    test_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("audit_runs.id", ondelete="CASCADE"), index=True)
    response_text: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(100))
    temperature: Mapped[float] = mapped_column(Float)
    # Attempts, latency and provider-reported token counts when available.
    # Raw provider payloads are deliberately not persisted.
    execution_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class TargetAgentMemoryModel(Base):
    """A private memory record owned by one controlled target-agent run.

    This is deliberately separate from ``memories``.  The latter is the
    human-reviewed audit ground truth; these rows model what the system under
    test independently wrote while ingesting the authorised conversation.
    """

    __tablename__ = "target_agent_memories"
    __table_args__ = (Index("ix_target_agent_memories_run_id_scope", "run_id", "scope"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"), index=True
    )
    source_conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    canonical_value: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(40), default="episodic")
    lifecycle_state: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    source_message_ids: Mapped[list] = mapped_column(JSON, default=list)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    write_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class TargetAgentMemoryRelationshipModel(Base):
    """Update/conflict/context links inside an individual target memory store."""

    __tablename__ = "target_agent_memory_relationships"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"), index=True
    )
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("target_agent_memories.id", ondelete="CASCADE"), index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(30))
    target_memory_id: Mapped[str] = mapped_column(
        ForeignKey("target_agent_memories.id", ondelete="CASCADE"), index=True
    )


class TargetAgentMemoryEventModel(Base):
    """Append-only write lifecycle evidence for reproducible target-agent runs."""

    __tablename__ = "target_agent_memory_events"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"), index=True
    )
    memory_id: Mapped[str | None] = mapped_column(
        ForeignKey("target_agent_memories.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(40))
    source_message_ids: Mapped[list] = mapped_column(JSON, default=list)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class TargetAgentRetrievalModel(Base):
    """Private retrieval trace. It is never represented by public test schemas."""

    __tablename__ = "target_agent_retrievals"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"), index=True
    )
    test_id: Mapped[str] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), index=True
    )
    strategy: Mapped[str] = mapped_column(String(40))
    selected_memory_ids: Mapped[list] = mapped_column(JSON, default=list)
    ranking_evidence: Mapped[list] = mapped_column(JSON, default=list)
    # A retrieval is only scored when it supplied the response that ultimately
    # completed this test. Earlier retry attempts remain traceable but cannot
    # inflate source-evidence quality metrics.
    final_response_id: Mapped[str | None] = mapped_column(
        ForeignKey("target_responses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

class EvaluationResultModel(Base):
    __tablename__ = "evaluation_results"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    test_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id", ondelete="CASCADE"), index=True)
    response_id: Mapped[str] = mapped_column(ForeignKey("target_responses.id", ondelete="CASCADE"))
    passed: Mapped[bool] = mapped_column(Boolean)
    failure_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    evidence_memory_ids: Mapped[list] = mapped_column(JSON, default=list)
    evaluator: Mapped[str] = mapped_column(String(40))


class EvaluationHumanReviewModel(Base):
    """A pseudonymous researcher label for one completed automated verdict.

    There is no account system in Foundation, so ``reviewer_label`` is a
    researcher-provided pseudonym.  The automated result is deliberately
    retained unchanged; these rows record calibration evidence rather than
    silently rewriting an audit outcome.  Independent labels can coexist;
    a separate reference or adjudication label is the explicit comparison
    target for automated-evaluator calibration.
    """

    __tablename__ = "evaluation_human_reviews"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_id", "reviewer_label", "review_role",
            name="uq_evaluation_human_review_reviewer_role",
        ),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"), index=True
    )
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_results.id", ondelete="CASCADE"), index=True
    )
    human_passed: Mapped[bool] = mapped_column(Boolean)
    human_failure_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reviewer_label: Mapped[str] = mapped_column(String(80))
    review_role: Mapped[str] = mapped_column(String(20), default="reference")
    based_on_review_ids: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
