"""Shared backend-only OpenRouter request configuration."""
import os
import re

CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


def sampling_parameters(model: str, temperature: float) -> dict:
    # Reasoning-family requests use model-controlled sampling. Requiring an
    # unsupported temperature can exclude otherwise callable provider routes.
    if re.match(r'^openai/gpt-(?:5\.6|6(?:\.\d+)?)(?:-|:|$)',model):
        return {}
    return {'temperature':temperature}


def default_model() -> str:
    return os.getenv("OPENROUTER_DEFAULT_MODEL", "").strip() or "google/gemini-2.5-flash-lite"


def request_options() -> dict:
    # Never silently switch models. Optionally pin an upstream provider too.
    provider: dict = {"require_parameters": True, "allow_fallbacks": False}
    upstream = os.getenv("OPENROUTER_PROVIDER", "").strip()
    if upstream:
        provider["only"] = [upstream]
    return {"provider": provider}
