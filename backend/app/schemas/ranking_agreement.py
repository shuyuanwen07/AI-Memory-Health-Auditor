"""Experiment C compares policy ordering, never absolute scores across suites."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.benchmark import BenchmarkDatasetProvenance
from app.schemas.semantic_review import SemanticReviewRequest
from app.schemas.domain import Dimension


class RankingAgreementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference_run_id: str = Field(min_length=1, max_length=40)
    candidate_run_id: str = Field(min_length=1, max_length=40)
    reference_benchmark: SemanticReviewRequest
    candidate_benchmark: SemanticReviewRequest


class RankingDimensionResult(BaseModel):
    dimension: Dimension
    total: int
    reference_correct: int
    candidate_correct: int
    reference_percentage: float | None
    candidate_percentage: float | None


class RankingSuiteResult(BaseModel):
    label: str
    total: int
    reference_correct: int
    candidate_correct: int
    reference_percentage: float | None
    candidate_percentage: float | None
    score_basis: Literal["dimension_macro_average", "response_accuracy"] = "response_accuracy"
    dimensions: list[RankingDimensionResult] = Field(default_factory=list)
    ordering: Literal["reference_higher", "candidate_higher", "tie", "unmeasured"]


class RankingAgreementReport(BaseModel):
    version: str
    provider: str
    model: str
    reference_strategy: str
    candidate_strategy: str
    output_token_limit: int
    suites: list[RankingSuiteResult]
    agreement: Literal["consistent", "reversed", "both_tied", "inconclusive_tie", "inconclusive_missing_dimensions"]
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
    experiment_id: str
    audit_suite_fingerprint_sha256: str
    audit_configuration_fingerprint_sha256: str
    benchmark_configuration_fingerprint_sha256: str
    evaluator_model: str
    evaluator_revision: str
    notice: str


class RankingTrialInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trial_id: str = Field(min_length=1, max_length=80)
    comparison: RankingAgreementRequest | None = None
    unavailable_reason: str | None = Field(default=None, max_length=500)


class RepeatedRankingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    planned_trial_ids: list[str] = Field(min_length=3, max_length=20)
    trials: list[RankingTrialInput] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_trials_and_executions(self):
        planned = self.planned_trial_ids
        submitted = [trial.trial_id for trial in self.trials]
        if any(not item.strip() or len(item) > 80 for item in planned) or len(set(planned)) != len(planned):
            raise ValueError("Declare unique, non-empty planned trial IDs.")
        if len(set(submitted)) != len(submitted) or not set(submitted).issubset(planned):
            raise ValueError("Each submitted trial must appear once in the declared plan.")
        runs = [run for trial in self.trials if trial.comparison for run in
                (trial.comparison.reference_run_id, trial.comparison.candidate_run_id)]
        if len(runs) != len(set(runs)):
            raise ValueError("A saved audit execution cannot be counted as more than one repeated trial.")
        if any(trial.comparison and trial.unavailable_reason for trial in self.trials):
            raise ValueError("Supply comparison evidence or a missing-data reason, not both.")
        return self


class RankingTrialResult(BaseModel):
    trial_id: str
    status: Literal["measured", "unmeasured", "invalid", "missing"]
    reason: str | None = None
    reference_run_id: str | None = None
    candidate_run_id: str | None = None
    report: RankingAgreementReport | None = None


class RepeatedRankingSuite(BaseModel):
    label: str
    score_basis: Literal["dimension_macro_average", "response_accuracy"]
    measured_trials: int
    reference_mean_percentage: float | None
    candidate_mean_percentage: float | None
    reference_standard_deviation: float | None
    candidate_standard_deviation: float | None
    ordering: Literal["reference_higher", "candidate_higher", "tie", "unmeasured"]


class RepeatedRankingReport(BaseModel):
    version: str
    status: Literal["complete", "partial"]
    planned_trial_ids: list[str]
    plan_fingerprint_sha256: str
    plan_provenance: Literal["caller_declared_analysis_plan", "server_frozen_preexecution_plan"] = "caller_declared_analysis_plan"
    provider: str | None = None
    model: str | None = None
    reference_strategy: str | None = None
    candidate_strategy: str | None = None
    trials: list[RankingTrialResult]
    planned_trials: int
    measured_trials: int
    invalid_trials: int
    missing_trials: int
    unmeasured_trials: int
    directional_trials: int
    consistent_trials: int
    reversed_trials: int
    both_tied_trials: int
    inconclusive_tie_trials: int
    ranking_agreement_percentage: float | None
    suites: list[RepeatedRankingSuite]
    notice: str
