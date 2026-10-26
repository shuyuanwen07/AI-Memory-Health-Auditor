"""Offline transport and persistence checks for opt-in advisory rejection."""
import copy
import hashlib

import pytest
from sqlalchemy import select

from app.extraction.llm import PipelineLLMClient, PipelineRequestError, _PIPELINE_METER
from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer
from app.memory_agent.identity_failure import (
    build_identity_failure_receipt, identity_failure_receipt_sha256,
    recorded_identity_failure_matches, validate_identity_failure_receipt,
)
from app.models import AgentExecutionModel, TargetAgentMemoryModel
from app.schemas import TargetConfiguration
from app.schemas.domain import TestCasePublic
from app.schemas.target_profile import TargetMemoryProfile
from app.services.agent_trace import agent_execution_schema
from app.target_ai.providers import HttpTargetAIConnector
from app.target_ai.rule_based import memory_input_evidence, private_context_instruction
from test_target_identity_integration import setup_target


def install_failed_analysis(monkeypatch, *, kind="contract", alter=None):
    seen = {"analysis": [], "answer": [], "observations": []}
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-offline-only")
    monkeypatch.delenv("PIPELINE_MAX_OUTPUT_TOKENS", raising=False)
    original_analyze = TargetIdentityEvidenceAnalyzer.analyze

    def analyze(self, **request):
        try:
            return original_analyze(self, **request)
        finally:
            seen["observations"].append(copy.deepcopy(self.last_observation))

    def transport(self, **request):
        seen["analysis"].append(request)
        meter = _PIPELINE_METER.get()
        meter.update(last_http_status=200, reported_model=self.model,
                     request_attempts=1, failed_http_attempts=0,
                     reported_finish_reason="length" if kind == "length" else "stop",
                     response_choice_count=1, reported_input_tokens=100,
                     reported_output_tokens=50, reported_total_tokens=150)
        if alter:
            meter.update(alter)
        if kind == "length":
            raise PipelineRequestError("The configured pipeline model reached its output limit before completing the required result.")
        if kind == "network":
            raise RuntimeError("Synthetic transport failure")
        if kind == "oversize":
            return {"quotes": [], "mentions": [], "relations": [], "limitations": "No links proposed."}
        return {"quotes": [{"quote_id": "Q1", "record_index": 1,
                            "quote": "UNTRUSTED_INVALID_DRAFT_DO_NOT_FORWARD", "occurrence": 0}],
                "mentions": [], "relations": [], "limitations": "Rejected synthetic quote."}

    def answer(self, audit, case, instructions, credential):
        seen["answer"].append((case, instructions, audit.model, audit.target_memory_profile.output_token_limit))
        assert "UNTRUSTED_INVALID_DRAFT_DO_NOT_FORWARD" not in instructions
        return "The original records support likely overlap, with unresolved identity."

    monkeypatch.setattr(TargetIdentityEvidenceAnalyzer, "analyze", analyze)
    monkeypatch.setattr(PipelineLLMClient, "_complete_json", transport)
    monkeypatch.setattr(HttpTargetAIConnector, "_execute_provider", answer)
    return seen


def enable(audit):
    audit.target_memory_profile = audit.target_memory_profile.model_copy(update={
        "identity_analysis_failure_policy": "continue_without_advisory"})


