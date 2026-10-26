"""Shared backend-only OpenRouter request configuration."""
import os
import re
from collections.abc import Mapping

CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


def completion_error(data: Mapping) -> dict | None:
    """Recognise failed completion envelopes without retaining provider text."""
    choices = data.get('choices')
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], Mapping) else {}
    error = data.get('error')
    scope = 'top_level' if error is not None else None
    if scope is None and choice.get('error') is not None:
        error, scope = choice['error'], 'choice'
    if scope is None and choice.get('finish_reason') == 'error':
        scope = 'finish_reason'
    if scope is None:
        return None
    code = error.get('code') if isinstance(error, Mapping) else None
    status = code if type(code) is int and 400 <= code <= 599 else 502
    result = {'provider_error_scope': scope, 'provider_error_status': status}
    message = error.get('message') if isinstance(error, Mapping) else None
    if status == 502 and isinstance(message, str):
        lowered = message.lower()
        if 'peak load' in lowered and ('maximum usage size' in lowered or 'high demand' in lowered):
            result['provider_error_category'] = 'capacity_limit'
    return result


def sampling_parameters(model: str, temperature: float) -> dict:
    # Reasoning-family requests use model-controlled sampling. Requiring an
    # unsupported temperature can exclude otherwise callable provider routes.
    if re.match(r'^openai/gpt-(?:5\.6|6(?:\.\d+)?)(?:-|:|$)',model):
        return {}
    return {'temperature':temperature}


def default_model() -> str:
    return os.getenv("OPENROUTER_DEFAULT_MODEL", "").strip() or "openai/gpt-6-luna"


def request_options() -> dict:
    # Never silently switch models. Optionally pin an upstream provider too.
    provider: dict = {"require_parameters": True, "allow_fallbacks": False}
    upstream = os.getenv("OPENROUTER_PROVIDER", "").strip()
    if upstream:
        provider["only"] = [upstream]
    return {"provider": provider}


def validate_reasoning_effort(provider: str, model: str, reasoning_effort: str | None):
    if reasoning_effort is not None and (reasoning_effort not in {'low', 'medium'} or provider != 'openrouter' or model != 'openai/gpt-6-luna'):
        raise ValueError('Explicit low or medium reasoning effort requires OpenRouter openai/gpt-6-luna.')


def build_openrouter_target_payload(*, model, instructions, prompt, temperature,
                                    max_output_tokens=None, reasoning_effort=None, provider_options):
    """Pure wire builder; routing/environment resolution belongs to its caller."""
    import copy
    validate_reasoning_effort('openrouter', model, reasoning_effort)
    if max_output_tokens is not None and (type(max_output_tokens) is not int or max_output_tokens < 1):
        raise ValueError('Invalid completion budget.')
    if (not isinstance(provider_options, dict) or provider_options.get('require_parameters') is not True
            or provider_options.get('allow_fallbacks') is not False
            or set(provider_options) - {'require_parameters', 'allow_fallbacks', 'only'}
            or ('only' in provider_options and (not isinstance(provider_options['only'], list)
                or not provider_options['only'] or any(not isinstance(v, str) or not v.strip() for v in provider_options['only'])))):
        raise ValueError('Invalid strict provider routing.')
    return {'model': model, **sampling_parameters(model, temperature),
            'messages': [{'role': 'system', 'content': instructions}, {'role': 'user', 'content': prompt}],
            'provider': copy.deepcopy(provider_options),
            **({'max_tokens': max_output_tokens} if max_output_tokens is not None else {}),
            **({'reasoning': {'effort': reasoning_effort}} if reasoning_effort is not None else {})}


def build_openrouter_json_payload(*, model, instructions, prompt, schema_name, schema,
                                  max_output_tokens=None, reasoning_effort=None, provider_options):
    import copy
    payload = build_openrouter_target_payload(model=model, instructions=instructions, prompt=prompt,
        temperature=0, max_output_tokens=max_output_tokens, reasoning_effort=reasoning_effort,
        provider_options=provider_options)
    payload['response_format'] = {'type': 'json_schema', 'json_schema': {
        'name': schema_name, 'strict': True, 'schema': copy.deepcopy(schema)}}
    return payload


def validate_profile_reasoning(provider, model, profile):
    validate_reasoning_effort(provider, model, profile.reasoning_effort)
    validate_reasoning_effort(provider, model, profile.identity_analysis_reasoning_effort)
    validate_reasoning_effort(provider, model, profile.answer_validation_reasoning_effort)
    if profile.answer_validation != "off" and (provider != 'openrouter' or model != 'openai/gpt-6-luna'):
        raise ValueError('Answer source validation requires the configured OpenRouter GPT 6 Luna target.')
