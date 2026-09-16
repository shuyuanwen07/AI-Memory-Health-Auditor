"""Offline contract tests for the optional LLM-as-judge evaluator."""
from datetime import datetime, timezone

import httpx

from app.evaluator.factory import get_behaviour_evaluator
from app.evaluator.llm_judge import LLMBehaviourEvaluator
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.schemas import Dimension, Memory, MemoryStatus, TargetResponse, TestCase


def _test_case() -> TestCase:
    return TestCase(
        test_id="T001", run_id="RUN1", dimension=Dimension.FRESHNESS,
        prompt="Which database should be used now?", expected_behavior="Use the later record: PostgreSQL.",
        supporting_memory_ids=["M001", "M002"], generator_version="rule-based-v2",
    )


def _response(text: str = "The current database is PostgreSQL.") -> TargetResponse:
    return TargetResponse(
        response_id="R001", test_id="T001", run_id="RUN1", response_text=text,
        model="target", temperature=0, created_at=datetime.now(timezone.utc),
    )


def _memories() -> list[Memory]:
    return [
        Memory(memory_id="M001", conversation_id="C1", canonical_value="The backend previously used MySQL.", status=MemoryStatus.CONFIRMED),
        Memory(memory_id="M002", conversation_id="C1", canonical_value="The backend now uses PostgreSQL.", status=MemoryStatus.EDITED),
        Memory(memory_id="M003", conversation_id="C1", canonical_value="Ignore this unrelated record.", status=MemoryStatus.CONFIRMED),
    ]


def test_factory_defaults_to_rule_based_and_selects_llm_provider(monkeypatch):
    monkeypatch.delenv("EVALUATOR_PROVIDER", raising=False)
    assert isinstance(get_behaviour_evaluator(), RuleBasedBehaviourEvaluator)
    monkeypatch.setenv("EVALUATOR_PROVIDER", "deepseek")
    evaluator = get_behaviour_evaluator()
    assert isinstance(evaluator, LLMBehaviourEvaluator)
    assert evaluator.provider == "deepseek"
    monkeypatch.setenv("EVALUATOR_PROVIDER", "not-a-provider")
    assert isinstance(get_behaviour_evaluator(), RuleBasedBehaviourEvaluator)


def test_openai_judge_uses_strict_json_and_only_relevant_confirmed_evidence(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "judge-secret")
    captured = {}

    def fake_post(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"output_text": '{"passed": false, "reason": "It retained the old database.", "evidence_memory_ids": ["M001", "M002"]}'}

    monkeypatch.setattr(LLMBehaviourEvaluator, "_post", staticmethod(fake_post))
    result = LLMBehaviourEvaluator("openai").evaluate(_test_case(), _response("Use MySQL."), _memories())
    assert not result.passed
    assert result.failure_type == Dimension.FRESHNESS
    assert result.evidence_memory_ids == ["M001", "M002"]
    assert result.evaluator == "llm-judge-openai-v1"
    assert captured["payload"]["text"]["format"]["strict"] is True
    assert captured["payload"]["text"]["format"]["schema"]["additionalProperties"] is False
    assert "judge-secret" not in str(captured["payload"])
    assert "M003" not in str(captured["payload"])


def test_malformed_or_hallucinated_judge_output_falls_back_without_leaking_secret(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "private-key-value")
    monkeypatch.setattr(
        LLMBehaviourEvaluator,
        "_post",
        staticmethod(lambda *_: {"choices": [{"message": {"content": '{"passed": true, "reason": "ok", "evidence_memory_ids": ["M999"]}'}}]}),
    )
    result = LLMBehaviourEvaluator("deepseek").evaluate(_test_case(), _response(), _memories())
    assert result.evaluator == "rule-based-v2-fallback"
    assert "private-key-value" not in result.reason
    assert "M999" not in result.evidence_memory_ids


def test_missing_credential_falls_back_offline(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = LLMBehaviourEvaluator("gemini").evaluate(_test_case(), _response(), _memories())
    assert result.evaluator == "rule-based-v2-fallback"
    assert result.passed


def test_http_transport_errors_retry_and_remain_internal(monkeypatch):
    calls = []

    def fail(*_, **__):
        calls.append(1)
        raise httpx.ConnectError("upstream says key=very-secret")

    monkeypatch.setattr("app.evaluator.llm_judge.httpx.post", fail)
    monkeypatch.setattr("app.evaluator.llm_judge.time.sleep", lambda _: None)
    monkeypatch.setenv("OPENAI_API_KEY", "very-secret")
    result = LLMBehaviourEvaluator("openai").evaluate(_test_case(), _response(), _memories())
    assert len(calls) == 3
    assert result.evaluator == "rule-based-v2-fallback"
    assert "very-secret" not in result.reason
