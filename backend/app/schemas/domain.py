from typing import Literal
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, model_validator, computed_field
from app.schemas.target_profile import TargetMemoryProfile

class ReassessmentRequest(BaseModel):
    """Explicit assessor selection over immutable saved target answers."""

    model_config = {'extra': 'forbid'}
    evaluator_provider: Literal['rule_based', 'openrouter', 'openrouter_taxonomy', 'openai', 'deepseek', 'gemini', 'ollama']
    evaluator_model: str | None = Field(default=None, max_length=200)

    @model_validator(mode='after')
    def concrete_model(self):
        if self.evaluator_model is not None:
            self.evaluator_model = self.evaluator_model.strip()
        if self.evaluator_provider != 'rule_based' and not self.evaluator_model:
            raise ValueError('Choose a specific evaluator model for the comparison.')
        if self.evaluator_provider == 'openrouter_taxonomy' and self.evaluator_model != 'openai/gpt-6-luna':
            raise ValueError('The validated taxonomy evaluator requires openai/gpt-6-luna.')
        base_model = (self.evaluator_model or '').lower().split(':', 1)[0]
        if self.evaluator_model and (base_model.split('/')[-1].endswith('latest')
                                     or base_model == 'openrouter/auto'):
            raise ValueError('Choose a fixed model name instead of an automatic or latest alias.')
        return self


class Dimension(str, Enum):
    ACCURACY = "accuracy"
    FRESHNESS = "freshness"
    CONFLICT_RESOLUTION = "conflict_resolution"
    APPROPRIATE_USE = "appropriate_use"

class MethodComparisonDefect(BaseModel):
    """One source-grounded failure in Experiment A's independently reviewed inventory."""
    model_config = {'extra': 'forbid'}
    defect_id: str = Field(min_length=1, max_length=100)
    dimension: Dimension
    supporting_memory_ids: list[str] = Field(min_length=1, max_length=20)
    source_message_ids: list[str] = Field(min_length=1, max_length=50)
    explanation: str = Field(min_length=10, max_length=2000)

    @model_validator(mode='after')
    def unique_evidence(self):
        if len(set(self.supporting_memory_ids)) != len(self.supporting_memory_ids):
            raise ValueError('A failure inventory item cannot repeat a supporting memory.')
        if len(set(self.source_message_ids)) != len(self.source_message_ids):
            raise ValueError('A failure inventory item cannot repeat a source message.')
        return self

class MethodComparisonFixedTemplateQuestion(BaseModel):
    """A source-bound fixed-template question reviewed and confirmed by a researcher."""
    model_config = {'extra': 'forbid'}
    template_id: str = Field(min_length=1, max_length=100)
    dimension: Dimension
    prompt: str = Field(min_length=8, max_length=2000)
    expected_behavior: str = Field(min_length=8, max_length=2000)
    supporting_memory_ids: list[str] = Field(min_length=1, max_length=20)
    source_message_ids: list[str] = Field(min_length=1, max_length=50)
    test_type: Literal["direct", "contextual", "paraphrased", "indirect"] = "contextual"

    @model_validator(mode='after')
    def unique_evidence(self):
        if len(set(self.supporting_memory_ids)) != len(self.supporting_memory_ids):
            raise ValueError('A fixed template cannot repeat a supporting memory.')
        if len(set(self.source_message_ids)) != len(self.source_message_ids):
            raise ValueError('A fixed template cannot repeat a source message.')
        return self

class MethodComparisonInventoryImport(BaseModel):
    """Researcher-reviewed source-defect inventory and fixed-template release for Experiment A."""
    model_config = {'extra': 'forbid'}
    schema_version: Literal['mha-experiment-a-inventory-v1']
    comparison_id: str = Field(min_length=8, max_length=100)
    release_id: str = Field(min_length=1, max_length=120)
    source_fingerprint_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    annotation_mode: Literal['two_independent_reviewers_with_adjudication']
    reviewers: list[str] = Field(min_length=2, max_length=2)
    defects: list[MethodComparisonDefect] = Field(max_length=500)
    fixed_template_release_id: str = Field(min_length=1, max_length=120)
    fixed_template_draft_generator_version: Literal['fixed-template-v2', 'fixed-template-v3', 'fixed-template-v4', 'fixed-template-v5', 'fixed-template-v6', 'fixed-template-v7', 'fixed-template-v8', 'fixed-template-v9']
    fixed_template_draft_fingerprint_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    fixed_template_review_confirmed: Literal[True]
    fixed_template_reviewers: list[str] = Field(min_length=1, max_length=2)
    fixed_template_questions: list[MethodComparisonFixedTemplateQuestion] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def independent_identities(self):
        normalised = [reviewer.strip().casefold() for reviewer in self.reviewers]
        if any(not reviewer for reviewer in normalised) or len(set(normalised)) != 2:
            raise ValueError('Enter two distinct, non-blank reviewer pseudonyms.')
        if len({defect.defect_id for defect in self.defects}) != len(self.defects):
            raise ValueError('Failure inventory IDs must be unique.')
        template_reviewers = [reviewer.strip().casefold() for reviewer in self.fixed_template_reviewers]
        if any(not reviewer for reviewer in template_reviewers) or len(set(template_reviewers)) != len(template_reviewers):
            raise ValueError('Enter distinct, non-blank fixed-template reviewer/editor pseudonyms.')
        if len({question.template_id for question in self.fixed_template_questions}) != len(self.fixed_template_questions):
            raise ValueError('Fixed-template IDs must be unique.')
        return self

