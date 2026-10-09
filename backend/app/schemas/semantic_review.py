"""Import contracts for external automated scoring; never human labels."""
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.schemas.benchmark import LiveBenchmarkResponse


class AutoevalLabel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    model: str = Field(min_length=1, max_length=160)
    label: StrictBool


class UpstreamEvaluationRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str = Field(min_length=1, max_length=200)
    hypothesis: str = Field(max_length=100_000)
    autoeval_label: AutoevalLabel


class SemanticReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: dict | list
    evidence: LiveBenchmarkResponse
    strategy: str = Field(min_length=1, max_length=100)
    evaluator_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    rows: list[UpstreamEvaluationRow] = Field(min_length=1, max_length=20)


class SemanticReviewedCase(BaseModel):
    case_id: str
    category: str
    question: str
    expected_answer: str
    response_text: str
    lexical_match: bool
    semantic_correct: bool | None


class SemanticSummary(BaseModel):
    category: str
    total: int
    reviewed: int
    correct: int
    percentage: float | None


class SemanticReviewReport(BaseModel):
    version: str
    run_id: str
    strategy: str
    source_fingerprint_sha256: str
    configuration_fingerprint_sha256: str
    evidence_fingerprint_sha256: str
    evaluation_fingerprint_sha256: str
    evaluator_revision: str
    evaluator_model: str
    total: int
    reviewed: int
    correct: int
    pending: int
    percentage: float | None
    lexical_disagreements: int
    cases: list[SemanticReviewedCase]
    categories: list[SemanticSummary]
    notice: str
