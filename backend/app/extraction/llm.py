"""Provider-backed, structured-output support for the audit pipeline.

This module deliberately contains no route or database code.  Both pipeline
stages use it to ask a configured model for JSON, then validate that JSON
locally before it can enter the shared domain model.  Credentials are read
only by the backend process and are never included in raised errors.
"""
from __future__ import annotations

import json
import hashlib
import math
import os
import time
from contextvars import ContextVar
from collections.abc import Mapping
from typing import Any

import httpx

from app.target_ai.openrouter import CHAT_COMPLETIONS_URL, default_model, request_options, sampling_parameters, completion_error
from fastapi import HTTPException


_KEY_BY_PROVIDER = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
_DEFAULT_MODEL_BY_PROVIDER = {
    "openrouter": default_model(),
    "openai": "gpt-5.6-luna",
    "deepseek": "deepseek-flash",
    "gemini": "gemini-2.5-flash-lite",
    "ollama": os.getenv("OLLAMA_DEFAULT_MODEL", "qwen3:1.7b").strip() or "qwen3:1.7b",
}
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_REQUEST_TIMEOUT_SECONDS = 60.0
_PIPELINE_METER = ContextVar('pipeline_http_meter',default=None)


class PipelineRequestError(HTTPException):
    """A user-safe pipeline error; never construct it from an upstream body."""

    def __init__(self, detail: str, status_code: int = 502) -> None:
        super().__init__(status_code=status_code, detail=detail)


def pipeline_provider() -> str:
    """Return the configured pipeline provider, rejecting misspellings early."""
    provider = os.getenv("PIPELINE_PROVIDER", "rule_based").strip().lower()
    if provider not in {"rule_based", *_KEY_BY_PROVIDER, "ollama"}:
        raise PipelineRequestError(
            "PIPELINE_PROVIDER must be one of: rule_based, openrouter, openai, deepseek, gemini, ollama.",
            status_code=500,
        )
    return provider


def configured_pipeline_model(provider: str | None = None) -> str:
    """Resolve the exact pipeline model stored with a reproducible audit run."""
    choice = provider or pipeline_provider()
    if choice == "rule_based":
        return "rule-based-v2"
    configured_choice = pipeline_provider()
    override = os.getenv("PIPELINE_MODEL", "").strip() if choice == configured_choice else ""
    return override or _DEFAULT_MODEL_BY_PROVIDER[choice]


def pipeline_output_token_cap() -> int | None:
    """Optional cloud pipeline budget; never truncate evidence or relax gates."""
    raw = os.getenv("PIPELINE_MAX_OUTPUT_TOKENS", "").strip()
    if not raw:
        return None
    if not raw.isascii() or not raw.isdigit() or not 256 <= int(raw) <= 12000:
        raise PipelineRequestError("PIPELINE_MAX_OUTPUT_TOKENS must be an integer from 256 to 12000.", 500)
    return int(raw)


