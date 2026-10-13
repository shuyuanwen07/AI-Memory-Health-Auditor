"""Experiment C compares policy ordering, never absolute scores across suites."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.benchmark import BenchmarkDatasetProvenance
from app.schemas.semantic_review import SemanticReviewRequest


class RankingAgreementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference_run_id: str = Field(min_length=1, max_length=40)
    candidate_run_id: str = Field(min_length=1, max_length=40)
    reference_benchmark: SemanticReviewRequest
    candidate_benchmark: SemanticReviewRequest


class RankingSuiteResult(BaseModel):
    label: str
    total: int
    reference_correct: int
    candidate_correct: int
    reference_percentage: float
    candidate_percentage: float
    ordering: Literal["reference_higher", "candidate_higher", "tie"]


class RankingAgreementReport(BaseModel):
    version: str
    provider: str
    model: str
    reference_strategy: str
    candidate_strategy: str
    output_token_limit: int
    suites: list[RankingSuiteResult]
    agreement: Literal["consistent", "reversed", "both_tied", "inconclusive_tie"]
    reference_run_id: str
    candidate_run_id: str
    dataset_provenance: BenchmarkDatasetProvenance
    source_fingerprint_sha256: str
    adapter_version: str
    adapter_fingerprint_sha256: str
    compatibility_limitations: list[str]
    benchmark_evidence_fingerprint_sha256: str
    reference_evaluation_fingerprint_sha256: str
    candidate_evaluation_fingerprint_sha256: str
    notice: str
