from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
"""Offline contracts: all OpenRouter network interactions are mocked."""
import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.evaluator.factory import configured_evaluator, get_behaviour_evaluator
from app.evaluator.llm_judge import LLMBehaviourEvaluator
from app.extraction.llm import PipelineLLMClient, PipelineRequestError, configured_pipeline_model
from app.schemas import AuditRun, AuditStatus, Dimension, Memory, MemoryStatus, TargetConfiguration, TargetProvider
from app.schemas import TestCase as Case
from app.target_ai.openrouter import CHAT_COMPLETIONS_URL, request_options
from app.target_ai.providers import HttpTargetAIConnector, configured


def make_case():
    return Case(test_id="T001", run_id="RUN1", dimension=Dimension.ACCURACY,
                prompt="Which database is current?", expected_behavior="EVALUATOR PRIVATE ANSWER",
                supporting_memory_ids=["M001"], generator_version="test",
                target_memory_context=["The database now uses PostgreSQL."])


def audit():
    return AuditRun(run_id="RUN1", conversation_id="C1", status=AuditStatus.CREATED,
                    target_configuration=TargetConfiguration.STRONG, provider=TargetProvider.OPENROUTER,
                    model="test/model", temperature=0, random_seed=42, test_budget=1,
                    prompt_template_version="test", created_at=datetime.now(timezone.utc))


def test_target_uses_openrouter_and_never_receives_expected_answer(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    captured = {}
    def post(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"choices": [{"message": {"content": "PostgreSQL"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}}
    monkeypatch.setattr(HttpTargetAIConnector, "_post", staticmethod(post))
    response = HttpTargetAIConnector().execute(make_case(), audit())
    assert captured["url"] == CHAT_COMPLETIONS_URL
    assert captured["headers"]["Authorization"] == "Bearer test-only-key"
    assert captured["payload"]["model"] == "test/model"
    assert "PostgreSQL" in captured["payload"]["messages"][0]["content"]
    assert "EVALUATOR PRIVATE ANSWER" not in repr(captured["payload"])
    assert response.response_text == "PostgreSQL"
    assert response.execution_metadata.total_tokens == 15
    assert response.execution_metadata.response_source == "openrouter"


def test_missing_key_is_not_configured_and_target_fails_clearly(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert not configured(TargetProvider.OPENROUTER)
    with pytest.raises(HTTPException) as error:
        HttpTargetAIConnector().execute(make_case(), audit())
    assert error.value.status_code == 503
    assert "OPENROUTER_API_KEY" in error.value.detail


def test_pipeline_uses_strict_schema_and_validates_json(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    captured = {}
    def post(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"choices": [{"message": {"content": '{"value":"PostgreSQL"}'}}]}
    monkeypatch.setattr(PipelineLLMClient, "_post", staticmethod(post))
    client = PipelineLLMClient("openrouter", "test/model")
    result = client.complete_json(instructions="Return JSON.", prompt="Extract.",
                                  schema_name="memory", schema={"type": "object"})
    assert result == {"value": "PostgreSQL"}
    assert captured["url"] == CHAT_COMPLETIONS_URL
    assert captured["payload"]["response_format"]["json_schema"]["strict"] is True
    assert captured["payload"]["provider"]["require_parameters"] is True
    monkeypatch.setattr(PipelineLLMClient, "_post", staticmethod(lambda *_: {
        "choices": [{"message": {"content": "not JSON"}}]}))
    with pytest.raises(PipelineRequestError):
        client.complete_json(instructions="Return JSON.", prompt="Extract.", schema_name="memory", schema={})


def test_judge_uses_openrouter_and_rejects_untrusted_evidence(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    response = HttpTargetAIConnector()
    monkeypatch.setattr(response, "_execute_provider", lambda *_: "PostgreSQL")
    answer = response.execute(make_case(), audit())
    captured = {}
    def post(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"choices": [{"message": {"content": json.dumps({
            "passed": True, "reason": "Matches evidence.", "evidence_memory_ids": ["M001"]})}}]}
    monkeypatch.setattr(LLMBehaviourEvaluator, "_post", staticmethod(post))
    memories = [Memory(memory_id="M001", conversation_id="C1", canonical_value="PostgreSQL", status=MemoryStatus.CONFIRMED)]
    judge = get_behaviour_evaluator("openrouter", "test/judge")
    result = judge.evaluate(make_case(), answer, memories)
    assert result.evaluator == "llm-judge-openrouter-v4"
    assert captured["url"] == CHAT_COMPLETIONS_URL
    assert captured["payload"]["response_format"]["json_schema"]["strict"] is True
    monkeypatch.setattr(LLMBehaviourEvaluator, "_post", staticmethod(lambda *_: {
        "choices": [{"message": {"content": json.dumps({
            "passed": True, "reason": "Unsupported.", "evidence_memory_ids": ["UNKNOWN"]})}}]}))
    assert judge.evaluate(make_case(), answer, memories).evaluator == f"fallback-{RuleBasedBehaviourEvaluator.VERSION}"


def test_config_and_provider_pinning(monkeypatch):
    monkeypatch.setenv("PIPELINE_PROVIDER", "openrouter")
    monkeypatch.setenv("PIPELINE_MODEL", "test/extractor")
    monkeypatch.setenv("EVALUATOR_PROVIDER", "openrouter")
    monkeypatch.setenv("EVALUATOR_MODEL", "test/judge")
    monkeypatch.setenv("OPENROUTER_PROVIDER", "test-provider")
    assert configured_pipeline_model() == "test/extractor"
    assert configured_evaluator() == ("openrouter", "test/judge")
    assert request_options()["provider"] == {
        "only": ["test-provider"], "allow_fallbacks": False, "require_parameters": True}