class MethodComparisonDiscoveryMappingEntry(BaseModel):
    """Human-reviewed link from one saved response to frozen known defects."""
    model_config = {'extra': 'forbid'}
    response_id: str = Field(min_length=1, max_length=40)
    test_id: str = Field(min_length=1, max_length=40)
    defect_ids: list[str] = Field(max_length=500)

    @model_validator(mode='after')
    def unique_defects(self):
        if len(set(self.defect_ids)) != len(self.defect_ids):
            raise ValueError('A response cannot map to the same frozen defect more than once.')
        return self

class MethodComparisonDiscoveryMappingImport(BaseModel):
    """Immutable researcher-confirmed response-to-defect mapping release."""
    model_config = {'extra': 'forbid'}
    schema_version: Literal['mha-experiment-a-discovery-map-v1']
    comparison_id: str = Field(min_length=8, max_length=100)
    inventory_fingerprint_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    mapping_release_id: str = Field(min_length=1, max_length=120)
    reviewer_pseudonym: str = Field(min_length=1, max_length=120)
    completed_by_human: Literal[True]
    entries: list[MethodComparisonDiscoveryMappingEntry] = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def unique_responses_and_reviewer(self):
        self.reviewer_pseudonym = self.reviewer_pseudonym.strip()
        self.mapping_release_id = self.mapping_release_id.strip()
        if not self.reviewer_pseudonym or not self.mapping_release_id:
            raise ValueError('A non-blank reviewer pseudonym and mapping release ID are required.')
        if len({entry.response_id for entry in self.entries}) != len(self.entries):
            raise ValueError('Each saved response must appear exactly once in the mapping release.')
        return self

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
    PAIRED_CONTEXTUAL = "paired_contextual"
    CONTEXTUAL_INDIRECT = "contextual_indirect"
class TestQualityStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
class HumanValidityStatus(str, Enum):
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
    CREATED="CREATED"; MEMORY_EXTRACTED="MEMORY_EXTRACTED"; GROUND_TRUTH_CONFIRMED="GROUND_TRUTH_CONFIRMED"; TESTS_GENERATED="TESTS_GENERATED"; TESTS_EXECUTED="TESTS_EXECUTED"; COMPLETED="COMPLETED"; FAILED="FAILED"; CANCELLED="CANCELLED"; RESEARCH_STAGED="RESEARCH_STAGED"
class TargetConfiguration(str, Enum): WEAK="weak"; STRONG="strong"
class MemoryStrategy(str, Enum):
    # Reference ablations make it clear whether a proposed memory policy
    # improves over no memory or simply approaches replaying the whole context.
    NO_MEMORY = "no_memory"
    FULL_CONTEXT = "full_context"
    WEAK_FIRST_HIT = "weak_first_hit"
    STRONG_RULE_BASED = "strong_rule_based"
    STRONG_SCORE_BASED = "strong_score_based"
    SCOPE_AWARE = "scope_aware"
    # A reproducible ablation that ranks source-message recency together with
    # transparent record importance.  It intentionally uses relative message
    # order, never the wall-clock time at which an audit happens.
    TEMPORAL_IMPORTANCE = "temporal_importance"
class TargetMemoryRetrievalMode(str, Enum):
    """Who chooses which target-private memories are supplied to the target."""
    AGENT = "agent"
    FIXED = "fixed"
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
class TargetSystemAdapterKind(str, Enum):
    """The system-under-test runtime selected for one reproducible audit."""
    CONTROLLED_MEMORY = "controlled-memory"
    EXTERNAL_HTTP = "external-http"
class TargetMemoryLifecycleState(str, Enum):
    """Private state of a controlled target agent's independently written record."""
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    CONFLICTED = "CONFLICTED"
    EVICTED = "EVICTED"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
class TargetMemoryEventType(str, Enum):
    INGESTED = "INGESTED"
    WRITTEN = "WRITTEN"
    UPDATED = "UPDATED"
    CONFLICT_RECORDED = "CONFLICT_RECORDED"
    CONTEXTUAL_OVERRIDE_RECORDED = "CONTEXTUAL_OVERRIDE_RECORDED"
    MAINTENANCE_APPLIED = "MAINTENANCE_APPLIED"
    RETRIEVED = "RETRIEVED"
