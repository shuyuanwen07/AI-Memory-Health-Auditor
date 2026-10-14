"""Server-frozen execution plans; benchmark source stays request-scoped."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.benchmark import LiveBenchmarkRequest
from app.schemas.ranking_agreement import RepeatedRankingRequest


class PlannedRankingTrial(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    trial_id: str = Field(min_length=1, max_length=80)
    reference_run_id: str = Field(min_length=1, max_length=40)
    candidate_run_id: str = Field(min_length=1, max_length=40)


class BenchmarkPlanCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    benchmark: LiveBenchmarkRequest
    trials: list[PlannedRankingTrial] = Field(min_length=3, max_length=20)
    sampling_rule: str = Field(min_length=20, max_length=1000)
    evaluator_model: str = Field(min_length=1, max_length=160)
    evaluator_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    metadata_storage_authorised: bool = False

    @model_validator(mode='after')
    def unique_executions(self):
        ids = [t.trial_id for t in self.trials]
        runs = [r for t in self.trials for r in (t.reference_run_id, t.candidate_run_id)]
        if len(ids) != len(set(ids)) or len(runs) != len(set(runs)):
            raise ValueError('Every planned repeat needs unique trial and audit execution IDs.')
        if not self.sampling_rule.strip() or not self.evaluator_model.strip():
            raise ValueError('Provide a selection rule and evaluator identity before freezing the plan.')
        return self


class BenchmarkPlanResponse(BaseModel):
    plan_id: str
    created_at: datetime
    plan_fingerprint_sha256: str
    protocol: dict
    executions: dict
    notice: str


class PlannedBenchmarkRun(BaseModel):
    model_config = ConfigDict(extra='forbid')
    trial_id: str
    benchmark: LiveBenchmarkRequest


class PlannedRankingAnalysis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    analysis: RepeatedRankingRequest
