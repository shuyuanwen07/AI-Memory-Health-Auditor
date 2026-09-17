from datetime import datetime, timezone
from app.schemas import AuditRun, AuditStatus, Dimension, TargetConfiguration, TargetProvider, TestCase as DomainTestCase
import httpx
import pytest
from fastapi import HTTPException

from app.target_ai.providers import HttpTargetAIConnector, ProviderRequestError, configured

def run(provider: TargetProvider, model: str) -> AuditRun:
    return AuditRun(run_id="RUN1",conversation_id="C1",status=AuditStatus.CREATED,target_configuration=TargetConfiguration.STRONG,provider=provider,model=model,temperature=0.0,random_seed=42,test_budget=1,prompt_template_version="rule-based-v1",created_at=datetime.now(timezone.utc))

def test_external_provider_uses_backend_key_and_returns_response(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(HttpTargetAIConnector, "_post", staticmethod(lambda *_: {"output_text":"A response from the controlled target."}))
    test=DomainTestCase(test_id="T001",run_id="RUN1",dimension=Dimension.ACCURACY,prompt="Answer the test.",expected_behavior="State the fact.",supporting_memory_ids=["M001"],generator_version="rule-based-v1")
    response=HttpTargetAIConnector().execute(test, run(TargetProvider.OPENAI, "gpt-5.6-luna"))
    assert response.response_text == "A response from the controlled target."
    assert response.model == "gpt-5.6-luna"

def test_provider_is_not_ready_without_a_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert not configured(TargetProvider.GEMINI)
    assert configured(TargetProvider.RULE_BASED)


def test_ollama_uses_a_local_health_check_without_a_credential(monkeypatch):
    class ReadyResponse:
        is_success = True
    monkeypatch.setattr("app.target_ai.providers.httpx.get", lambda *_args, **_kwargs: ReadyResponse())
    assert configured(TargetProvider.OLLAMA)


def test_ollama_payload_and_response_are_normalised(monkeypatch):
    captured = {}
    def fake_post(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"message": {"content": "PostgreSQL is the current backend."}, "prompt_eval_count": 20, "eval_count": 7}
    monkeypatch.setattr(HttpTargetAIConnector, "_post", staticmethod(fake_post))
    test = DomainTestCase(test_id="T001", run_id="RUN1", dimension=Dimension.ACCURACY, prompt="Which database is current?", expected_behavior="Evaluator only.", supporting_memory_ids=["M001"], generator_version="rule-based-v1", target_memory_context=["The backend now uses PostgreSQL."])
    response = HttpTargetAIConnector().execute(test, run(TargetProvider.OLLAMA, "qwen3:1.7b"))
    assert captured["url"].endswith("/api/chat")
    assert captured["headers"] == {}
    assert captured["payload"]["model"] == "qwen3:1.7b"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["think"] is False
    assert "Evaluator only" not in repr(captured["payload"])
    assert response.response_text == "PostgreSQL is the current backend."
    assert response.execution_metadata.total_tokens == 27


def test_gemini_uses_a_header_for_credential_and_parses_response(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    captured = {}
    def fake_post(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"candidates": [{"content": {"parts": [{"text": "Gemini result"}]}}]}
    monkeypatch.setattr(HttpTargetAIConnector, "_post", staticmethod(fake_post))
    test = DomainTestCase(test_id="T001", run_id="RUN1", dimension=Dimension.ACCURACY, prompt="Answer.", expected_behavior="State a fact.", supporting_memory_ids=["M001"], generator_version="rule-based-v1")
    response = HttpTargetAIConnector().execute(test, run(TargetProvider.GEMINI, "gemini-2.5-flash-lite"))
    assert response.response_text == "Gemini result"
    assert "test-key" not in captured["url"]
    assert captured["headers"]["x-goog-api-key"] == "test-key"


def test_missing_credential_is_a_readable_error_without_secret(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    test = DomainTestCase(test_id="T001", run_id="RUN1", dimension=Dimension.ACCURACY, prompt="Answer.", expected_behavior="State a fact.", supporting_memory_ids=["M001"], generator_version="rule-based-v1")
    with pytest.raises(HTTPException) as exc_info:
        HttpTargetAIConnector().execute(test, run(TargetProvider.DEEPSEEK, "deepseek-flash"))
    assert exc_info.value.status_code == 503
    assert "DEEPSEEK_API_KEY" in exc_info.value.detail


def test_provider_error_does_not_expose_upstream_response_body(monkeypatch):
    class FakeResponse:
        is_success = False
        status_code = 401
    monkeypatch.setattr("app.target_ai.providers.httpx.post", lambda *_, **__: FakeResponse())
    with pytest.raises(ProviderRequestError) as exc_info:
        HttpTargetAIConnector._post("https://example.invalid", {}, {})
    assert "credential" in str(exc_info.value).lower()
    assert "secret" not in str(exc_info.value).lower()


def test_transport_failures_are_retried_then_sanitised(monkeypatch):
    attempts = []
    def fail(*_, **__):
        attempts.append(1)
        raise httpx.ConnectError("network is unavailable")
    monkeypatch.setattr("app.target_ai.providers.httpx.post", fail)
    monkeypatch.setattr("app.target_ai.providers.time.sleep", lambda _: None)
    with pytest.raises(ProviderRequestError) as exc_info:
        HttpTargetAIConnector._post("https://example.invalid", {}, {})
    assert len(attempts) == 3
    assert exc_info.value.status_code == 503
