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
