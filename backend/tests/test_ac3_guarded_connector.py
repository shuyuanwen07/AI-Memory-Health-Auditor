"""Tests use the real request-contract path with an inert fake HTTP transport."""
from types import SimpleNamespace
from unittest.mock import patch
import httpx
import pytest
from app.schemas import TargetProvider
from app.services.ac3_guarded_connector import AC3DispatchBlocked, execute_through_blocked_ac3_bridge
from app.target_ai.openrouter import CHAT_COMPLETIONS_URL, build_openrouter_target_payload
from app.target_ai.providers import HttpTargetAIConnector, ProviderRequestError, single_attempt_target_request


def test_real_connector_post_is_vetoed_before_any_network_call():
    payload = build_openrouter_target_payload(model='openai/gpt-6-luna', instructions='fixture', prompt='fixture',
        temperature=0, max_output_tokens=100, provider_options={'require_parameters': True, 'allow_fallbacks': False})
    def adapter_execute(_self, _test, _audit):
        return HttpTargetAIConnector._post(CHAT_COMPLETIONS_URL, {'Authorization': 'fixture'}, payload)
    with patch.object(HttpTargetAIConnector, 'execute', adapter_execute), patch('app.target_ai.providers.httpx.post') as post:
        with pytest.raises(AC3DispatchBlocked, match='live execution is disabled'):
            execute_through_blocked_ac3_bridge(object(), SimpleNamespace(provider=TargetProvider.OPENROUTER))
        post.assert_not_called()


def test_other_providers_cannot_bypass_the_openrouter_veto():
    with patch.object(HttpTargetAIConnector, 'execute') as execute:
        with pytest.raises(AC3DispatchBlocked):
            execute_through_blocked_ac3_bridge(object(), SimpleNamespace(provider=TargetProvider.OLLAMA))
        execute.assert_not_called()


def test_scoped_attempt_limit_does_not_change_normal_retry_behavior():
    payload = build_openrouter_target_payload(model='openai/gpt-6-luna', instructions='fixture', prompt='fixture',
        temperature=0, max_output_tokens=100, provider_options={'require_parameters': True, 'allow_fallbacks': False})
    with patch('app.target_ai.providers.httpx.post', return_value=httpx.Response(503)) as post, patch('app.target_ai.providers.time.sleep'):
        with single_attempt_target_request():
            with pytest.raises(ProviderRequestError):
                HttpTargetAIConnector._post(CHAT_COMPLETIONS_URL, {}, payload)
        assert post.call_count == 1
        post.reset_mock()
        with pytest.raises(ProviderRequestError):
            HttpTargetAIConnector._post(CHAT_COMPLETIONS_URL, {}, payload)
        assert post.call_count == 3
