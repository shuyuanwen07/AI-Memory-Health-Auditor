"""Synthetic budget/wire tests; all HTTP is replaced and no model is called."""
from datetime import datetime, timezone
import json

import httpx
import pytest
from pydantic import ValidationError

from app.evaluator import llm_judge
from app.evaluator.llm_judge import LLMBehaviourEvaluator
from app.schemas import Dimension, EvaluationResult, JudgeExecutionEvidence, Memory, MemoryStatus, TargetResponse, TestCase


class FixedRule:
    VERSION = "synthetic-fixed-rule"

    def __init__(self, passed=True):
        self.passed = passed

    def evaluate(self, test, response, memories):
        return EvaluationResult(
            evaluation_id="E-BUDGET", test_id=test.test_id, response_id=response.response_id,
            passed=self.passed, reason="Synthetic rule cross-check.",
            evidence_memory_ids=["M-BUDGET"], evaluator=self.VERSION,
        )


@pytest.fixture(autouse=True)
def isolated_budget_environment(monkeypatch):
    monkeypatch.delenv("PIPELINE_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.delenv("OPENROUTER_PROVIDER", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-budget-key")

    def unexpected_http(*args, **kwargs):
        pytest.fail("Unexpected HTTP: every request in these tests must be fake.")

    monkeypatch.setattr(llm_judge.httpx, "post", unexpected_http)


def fixtures():
    test = TestCase(
        test_id="T-BUDGET", run_id="RUN-BUDGET", dimension=Dimension.ACCURACY,
        prompt="What language was recorded?", expected_behavior="Python.",
        supporting_memory_ids=["M-BUDGET"], generator_version="synthetic-budget",
    )
    response = TargetResponse(
        response_id="R-BUDGET", test_id=test.test_id, run_id=test.run_id,
        response_text="Python.", model="synthetic-target", temperature=0,
        created_at=datetime.now(timezone.utc),
    )
    memories = [Memory(
        memory_id="M-BUDGET", conversation_id="C-BUDGET",
        canonical_value="The recorded language is Python.", status=MemoryStatus.CONFIRMED,
    )]
    return test, response, memories


