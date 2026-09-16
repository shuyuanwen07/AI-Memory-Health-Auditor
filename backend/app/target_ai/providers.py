"""Backend-only connectors for selectable third-party target models.

Provider-specific request and response details live here so API routes remain
agnostic to the target model. Credentials are never included in exceptions or
API responses.
"""
from __future__ import annotations

import os
import time
from contextvars import ContextVar
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException

from app.schemas import AuditRun, TargetProvider, TargetResponse, TestCase
from app.services.interfaces import TargetAIConnector
from app.target_ai.rule_based import RuleBasedTargetAIConnector, private_context_instruction


PROVIDERS = {
    TargetProvider.RULE_BASED: ("Local rule-based baseline", "rule-based-target-ai", "Runs locally without an API key."),
    TargetProvider.OPENAI: ("OpenAI GPT-5.6 Luna", "gpt-5.6-luna", "Low-cost OpenAI target model."),
    TargetProvider.DEEPSEEK: ("DeepSeek Flash", "deepseek-flash", "DeepSeek's OpenAI-compatible Flash API."),
    TargetProvider.GEMINI: ("Gemini 2.5 Flash-Lite", "gemini-2.5-flash-lite", "Google Gemini API free-tier eligible model."),
}

_ENVIRONMENT_KEY = {
    TargetProvider.OPENAI: "OPENAI_API_KEY",
    TargetProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
    TargetProvider.GEMINI: "GEMINI_API_KEY",
}
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_REQUEST_TIMEOUT_SECONDS = 60.0
# Request-local facts are captured without saving raw upstream payloads.  They
# also remain correct when several audits execute concurrently in one process.
_ATTEMPTS: ContextVar[int] = ContextVar("target_provider_attempts", default=0)
_USAGE: ContextVar[dict[str, int | None]] = ContextVar("target_provider_usage", default={})


def configured(provider: TargetProvider) -> bool:
    """Return whether the backend has a non-blank credential for a provider."""
    if provider == TargetProvider.RULE_BASED:
        return True
    key_name = _ENVIRONMENT_KEY.get(provider)
    return bool(key_name and os.getenv(key_name, "").strip())


