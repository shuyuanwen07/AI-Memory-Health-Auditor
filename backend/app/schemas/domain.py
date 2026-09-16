from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class Dimension(str, Enum):
    ACCURACY = "accuracy"
    FRESHNESS = "freshness"
    CONFLICT_RESOLUTION = "conflict_resolution"
    APPROPRIATE_USE = "appropriate_use"
class TestType(str, Enum):
    """How a question elicits memory use; intentionally separate from dimension."""
    DIRECT = "direct"
    CONTEXTUAL = "contextual"
    PARAPHRASED = "paraphrased"
    INDIRECT = "indirect"
class TestSuiteMode(str, Enum):
    """Reproducible suite-construction method chosen by an experiment."""
    BEHAVIOURAL = "behavioural"
    DIRECT_GROUND_TRUTH = "direct_ground_truth"
    FIXED_TEMPLATE = "fixed_template"
class TestQualityStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
class GroundingStatus(str, Enum):
    PENDING = "pending"
    GROUNDED = "grounded"
    UNGROUNDED = "ungrounded"
class MemoryStatus(str, Enum):
    CANDIDATE = "candidate"; CONFIRMED = "confirmed"; EDITED = "edited"; REJECTED = "rejected"
class RelationshipType(str, Enum):
    UPDATE = "UPDATE"; CONFLICT = "CONFLICT"; CONTEXTUAL_OVERRIDE = "CONTEXTUAL_OVERRIDE"
class AuditStatus(str, Enum):
    CREATED="CREATED"; MEMORY_EXTRACTED="MEMORY_EXTRACTED"; GROUND_TRUTH_CONFIRMED="GROUND_TRUTH_CONFIRMED"; TESTS_GENERATED="TESTS_GENERATED"; TESTS_EXECUTED="TESTS_EXECUTED"; EVALUATED="EVALUATED"; COMPLETED="COMPLETED"; FAILED="FAILED"
class TargetConfiguration(str, Enum): WEAK="weak"; STRONG="strong"
class MemoryStrategy(str, Enum):
    WEAK_FIRST_HIT = "weak_first_hit"
    STRONG_RULE_BASED = "strong_rule_based"
    STRONG_SCORE_BASED = "strong_score_based"
    SCOPE_AWARE = "scope_aware"
class TargetMemoryScope(str, Enum):
    """Semantic area assigned to a record in the controlled Agent's store."""
    PROFILE = "profile"
    PREFERENCE = "preference"
    PROJECT_REQUIREMENT = "project_requirement"
    EPISODIC = "episodic"
class TargetMemoryMaintenancePolicy(str, Enum):
    """Write-side policy, independent of the target's retrieval strategy."""
    APPEND_ONLY = "append_only"
    UPDATE_AWARE_CONSOLIDATION = "update_aware_consolidation"
class TargetMemoryWriterKind(str, Enum):
    """The independently configured writer used by the controlled target Agent.

    This setting is frozen when an audit is created.  It is deliberately
    separate from the Auditor's extraction provider and from the target model
    that answers test prompts.
    """
    RULE_BASED = "rule_based"
    LLM_STRUCTURED = "llm_structured"
class TargetMemoryLifecycleState(str, Enum):
    """Private state of a controlled target agent's independently written record."""
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    CONFLICTED = "CONFLICTED"
class TargetMemoryEventType(str, Enum):
    INGESTED = "INGESTED"
    WRITTEN = "WRITTEN"
    UPDATED = "UPDATED"
    CONFLICT_RECORDED = "CONFLICT_RECORDED"
    CONTEXTUAL_OVERRIDE_RECORDED = "CONTEXTUAL_OVERRIDE_RECORDED"
    MAINTENANCE_APPLIED = "MAINTENANCE_APPLIED"
    RETRIEVED = "RETRIEVED"
class TargetProvider(str, Enum): RULE_BASED="rule_based"; OPENAI="openai"; DEEPSEEK="deepseek"; GEMINI="gemini"
class ExperimentStatus(str, Enum):
    CREATED = "CREATED"
    TEST_SUITE_GENERATED = "TEST_SUITE_GENERATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class ConversationMessage(BaseModel):
    message_id: str
    role: str
    content: str
    timestamp: datetime
class Conversation(BaseModel):
    conversation_id: str
    created_at: datetime
    authorised: bool
    messages: list[ConversationMessage] = []
class ConversationCreate(BaseModel):
    authorised: bool
    pasted_text: str | None = None
    messages: list[ConversationMessage] | None = None
