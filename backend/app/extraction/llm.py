"""Provider-backed, structured-output support for the audit pipeline.

This module deliberately contains no route or database code.  Both pipeline
stages use it to ask a configured model for JSON, then validate that JSON
locally before it can enter the shared domain model.  Credentials are read
only by the backend process and are never included in raised errors.
"""
from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from typing import Any

import httpx
from fastapi import HTTPException


_KEY_BY_PROVIDER = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
_DEFAULT_MODEL_BY_PROVIDER = {
    "openai": "gpt-5.6-luna",
    "deepseek": "deepseek-flash",
    "gemini": "gemini-2.5-flash-lite",
}
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_REQUEST_TIMEOUT_SECONDS = 60.0


class PipelineRequestError(HTTPException):
    """A user-safe pipeline error; never construct it from an upstream body."""

    def __init__(self, detail: str, status_code: int = 502) -> None:
        super().__init__(status_code=status_code, detail=detail)


def pipeline_provider() -> str:
    """Return the configured pipeline provider, rejecting misspellings early."""
    provider = os.getenv("PIPELINE_PROVIDER", "rule_based").strip().lower()
    if provider not in {"rule_based", *_KEY_BY_PROVIDER}:
        raise PipelineRequestError(
            "PIPELINE_PROVIDER must be one of: rule_based, openai, deepseek, gemini.",
            status_code=500,
        )
    return provider


def configured_pipeline_model(provider: str | None = None) -> str:
    """Resolve the exact pipeline model stored with a reproducible audit run."""
    choice = provider or pipeline_provider()
    if choice == "rule_based":
        return "rule-based-v2"
    return os.getenv("PIPELINE_MODEL", "").strip() or _DEFAULT_MODEL_BY_PROVIDER[choice]


class PipelineLLMClient:
    """Minimal HTTP client shared by LLM extraction and LLM test generation."""

    def __init__(self, provider: str | None = None, model: str | None = None) -> None:
        self.provider = (provider or pipeline_provider()).lower()
        if self.provider == "rule_based":
            raise ValueError("Rule-based pipeline mode does not use PipelineLLMClient.")
        if self.provider not in _KEY_BY_PROVIDER:
            raise PipelineRequestError("The configured pipeline provider is not supported.", 500)
        self._model_override = (model or "").strip()

    @property
    def model(self) -> str:
        return self._model_override or configured_pipeline_model(self.provider)

    def complete_json(self, *, instructions: str, prompt: str, schema_name: str, schema: dict[str, Any]) -> Any:
        """Request strict JSON and parse it without accepting prose or Markdown."""
        credential = self._credential()
        if self.provider == "openai":
            payload = {
                "model": self.model,
                "instructions": instructions,
                "input": prompt,
                "temperature": 0,
                "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}},
            }
            data = self._post("https://api.openai.com/v1/responses", {"Authorization": f"Bearer {credential}"}, payload)
            text = self._openai_text(data)
        elif self.provider == "deepseek":
            payload = {
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": instructions}, {"role": "user", "content": prompt}],
            }
            data = self._post("https://api.deepseek.com/chat/completions", {"Authorization": f"Bearer {credential}"}, payload)
            text = self._deepseek_text(data)
        else:  # Gemini
            payload = {
                "system_instruction": {"parts": [{"text": instructions}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseJsonSchema": schema},
            }
            data = self._post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                {"x-goog-api-key": credential}, payload,
            )
            text = self._gemini_text(data)
        try:
            return json.loads(text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise PipelineRequestError(
                "The configured pipeline model returned invalid JSON. Retry the operation or select the rule-based pipeline."
            ) from exc

    def _credential(self) -> str:
        key_name = _KEY_BY_PROVIDER[self.provider]
        credential = os.getenv(key_name, "").strip()
        if not credential:
            raise PipelineRequestError(
                f"The {self.provider.title()} pipeline is not configured. Add {key_name} to the backend .env file and restart the backend.",
                status_code=503,
            )
        return credential

    @staticmethod
    def _post(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        last_transport_error: httpx.TransportError | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = httpx.post(
                    url, headers={"Content-Type": "application/json", **headers}, json=payload,
                    timeout=_REQUEST_TIMEOUT_SECONDS,
                )
            except httpx.TransportError as exc:
                last_transport_error = exc
            else:
                if response.is_success:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise PipelineRequestError("The configured pipeline model returned an invalid API response.") from exc
                    if isinstance(data, dict):
                        return data
                    raise PipelineRequestError("The configured pipeline model returned an unexpected API response.")
                if response.status_code not in _RETRYABLE_STATUS_CODES:
                    raise PipelineRequestError(PipelineLLMClient._http_error(response.status_code))
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(2**attempt)
        if last_transport_error is not None:
            raise PipelineRequestError("The configured pipeline model could not be reached. Please try again.", 503) from last_transport_error
        raise PipelineRequestError("The configured pipeline model is temporarily unavailable. Please try again.", 503)

    @staticmethod
    def _http_error(status_code: int) -> str:
        if status_code in {401, 403}:
            return "The configured pipeline credential was rejected. Check the backend configuration."
        if status_code == 404:
            return "The configured pipeline model is not available. Check PIPELINE_MODEL."
        if 400 <= status_code < 500:
            return "The configured pipeline model rejected this request. Check its configuration."
        return "The configured pipeline model could not complete the request."

    @staticmethod
    def _openai_text(data: Mapping[str, Any]) -> str:
        direct = data.get("output_text")
        if isinstance(direct, str) and direct.strip():
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
        raise PipelineRequestError("The configured pipeline model returned no usable JSON content.")

    @staticmethod
    def _deepseek_text(data: Mapping[str, Any]) -> str:
        try:
            content = data["choices"][0]["message"].get("content")
        except (KeyError, IndexError, TypeError) as exc:
            raise PipelineRequestError("The configured pipeline model returned no usable JSON content.") from exc
        if isinstance(content, str):
            return content
        raise PipelineRequestError("The configured pipeline model returned no usable JSON content.")

    @staticmethod
    def _gemini_text(data: Mapping[str, Any]) -> str:
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            raise PipelineRequestError("The configured pipeline model returned no usable JSON content.") from exc
        if isinstance(parts, list):
            text = "".join(item.get("text", "") for item in parts if isinstance(item, Mapping))
            if text:
                return text
        raise PipelineRequestError("The configured pipeline model returned no usable JSON content.")
