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
from app.target_ai.openrouter import CHAT_COMPLETIONS_URL, request_options, sampling_parameters
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
    client.complete_json(instructions="Return JSON.", prompt="Synthetic availability check.",
        schema_name="availability_check", schema={"type":"object"}, max_output_tokens=64)
    assert captured["payload"]["max_tokens"] == 64
    monkeypatch.setattr(PipelineLLMClient, "_post", staticmethod(lambda *_: {
        "choices": [{"message": {"content": "not JSON"}}]}))
    with pytest.raises(PipelineRequestError):
        client.complete_json(instructions="Return JSON.", prompt="Extract.", schema_name="memory", schema={})


def test_reasoning_model_sampling_is_model_controlled_and_other_families_keep_fixed_temperature():
    for model in ('openai/gpt-5.6', 'openai/gpt-5.6-pro', 'openai/gpt-6.1-sol', 'openai/gpt-6-astra'):
        assert sampling_parameters(model, 0) == {}
    assert sampling_parameters('anthropic/claude-opus-5.5', 0) == {'temperature': 0}
    assert sampling_parameters('google/gemini-3.1-flash', 0) == {'temperature': 0}


def test_judge_uses_openrouter_and_rejects_untrusted_evidence(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    response = HttpTargetAIConnector()
    monkeypatch.setattr(response, "_execute_provider", lambda *_: "PostgreSQL")
    answer = response.execute(make_case(), audit())
    captured = {}
    def post(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"choices": [{"message": {"content": json.dumps({
            "failure_type": None, "classification_reason": "No observed error.", "passed": True, "reason": "Matches evidence.", "evidence_memory_ids": ["M001"]})}}]}
    monkeypatch.setattr(LLMBehaviourEvaluator, "_post", staticmethod(post))
    memories = [Memory(memory_id="M001", conversation_id="C1", canonical_value="PostgreSQL", status=MemoryStatus.CONFIRMED)]
    judge = get_behaviour_evaluator("openrouter", "test/judge")
    result = judge.evaluate(make_case(), answer, memories)
    assert result.evaluator == "llm-judge-openrouter-v6"
    assert captured["url"] == CHAT_COMPLETIONS_URL
    assert captured["payload"]["response_format"]["json_schema"]["strict"] is True
    monkeypatch.setattr(LLMBehaviourEvaluator, "_post", staticmethod(lambda *_: {
        "choices": [{"message": {"content": json.dumps({
            "failure_type": None, "classification_reason": "No observed error.", "passed": True, "reason": "Unsupported.", "evidence_memory_ids": ["UNKNOWN"]})}}]}))
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

@pytest.mark.parametrize('provider,key,path',[
    (TargetProvider.OPENROUTER,'OPENROUTER_API_KEY',('max_tokens',)),
    (TargetProvider.OLLAMA,None,('options','num_predict')),
    (TargetProvider.OPENAI,'OPENAI_API_KEY',('max_output_tokens',)),
    (TargetProvider.DEEPSEEK,'DEEPSEEK_API_KEY',('max_tokens',)),
    (TargetProvider.GEMINI,'GEMINI_API_KEY',('generationConfig','maxOutputTokens')),
])
def test_frozen_output_limit_reaches_provider_request_and_receipt(monkeypatch,provider,key,path):
    from app.schemas.target_profile import TargetMemoryProfile
    if key:
        monkeypatch.setenv(key,'test-only-key')
    monkeypatch.setenv('OLLAMA_NUM_PREDICT','7')
    captured={}
    def post(url,headers,payload):
        captured.update(payload)
        return {'message':{'content':'PostgreSQL'},'choices':[{'message':{'content':'PostgreSQL'}}],
                'output_text':'PostgreSQL','candidates':[{'content':{'parts':[{'text':'PostgreSQL'}]}}]}
    monkeypatch.setattr(HttpTargetAIConnector,'_post',staticmethod(post))
    run=audit().model_copy(update={'provider':provider,'target_memory_profile':TargetMemoryProfile(output_token_limit=768)})
    response=HttpTargetAIConnector().execute(make_case(),run)
    value=captured
    for item in path:
        value=value[item]
    assert value==768
    assert response.execution_metadata.requested_output_token_limit==768
    assert 'EVALUATOR PRIVATE ANSWER' not in repr(captured)


def test_legacy_cloud_record_does_not_invent_an_output_limit(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','test-only-key')
    captured={}
    def post(url,headers,payload):
        captured.update(payload)
        return {'choices':[{'message':{'content':'PostgreSQL'}}]}
    monkeypatch.setattr(HttpTargetAIConnector,'_post',staticmethod(post))
    response=HttpTargetAIConnector().execute(make_case(),audit())
    assert 'max_tokens' not in captured
    assert response.execution_metadata.requested_output_token_limit is None