class ConversationDeletionRequest(BaseModel):
    """Explicit acknowledgement required before local source data is erased."""
    confirmation: str = Field(min_length=1, max_length=40)
class ConversationDeletionReceipt(BaseModel):
    conversation_id: str
    deleted_audit_runs: int
    deleted_experiments: int
    message: str
class MemoryRelationship(BaseModel):
    relationship_id: str | None = None
    type: RelationshipType
    target_memory_id: str
class Memory(BaseModel):
    memory_id: str
    conversation_id: str
    canonical_value: str
    status: MemoryStatus
    source_message_ids: list[str] = []
    timestamp: datetime | None = None
    relationships: list[MemoryRelationship] = []

# The following contracts are intentionally server-side only.  Public routes
# continue to return TestCasePublic, never these target-agent internals.
class TargetAgentMemoryRecord(BaseModel):
    memory_id: str
    run_id: str
    source_conversation_id: str
    canonical_value: str
    scope: TargetMemoryScope
    lifecycle_state: TargetMemoryLifecycleState
    source_message_ids: list[str] = []
    observed_at: datetime | None = None
    write_order: int
    relationships: list[MemoryRelationship] = []

class TargetMemoryWriteEvidence(BaseModel):
    event_id: str
    run_id: str
    memory_id: str | None = None
    event_type: TargetMemoryEventType
    source_message_ids: list[str] = []
    details: dict = Field(default_factory=dict)
    created_at: datetime

class TargetMemoryRetrievalEvidence(BaseModel):
    retrieval_id: str
    run_id: str
    test_id: str
    strategy: MemoryStrategy
    selected_memory_ids: list[str] = []
    # A transparent score/reason record for every candidate considered.
    ranking_evidence: list[dict] = []
    created_at: datetime

class TargetMemoryIngestionResult(BaseModel):
    run_id: str
    records: list[TargetAgentMemoryRecord]
    write_evidence: list[TargetMemoryWriteEvidence]

class TargetMemoryRetrievalResult(BaseModel):
    context: list[str] = []
    evidence: TargetMemoryRetrievalEvidence

# These are deliberately separate from the runtime target-memory contracts
# above.  They form a *post-completion* audit view: no expected behaviour,
# prompt template, or private retrieval context is included.
class TargetMemoryTraceRecord(BaseModel):
    memory_id: str
    canonical_value: str
    scope: TargetMemoryScope
    lifecycle_state: TargetMemoryLifecycleState
    source_message_ids: list[str] = []
    observed_at: datetime | None = None
    write_order: int
    relationships: list[MemoryRelationship] = []

class TargetMemoryTraceEvent(BaseModel):
    event_id: str
    event_type: TargetMemoryEventType
    memory_id: str | None = None
    source_message_ids: list[str] = []
    details: dict = Field(default_factory=dict)
    created_at: datetime

class TargetMemoryTraceRetrieval(BaseModel):
    retrieval_id: str
    test_id: str
    strategy: MemoryStrategy
    selected_memory_ids: list[str] = []
    ranking_evidence: list[dict] = []
    created_at: datetime

class TargetMemoryTrace(BaseModel):
    run_id: str
    memory_strategy: MemoryStrategy
    memory_maintenance_policy: TargetMemoryMaintenancePolicy
    target_memory_writer: TargetMemoryWriterKind = TargetMemoryWriterKind.RULE_BASED
    target_memory_writer_version: str | None = None
    records: list[TargetMemoryTraceRecord] = []
    events: list[TargetMemoryTraceEvent] = []
    retrievals: list[TargetMemoryTraceRetrieval] = []
class MemoryCreate(BaseModel):
    conversation_id: str
    canonical_value: str
    source_message_ids: list[str] = []
    timestamp: datetime | None = None
    relationships: list[MemoryRelationship] = []
class MemoryUpdate(BaseModel):
    canonical_value: str | None = None
    status: MemoryStatus | None = None
    relationships: list[MemoryRelationship] | None = None
class GroundTruthConfirm(BaseModel):
    confirmed_memory_ids: list[str] = []

class TestSuiteConfiguration(BaseModel):
    """Frozen inputs used once when generating an experiment test suite."""
    __test__ = False  # avoid pytest treating this Pydantic contract as a test class
    test_budget: int = Field(default=8, ge=1, le=100)
    random_seed: int = 42
    prompt_template_version: str = "rule-based-v1"
    pipeline_provider: TargetProvider = TargetProvider.RULE_BASED
    pipeline_model: str = "rule-based-v2"
    dimensions: list[Dimension] = Field(default_factory=lambda: list(Dimension))
    # Existing experiments retain their behavioural-generator semantics.
    suite_mode: TestSuiteMode = TestSuiteMode.BEHAVIOURAL

