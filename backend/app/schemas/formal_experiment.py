"""Contracts for importing a *synthetic* frozen study into operational runs.

The normal research endpoints deliberately keep human labels request-scoped.
This contract is narrower: it permits only a dataset explicitly identified as
synthetic to become reproducible, executable audit records.  This makes the
boundary between a study harness and participant data explicit.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.annotation import AnnotationDataset
from app.schemas.domain import MemoryStrategy, TargetConfiguration, TargetProvider
from app.schemas.pilot import PilotAnnotationPackage
from app.schemas.research import annotation_fingerprint
from app.target_ai.openrouter import default_model


class FormalSuccessCriteria(BaseModel):
    """Pilot-selected percentages, required before collecting new results."""

    failure_detection_recall_min_percent: float = Field(ge=0, le=100)
    failure_classification_accuracy_min_percent: float = Field(ge=0, le=100)
    test_validity_min_percent: float = Field(ge=0, le=100)
    false_positive_rate_max_percent: float = Field(ge=0, le=100)


class FormalStudyDesign(BaseModel):
    """Predeclared analysis choices, not proof of execution or independence."""

    sampling_rule: str = Field(min_length=20, max_length=1000)
    primary_outcome: Literal['overall_memory_health', 'accuracy', 'freshness', 'conflict_resolution', 'appropriate_use']
    analysis_unit: Literal['source_history'] = 'source_history'
    incomplete_results: Literal['report_without_imputing_scores'] = 'report_without_imputing_scores'

    @field_validator('sampling_rule', mode='before')
    @classmethod
    def strip_sampling_rule(cls, value):
        return value.strip() if isinstance(value, str) else value


class FormalAcceptanceProtocol(BaseModel):
    format: str = "formal-acceptance-protocol-v1"
    # Older unplanned matrices are classified as exploratory when restored.
    study_mode: Literal["formal_experiment_b", "exploratory"] = "exploratory"
    frozen_at: datetime
    criteria: FormalSuccessCriteria
    dataset_fingerprint_sha256: str
    runtime_source_sha256: str
    development_dataset_fingerprint_sha256: str | None = None
    distinct_history_check: str = "not_checked"
    study_design: FormalStudyDesign | None = None
    notice: str = "Criteria were saved before these new runs. This does not verify independent labels or that earlier results were unseen."


class FormalMatrixCondition(BaseModel):
    """One controlled target condition repeated for every synthetic scenario."""

    label: str = Field(min_length=1, max_length=100)
    memory_strategy: MemoryStrategy
    provider: TargetProvider = TargetProvider.OPENROUTER
    model: str = Field(default_factory=default_model, min_length=1, max_length=100)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    @field_validator('model', 'label')
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('Provide a non-empty model name and condition label.')
        return value

    @property
    def identity(self) -> tuple[str, str, str, float]:
        return (self.memory_strategy.value, self.provider.value, self.model, self.temperature)

    @property
    def target_configuration(self) -> TargetConfiguration:
        return (
            TargetConfiguration.WEAK
            if self.memory_strategy == MemoryStrategy.WEAK_FIRST_HIT
            else TargetConfiguration.STRONG
        )


class SyntheticMatrixCreateRequest(BaseModel):
    """Shared input contract for explicitly formal or exploratory matrices."""

    dataset: AnnotationDataset
    pilot: PilotAnnotationPackage
    conditions: list[FormalMatrixCondition] = Field(min_length=2, max_length=8)
    random_seed: int = 42
    repetitions: int = Field(default=1, ge=1, le=5, strict=True)
    label_prefix: str = Field(default="Synthetic Pilot v2", min_length=1, max_length=100)
    synthetic_data_confirmation: bool
    success_criteria: FormalSuccessCriteria
    development_dataset: AnnotationDataset | None = None
    study_design: FormalStudyDesign | None = None

    @model_validator(mode="after")
    def is_a_safe_synthetic_matrix(self) -> "SyntheticMatrixCreateRequest":
        if not self.synthetic_data_confirmation:
            raise ValueError("Confirm that this is authorised synthetic data before creating operational audit records.")
        if "synthetic" not in self.dataset.data_origin.lower():
            raise ValueError("Only a dataset explicitly identified as synthetic may be imported into the formal matrix runner.")
        if (self.pilot.dataset_id, self.pilot.dataset_version) != (self.dataset.dataset_id, self.dataset.dataset_version):
            raise ValueError("The double-annotation pilot must refer to the selected dataset and version.")
        if self.pilot.dataset_fingerprint_sha256 != annotation_fingerprint(self.dataset):
            raise ValueError("The pilot must bind to the exact reviewed dataset content. "
                             "Validate the dataset and record its dataset_fingerprint_sha256 in the pilot "
                             "after reviewing that release. Changed data needs a newly reviewed pilot.")
        identities = [condition.identity for condition in self.conditions]
        if len(identities) != len(set(identities)):
            raise ValueError("Each strategy, service, model and temperature combination may appear only once. Different labels do not create different conditions.")
        if self.study_design is not None and self.development_dataset is None:
            raise ValueError("Provide the development dataset before freezing an analysis plan so history reuse can be checked.")
        if self.development_dataset is not None:
            development = history_fingerprints(self.development_dataset)
            formal = history_fingerprints(self.dataset)
            if len(formal) != len(set(formal)):
                raise ValueError("Formal scenarios contain duplicate conversation content. Use distinct histories before declaring a held-out comparison.")
            if set(formal) & set(development):
                raise ValueError("Formal and development datasets share conversation content, even if their IDs differ. Use new histories for the held-out comparison.")
        return self


class FormalMatrixCreateRequest(SyntheticMatrixCreateRequest):
    """Experiment B request: a frozen plan and repeated, paired Weak/Strong runs."""

    study_design: FormalStudyDesign
    repetitions: int = Field(default=3, ge=1, le=5, strict=True)

    @model_validator(mode="after")
    def is_a_frozen_experiment_b(self) -> "FormalMatrixCreateRequest":
        if self.development_dataset is None:
            raise ValueError("Provide the development dataset before freezing Experiment B so history reuse can be checked.")
        if self.repetitions < 3:
            raise ValueError("Formal Experiment B requires at least three repetitions per condition, including local Ollama and the deterministic baseline.")
        target_settings = {(condition.provider, condition.model, condition.temperature) for condition in self.conditions}
        strategies = {condition.memory_strategy for condition in self.conditions}
        required = {MemoryStrategy.WEAK_FIRST_HIT, MemoryStrategy.STRONG_RULE_BASED}
        if len(target_settings) != 1:
            raise ValueError("Experiment B must keep one target provider, model and temperature fixed; vary only the memory strategy.")
        if not required.issubset(strategies):
            raise ValueError("Experiment B needs both the predeclared Weak first-hit and Strong rule-based conditions.")
        return self


class ExploratoryMatrixCreateRequest(SyntheticMatrixCreateRequest):
    """Explicit non-formal route for small strategy/model engineering checks."""

    study_design: None = None


def history_fingerprints(dataset: AnnotationDataset) -> list[str]:
    """Ignore IDs/timestamps when detecting exact normalized history reuse.

    This cannot detect paraphrases or independently verify source provenance.
    Hash complete ordered role/content sequences, not isolated common messages.
    """
    def normalized(value: str) -> str:
        return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())
    return [hashlib.sha256(json.dumps(
        [(normalized(message.role), normalized(message.content)) for message in scenario.messages],
        ensure_ascii=False, separators=(',', ':'),
    ).encode('utf-8')).hexdigest() for scenario in dataset.conversations]


class FormalMatrixScenario(BaseModel):
    source_conversation_id: str
    experiment_id: str
    run_ids: list[str]
    test_count: int


class FormalMatrixCreateResponse(BaseModel):
    dataset_id: str
    dataset_version: str
    dataset_fingerprint_sha256: str
    pilot_id: str
    condition_count: int
    repetition_count: int = Field(default=1, ge=1, le=5)
    scenario_count: int
    total_audit_runs: int
    total_target_calls: int
    scenarios: list[FormalMatrixScenario]
    notice: str
    acceptance_protocol: FormalAcceptanceProtocol