@pytest.mark.parametrize("kind", ["contract", "length", "oversize"])
def test_opt_in_rejects_entire_advisory_preserves_failed_stage_and_calls_same_final_once(monkeypatch, kind):
    seen = install_failed_analysis(monkeypatch, kind=kind)
    if kind == "oversize":
        monkeypatch.setattr(TargetIdentityEvidenceAnalyzer, "MAX_ADVISORY_CHARACTERS", 1)
    db, audit, case, adapter = setup_target()
    enable(audit)
    before = [(r.id, r.canonical_value, r.lifecycle_state) for r in db.scalars(select(TargetAgentMemoryModel))]
    try:
        response = adapter.answer(case, audit)
        assert len(seen["analysis"]) == len(seen["answer"]) == 1
        private, instructions, model, cap = seen["answer"][0]
        assert model == audit.model and cap == 4096
        assert private.target_identity_evidence is None
        assert "AUXILIARY IDENTITY ANALYSIS NOT APPLIED" in instructions
        assert "UNTRUSTED ADVISORY JSON" not in instructions
        assert "only the original selected memory records" in instructions
        metadata = response.execution_metadata.identity_analysis
        assert metadata["status"] == "degraded_without_advisory"
        assert metadata["advisory_applied"] is False
        receipt = metadata["failure_receipt"]
        assert receipt == private.target_identity_failure_receipt
        assert receipt["reason"] == ("provider_output_truncated" if kind == "length" else "invalid_identity_contract")
        assert metadata["execution"] == seen["observations"][0]["execution"]
        digest = identity_failure_receipt_sha256(receipt)
        assert digest == metadata["failure_receipt_sha256"]
        assert digest == response.execution_metadata.memory_input.identity_failure_receipt_sha256
        assert response.execution_metadata.memory_input.identity_advisory_sha256 is None
        assert response.execution_metadata.memory_input.instruction_sha256 == hashlib.sha256(instructions.encode()).hexdigest()
        assert len(response.execution_metadata.memory_input.sent_memory_ids) == 2
        row = db.scalar(select(AgentExecutionModel))
        assert row.status == "failed" and row.output_data is None
        assert row.error_code == ("PipelineRequestError" if kind == "length" else "invalid_identity_contract")
        assert recorded_identity_failure_matches(receipt, agent_execution_schema(row))
        assert before == [(r.id, r.canonical_value, r.lifecycle_state) for r in db.scalars(select(TargetAgentMemoryModel))]
        observation = seen["observations"][0]
        assert validate_identity_failure_receipt(receipt, observation=observation,
            provider=audit.provider.value, model=audit.model, max_output_tokens=4096)
        assert "execution_id" not in receipt and "created_at" not in receipt
        assert "raw_model_draft" not in receipt
        if kind == "oversize":
            assert observation["error_diagnostics"]["reason_code"] == "advisory_budget_exceeded"
    finally:
        db.close()


def test_default_remains_fail_closed_even_with_fully_matching_http_receipt(monkeypatch):
    seen = install_failed_analysis(monkeypatch)
    db, audit, case, adapter = setup_target()
    try:
        assert TargetMemoryProfile().identity_analysis_failure_policy == "fail_closed"
        with pytest.raises(PipelineRequestError):
            adapter.answer(case, audit)
        assert len(seen["analysis"]) == 1 and seen["answer"] == []
        assert db.scalar(select(AgentExecutionModel)).status == "failed"
    finally:
        db.close()


@pytest.mark.parametrize("alter", [
    {"provider": "deepseek"}, {"model": "different/model"}, {"reported_model": "different/model"},
    {"agent_role": "other_role"}, {"last_http_status": 500}, {"last_http_status": None},
    {"requested_output_token_limit": 2048}, {"declared_output_token_limit": 2048},
    {"configured_output_token_cap": 2048}, {"request_attempts": 2}, {"failed_http_attempts": 1},
    {"prompt_fingerprint": "0" * 64}, {"input_fingerprint": "0" * 64},
    {"reported_finish_reason": "content_filter"}, {"completion_status": "truncated"},
    {"response_choice_count": 2}, {"response_choice_count": 0},
    {"response_choice_count": True}, {"response_choice_count": False},
    {"response_choice_count": None}, {"provider_error_scope": "choice"},
])
def test_mismatched_or_unknown_receipt_still_stops_before_final(monkeypatch, alter):
    seen = install_failed_analysis(monkeypatch, alter=alter)
    db, audit, case, adapter = setup_target()
    enable(audit)
    try:
        with pytest.raises(PipelineRequestError):
            adapter.answer(case, audit)
        assert seen["answer"] == []
        assert len(seen["analysis"]) == 1
    finally:
        db.close()


def test_unknown_network_failure_is_not_a_length_rejection(monkeypatch):
    seen = install_failed_analysis(monkeypatch, kind="network")
    db, audit, case, adapter = setup_target()
    enable(audit)
    try:
        with pytest.raises(RuntimeError, match="Synthetic"):
            adapter.answer(case, audit)
        assert seen["answer"] == []
    finally:
        db.close()


def test_input_validation_and_missing_persisted_stage_still_fail_closed(monkeypatch):
    seen = install_failed_analysis(monkeypatch)
    db, audit, case, adapter = setup_target()
    enable(audit)
    try:
        long_question = case.model_copy(update={"prompt": "How many events? " + "x" * 4000,
            "target_memory_context": ["I attended one recital.", "I attended another recital."]})
        with pytest.raises(PipelineRequestError):
            adapter._identity_evidence(long_question, audit)
        assert seen["analysis"] == []
        monkeypatch.setattr(adapter, "_record_identity_stage", lambda *args: None)
        with pytest.raises(PipelineRequestError):
            adapter.answer(case, audit)
        assert seen["answer"] == []
    finally:
        db.close()