class TestSuiteMetadata(BaseModel):
    """Facts recorded after suite generation, rather than user-supplied configuration."""
    __test__ = False
    test_count: int = Field(default=0, ge=0)
    dimensions: list[Dimension] = Field(default_factory=list)
    generator_version: str | None = None
    generated_at: datetime | None = None

class ExperimentCreate(BaseModel):
    conversation_id: str
    label: str = Field(min_length=1, max_length=160)
    test_suite_configuration: TestSuiteConfiguration = Field(default_factory=TestSuiteConfiguration)

class ExperimentUpdate(BaseModel):
    """Route layer must only set suite source/metadata after validating the run."""
    label: str | None = Field(default=None, min_length=1, max_length=160)
    status: ExperimentStatus | None = None
    test_suite_source_run_id: str | None = None
    test_suite_metadata: TestSuiteMetadata | None = None

class Experiment(BaseModel):
    experiment_id: str
    conversation_id: str
    label: str
    status: ExperimentStatus
    test_suite_configuration: TestSuiteConfiguration
    test_suite_metadata: TestSuiteMetadata
    test_suite_source_run_id: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

class AuditCreate(BaseModel):
    conversation_id: str
    experiment_id: str | None = None
    target_configuration: TargetConfiguration
    provider: TargetProvider = TargetProvider.RULE_BASED
    model: str = "rule-based-target-ai"
    temperature: float = 0.0
    random_seed: int = 42
    test_budget: int = Field(default=8, ge=1, le=100)
    prompt_template_version: str = "rule-based-v1"
    pipeline_provider: TargetProvider | None = None
    pipeline_model: str | None = None
    evaluator_provider: TargetProvider | None = None
    evaluator_model: str | None = None
    memory_strategy: MemoryStrategy | None = None
    memory_maintenance_policy: TargetMemoryMaintenancePolicy = TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION
    # Omitted means use TARGET_MEMORY_WRITER only as an audit-creation default.
    # The selected value is persisted on the resulting AuditRun and is never
    # re-read from the environment during execution.
    target_memory_writer: TargetMemoryWriterKind | None = None


class RetryPolicyMetadata(BaseModel):
    """The bounded target-provider retry policy frozen with a run."""
    max_attempts: int = 3
    timeout_seconds: float = 60.0
    retryable_status_codes: list[int] = [408, 409, 425, 429, 500, 502, 503, 504]


class ReproducibilityMetadata(BaseModel):
    """Safe, portable provenance for a controlled audit run.

    Fingerprints cover configuration/template identity, not conversation text or
    credentials. A run snapshot allows later reproduction after environment
    defaults change.
    """
    schema_version: str = "reproducibility-v1"
    configuration_fingerprint: str | None = None
    prompt_template_fingerprint: str | None = None
    target_memory_writer_version: str | None = None
    target_memory_writer: TargetMemoryWriterKind = TargetMemoryWriterKind.RULE_BASED
    memory_policy_version: str | None = None
    target_retry_policy: RetryPolicyMetadata = Field(default_factory=RetryPolicyMetadata)


class ExecutionMetadata(BaseModel):
    """Sanitised per-response facts; optional usage is provider supplied."""
    request_attempts: int = 0
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    response_source: str = "unknown"

class AuditRun(BaseModel):
    run_id: str; conversation_id: str; experiment_id: str | None = None; status: AuditStatus; target_configuration: TargetConfiguration; provider: TargetProvider
    model: str; temperature: float; random_seed: int; test_budget: int; prompt_template_version: str
    pipeline_provider: str = "rule_based"; pipeline_model: str = "rule-based-v2"
    evaluator_provider: str = "rule_based"; evaluator_model: str = "rule-based-v2"
    memory_strategy: MemoryStrategy = MemoryStrategy.STRONG_RULE_BASED
    memory_maintenance_policy: TargetMemoryMaintenancePolicy = TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION
    target_memory_writer: TargetMemoryWriterKind = TargetMemoryWriterKind.RULE_BASED
    target_memory_writer_version: str | None = None
    reproducibility: ReproducibilityMetadata = Field(default_factory=ReproducibilityMetadata)
    created_at: datetime; completed_at: datetime | None = None
