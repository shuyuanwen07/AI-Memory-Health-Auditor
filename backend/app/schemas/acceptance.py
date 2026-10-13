"""Threshold arithmetic against a server-saved protocol, not research certification."""
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.formal_experiment import FormalAcceptanceProtocol
from app.schemas.research import ResearchValidityRequest, ResearchValidityReport


class AcceptanceCheckRequest(ResearchValidityRequest):
    frozen_run_id: str = Field(min_length=1, max_length=100)


class AcceptanceMeasure(BaseModel):
    key: str
    label: str
    direction: Literal['minimum', 'maximum']
    threshold_percent: float
    numerator: int
    denominator: int
    observed_percent: float | None
    status: Literal['meets_threshold', 'threshold_not_met', 'insufficient_evidence']
    definition: str
    reason: str


class SavedEvidenceBinding(BaseModel):
    status: Literal['verified', 'incomplete']
    condition_label: str
    reference_cases: int
    matched: int
    missing: int
    mismatched: int
    ambiguous: int
    receipt_sha256: str
    notice: str = 'Exact saved-answer and automated-verdict matches do not verify independent human labels.'


class AcceptanceCheckReport(BaseModel):
    format: str = 'supplied-evidence-threshold-check-v2'
    protocol: FormalAcceptanceProtocol
    metrics: ResearchValidityReport
    measures: list[AcceptanceMeasure]
    all_thresholds_met: bool
    saved_evidence_binding: SavedEvidenceBinding | None = None
    saved_result_thresholds_met: bool = False
    notice: str = ('This checks supplied labels and predictions against server-saved thresholds. '
                   'It does not verify their authorship, independence, held-out status, or mapping to this run’s saved answers. '
                   'Meeting these thresholds does not certify the experiment or proposal as complete.')


class SavedReviewCoverage(BaseModel):
    expected_tests: int
    saved_answers: int
    resolved_labels: int
    missing_labels: int
    ambiguous_tests: int
    independently_adjudicated: int
    failure_categories_missing: int


class ReviewedSavedAcceptanceReport(BaseModel):
    format: str = 'reviewed-saved-threshold-check-v1'
    protocol: FormalAcceptanceProtocol
    measures: list[AcceptanceMeasure]
    all_thresholds_met: bool
    saved_result_thresholds_met: bool
    review_coverage: SavedReviewCoverage
    receipt_sha256: str
    notice: str = ('These calculations use resolved labels attached to the selected run’s actual saved answers, '
                   'not the frozen corpus’s example responses. Distinct reviewer pseudonyms and adjudication '
                   'measure the recorded review process, not verified human identity or independence. '
                   'Numerical success does not certify held-out validity or the full proposal.')


class SavedFormalRunOption(BaseModel):
    run_id: str
    study_mode: Literal['formal_experiment_b', 'exploratory'] = 'exploratory'
    provider: str
    model: str
    memory_strategy: str
    created_at: str
    status: str
    has_frozen_criteria: bool
    repetition_index: int | None = Field(default=None, ge=1, le=5)
    repetition_count: int | None = Field(default=None, ge=1, le=5)


class SavedFormalRunPage(BaseModel):
    items: list[SavedFormalRunOption]
    total: int
    offset: int
    limit: int
