"""Frozen, target-side configuration. Contains no audit reference answers."""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_serializer


class TargetMemoryProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(default="Original configuration", min_length=1, max_length=100)
    version: int = Field(default=1, ge=1)
    max_retrieved_records: int = Field(default=50, ge=1, le=500)
    context_character_budget: int = Field(default=16000, ge=100, le=100000)
    isolate_project_scope: bool = False
    prefer_current_state: bool = False
    # Explicit opt-ins keep historical frozen configurations reproducible.
    retain_assistant_history: bool = False
    retrieve_message_context: bool = False
    # A separately frozen retention choice; coverage is source diversity,
    # never evidence that two observations are the same entity/event.
    retention_policy: Literal["scope_recency", "source_coverage"] = "scope_recency"
    # An optional target-owned semantic pass, separately metered from answering.
    identity_analysis: Literal["off", "evidence_links"] = "off"
    identity_analysis_failure_policy: Literal["fail_closed", "continue_without_advisory"] = "fail_closed"
    identity_analysis_output_token_limit: int = Field(default=4096, ge=512, le=8192, strict=True)
    reasoning_effort: Literal["low", "medium"] | None = None
    identity_analysis_reasoning_effort: Literal["low"] | None = None
    # This is a target-side step over its own selected evidence and draft.
    # It never receives the Auditor's expected answer or reviewed memories.
    answer_validation: Literal["off", "source_grounding"] = "off"
    answer_validation_output_token_limit: int = Field(default=8192, ge=512, le=8192, strict=True)
    answer_validation_reasoning_effort: Literal["low", "medium"] | None = None

    @model_serializer(mode="wrap")
    def _omit_unrequested_reasoning(self, handler):
        value = handler(self)
        for key in ("reasoning_effort", "identity_analysis_reasoning_effort", "answer_validation_reasoning_effort"):
            if value.get(key) is None:
                value.pop(key, None)
        # Preserve the representation of historical configurations whose
        # retention policy was the original scope/recency default.
        if value.get("retention_policy") == "scope_recency":
            value.pop("retention_policy", None)
        # Older runs did not request this step. Preserve their representation
        # instead of retrospectively attributing a validation budget to them.
        if (self.answer_validation == "off"
                and self.answer_validation_output_token_limit == 8192
                and self.answer_validation_reasoning_effort is None):
            value.pop("answer_validation", None)
            value.pop("answer_validation_output_token_limit", None)
        return value

    additional_instructions: str = Field(default="", max_length=4000)
    # None keeps legacy records honest: no per-run output limit was frozen.
    output_token_limit: int | None = Field(default=None, ge=1, le=8192, strict=True)


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
