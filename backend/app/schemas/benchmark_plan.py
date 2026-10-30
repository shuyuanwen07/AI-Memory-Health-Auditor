"""Server-frozen execution plans; benchmark source stays request-scoped."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal
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


class BenchmarkHumanJudgment(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    strategy: str = Field(min_length=1, max_length=100)
    case_id: str = Field(min_length=1, max_length=200)
    verdict: Literal['pass', 'fail', 'uncertain']


class BenchmarkHumanReviewer(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    reviewer: str = Field(min_length=1, max_length=100)
    judgments: list[BenchmarkHumanJudgment] = Field(min_length=1, max_length=80)


class BenchmarkHumanReviewImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    evidence_fingerprint_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    independent_review_confirmed: Literal[True]
    reviewers: list[BenchmarkHumanReviewer] = Field(min_length=2, max_length=2)

    @model_validator(mode='after')
    def distinct(self):
        if self.reviewers[0].reviewer.casefold() == self.reviewers[1].reviewer.casefold():
            raise ValueError('Supply two distinct reviewer pseudonyms.')
        for reviewer in self.reviewers:
            keys = [(j.strategy, j.case_id) for j in reviewer.judgments]
            if len(keys) != len(set(keys)):
                raise ValueError('Each reviewer may judge a case once per strategy.')
        return self
