"""Contracts for importing a *synthetic* frozen study into operational runs.

The normal research endpoints deliberately keep human labels request-scoped.
This contract is narrower: it permits only a dataset explicitly identified as
synthetic to become reproducible, executable audit records.  This makes the
boundary between a study harness and participant data explicit.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.schemas.annotation import AnnotationDataset
from app.schemas.domain import MemoryStrategy, TargetConfiguration, TargetProvider
from app.schemas.pilot import PilotAnnotationPackage


class FormalMatrixCondition(BaseModel):
    """One controlled target condition repeated for every synthetic scenario."""

    label: str = Field(min_length=1, max_length=100)
    memory_strategy: MemoryStrategy
    provider: TargetProvider = TargetProvider.OLLAMA
    model: str = Field(default="qwen3:1.7b", min_length=1, max_length=100)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    @property
    def target_configuration(self) -> TargetConfiguration:
        return (
            TargetConfiguration.WEAK
            if self.memory_strategy == MemoryStrategy.WEAK_FIRST_HIT
            else TargetConfiguration.STRONG
        )


class FormalMatrixCreateRequest(BaseModel):
    """Authorised request to materialise a frozen synthetic experiment matrix."""

    dataset: AnnotationDataset
    pilot: PilotAnnotationPackage
    conditions: list[FormalMatrixCondition] = Field(min_length=2, max_length=8)
    random_seed: int = 42
    label_prefix: str = Field(default="Synthetic Pilot v2", min_length=1, max_length=100)
    synthetic_data_confirmation: bool

    @model_validator(mode="after")
    def is_a_safe_fair_matrix(self) -> "FormalMatrixCreateRequest":
        if not self.synthetic_data_confirmation:
            raise ValueError("Confirm that this is authorised synthetic data before creating operational audit records.")
        if "synthetic" not in self.dataset.data_origin.lower():
            raise ValueError("Only a dataset explicitly identified as synthetic may be imported into the formal matrix runner.")
        if (self.pilot.dataset_id, self.pilot.dataset_version) != (self.dataset.dataset_id, self.dataset.dataset_version):
            raise ValueError("The double-annotation pilot must refer to the selected dataset and version.")
        strategies = [condition.memory_strategy for condition in self.conditions]
        if len(strategies) != len(set(strategies)):
            raise ValueError("Each memory strategy may appear only once in a formal matrix.")
        return self


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
    scenario_count: int
    total_audit_runs: int
    total_target_calls: int
    scenarios: list[FormalMatrixScenario]
    notice: str
