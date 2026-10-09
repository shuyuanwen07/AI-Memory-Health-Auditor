"""Frozen, target-side configuration. Contains no audit reference answers."""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class TargetMemoryProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(default="Original configuration", min_length=1, max_length=100)
    version: int = Field(default=1, ge=1)
    max_retrieved_records: int = Field(default=50, ge=1, le=500)
    context_character_budget: int = Field(default=16000, ge=100, le=100000)
    isolate_project_scope: bool = False
    prefer_current_state: bool = False
    additional_instructions: str = Field(default="", max_length=4000)


class RepairExperimentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targeted_profile: TargetMemoryProfile
    targeted_memory_strategy: Literal['no_memory', 'full_context', 'weak_first_hit', 'strong_rule_based', 'strong_score_based', 'scope_aware', 'temporal_importance'] | None = None
    targeted_memory_capacity: int | None = Field(default=None, ge=1, le=500, strict=True)
    diagnosis_note: str = Field(min_length=10, max_length=2000)
    validation_conversation_id: str | None = Field(default=None, min_length=1, max_length=40)


class FollowUpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    test_budget: int = Field(default=4, ge=1, le=12)