class ProviderRequestError(RuntimeError):
    """A sanitised provider error safe to expose through the REST API."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class HttpTargetAIConnector(TargetAIConnector):
    """Execute a test against a configured cloud model with bounded retries."""

    def execute(self, test: TestCase, audit: AuditRun) -> TargetResponse:
        if audit.provider == TargetProvider.RULE_BASED:
            return RuleBasedTargetAIConnector().execute(test, audit)

        credential = self._credential_for(audit.provider)
        # This derives only from target_memory_context. expected_behavior is
        # evaluator-private and must never reach the model under test.
        instructions = private_context_instruction(test, audit.target_configuration)
        attempts_token = _ATTEMPTS.set(0)
        usage_token = _USAGE.set({})
        started = time.perf_counter()
        try:
            response_text = self._execute_provider(audit, test, instructions, credential)
        except ProviderRequestError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
        finally:
            attempts = _ATTEMPTS.get()
            usage = _USAGE.get()
            _ATTEMPTS.reset(attempts_token)
            _USAGE.reset(usage_token)

        if not response_text.strip():
            raise HTTPException(502, f"{PROVIDERS[audit.provider][0]} returned an empty target response.")

        return TargetResponse(
            response_id=f"R{test.test_id[1:]}", test_id=test.test_id, run_id=audit.run_id,
            response_text=response_text.strip(), model=audit.model, temperature=audit.temperature,
            execution_metadata={
                "request_attempts": attempts or 1,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "response_source": audit.provider.value,
            },
            created_at=datetime.now(timezone.utc),
        )

    def _credential_for(self, provider: TargetProvider) -> str:
        key_name = _ENVIRONMENT_KEY.get(provider)
        credential = os.getenv(key_name, "").strip() if key_name else ""
        if not credential:
            label = PROVIDERS[provider][0]
            raise HTTPException(503, f"{label} is not configured. Add {key_name} to the backend .env file and restart the backend.")
        return credential

    def _execute_provider(self, audit: AuditRun, test: TestCase, instructions: str, credential: str) -> str:
        if audit.provider == TargetProvider.OPENAI:
            data = self._post("https://api.openai.com/v1/responses", {"Authorization": f"Bearer {credential}"}, {
                "model": audit.model, "instructions": instructions, "input": test.prompt, "temperature": audit.temperature,
            })
            _USAGE.set(self._usage(data, audit.provider))
            return self._openai_text(data)
        if audit.provider == TargetProvider.DEEPSEEK:
            data = self._post("https://api.deepseek.com/chat/completions", {"Authorization": f"Bearer {credential}"}, {
                "model": audit.model, "temperature": audit.temperature,
                "messages": [{"role": "system", "content": instructions}, {"role": "user", "content": test.prompt}],
            })
            _USAGE.set(self._usage(data, audit.provider))
            return self._deepseek_text(data)
        if audit.provider == TargetProvider.GEMINI:
            data = self._post(f"https://generativelanguage.googleapis.com/v1beta/models/{audit.model}:generateContent", {"x-goog-api-key": credential}, {
                "system_instruction": {"parts": [{"text": instructions}]},
                "contents": [{"role": "user", "parts": [{"text": test.prompt}]}],
                "generationConfig": {"temperature": audit.temperature},
            })
            _USAGE.set(self._usage(data, audit.provider))
            return self._gemini_text(data)
        raise ProviderRequestError("The selected target provider is not supported.", 400)

    @staticmethod
    def _post(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        """Post JSON with retries for transient errors; never expose response bodies."""
        provider_name = "The target AI provider"
        last_transport_error: httpx.TransportError | None = None
        for attempt in range(_MAX_ATTEMPTS):
            _ATTEMPTS.set(_ATTEMPTS.get() + 1)
            try:
                response = httpx.post(url, headers={"Content-Type": "application/json", **headers}, json=payload, timeout=_REQUEST_TIMEOUT_SECONDS)
            except httpx.TransportError as exc:
                last_transport_error = exc
            else:
                if response.is_success:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise ProviderRequestError(f"{provider_name} returned an invalid JSON response.") from exc
                    if not isinstance(data, dict):
                        raise ProviderRequestError(f"{provider_name} returned an unexpected response format.")
                    return data
                if response.status_code not in _RETRYABLE_STATUS_CODES:
                    raise ProviderRequestError(HttpTargetAIConnector._http_error_message(response.status_code))
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(2**attempt)

        if last_transport_error is not None:
            raise ProviderRequestError(f"{provider_name} could not be reached. Please try the audit again.", 503) from last_transport_error
        raise ProviderRequestError(f"{provider_name} is temporarily unavailable. Please try the audit again.", 503)

    @staticmethod
    def _usage(data: Mapping[str, Any], provider: TargetProvider) -> dict[str, int | None]:
        """Normalise provider-reported usage only when a response includes it."""
        raw = data.get("usage") if provider != TargetProvider.GEMINI else data.get("usageMetadata")
        if not isinstance(raw, Mapping):
            return {}
        keys = {
            TargetProvider.OPENAI: ("input_tokens", "output_tokens", "total_tokens"),
            TargetProvider.DEEPSEEK: ("prompt_tokens", "completion_tokens", "total_tokens"),
            TargetProvider.GEMINI: ("promptTokenCount", "candidatesTokenCount", "totalTokenCount"),
        }[provider]
        values: list[int | None] = []
        for key in keys:
            value = raw.get(key)
            values.append(value if isinstance(value, int) and not isinstance(value, bool) else None)
        return {"input_tokens": values[0], "output_tokens": values[1], "total_tokens": values[2]}

    @staticmethod
    def _http_error_message(status_code: int) -> str:
        if status_code in {401, 403}:
            return "The target AI provider rejected the configured credential. Check the backend configuration."
        if status_code == 404:
            return "The selected target model is not available from this provider. Check the model name."
        if 400 <= status_code < 500:
            return "The target AI provider rejected this audit request. Check the selected model and configuration."
        return "The target AI provider could not complete the request."

    @staticmethod
    def _openai_text(data: Mapping[str, Any]) -> str:
        direct = data.get("output_text")
        if isinstance(direct, str):
            return direct
        output = data.get("output")
        if isinstance(output, list):
            texts = [
                item.get("text", "")
                for message in output
                if isinstance(message, Mapping) and isinstance(message.get("content"), list)
                for item in message["content"]
                if isinstance(item, Mapping) and isinstance(item.get("text"), str)
            ]
            if texts:
                return "".join(texts)
        raise ProviderRequestError("OpenAI returned a response without usable text.")

    @staticmethod
    def _deepseek_text(data: Mapping[str, Any]) -> str:
        try:
            content = data["choices"][0]["message"].get("content")
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderRequestError("DeepSeek returned a response without usable text.") from exc
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(item.get("text", "") for item in content if isinstance(item, Mapping))
        raise ProviderRequestError("DeepSeek returned a response without usable text.")

    @staticmethod
    def _gemini_text(data: Mapping[str, Any]) -> str:
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderRequestError("Gemini returned a response without usable text.") from exc
        if isinstance(parts, list):
            text = "".join(item.get("text", "") for item in parts if isinstance(item, Mapping))
            if text:
                return text
        raise ProviderRequestError("Gemini returned a response without usable text.")
