"""Offline checks for controlled target context and evaluator-data isolation."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas import (
    AuditRun,
    AuditStatus,
    Dimension,
    TargetConfiguration,
    TargetProvider,
    TestCase as DomainTestCase,
)
from app.target_ai.providers import HttpTargetAIConnector
from app.target_ai.rule_based import RuleBasedTargetAIConnector, private_context_instruction


def _audit(provider: TargetProvider, configuration: TargetConfiguration) -> AuditRun:
    return AuditRun(
        run_id="RUN-CONTEXT", conversation_id="C-CONTEXT", status=AuditStatus.CREATED,
        target_configuration=configuration, provider=provider, model="test-model", temperature=0.0,
        random_seed=42, test_budget=1, prompt_template_version="test-v1",
        created_at=datetime.now(timezone.utc),
    )


def _test_case() -> DomainTestCase:
    return DomainTestCase(
        test_id="T-CONTEXT", run_id="RUN-CONTEXT", dimension=Dimension.FRESHNESS,
        prompt="Which database should be used now?", supporting_memory_ids=["M1", "M2"],
        # This marker is deliberately never target-visible.
        expected_behavior="EVALUATOR_ONLY_SECRET: use PostgreSQL and explain the later update.",
        generator_version="test-v1",
        target_memory_context=[
            "The backend previously used MySQL.",
            "The backend now uses PostgreSQL.",
        ],
    )


@pytest.mark.parametrize("provider", [TargetProvider.OPENAI, TargetProvider.DEEPSEEK, TargetProvider.GEMINI])
def test_external_payload_never_contains_expected_behavior(monkeypatch, provider: TargetProvider):
    credential_name = {
        TargetProvider.OPENAI: "OPENAI_API_KEY",
        TargetProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
        TargetProvider.GEMINI: "GEMINI_API_KEY",
    }[provider]
    monkeypatch.setenv(credential_name, "test-key")
    captured: dict[str, object] = {}

    def fake_post(_url, _headers, payload):
        captured["payload"] = payload
        if provider == TargetProvider.OPENAI:
            return {"output_text": "target response"}
        if provider == TargetProvider.DEEPSEEK:
            return {"choices": [{"message": {"content": "target response"}}]}
        return {"candidates": [{"content": {"parts": [{"text": "target response"}]}}]}

    monkeypatch.setattr(HttpTargetAIConnector, "_post", staticmethod(fake_post))
    HttpTargetAIConnector().execute(_test_case(), _audit(provider, TargetConfiguration.STRONG))

    serialised = repr(captured["payload"])
    assert "EVALUATOR_ONLY_SECRET" not in serialised
    assert "use PostgreSQL and explain" not in serialised
    assert "The backend now uses PostgreSQL." in serialised


def test_strong_and_weak_contexts_are_isolated_and_have_distinct_policies():
    test = _test_case()
    strong = private_context_instruction(test, TargetConfiguration.STRONG)
    weak = private_context_instruction(test, TargetConfiguration.WEAK)

    assert "previously used MySQL" in strong
    assert "now uses PostgreSQL" in strong
    assert "now uses PostgreSQL" not in weak
    assert "Prefer an explicit later update" in strong
    assert "single retrieved record" in weak
    assert "Start with the concrete factual answer" in strong
    assert "EVALUATOR_ONLY_SECRET" not in strong
    assert "EVALUATOR_ONLY_SECRET" not in weak


def test_rule_based_target_uses_context_not_evaluator_expected_behavior():
    test = _test_case()
    weak = RuleBasedTargetAIConnector().execute(test, _audit(TargetProvider.RULE_BASED, TargetConfiguration.WEAK))
    strong = RuleBasedTargetAIConnector().execute(test, _audit(TargetProvider.RULE_BASED, TargetConfiguration.STRONG))

    assert "EVALUATOR_ONLY_SECRET" not in weak.response_text
    assert "EVALUATOR_ONLY_SECRET" not in strong.response_text
    assert "MySQL" in weak.response_text
    assert "PostgreSQL" in strong.response_text
    assert weak.response_text != strong.response_text