class TestCase(BaseModel):
    test_id: str; run_id: str; dimension: Dimension; prompt: str; expected_behavior: str
    supporting_memory_ids: list[str]; generator_version: str
    test_type: TestType = TestType.CONTEXTUAL
    quality_status: TestQualityStatus = TestQualityStatus.PENDING
    grounding_status: GroundingStatus = GroundingStatus.PENDING
    validation_notes: str | None = None
    # Private runtime memory supplied to the controlled target, not displayed in the UI.
    target_memory_context: list[str] = []
class TestCasePublic(BaseModel):
    """Test data visible to clients; controlled-target context stays server-side."""
    test_id: str; run_id: str; dimension: Dimension; prompt: str; expected_behavior: str
    supporting_memory_ids: list[str]; generator_version: str
    test_type: TestType = TestType.CONTEXTUAL
    quality_status: TestQualityStatus = TestQualityStatus.PENDING
    grounding_status: GroundingStatus = GroundingStatus.PENDING
    validation_notes: str | None = None
class TestReviewUpdate(BaseModel):
    """A researcher decision on a generated test before target execution."""
    quality_status: TestQualityStatus
    note: str | None = Field(default=None, max_length=1000)
class TestReviewSuite(BaseModel):
    run_id: str
    canonical_run_id: str
    tests: list[TestCasePublic]
class TestQualityAssessment(BaseModel):
    """A traceable decision about whether a generated test belongs in a suite."""
    quality_status: TestQualityStatus
    grounding_status: GroundingStatus
    reason: str
    validator_version: str
class TargetResponse(BaseModel):
    response_id: str; test_id: str; run_id: str; response_text: str; model: str; temperature: float
    execution_metadata: ExecutionMetadata = Field(default_factory=ExecutionMetadata)
    created_at: datetime
class EvaluationResult(BaseModel):
    evaluation_id: str; test_id: str; response_id: str; passed: bool; failure_type: Dimension | None = None
    reason: str; evidence_memory_ids: list[str]; evaluator: str
class DimensionScores(BaseModel):
    dimension: Dimension; percentage: float | None; passed: int; total: int
class FailureDetail(BaseModel):
    failure_id: str; test: TestCasePublic; response: TargetResponse; evaluation: EvaluationResult; evidence: list[Memory]
class AuditResult(BaseModel):
    run_id: str; overall_score: float | None; tests_passed: int; tests_total: int
    dimensions: list[DimensionScores]; failures: list[FailureDetail]
    reproducibility: ReproducibilityMetadata = Field(default_factory=ReproducibilityMetadata)
class ExperimentResult(BaseModel):
    experiment_id: str; label: str; weak_score: float; strong_score: float; notes: str

# Experiment-history contracts intentionally expose only public test and
# evaluation data.  A controlled target's private retrieval context remains
# server-side even when a whole comparison group is inspected or exported.
class ExperimentDimensionSummary(BaseModel):
    dimension: Dimension
    mean_percentage: float | None = None
    standard_deviation: float | None = None
    passed: int = 0
    total: int = 0
    measured_runs: int = 0

class ExperimentConditionSummary(BaseModel):
    condition_id: str
    label: str
    provider: TargetProvider
    model: str
    memory_strategy: MemoryStrategy
    planned_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    run_ids: list[str] = []
    overall_mean: float | None = None
    overall_standard_deviation: float | None = None
    tests_passed: int = 0
    tests_total: int = 0
    failure_count: int = 0
    dimensions: list[ExperimentDimensionSummary] = []

class PairedComparison(BaseModel):
    """A per-run paired signal, aligned through the frozen source test IDs."""
    reference_run_id: str
    reference_label: str
    candidate_run_id: str
    candidate_label: str
    shared_tests: int
    both_passed: int
    both_failed: int
    reference_only_passed: int
    candidate_only_passed: int
    candidate_delta_percentage_points: float | None = None
    candidate_delta_confidence_interval_low: float | None = None
    candidate_delta_confidence_interval_high: float | None = None
    two_sided_sign_test_p_value: float | None = None

class ExperimentRunReport(BaseModel):
    run: AuditRun
    result: AuditResult | None = None

class ExperimentAnalytics(BaseModel):
    experiment: Experiment
    runs: list[ExperimentRunReport] = []
    conditions: list[ExperimentConditionSummary] = []
    paired_comparisons: list[PairedComparison] = []
class ProviderOption(BaseModel):
    provider: TargetProvider
    label: str
    default_model: str
    configured: bool
    description: str