def fake_http(monkeypatch, *, status=200, finish_reason="stop", native_finish_reason=None, text=None):
    captured = []
    verdict = {
        "passed": True, "reason": "The supplied source says Python.",
        "evidence_memory_ids": ["M-BUDGET"], "failure_type": None,
        "classification_reason": "No failure category applies.",
    }

    serialized_verdict = json.dumps(verdict)

    def post(url, *, headers, json: dict, timeout):
        captured.append({"url": url, "payload": json, "timeout": timeout})
        return httpx.Response(status, json={
            "model": "openai/gpt-6-luna",
            "choices": [{"finish_reason": finish_reason, "native_finish_reason": native_finish_reason, "message": {
                "content": text if text is not None else serialized_verdict,
            }}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
        })

    monkeypatch.setattr(llm_judge.httpx, "post", post)
    return captured


def evaluator(*, fallback=None):
    return LLMBehaviourEvaluator("openrouter", model="openai/gpt-6-luna", fallback=fallback or FixedRule())


@pytest.mark.parametrize("cap", [256, 512, 8192, 12000])
def test_configured_budget_is_actual_payload_and_exported_execution(monkeypatch, cap):
    monkeypatch.setenv("PIPELINE_MAX_OUTPUT_TOKENS", str(cap))
    sent = fake_http(monkeypatch)
    result = evaluator().evaluate(*fixtures())
    assert result.passed is True
    assert len(sent) == 1 and sent[0]["payload"]["max_tokens"] == cap
    evidence = result.judge_execution
    assert evidence.version == "judge-http-meter-v5"
    assert evidence.requested_output_token_limit == cap
    assert evidence.configured_output_token_cap == cap
    assert evidence.declared_output_token_limit is None
    assert evidence.output_budget_status == "configured"
    assert evidence.request_attempts == 1
    assert sent[0]["payload"]["response_format"]["json_schema"]["strict"] is True
    assert "reasoning" not in sent[0]["payload"]
    exported = result.model_dump(mode="json")["judge_execution"]
    assert exported["requested_output_token_limit"] == cap
    assert exported["declared_output_token_limit"] is None
    assert exported["configured_output_token_cap"] == cap
    assert EvaluationResult.model_validate(result.model_dump(mode="json")).judge_execution == evidence


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_unconfigured_cap_preserves_provider_default_omission(monkeypatch, raw):
    if raw is not None:
        monkeypatch.setenv("PIPELINE_MAX_OUTPUT_TOKENS", raw)
    sent = fake_http(monkeypatch)
    result = evaluator().evaluate(*fixtures())
    assert result.passed is True and len(sent) == 1
    assert "max_tokens" not in sent[0]["payload"]
    assert result.judge_execution.output_budget_status == "provider_default"
    assert result.judge_execution.requested_output_token_limit is None
    assert result.judge_execution.declared_output_token_limit is None
    assert result.judge_execution.configured_output_token_cap is None


@pytest.mark.parametrize("raw", ["0", "255", "12001", "-1", "8192.0", "true", "８１９２", "Infinity", "8192 secret"])
def test_invalid_cap_abstains_before_credential_or_http(monkeypatch, raw):
    monkeypatch.setenv("PIPELINE_MAX_OUTPUT_TOKENS", raw)
    judge = evaluator()

    def no_credential():
        pytest.fail("Invalid budget must be rejected before credential lookup.")

    monkeypatch.setattr(judge, "_credential", no_credential)
    result = judge.evaluate(*fixtures())
    assert result.passed is None and result.evaluator.startswith("fallback-")
    assert result.judge_execution.output_budget_status == "invalid"
    assert result.judge_execution.verdict_status == "uncertain_fallback"
    assert result.judge_execution.request_attempts == 0
    assert result.judge_execution.requested_output_token_limit is None
    assert result.judge_execution.configured_output_token_cap is None
    assert raw not in result.reason


@pytest.mark.parametrize("failure", ["rejected", "malformed", "length"])
def test_provider_failure_retains_valid_budget_but_never_accepts_fallback(monkeypatch, failure):
    monkeypatch.setenv("PIPELINE_MAX_OUTPUT_TOKENS", "8192")
    sent = fake_http(monkeypatch, status=400 if failure == "rejected" else 200,
                     text="not JSON" if failure == "malformed" else None,
                     finish_reason="length" if failure == "length" else "stop")
    result = evaluator().evaluate(*fixtures())
    assert len(sent) == 1 and sent[0]["payload"]["max_tokens"] == 8192
    assert result.passed is None
    assert result.judge_execution.verdict_status == "uncertain_fallback"
    assert result.judge_execution.output_budget_status == "configured"
    assert result.judge_execution.requested_output_token_limit == 8192
    if failure == "length":
        assert result.judge_execution.completion_status == "truncated"
        assert result.judge_execution.finish_reason == "length"
        assert result.judge_execution.reported_output_tokens == 8
        assert result.judge_execution.request_attempts == 1


@pytest.mark.parametrize("field,reason", [
    ("finish_reason", "length"), ("finish_reason", "max_tokens"),
    ("finish_reason", "max_output_tokens"), ("finish_reason", "max_completion_tokens"),
    ("native_finish_reason", "MAX_TOKENS"), ("native_finish_reason", "length"),
])
def test_explicit_truncation_rejects_even_complete_valid_json_without_retry(monkeypatch, field, reason):
    monkeypatch.setenv("PIPELINE_MAX_OUTPUT_TOKENS", "8192")
    sent = fake_http(monkeypatch, **{field: reason})
    result = evaluator().evaluate(*fixtures())
    assert result.passed is None
    assert result.judge_execution.verdict_status == "uncertain_fallback"
    assert result.judge_execution.completion_status == "truncated"
    assert getattr(result.judge_execution, field) == reason
    assert result.judge_execution.reported_model == "openai/gpt-6-luna"
    assert result.judge_execution.reported_output_tokens == 8
    assert result.judge_execution.requested_output_token_limit == 8192
    assert result.judge_execution.request_attempts == len(sent) == 1


@pytest.mark.parametrize("reason", [None, "unrecognized_terminal", "unsafe upstream text with spaces"])
def test_unknown_completion_reason_is_not_invented_as_stop(monkeypatch, reason):
    sent = fake_http(monkeypatch, finish_reason=reason)
    result = evaluator().evaluate(*fixtures())
    # Preserve existing valid-JSON semantics for unknown finish metadata.
    assert result.passed is True and len(sent) == 1
    assert result.judge_execution.completion_status is None
    assert result.judge_execution.finish_reason == (reason if reason == "unrecognized_terminal" else None)


def test_budget_does_not_change_prompt_schema_or_disagreement_gate(monkeypatch):
    sent = fake_http(monkeypatch)
    judge = evaluator(fallback=FixedRule(False))
    unconfigured = judge.evaluate(*fixtures())
    monkeypatch.setenv("PIPELINE_MAX_OUTPUT_TOKENS", "8192")
    configured = judge.evaluate(*fixtures())
    assert unconfigured.passed is configured.passed is None
    assert unconfigured.judge_execution.verdict_status == configured.judge_execution.verdict_status == "review_disagreement"
    first, second = sent[0]["payload"], dict(sent[1]["payload"])
    assert second.pop("max_tokens") == 8192
    assert first == second
    assert unconfigured.judge_execution.prompt_fingerprint == configured.judge_execution.prompt_fingerprint
    assert "strong_rule_based" not in json.dumps(first) and "weak_first_hit" not in json.dumps(first)


def test_budget_context_does_not_leak_between_evaluations(monkeypatch):
    sent = fake_http(monkeypatch)
    judge = evaluator()
    monkeypatch.setenv("PIPELINE_MAX_OUTPUT_TOKENS", "invalid")
    assert judge.evaluate(*fixtures()).passed is None
    monkeypatch.setenv("PIPELINE_MAX_OUTPUT_TOKENS", "8192")
    second = judge.evaluate(*fixtures())
    monkeypatch.delenv("PIPELINE_MAX_OUTPUT_TOKENS")
    third = judge.evaluate(*fixtures())
    assert second.judge_execution.configured_output_token_cap == 8192
    assert third.judge_execution.configured_output_token_cap is None
    assert [row["payload"].get("max_tokens") for row in sent] == [8192, None]


def test_one_request_uses_same_preflight_snapshot_for_meter_and_payload(monkeypatch):
    sent = fake_http(monkeypatch)
    monkeypatch.setenv("PIPELINE_MAX_OUTPUT_TOKENS", "8192")
    judge = evaluator()

    def credential():
        monkeypatch.setenv("PIPELINE_MAX_OUTPUT_TOKENS", "512")
        return "synthetic-budget-key"

    monkeypatch.setattr(judge, "_credential", credential)
    result = judge.evaluate(*fixtures())
    assert sent[0]["payload"]["max_tokens"] == 8192
    assert result.judge_execution.configured_output_token_cap == 8192


def test_other_provider_payload_keeps_existing_budget_behavior(monkeypatch):
    monkeypatch.setenv("PIPELINE_MAX_OUTPUT_TOKENS", "invalid")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-key")
    sent = fake_http(monkeypatch)
    result = LLMBehaviourEvaluator("deepseek", model="synthetic-deepseek", fallback=FixedRule()).evaluate(*fixtures())
    assert result.passed is True
    assert "max_tokens" not in sent[0]["payload"]
    assert result.judge_execution.output_budget_status == "not_applicable"
    assert result.judge_execution.configured_output_token_cap is None


def test_old_evidence_never_acquires_current_environment_cap(monkeypatch):
    monkeypatch.setenv("PIPELINE_MAX_OUTPUT_TOKENS", "8192")
    old = {
        "version": "judge-http-meter-v3", "provider": "openrouter", "model": "old-model",
        "request_attempts": 1, "failed_http_attempts": 0, "elapsed_ms": 1,
        "verdict_status": "valid",
    }
    receipt = JudgeExecutionEvidence.model_validate(old)
    assert receipt.version == "judge-http-meter-v3"
    for field in ("requested_output_token_limit", "declared_output_token_limit", "configured_output_token_cap", "output_budget_status"):
        assert getattr(receipt, field) is None
        assert field not in receipt.model_dump(exclude_unset=True)
    assert receipt.completion_status is None
    assert receipt.finish_reason is None
    assert receipt.native_finish_reason is None


@pytest.mark.parametrize("field", ["requested_output_token_limit", "declared_output_token_limit", "configured_output_token_cap"])
def test_budget_evidence_rejects_nonpositive_values(field):
    with pytest.raises(ValidationError):
        JudgeExecutionEvidence.model_validate({
            "provider": "openrouter", "model": "synthetic", "request_attempts": 0,
            "failed_http_attempts": 0, "elapsed_ms": 0, "verdict_status": "uncertain_fallback", field: 0,
        })
