"""Portable benchmark case contracts, intentionally independent of source data."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict

from app.schemas.domain import Dimension, MemoryStrategy, TargetProvider, ExecutionMetadata
from app.schemas.target_profile import TargetMemoryProfile


class BenchmarkMessage(BaseModel):
    message_id: str
    role: str
    content: str = Field(min_length=1)
    timestamp: datetime
    source_session_id: str | None = None
    timestamp_basis: str = "message_or_deterministic_fallback"


class LongMemEvalCase(BaseModel):
    case_id: str
    question: str = Field(min_length=1)
    expected_answer: str = Field(min_length=1)
    messages: list[BenchmarkMessage] = Field(min_length=1)
    category: str
    dimension_hint: str | None = None
    source_metadata: dict = Field(default_factory=dict)
    question_timestamp: datetime | None = None


class LongMemEvalImportRequest(BaseModel):
    """Raw JSON from a locally obtained, licence-compliant source file."""

    payload: dict | list


class LongMemEvalImportReport(BaseModel):
    adapter_version: str
    cases_imported: int
    case_ids: list[str]
    dimension_hints: list[str]
    source_format: str
    notice: str


class LongMemEvalValidationResponse(BaseModel):
    report: LongMemEvalImportReport
    # Small metadata previews, not full source conversations.
    cases: list[LongMemEvalCase]


class LongMemEvalRunRequest(BaseModel):
    """One local, ephemeral benchmark execution request.

    The Auditor intentionally does not bundle, download, or retain benchmark
    records.  The caller is therefore required to explicitly confirm that the
    locally supplied source may be processed for this research run.
    """

    payload: dict | list
    source_authorised: bool = False
    source_label: str | None = Field(default=None, max_length=160)
    memory_strategy: MemoryStrategy = MemoryStrategy.STRONG_RULE_BASED
    random_seed: int = 42


class BenchmarkMemoryEvidence(BaseModel):
    """One private-memory candidate considered by the deterministic runner."""

    memory_id: str
    canonical_value: str
    write_order: int
    lifecycle_state: str
    relevance_score: float
    policy_score: float
    memory_scope: str | None = None
    scope_score: float = 0.0
    # ``temporal_importance`` uses only the record's normalised write order,
    # not an audit-time clock.  Other policies expose the same values to keep
    # comparisons traceable.
    relative_chronology: float = 0.0
    chronology_basis: str = "sequential_message_order"
    recency_factor: float = 0.0
    importance_factor: float | None = None
    importance_components: list[str] = Field(default_factory=list)
    temporal_importance_score: float | None = None
    selected: bool
    reason: str


class LongMemEvalCaseRunResult(BaseModel):
    case_id: str
    category: str
    dimension: Dimension | None = None
    question: str
    expected_answer: str
    response_text: str
    passed: bool
    evaluation_reason: str
    ingested_memory_count: int
    retrieved_memory_ids: list[str] = Field(default_factory=list)
    retrieval_evidence: list[BenchmarkMemoryEvidence] = Field(default_factory=list)
    token_f1: float = 0.0
    latency_ms: float = 0.0


class BenchmarkScoreSummary(BaseModel):
    """A measured bucket; percentage is ``None`` when it has no cases."""

    key: str
    passed: int
    total: int
    percentage: float | None = None


class LongMemEvalRunMetadata(BaseModel):
    run_id: str
    runner_version: str
    adapter_version: str
    source_fingerprint_sha256: str
    source_format: str
    source_label: str | None = None
    random_seed: int
    memory_strategy: MemoryStrategy
    execution_mode: str
    evaluator: str
    case_order: list[str]
    notice: str


class LongMemEvalRunResponse(BaseModel):
    """An ephemeral, deterministic local benchmark result.

    These scores are explicitly *not* official LongMemEval results.  They
    evaluate the selected local memory-policy baseline with the compact local
    answer matcher documented in the response metadata.
    """

    metadata: LongMemEvalRunMetadata
    cases: list[LongMemEvalCaseRunResult]
    categories: list[BenchmarkScoreSummary]
    dimensions: list[BenchmarkScoreSummary]
    tests_passed: int
    tests_total: int
    overall_percentage: float | None = None
    mean_token_f1: float | None = None
    mean_latency_ms: float | None = None


# LoCoMo and BEAM are externally maintained datasets.  These contracts are a
# deliberately small local compatibility boundary; they do not claim complete
# parser coverage or reproduce an upstream scorer.
class LocalCompatibleImportRequest(BaseModel):
    """Caller-supplied JSON for a permitted local LoCoMo/BEAM-style source."""
    payload: dict | list


class LocalCompatibleRunRequest(LocalCompatibleImportRequest):
    source_authorised: bool = False
    source_label: str | None = Field(default=None, max_length=160)
    memory_strategy: MemoryStrategy = MemoryStrategy.STRONG_RULE_BASED
    random_seed: int = 42


class LocalCompatibleImportReport(BaseModel):
    benchmark_family: str
    adapter_version: str
    cases_imported: int
    case_ids: list[str]
    dimension_hints: list[str]
    source_format: str
    notice: str


class LocalCompatibleValidationResponse(BaseModel):
    report: LocalCompatibleImportReport
    cases: list[LongMemEvalCase]


class LocalCompatibleRunMetadata(BaseModel):
    benchmark_family: str
    run_id: str
    runner_version: str
    adapter_version: str
    source_fingerprint_sha256: str
    source_format: str
    source_label: str | None = None
    random_seed: int
    memory_strategy: MemoryStrategy
    execution_mode: str
    evaluator: str
    case_order: list[str]
    notice: str


class LocalCompatibleRunResponse(BaseModel):
    """Ephemeral local results, never an official LoCoMo or BEAM score."""
    metadata: LocalCompatibleRunMetadata
    cases: list[LongMemEvalCaseRunResult]
    categories: list[BenchmarkScoreSummary]
    dimensions: list[BenchmarkScoreSummary]
    tests_passed: int
    tests_total: int
    overall_percentage: float | None = None
    mean_token_f1: float | None = None
    mean_latency_ms: float | None = None


class LiveBenchmarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload: dict | list
    source_authorised: bool = False
    source_label: str | None = Field(default=None, max_length=160)
    random_seed: int = 42
    provider: TargetProvider = TargetProvider.OLLAMA
    model: str = Field(default="qwen3:1.7b", min_length=1, max_length=100)
    strategies: list[MemoryStrategy] = Field(default_factory=lambda: [MemoryStrategy.WEAK_FIRST_HIT, MemoryStrategy.SCOPE_AWARE], min_length=1, max_length=4)
    temperature: float = Field(default=0, ge=0, le=2)
    target_memory_capacity: int = Field(default=50, ge=1, le=500)
    target_memory_profile: TargetMemoryProfile = Field(default_factory=TargetMemoryProfile)
    max_cases: int = Field(default=8, ge=1, le=20)
    include_mem0: bool = False
    native_repair_comparison: bool = False


class LiveBenchmarkCaseResult(BaseModel):
    case_id: str
    category: str
    question: str
    expected_answer: str
    response_text: str
    lexical_match: bool
    token_f1: float
    execution_metadata: ExecutionMetadata
    retrieved_memory_ids: list[str]
    supplied_memory_ids: list[str]
    stored_memory_count: int
    retained_memory_count: int
    message_count: int
    assistant_message_count: int
    memory_evidence: list[dict] = Field(default_factory=list)
    ranking_evidence: list[dict] = Field(default_factory=list)
    memory_preparation: dict = Field(default_factory=dict)
    intervention: dict = Field(default_factory=dict)


class LiveBenchmarkCondition(BaseModel):
    strategy: str
    cases: list[LiveBenchmarkCaseResult]
    lexical_matches: int
    total: int
    percentage: float


class LiveBenchmarkResponse(BaseModel):
    run_id: str
    source_fingerprint_sha256: str
    configuration_fingerprint_sha256: str
    runner_version: str
    adapter_version: str
    target_adapter_version: str
    writer_version: str
    reader_configuration: str = "strong"
    provider: TargetProvider
    model: str
    temperature: float
    seed_control: str
    target_memory_capacity: int
    target_memory_profile: TargetMemoryProfile
    conditions: list[LiveBenchmarkCondition]
    notice: str