@pytest.mark.parametrize("mode,weak", [("off", False), ("evidence_links", True)])
def test_incoming_failure_and_advisory_are_cleared_even_when_analysis_off(monkeypatch, mode, weak):
    seen = install_failed_analysis(monkeypatch)
    db, audit, case, adapter = setup_target(mode=mode, weak=weak)
    enable(audit)
    case.target_identity_failure_receipt = {"stale_condition": "UNTRUSTED_INVALID_DRAFT_DO_NOT_FORWARD"}
    try:
        response = adapter.answer(case, audit)
        private = seen["answer"][0][0]
        assert private.target_identity_failure_receipt is None and private.target_identity_evidence is None
        assert response.execution_metadata.memory_input.identity_failure_receipt_sha256 is None
        assert seen["analysis"] == []
        # Direct optional-analysis entry also clears both runtime fields.
        clean, _ = adapter._identity_evidence(case, audit)
        assert clean.target_identity_failure_receipt is None and clean.target_identity_evidence is None
    finally:
        db.close()


def test_receipt_hash_replays_stably_and_cannot_be_transplanted(monkeypatch):
    seen = install_failed_analysis(monkeypatch)
    db, audit, case, adapter = setup_target()
    enable(audit)
    try:
        first = adapter.answer(case, audit).execution_metadata.identity_analysis
        second = adapter.answer(case, audit).execution_metadata.identity_analysis
        assert first["execution_id"] != second["execution_id"]
        assert first["failure_receipt"] == second["failure_receipt"]
        assert first["failure_receipt_sha256"] == second["failure_receipt_sha256"]
        observation = seen["observations"][0]
        kwargs = {"observation": observation, "provider": audit.provider.value,
                  "model": audit.model, "max_output_tokens": 4096}
        assert build_identity_failure_receipt(**kwargs, question="How many different events?") is None
        assert build_identity_failure_receipt(**kwargs, context=["Changed memory."]) is None
        # Even a self-consistent receipt for an unsupported transport cannot
        # enable degradation; this implementation only supports OpenRouter.
        for provider in ("deepseek", "openai", "gemini", "ollama", "unknown"):
            unsupported = copy.deepcopy(observation)
            unsupported["provider"] = provider
            unsupported["execution"]["provider"] = provider
            assert build_identity_failure_receipt(**{**kwargs, "provider": provider,
                "observation": unsupported}) is None
        for missing in ("execution", "raw_input_payload", "raw_model_draft"):
            incomplete = copy.deepcopy(observation)
            incomplete.pop(missing)
            assert build_identity_failure_receipt(**{**kwargs, "observation": incomplete}) is None
        incomplete = copy.deepcopy(observation)
        incomplete["execution"].pop("response_choice_count")
        assert build_identity_failure_receipt(**{**kwargs, "observation": incomplete}) is None
        receipt = first["failure_receipt"]
        assert not validate_identity_failure_receipt({**receipt, "reason": "forged"}, **kwargs)
        row = db.scalar(select(AgentExecutionModel))
        saved = agent_execution_schema(row)
        assert not recorded_identity_failure_matches(receipt, {**saved, "execution_id": None})
        assert not recorded_identity_failure_matches(receipt, {**saved, "status": "completed"})
        assert not recorded_identity_failure_matches(receipt, {**saved, "prompt_fingerprint": "other"})
        public = TestCasePublic.model_validate(case.model_dump()).model_dump()
        assert "target_identity_failure_receipt" not in public
        failed_case = seen["answer"][0][0]
        weak = private_context_instruction(failed_case, TargetConfiguration.WEAK)
        assert "AUXILIARY IDENTITY ANALYSIS" not in weak
        assert memory_input_evidence(failed_case, TargetConfiguration.WEAK, weak).identity_failure_receipt_sha256 is None
    finally:
        db.close()


@pytest.mark.parametrize("configured_cap,allowed", [(2048, False), (4096, True), (8192, False)])
def test_actual_configured_pipeline_cap_must_match_the_frozen_auxiliary_cap(monkeypatch, configured_cap, allowed):
    seen = install_failed_analysis(monkeypatch)
    monkeypatch.setenv("PIPELINE_MAX_OUTPUT_TOKENS", str(configured_cap))
    db, audit, case, adapter = setup_target()
    enable(audit)
    try:
        if allowed:
            response = adapter.answer(case, audit)
            receipt = response.execution_metadata.identity_analysis["failure_receipt"]
            assert receipt["configured_output_token_cap"] == configured_cap
            assert receipt["requested_output_token_limit"] == 4096
            assert len(seen["answer"]) == 1
        else:
            with pytest.raises(PipelineRequestError):
                adapter.answer(case, audit)
            assert seen["answer"] == []
        assert len(seen["analysis"]) == 1
    finally:
        db.close()