class PipelineLLMClient:
    """Minimal HTTP client shared by LLM extraction and LLM test generation."""

    def __init__(self, provider: str | None = None, model: str | None = None) -> None:
        self.provider = (provider or pipeline_provider()).lower()
        if self.provider == "rule_based":
            raise ValueError("Rule-based pipeline mode does not use PipelineLLMClient.")
        if self.provider not in {*_KEY_BY_PROVIDER, "ollama"}:
            raise PipelineRequestError("The configured pipeline provider is not supported.", 500)
        self._model_override = (model or "").strip()
        self.last_execution = None

    @property
    def model(self) -> str:
        return self._model_override or configured_pipeline_model(self.provider)

    def complete_json(self, *, instructions: str, prompt: str, schema_name: str, schema: dict[str, Any],
                      max_output_tokens: int | None = None, agent_role: str | None = None,
                      prompt_template_version: str | None = None, thinking: bool = False) -> Any:
        if type(thinking) is not bool or (thinking and self.provider != 'ollama'):
            raise PipelineRequestError('Explicit thinking mode is supported only for the local pipeline.', 422)
        declared_output_limit = max_output_tokens
        configured_cap = pipeline_output_token_cap() if self.provider == 'openrouter' else None
        if configured_cap is not None:
            max_output_tokens = min(max_output_tokens, configured_cap) if max_output_tokens is not None else configured_cap
        meter={'version':'pipeline-http-meter-v2','provider':self.provider,'model':self.model,
            'request_attempts':0,'failed_http_attempts':0,'status':'started',
            'reported_input_tokens':None,'reported_output_tokens':None,'reported_total_tokens':None,
            'reported_cost_credits':None,'reported_model':None,'last_http_status':None,
            'agent_role': agent_role or schema_name,
            'requested_ollama_thinking': thinking if self.provider == 'ollama' else None,
            'requested_output_token_limit': max_output_tokens,
            'declared_output_token_limit': declared_output_limit,
            'configured_output_token_cap': configured_cap,
            'prompt_template_version': prompt_template_version or 'unversioned',
            'prompt_fingerprint': hashlib.sha256(json.dumps({
                'version': prompt_template_version or 'unversioned', 'instructions': instructions,
                'prompt': prompt, 'schema': schema, 'ollama_thinking': thinking if self.provider == 'ollama' else None,
            }, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest(),
            'input_fingerprint': hashlib.sha256(prompt.encode('utf-8')).hexdigest(),
            'output_fingerprint':None,'error_code':None,
            'scope':'Last successful HTTP reply only; failed-attempt usage unknown. Elapsed time includes retry waits and parsing.'}
        self.last_execution=None
        token=_PIPELINE_METER.set(meter);started=time.perf_counter()
        try:
            result=self._complete_json(instructions=instructions,prompt=prompt,schema_name=schema_name,schema=schema,
                                       max_output_tokens=max_output_tokens)
            meter['status']='parsed'
            meter['output_fingerprint'] = hashlib.sha256(json.dumps(
                result, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str
            ).encode('utf-8')).hexdigest()
            return result
        except Exception as exc:
            meter['status']='failed'
            meter['error_code']=type(exc).__name__
            raise
        finally:
            meter['elapsed_ms']=round((time.perf_counter()-started)*1000,2)
            self.last_execution=dict(meter)
            _PIPELINE_METER.reset(token)

    def _complete_json(self, *, instructions: str, prompt: str, schema_name: str, schema: dict[str, Any],
                       max_output_tokens: int | None = None) -> Any:
        """Request strict JSON and parse it without accepting prose or Markdown."""
        if self.provider == "ollama":
            from app.target_ai.providers import ollama_base_url
            meter = _PIPELINE_METER.get()
            requested_thinking = bool(meter and meter.get("requested_ollama_thinking"))
            data = self._post(f"{ollama_base_url()}/api/chat", {}, {
                "model": self.model,
                "stream": False,
                "think": requested_thinking,
                "keep_alive": "5m",
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": prompt},
                ],
                "format": schema,
                "options": {
                    "temperature": 0,
                    "num_ctx": 8192,
                    "num_predict": max_output_tokens or 4096,
                },
            })
            meter = _PIPELINE_METER.get()
            reported_model = data.get("model")
            if meter is not None and isinstance(reported_model, str) and 0 < len(reported_model) <= 200:
                meter["reported_model"] = reported_model
            done_reason = data.get("done_reason")
            if (meter is not None and meter.get("agent_role") == "independent_memory_review"
                    and isinstance(done_reason, str)):
                meter["reported_done_reason"] = done_reason if done_reason in {"stop", "length", "load", "unload", "error"} else "other"
            message = data.get("message")
            if meter is not None:
                meter["reported_ollama_thinking_present"] = bool(isinstance(message, Mapping) and message.get("thinking"))
            if (data.get("done") is not True or data.get("done_reason") == "length"
                    or not isinstance(message, Mapping) or not isinstance(message.get("content"), str)):
                raise PipelineRequestError("The local pipeline model did not complete a usable answer.")
            text = message["content"]
            try:
                return json.loads(text)
            except (TypeError, json.JSONDecodeError) as exc:
                raise PipelineRequestError(
                    "The configured pipeline model returned invalid JSON. Retry the operation or select another model."
                ) from exc
        credential = self._credential()
        if self.provider == "openrouter":
            payload = {
                "model": self.model,
                **sampling_parameters(self.model,0),
                "messages": [{"role": "system", "content": instructions}, {"role": "user", "content": prompt}],
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": schema_name, "strict": True, "schema": schema,
                }},
                **({"max_tokens": max_output_tokens} if max_output_tokens is not None else {}),
                **request_options(),
            }
            try:
                data = self._post(CHAT_COMPLETIONS_URL, {"Authorization": f"Bearer {credential}"}, payload)
            except PipelineRequestError:
                # Some OpenRouter routes accept JSON Schema for a small
                # availability probe but reject a full extraction schema.
                # Retry only that non-retryable schema request as JSON mode;
                # the extraction Agent still validates the result against its
                # strict local Pydantic contract before saving any candidates.
                meter = _PIPELINE_METER.get()
                if (meter is None or meter.get("agent_role") != "memory_extraction"
                        or meter.get("last_http_status") != 400):
                    raise
                meter["response_format_fallback"] = "json_object_after_schema_http_400"
                meter["schema_rejection_http_status"] = 400
                payload["response_format"] = {"type": "json_object"}
                data = self._post(CHAT_COMPLETIONS_URL, {"Authorization": f"Bearer {credential}"}, payload)
            text = self._deepseek_text(data)
        elif self.provider == "openai":
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
        if self.provider == "ollama":
            return ""
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
        meter = _PIPELINE_METER.get()
        local_model = bool(meter and meter.get("provider") == "ollama")
        max_attempts = 1 if local_model else _MAX_ATTEMPTS
        # Local inference latency scales with the requested JSON budget and can
        # exceed cloud API timeouts even when Ollama is healthy. Keep one local
        # attempt, but allow enough time for the configured small model to finish.
        timeout_seconds = 240.0 if local_model else _REQUEST_TIMEOUT_SECONDS
        for attempt in range(max_attempts):
            meter=_PIPELINE_METER.get()
            if meter is not None:
                temperature=payload.get('temperature',payload.get('generationConfig',{}).get('temperature',payload.get('options',{}).get('temperature')))
                meter['sampling_control']='fixed' if temperature is not None else 'model_default'
                meter['sent_temperature']=temperature
            if meter is not None:meter['request_attempts']+=1
            try:
                response = httpx.post(
                    url, headers={"Content-Type": "application/json", **headers}, json=payload,
                    timeout=timeout_seconds,
                )
            except httpx.TransportError as exc:
                if meter is not None:meter['failed_http_attempts']+=1
                last_transport_error = exc
            else:
                if response.is_success:
                    if meter is not None:meter['last_http_status']=response.status_code
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise PipelineRequestError("The configured pipeline model returned an invalid API response.") from exc
                    if isinstance(data, dict):
                        PipelineLLMClient._record_usage(data,meter)
                        if meter is not None:
                            choices = data.get('choices')
                            meter['response_choice_count'] = len(choices) if isinstance(choices, list) else None
                        error = completion_error(data)
                        if error:
                            if meter is not None:
                                meter.update(error)
                            detail = PipelineLLMClient._http_error(error['provider_error_status'])
                            if error.get('provider_error_category') == 'capacity_limit':
                                detail = ('The model service rejected this request during peak load because its requested budget is too large. '
                                          'Try later or configure PIPELINE_MAX_OUTPUT_TOKENS to a smaller output budget. No result was accepted.')
                            raise PipelineRequestError(detail, error['provider_error_status'])
                        return data
                    raise PipelineRequestError("The configured pipeline model returned an unexpected API response.")
                if meter is not None:meter['failed_http_attempts']+=1
                if meter is not None:meter['last_http_status']=response.status_code
                if response.status_code not in _RETRYABLE_STATUS_CODES:
                    raise PipelineRequestError(PipelineLLMClient._http_error(response.status_code))
            if attempt < max_attempts - 1:
                time.sleep(2**attempt)
        if last_transport_error is not None:
            raise PipelineRequestError("The configured pipeline model could not be reached. Please try again.", 503) from last_transport_error
        raise PipelineRequestError("The configured pipeline model is temporarily unavailable. Please try again.", 503)

    @staticmethod
    def _record_usage(data,meter):
        if meter is None:return
        usage=data.get('usage') if isinstance(data.get('usage'),dict) else {}
        google=data.get('usageMetadata') if isinstance(data.get('usageMetadata'),dict) else {}
        values={'reported_input_tokens':usage.get('input_tokens',usage.get('prompt_tokens',google.get('promptTokenCount'))),
            'reported_output_tokens':usage.get('output_tokens',usage.get('completion_tokens',google.get('candidatesTokenCount'))),
            'reported_total_tokens':usage.get('total_tokens',google.get('totalTokenCount'))}
        for key,value in values.items():
            if type(value) is int and value>=0:meter[key]=value
        if meter['reported_total_tokens'] is None and meter['reported_input_tokens'] is not None and meter['reported_output_tokens'] is not None:
            meter['reported_total_tokens']=meter['reported_input_tokens']+meter['reported_output_tokens']
        cost=usage.get('cost')
        if meter['provider']=='openrouter' and type(cost) in (int,float):
            try:amount=float(cost)
            except OverflowError:amount=float('nan')
            if math.isfinite(amount) and amount>=0:meter['reported_cost_credits']=amount
        reported=data.get('model',data.get('modelVersion'))
        if isinstance(reported,str) and 0<len(reported)<=200:meter['reported_model']=reported

    @staticmethod
    def _http_error(status_code: int) -> str:
        if status_code in {401, 403}:
            return "The configured pipeline credential was rejected. Check the backend configuration."
        if status_code == 402:
            return "The model service could not fund this request. Check its account credits and request budget."
        if status_code == 429:
            return "The model service is rate limited. Try again later."
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
            choice = data["choices"][0]
            meter = _PIPELINE_METER.get()
            finish = choice.get("finish_reason")
            if meter is not None and isinstance(finish, str):
                meter["reported_finish_reason"] = finish if finish in {"stop", "length", "content_filter", "tool_calls", "error"} else "other"
            if finish == "length":
                raise PipelineRequestError("The configured pipeline model reached its output limit before completing the required result.")
            content = choice["message"].get("content")
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
