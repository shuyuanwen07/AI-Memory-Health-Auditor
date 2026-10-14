"""Provider failures remain failures even with HTTP200 and parseable content."""
import httpx
import pytest

from app.target_ai.openrouter import completion_error, CHAT_COMPLETIONS_URL
from app.target_ai.providers import HttpTargetAIConnector, ProviderRequestError
from app.extraction.llm import PipelineLLMClient, PipelineRequestError
from app.evaluator.llm_judge import LLMBehaviourEvaluator, LLMJudgeRequestError


ENVELOPES = [
    ({'error': {'code': 402, 'message': 'synthetic-secret raw error'}}, 'top_level', 402),
    ({'choices': [{'error': {'code': 429, 'message': 'synthetic-secret'}, 'message': {'content': '{}'}}]}, 'choice', 429),
    ({'choices': [{'finish_reason': 'error', 'message': {'content': '{}'}}]}, 'finish_reason', 502),
]


@pytest.mark.parametrize('data,scope,status', ENVELOPES)
def test_safe_completion_error_classifier(data, scope, status):
    assert completion_error(data) == {'provider_error_scope': scope, 'provider_error_status': status}
    assert 'synthetic-secret' not in str(completion_error(data))


@pytest.mark.parametrize('code', [True, 'synthetic-secret', -1, 9999, {'secret': 'synthetic-secret'}])
def test_unrecognised_provider_codes_stay_safe(code):
    assert completion_error({'error': {'code': code}})['provider_error_status'] == 502


def test_null_error_and_normal_completion_are_not_failures():
    assert completion_error({'error': None, 'choices': [{'finish_reason': 'stop', 'message': {'content': '{}'}}]}) is None


@pytest.mark.parametrize('data,scope,status', ENVELOPES)
def test_pipeline_rejects_envelope_and_retains_safe_error_scope(monkeypatch, data, scope, status):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-secret')
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        return httpx.Response(200, json=data)
    monkeypatch.setattr('app.extraction.llm.httpx.post', post)
    client = PipelineLLMClient('openrouter', 'synthetic-model')
    with pytest.raises(PipelineRequestError) as error:
        client.complete_json(instructions='Return JSON.', prompt='Synthetic input.', schema_name='fixture', schema={'type': 'object'})
    assert error.value.status_code == status
    assert client.last_execution['provider_error_scope'] == scope
    assert client.last_execution['provider_error_status'] == status
    assert client.last_execution['last_http_status'] == 200
    assert len(calls) == 1
    assert 'synthetic-secret' not in str(client.last_execution)
    assert 'synthetic-secret' not in error.value.detail


@pytest.mark.parametrize('data,scope,status', ENVELOPES)
def test_target_and_judge_never_accept_error_envelopes(monkeypatch, data, scope, status):
    monkeypatch.setattr('app.target_ai.providers.httpx.post', lambda *args, **kwargs: httpx.Response(200, json=data))
    with pytest.raises(ProviderRequestError) as target_error:
        HttpTargetAIConnector._post(CHAT_COMPLETIONS_URL, {}, {})
    assert target_error.value.status_code == status
    assert 'synthetic-secret' not in str(target_error.value)
    with pytest.raises(LLMJudgeRequestError) as judge_error:
        LLMBehaviourEvaluator._post(CHAT_COMPLETIONS_URL, {}, {})
    assert 'synthetic-secret' not in str(judge_error.value)