class HumanReviewRole(str, Enum):
    """Purpose of a saved human evaluator label.

    Independent labels are kept separate from the single resolved label used
    to calibrate the automated evaluator.  This prevents a majority vote from
    being silently mistaken for an adjudicated research decision.
    """
    INDEPENDENT = "independent"
    REFERENCE = "reference"
    ADJUDICATION = "adjudication"
class TargetProvider(str, Enum): RULE_BASED="rule_based"; OPENAI="openai"; DEEPSEEK="deepseek"; GEMINI="gemini"; OLLAMA="ollama"; OPENROUTER="openrouter"
class ExperimentStatus(str, Enum):
    CREATED = "CREATED"
    TEST_SUITE_GENERATED = "TEST_SUITE_GENERATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class ConversationMessage(BaseModel):
    message_id: str
    role: str
    content: str
    timestamp: datetime
    original_timestamp: str | None = None

class ConversationMessageInput(BaseModel):
    """Lossless message input while retaining compatibility with pasted text."""
    message_id: str | None = Field(default=None, min_length=1, max_length=160)
    role: str = Field(default="user", min_length=1, max_length=20)
    content: str = Field(min_length=1, max_length=100_000)
    timestamp: datetime | None = None
    original_timestamp: str | None = Field(default=None, max_length=80)

    @model_validator(mode='after')
    def matching_original_time(self):
        if self.original_timestamp is not None:
            try:
                original = datetime.fromisoformat(self.original_timestamp)
            except ValueError as exc:
                raise ValueError('Original timestamp must be a valid ISO timestamp.') from exc
            if self.timestamp is None or original != self.timestamp:
                raise ValueError('Original timestamp must identify the same time as timestamp.')
        return self
class Conversation(BaseModel):
    conversation_id: str
    created_at: datetime
    authorised: bool
    source_origin: Literal["synthetic", "authorised", "deidentified", "unknown"] = "unknown"
    messages: list[ConversationMessage] = []
    extraction_provenance: dict | None = None
