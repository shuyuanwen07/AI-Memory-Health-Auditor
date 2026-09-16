"""Contract tests for provider-backed extraction and behavioural test generation.

Every provider interaction is mocked: these tests verify request shape and
local validation without spending tokens or requiring credentials.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.extraction.factory import get_memory_extractor
from app.extraction.llm import PipelineLLMClient, PipelineRequestError
from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.schemas import (
    AuditRun, AuditStatus, Conversation, ConversationMessage, Dimension, Memory,
    MemoryStatus, TargetConfiguration, TargetProvider,
)
from app.test_generator.factory import get_test_generator
from app.test_generator.rule_based import RuleBasedTestGenerator


def _conversation() -> Conversation:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Conversation(
        conversation_id="C001", created_at=now, authorised=True,
        messages=[ConversationMessage(message_id="MSG001", role="user", content="I now use PostgreSQL.", timestamp=now)],
    )


def _audit() -> AuditRun:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return AuditRun(
        run_id="RUN001", conversation_id="C001", status=AuditStatus.CREATED,
        target_configuration=TargetConfiguration.STRONG, provider=TargetProvider.RULE_BASED,
        model="rule-based-target-ai", temperature=0, random_seed=42, test_budget=4,
        prompt_template_version="v1", created_at=now,
    )


def test_pipeline_factories_default_to_rule_based(monkeypatch):
    monkeypatch.delenv("PIPELINE_PROVIDER", raising=False)
    assert isinstance(get_memory_extractor(), RuleBasedMemoryExtractor)
    assert isinstance(get_test_generator(), RuleBasedTestGenerator)


def test_openai_extractor_uses_strict_json_and_validates_memories(monkeypatch):
    monkeypatch.setenv("PIPELINE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-secret")
    captured = {}

    def fake_post(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"output_text": json.dumps({"memories": [{
            "memory_id": "M001", "canonical_value": "The user now uses PostgreSQL.",
            "source_message_ids": ["MSG001"], "timestamp": "2026-01-01T00:00:00Z", "relationships": [],
        }]})}

    monkeypatch.setattr(PipelineLLMClient, "_post", staticmethod(fake_post))
    memories = get_memory_extractor().extract(_conversation())

    assert memories[0].memory_id == "M001"
    assert memories[0].status == MemoryStatus.CANDIDATE
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer unit-test-secret"
    assert captured["payload"]["text"]["format"]["strict"] is True
    assert captured["payload"]["text"]["format"]["type"] == "json_schema"


def test_llm_extractor_rejects_untrusted_message_reference(monkeypatch):
    monkeypatch.setenv("PIPELINE_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-secret")
    monkeypatch.setattr(PipelineLLMClient, "_post", staticmethod(lambda *_: {
        "candidates": [{"content": {"parts": [{"text": json.dumps({"memories": [{
            "memory_id": "M001", "canonical_value": "A fact", "source_message_ids": ["NOT-A-MESSAGE"], "relationships": [],
        }]})}]}}]
    }))
    with pytest.raises(PipelineRequestError) as exc_info:
        get_memory_extractor().extract(_conversation())
    assert exc_info.value.status_code == 502
    assert "authorised conversation" in exc_info.value.detail
    assert "unit-test-secret" not in exc_info.value.detail


def test_deepseek_generator_uses_json_mode_and_rejects_answer_leakage(monkeypatch):
    monkeypatch.setenv("PIPELINE_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "unit-test-secret")
    captured = {}
    memory = Memory(memory_id="M001", conversation_id="C001", canonical_value="The user is based in Sydney.",
                    status=MemoryStatus.CONFIRMED, source_message_ids=["MSG001"])

    def fake_post(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"choices": [{"message": {"content": json.dumps({"tests": [{
            "dimension": "accuracy", "prompt": "What city is recorded as the user's location?",
            "expected_behavior": "State that the user is based in Sydney.", "supporting_memory_ids": ["M001"],
        }]})}}]}

    monkeypatch.setattr(PipelineLLMClient, "_post", staticmethod(fake_post))
    tests = get_test_generator().generate([memory], _audit())
    assert tests[0].dimension == Dimension.ACCURACY
    assert tests[0].generator_version == "llm-structured-v1"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["payload"]["response_format"] == {"type": "json_object"}

    def leaked_post(*_):
        return {"choices": [{"message": {"content": json.dumps({"tests": [{
            "dimension": "accuracy", "prompt": "Is the user based in Sydney?", "expected_behavior": "Answer yes.",
            "supporting_memory_ids": ["M001"],
        }]})}}]}

    monkeypatch.setattr(PipelineLLMClient, "_post", staticmethod(leaked_post))
    with pytest.raises(PipelineRequestError, match="leaked"):
        get_test_generator().generate([memory], _audit())


def test_invalid_pipeline_provider_and_missing_key_are_sanitised(monkeypatch):
    monkeypatch.setenv("PIPELINE_PROVIDER", "not-a-provider")
    with pytest.raises(PipelineRequestError, match="PIPELINE_PROVIDER"):
        get_memory_extractor()

    monkeypatch.setenv("PIPELINE_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Construction is intentionally lazy; the missing credential surfaces only
    # when an audit actually requests provider work.
    with pytest.raises(PipelineRequestError) as exc_info:
        get_memory_extractor().extract(_conversation())
    assert exc_info.value.status_code == 503
    assert "OPENAI_API_KEY" in exc_info.value.detail