class ConversationCreate(BaseModel):
    creation_request_key: str | None = Field(default=None, min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    authorised: bool
    source_origin: Literal["synthetic", "authorised", "deidentified", "unknown"] = "unknown"
    pasted_text: str | None = Field(default=None, max_length=1_000_000)
    messages: list[ConversationMessageInput] | None = Field(default=None, max_length=10_000)
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
    evidence_message_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
class Memory(BaseModel):
    memory_id: str
    conversation_id: str
    canonical_value: str
    status: MemoryStatus
    source_message_ids: list[str] = []
    timestamp: datetime | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    relationships: list[MemoryRelationship] = []


class AgentExecution(BaseModel):
    """One traceable semantic-agent stage; source text stays in its parent record."""
    execution_id: str
    role: str
    conversation_id: str | None = None
    run_id: str | None = None
    provider: str
    model: str
    reported_model: str | None = None
    prompt_template_version: str
    prompt_fingerprint: str
    input_fingerprint: str
    input_refs: dict = Field(default_factory=dict)
    output_data: dict | list | None = None
    status: Literal["completed", "failed", "skipped"]
    attempt_count: int = Field(ge=0)
    elapsed_ms: float | None = Field(default=None, ge=0)
    error_code: str | None = None
    error_summary: str | None = None
    error_diagnostics: dict | None = None
    handoff_from: str | None = None
    handoff_to: str | None = None
    created_at: datetime

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
    final_response_id: str | None = None
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

class TargetMemoryInputEvidence(BaseModel):
    """Client-side input receipt, not proof of provider attention or grounding."""
    version: str = "target-memory-input-v1"
    record_count: int
    context_sha256: str
    instruction_sha256: str
    prompt_sha256: str
    sent_memory_ids: list[str] | None = None
    identity_advisory_sha256: str | None = None
    identity_failure_receipt_sha256: str | None = None

class TargetMemoryTraceRetrieval(BaseModel):
    question: str | None = None
    retrieval_id: str
    test_id: str
    strategy: MemoryStrategy
    selected_memory_ids: list[str] = []
    ranking_evidence: list[dict] = []
    final_response_id: str | None = None
    memory_input: TargetMemoryInputEvidence | None = None
    created_at: datetime

class TargetMemoryTrace(BaseModel):
    run_id: str
    shared_answer_source_run_id: str | None = None
    memory_strategy: MemoryStrategy
    retrieval_mode: TargetMemoryRetrievalMode = TargetMemoryRetrievalMode.FIXED
    retrieval_provider: str | None = None
    retrieval_model: str | None = None
    target_system_adapter: TargetSystemAdapterKind = TargetSystemAdapterKind.CONTROLLED_MEMORY
    target_system_adapter_version: str | None = None
    memory_maintenance_policy: TargetMemoryMaintenancePolicy
    target_memory_capacity: int = 50
    target_memory_writer: TargetMemoryWriterKind = TargetMemoryWriterKind.RULE_BASED
    target_memory_writer_version: str | None = None
    records: list[TargetMemoryTraceRecord] = []
    events: list[TargetMemoryTraceEvent] = []
    retrievals: list[TargetMemoryTraceRetrieval] = []
class ExtractionRequest(BaseModel):
    provider: TargetProvider | None = None
    model: str | None = Field(default=None, min_length=1, max_length=200)


class MemoryCreate(BaseModel):
    conversation_id: str
    canonical_value: str = Field(min_length=1, max_length=4000)
    source_message_ids: list[str] = []
    timestamp: datetime | None = None
    relationships: list[MemoryRelationship] = []
class MemoryUpdate(BaseModel):
    canonical_value: str | None = Field(default=None, min_length=1, max_length=4000)
    status: MemoryStatus | None = None
    source_message_ids: list[str] | None = None
    timestamp: datetime | None = None
    relationships: list[MemoryRelationship] | None = None
class GroundTruthConfirm(BaseModel):
    confirmed_memory_ids: list[str] = []

CoveragePolicy = Literal["strict_full_v1", "evidence_supported_only_v1"]


class TestSuiteConfiguration(BaseModel):
    """Frozen inputs used once when generating an experiment test suite."""
    __test__ = False  # avoid pytest treating this Pydantic contract as a test class
    test_budget: int = Field(default=8, ge=1, le=100)
    coverage_policy: CoveragePolicy = "strict_full_v1"
    random_seed: int = 42
    prompt_template_version: str = "rule-based-v4"
    pipeline_provider: TargetProvider = TargetProvider.RULE_BASED
    pipeline_model: str = "rule-based-v2"
    # Optional on input for compatibility; the experiment creation route
    # freezes explicit values and defaults the reviewer to the generator.
    semantic_review_provider: TargetProvider | None = None
    semantic_review_model: str | None = Field(default=None, min_length=1, max_length=200)
    # Evaluation must be held constant within a controlled comparison.  It is
    # part of the experiment protocol rather than a per-condition preference.
    evaluator_provider: TargetProvider = TargetProvider.RULE_BASED
    evaluator_model: str = "rule-based-v4"
    compare_evaluators: bool = False
    auditor_comparison_id: str | None = Field(default=None, min_length=8, max_length=100)
    dimensions: list[Dimension] = Field(default_factory=lambda: list(Dimension))
    # Existing experiments retain their behavioural-generator semantics.
    suite_mode: TestSuiteMode = TestSuiteMode.BEHAVIOURAL

    @model_validator(mode="after")
    def complete_pairs(self):
        if self.coverage_policy != "strict_full_v1" and (self.compare_evaluators or self.auditor_comparison_id):
            raise ValueError("Formal auditor comparison requires strict coverage.")
        if self.suite_mode == TestSuiteMode.PAIRED_CONTEXTUAL and self.test_budget < 2:
            raise ValueError("Paired probes require a budget of at least two questions.")
        return self

class TestSuiteMetadata(BaseModel):
    """Facts recorded after suite generation, rather than user-supplied configuration."""
    __test__ = False
    test_count: int = Field(default=0, ge=0)
    dimensions: list[Dimension] = Field(default_factory=list)
    generator_version: str | None = None
    generated_at: datetime | None = None
    study_role: str | None = None
    diagnostic_source_run_id: str | None = None
    method_comparison_id: str | None = None
    failure_inventory_fingerprint_sha256: str | None = None
    failure_inventory_release_id: str | None = None
    failure_inventory_defect_count: int | None = Field(default=None, ge=0)

class ExperimentCreate(BaseModel):
    creation_request_key: str | None = Field(default=None, min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
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
    shared_answer_source_run_id: str | None = Field(default=None, min_length=1, max_length=100)
    creation_request_key: str | None = Field(default=None, min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    conversation_id: str
    experiment_id: str | None = None
    target_configuration: TargetConfiguration
    provider: TargetProvider = TargetProvider.RULE_BASED
    model: str = "rule-based-target-ai"
    temperature: float = 0.0
    random_seed: int = 42
    test_budget: int = Field(default=8, ge=1, le=100)
    coverage_policy: CoveragePolicy = "strict_full_v1"
    prompt_template_version: str = "rule-based-v4"
    pipeline_provider: TargetProvider | None = None
    pipeline_model: str | None = None
    semantic_review_provider: TargetProvider | None = None
    semantic_review_model: str | None = Field(default=None, min_length=1, max_length=200)
    evaluator_provider: TargetProvider | None = None
    evaluator_model: str | None = None
    # Keep API callers and rule-based offline audits deterministic unless they
    # explicitly select the model-backed retrieval Agent. The guided UI sends
    # its selected mode and model as explicit fields.
    retrieval_mode: TargetMemoryRetrievalMode = TargetMemoryRetrievalMode.FIXED
    retrieval_provider: TargetProvider | None = None
    retrieval_model: str | None = Field(default=None, min_length=1, max_length=200)
    memory_strategy: MemoryStrategy | None = None
    memory_maintenance_policy: TargetMemoryMaintenancePolicy = TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION
    target_memory_capacity: int = Field(default=50, ge=1, le=500)
    # Omitted means use TARGET_MEMORY_WRITER only as an audit-creation default.
    # The selected value is persisted on the resulting AuditRun and is never
    # re-read from the environment during execution.
    target_memory_writer: TargetMemoryWriterKind | None = None
    target_system_adapter: TargetSystemAdapterKind = TargetSystemAdapterKind.CONTROLLED_MEMORY
    target_memory_profile: TargetMemoryProfile = Field(default_factory=TargetMemoryProfile)

    @model_validator(mode='after')
    def validate_answer_validation_target(self):
        if self.target_memory_profile.answer_validation != 'off':
            if self.target_system_adapter != TargetSystemAdapterKind.CONTROLLED_MEMORY:
                raise ValueError('Answer source validation requires the controlled memory target.')
            if self.provider != TargetProvider.OPENROUTER or self.model != 'openai/gpt-6-luna':
                raise ValueError('Answer source validation requires OpenRouter GPT 6 Luna.')
        return self


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
    coverage_policy: CoveragePolicy = "strict_full_v1"
    extraction_provenance: dict | None = None
    auditor_method: Literal["rules", "model_generation", "hybrid", "custom"] = "custom"
    auditor_comparison_id: str | None = None
    audit_runtime_signature: dict[str, str] | None = None
    configuration_fingerprint: str | None = None
    prompt_template_fingerprint: str | None = None
    target_memory_writer_version: str | None = None
    target_memory_writer: TargetMemoryWriterKind = TargetMemoryWriterKind.RULE_BASED
    target_system_adapter: TargetSystemAdapterKind = TargetSystemAdapterKind.CONTROLLED_MEMORY
    target_system_adapter_version: str | None = None
    intervention: str | None = None
    diagnostic_source_run_id: str | None = None
    diagnosis_note: str | None = None
    study_role: str | None = None
    validation_split: str | None = None
    human_validation: str | None = None
    memory_policy_version: str | None = None
    target_memory_profile: TargetMemoryProfile = Field(default_factory=TargetMemoryProfile)
    seed_control: dict[str, str] = Field(default_factory=dict)
    target_retry_policy: RetryPolicyMetadata = Field(default_factory=RetryPolicyMetadata)
    assessment_source_run_id: str | None = None
    assessment_input_signature: str | None = None
    assessment_copy_signature: str | None = None
    comparison_source_run_id: str | None = None
    comparison_input_signature: str | None = None
    generator_comparison_id: str | None = None
    generation_observations: list[dict] = Field(default_factory=list)
    shared_answer_source_run_id: str | None = None
    execution_budget: dict[str, int] = Field(default_factory=dict)
    ac3_staged_suite: dict | None = None
    ac3_paired_retest: dict | None = None


class SharedAnswerRequest(BaseModel):
    source_run_id: str = Field(min_length=1, max_length=100)


from pydantic import model_serializer
from app.schemas.request_contracts import OpenRouterRequestContract, HTTPRequestAttemptReceipt


class ExecutionMetadata(BaseModel):
    """Sanitised per-response facts; optional usage is provider supplied."""
    request_attempts: int = 0
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = Field(default=None, ge=0, le=10_000_000)
    reported_cost_usd: str | None = Field(default=None, max_length=64)
    sampling_control: str = 'unknown'
    sent_temperature: float | None = None
    reported_model: str | None = Field(default=None, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/+_-]*$")
    shared_source_run_id: str | None = None
    shared_source_response_id: str | None = None
    response_source: str = "unknown"
    completion_status: Literal["complete", "truncated"] | None = None
    finish_reason: str | None = Field(default=None, max_length=40)
    requested_output_token_limit: int | None = Field(default=None, ge=1, le=8192)
    memory_input: TargetMemoryInputEvidence | None = None
    identity_analysis: dict | None = None
    answer_validation: dict | None = None
    requested_reasoning_effort: Literal['low', 'medium'] | None = None
    request_contract: OpenRouterRequestContract | None = None
    request_contract_sha256: str | None = None
    request_contract_attempts: list[HTTPRequestAttemptReceipt] | None = None

    @model_serializer(mode='wrap')
    def _omit_missing_wire_metadata(self, handler):
        value = handler(self)
        for key in ('requested_reasoning_effort', 'request_contract', 'request_contract_sha256', 'request_contract_attempts', 'answer_validation'):
            if value.get(key) is None:
                value.pop(key, None)
        return value

class AuditRun(BaseModel):
    run_id: str; conversation_id: str; experiment_id: str | None = None; status: AuditStatus; target_configuration: TargetConfiguration; provider: TargetProvider
    model: str; temperature: float; random_seed: int; test_budget: int; prompt_template_version: str
    pipeline_provider: str = "rule_based"; pipeline_model: str = "rule-based-v2"
    semantic_review_provider: str | None = None; semantic_review_model: str | None = None
    evaluator_provider: str = "rule_based"; evaluator_model: str = "rule-based-v4"
    retrieval_mode: TargetMemoryRetrievalMode = TargetMemoryRetrievalMode.FIXED
    retrieval_provider: str | None = None; retrieval_model: str | None = None
    memory_strategy: MemoryStrategy = MemoryStrategy.STRONG_RULE_BASED
    memory_maintenance_policy: TargetMemoryMaintenancePolicy = TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION
    target_memory_capacity: int = 50
    target_memory_writer: TargetMemoryWriterKind = TargetMemoryWriterKind.RULE_BASED
    target_memory_writer_version: str | None = None
    target_system_adapter: TargetSystemAdapterKind = TargetSystemAdapterKind.CONTROLLED_MEMORY
    target_system_adapter_version: str | None = None
    reproducibility: ReproducibilityMetadata = Field(default_factory=ReproducibilityMetadata)
    target_memory_profile: TargetMemoryProfile = Field(default_factory=TargetMemoryProfile)
    created_at: datetime; completed_at: datetime | None = None
class TestCase(BaseModel):
    test_id: str; run_id: str; dimension: Dimension; prompt: str; expected_behavior: str
    supporting_memory_ids: list[str]; generator_version: str
    test_type: TestType = TestType.CONTEXTUAL
    quality_status: TestQualityStatus = TestQualityStatus.PENDING
    grounding_status: GroundingStatus = GroundingStatus.PENDING
    validation_notes: str | None = None
    human_validity_status: HumanValidityStatus = HumanValidityStatus.PENDING
    human_validity_reviewer: str | None = None
    human_validity_note: str | None = None
    human_validity_reviewed_at: datetime | None = None
    probe_group_id: str | None = None
    probe_variant: str | None = None
    # Private runtime memory supplied to the controlled target, not displayed in the UI.
    target_memory_context: list[str] = []
    target_identity_evidence: dict | None = None
    target_identity_failure_receipt: dict | None = None
class TestCasePublic(BaseModel):
    """Test data visible to clients; controlled-target context stays server-side."""
    test_id: str; run_id: str; dimension: Dimension; prompt: str; expected_behavior: str
    supporting_memory_ids: list[str]; generator_version: str
    test_type: TestType = TestType.CONTEXTUAL
    quality_status: TestQualityStatus = TestQualityStatus.PENDING
    grounding_status: GroundingStatus = GroundingStatus.PENDING
    validation_notes: str | None = None
    human_validity_status: HumanValidityStatus = HumanValidityStatus.PENDING
    human_validity_reviewer: str | None = None
    human_validity_note: str | None = None
    human_validity_reviewed_at: datetime | None = None
    probe_group_id: str | None = None
    probe_variant: str | None = None
class TestReviewUpdate(BaseModel):
    """A researcher decision on a generated test before target execution."""
    quality_status: TestQualityStatus
    note: str | None = Field(default=None, max_length=1000)
class HumanValidityReviewUpdate(BaseModel):
    """Self-declared researcher decision on a test's validity for Experiment A."""
    model_config = {'extra': 'forbid'}
    decision: Literal['accepted', 'rejected']
    reviewer_pseudonym: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode='after')
    def trim_reviewer_identity(self):
        self.reviewer_pseudonym = self.reviewer_pseudonym.strip()
        if not self.reviewer_pseudonym:
            raise ValueError('Enter the reviewer pseudonym used for this decision.')
        if self.note is not None:
            self.note = self.note.strip() or None
        return self
class TestDimensionCoverage(BaseModel):
    dimension: Dimension
    evidence_supported: bool | None = None
    reason: str
    planned_question_count: int = 0
    required_question_count: int = 0
    available_question_count: int = 0
    accepted_question_count: int = 0
class TestCoveragePreview(BaseModel):
    coverage_policy: CoveragePolicy = "strict_full_v1"
    planned_test_count: int | None = None
    requested_test_count: int
    minimum_met: bool
    dimensions: list[TestDimensionCoverage] = Field(default_factory=list)
class TestReviewSuite(BaseModel):
    coverage_policy: CoveragePolicy = "strict_full_v1"
    planned_test_count: int | None = None
    run_id: str
    canonical_run_id: str
    tests: list[TestCasePublic]
    requested_test_count: int | None = None
    generated_test_count: int | None = None
    count_target_met: bool | None = None
    quantity_shortfall_reason: str | None = None
    can_continue_generation: bool = False
    dimension_coverage: list[TestDimensionCoverage] = Field(default_factory=list)
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
class CancelledAuditEvidence(BaseModel):
    """Safe, terminal-only artifacts retained when an audit is cancelled."""
    audit: AuditRun
    completed_responses: list[TargetResponse] = Field(default_factory=list)
    trace: TargetMemoryTrace
class JudgeExecutionEvidence(BaseModel):
    """Sanitised HTTP-boundary observations; historical missing data stays unknown."""
    version: str = "judge-http-meter-v2"
    provider: str
    model: str
    reported_model: str | None = None
    agent_role: str = "blind_evaluation"
    prompt_template_version: str = "llm-judge-v1"
    prompt_fingerprint: str | None = None
    input_fingerprint: str | None = None
    request_attempts: int = Field(ge=0)
    failed_http_attempts: int = Field(ge=0)
    elapsed_ms: float = Field(ge=0)
    reported_input_tokens: int | None = Field(default=None, ge=0)
    reported_output_tokens: int | None = Field(default=None, ge=0)
    reported_total_tokens: int | None = Field(default=None, ge=0)
    reported_cost_credits: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    sampling_control: str = 'unknown'
    sent_temperature: float | None = None
    # Missing historical fields remain unknown; no provider cap is inferred.
    requested_output_token_limit: int | None = Field(default=None, ge=1)
    declared_output_token_limit: int | None = Field(default=None, ge=1)
    configured_output_token_cap: int | None = Field(default=None, ge=1)
    output_budget_status: Literal["configured", "provider_default", "invalid", "not_applicable"] | None = None
    completion_status: Literal["complete", "truncated"] | None = None
    finish_reason: str | None = Field(default=None, max_length=40)
    native_finish_reason: str | None = Field(default=None, max_length=40)
    usage_scope: str = "last successful provider reply only; failed-attempt usage unknown"
    verdict_status: str
    provider_verdict: bool | None = None
    rule_cross_check_verdict: bool | None = None
    cross_check_version: str | None = None


class FailureClassification(BaseModel):
    """Observed answer error, independent of the question's intended dimension."""
    status: Literal["classified", "unclassified", "legacy_test_dimension"] = "unclassified"
    method: str = "not_classified"
    reason: str = "The test dimension is not an observed failure diagnosis."


class EvaluationResult(BaseModel):
    evaluation_id: str; test_id: str; response_id: str; passed: bool | None; failure_type: Dimension | None = None
    reason: str; evidence_memory_ids: list[str]; evaluator: str
    judge_execution: JudgeExecutionEvidence | None = None
    failure_classification: FailureClassification = Field(default_factory=FailureClassification)
class EvaluationHumanReviewUpdate(BaseModel):
    """Human calibration label; keeps automated result immutable."""
    human_passed: bool
    human_failure_type: Dimension | None = None
    reviewer_label: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=1500)
    review_role: HumanReviewRole = HumanReviewRole.REFERENCE
    based_on_review_ids: list[str] = Field(default_factory=list, max_length=20)
    based_on_review_versions: dict[str, datetime] = Field(default_factory=dict, max_length=20)

    def model_post_init(self, __context):
        if not self.reviewer_label.strip():
            raise ValueError("Enter a non-blank reviewer pseudonym.")
        if self.human_passed and self.human_failure_type is not None:
            raise ValueError("A passing human verdict must not include a failure type.")
        if self.review_role == HumanReviewRole.INDEPENDENT and self.based_on_review_ids:
            raise ValueError("Independent reviews cannot cite other review labels.")
        if self.review_role == HumanReviewRole.ADJUDICATION and not self.based_on_review_ids:
            raise ValueError("An adjudication must cite the independent reviews it resolves.")
        if self.review_role == HumanReviewRole.ADJUDICATION and set(self.based_on_review_versions) != set(self.based_on_review_ids):
            raise ValueError("Refresh the review evidence before submitting a final decision; every cited review needs its saved version.")
        if self.review_role != HumanReviewRole.ADJUDICATION and self.based_on_review_versions:
            raise ValueError("Only final decisions may cite saved review versions.")

class EvaluationHumanReview(BaseModel):
    review_id: str
    evaluation_id: str
    human_passed: bool
    human_failure_type: Dimension | None = None
    reviewer_label: str
    review_role: HumanReviewRole = HumanReviewRole.REFERENCE
    based_on_review_ids: list[str] = Field(default_factory=list)
    note: str | None = None
    created_at: datetime
    updated_at: datetime

class EvaluationReviewItem(BaseModel):
    test: TestCasePublic
    response: TargetResponse
    automated: EvaluationResult
    human_review: EvaluationHumanReview | None = None
    human_reviews: list[EvaluationHumanReview] = Field(default_factory=list)
    independent_reviewer_count: int = Field(default=0, ge=0)

class EvaluationCalibrationSummary(BaseModel):
    run_id: str
    automated_failure_count: int
    human_reviewed_count: int
    agreement_count: int
    disagreement_count: int
    agreement_percentage: float | None = None
    failure_precision: float | None = None
    failure_recall: float | None = None
    failure_f1: float | None = None
    by_dimension: dict[str, dict[str, int]] = Field(default_factory=dict)
    independent_review_count: int = 0
    independently_reviewed_evaluation_count: int = 0
    independent_consensus_count: int = 0
    independent_conflict_count: int = 0
    independent_failure_category_compared_count: int = 0
    independent_failure_category_agreement_count: int = 0
    independent_failure_category_conflict_count: int = 0
    independent_failure_category_missing_count: int = 0
    independent_pair_count: int = 0
    independent_pair_agreement_percentage: float | None = None
    independent_pair_kappa: float | None = None
class DimensionScores(BaseModel):
    dimension: Dimension; percentage: float | None; passed: int; total: int
    uncertain_count: int = 0
    expected_tests: int = Field(default=0, ge=0)
    excluded_evidence_count: int = Field(default=0, ge=0)
class RetrievalQualityScores(BaseModel):
    """Source-evidence proxy metrics for the target's retrieval trace."""
    tests_measured: int = 0
    unlinked_attempts_excluded: int = 0
    evidence_recall_at_k: float | None = None
    evidence_precision_at_k: float | None = None
    update_evidence_recall: float | None = None
    conflict_evidence_coverage: float | None = None
    unnecessary_memory_retrieval_rate: float | None = None
class SourceStatement(BaseModel):
    role: str
    content: str
    timestamp: datetime

class AssessmentDetail(BaseModel):
    test: TestCasePublic; response: TargetResponse; evaluation: EvaluationResult; evidence: list[Memory]
    source_statements: list[SourceStatement] = Field(default_factory=list)
class FailureDetail(AssessmentDetail):
    failure_id: str
class AuditAnswerDetail(BaseModel):
    """One saved target response and its unique assessment, if available."""
    test: TestCasePublic
    response: TargetResponse
    outcome: Literal["pass", "fail", "uncertain", "unassessed"]
    evaluation: EvaluationResult | None = None
    reason: str | None = None
    evidence: list[Memory] = Field(default_factory=list)
    source_statements: list[SourceStatement] = Field(default_factory=list)
class AuditResult(BaseModel):
    run_id: str; overall_score: float | None; tests_passed: int; tests_total: int
    dimensions: list[DimensionScores]; failures: list[FailureDetail]
    answers: list[AuditAnswerDetail] = Field(default_factory=list)
    uncertain_count: int = 0
    uncertain_answers: list[AssessmentDetail] = Field(default_factory=list)
    evaluated_count: int = 0
    expected_tests: int | None = Field(default=None, ge=0)
    excluded_evidence_count: int = Field(default=0, ge=0)
    evaluation_warnings: list[str] = Field(default_factory=list)
    retrieval_quality: RetrievalQualityScores = Field(default_factory=RetrievalQualityScores)
    reproducibility: ReproducibilityMetadata = Field(default_factory=ReproducibilityMetadata)
    @computed_field
    @property
    def formal_overall_score(self) -> float | None:
        if self.excluded_evidence_count:
            return None
        scores = {item.dimension: item.percentage for item in self.dimensions}
        if set(scores) != set(Dimension) or any(value is None for value in scores.values()):
            return None
        return round(sum(scores.values()) / len(Dimension), 2)

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
    uncertain_count: int = 0
    excluded_evidence_count: int = 0
    expected_tests: int | None = None

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
    mean_latency_ms: float | None = None
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    total_tokens: int | None = None
    dimensions: list[ExperimentDimensionSummary] = []

class PairedComparison(BaseModel):
    """A per-run paired signal, aligned through the frozen source test IDs."""
    reference_run_id: str
    reference_label: str
    candidate_run_id: str
    candidate_label: str
    shared_tests: int
    excluded_assessment_count: int = Field(default=0, ge=0)
    shared_question_count: int | None = Field(default=None, ge=0)
    excluded_uncertain_count: int = Field(default=0, ge=0)
    both_passed: int
    both_failed: int
    reference_only_passed: int
    candidate_only_passed: int
    candidate_delta_percentage_points: float | None = None
    candidate_delta_confidence_interval_low: float | None = None
    candidate_delta_confidence_interval_high: float | None = None
    two_sided_sign_test_p_value: float | None = None

class ExperimentAnswerSourceEvidence(BaseModel):
    memory_id: str
    canonical_value: str
    source_message_ids: list[str] = Field(default_factory=list)

class ExperimentAnswerReport(BaseModel):
    """One uniquely paired saved question and response, optionally assessed."""
    run_id: str
    test_id: str
    response_id: str
    evaluation_id: str | None = None
    dimension: Dimension
    prompt: str
    expected_behavior: str
    answer: str
    outcome: Literal['pass', 'fail', 'uncertain', 'unassessed']
    observed_category: Dimension | None = None
    failure_classification: FailureClassification | None = None
    evaluation_reason: str | None = None
    supporting_memory_ids: list[str] = Field(default_factory=list)
    source_evidence: list[ExperimentAnswerSourceEvidence] = Field(default_factory=list)
    source_statements: list[SourceStatement] = Field(default_factory=list)

class ExperimentRunReport(BaseModel):
    run: AuditRun
    result: AuditResult | None = None
    answers: list[ExperimentAnswerReport] = Field(default_factory=list)

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
    default_pipeline_model: str | None = None
    default_evaluator_model: str | None = None
