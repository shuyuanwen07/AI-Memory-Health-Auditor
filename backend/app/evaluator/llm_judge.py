"""Optional LLM-as-judge implementation for behavioural evaluations.

This module intentionally has no route-level concerns.  It implements the
same :class:`BehaviourEvaluator` boundary as the deterministic evaluator, so
an audit can choose a judge without changing its API contract.  A failed,
misconfigured, or malformed upstream judge response safely falls back to the
deterministic evaluator; upstream payloads and credentials never leave this
module.
"""
from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from typing import Any

import httpx

from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.schemas import EvaluationResult, Memory, MemoryStatus, TargetResponse, TestCase
from app.services.interfaces import BehaviourEvaluator


_PROVIDERS = frozenset({"openai", "deepseek", "gemini"})
_CREDENTIAL_ENV = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
_DEFAULT_MODELS = {
    "openai": "gpt-5.6-luna",
    "deepseek": "deepseek-flash",
    "gemini": "gemini-2.5-flash-lite",
}
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_REQUEST_TIMEOUT_SECONDS = 60.0
_GROUND_TRUTH_STATUSES = frozenset({MemoryStatus.CONFIRMED, MemoryStatus.EDITED})


class LLMJudgeRequestError(RuntimeError):
    """Internal error whose message is deliberately safe and generic."""


class LLMBehaviourEvaluator(BehaviourEvaluator):
    """Judge a target response with a configured cloud model.

    The class is deliberately fail-safe: a temporary provider problem must not
    turn an otherwise reproducible audit into an API error or disclose a key,
    URL payload, or upstream response.  The returned evaluator label records
    that the rule evaluator was used as a fallback.
    """

    VERSION_PREFIX = "llm-judge"

    def __init__(
        self,
        provider: str,
        *,
        model: str | None = None,
        fallback: BehaviourEvaluator | None = None,
    ) -> None:
        normalised = provider.strip().lower()
        if normalised not in _PROVIDERS:
            raise ValueError("Unsupported LLM judge provider.")
        self.provider = normalised
        self.model = model or os.getenv("EVALUATOR_MODEL", "").strip() or _DEFAULT_MODELS[normalised]
        self.fallback = fallback or RuleBasedBehaviourEvaluator()

    def evaluate(self, test: TestCase, response: TargetResponse, memories: list[Memory]) -> EvaluationResult:
        relevant_memories = self._relevant_memories(test, memories)
        allowed_evidence_ids = {memory.memory_id for memory in relevant_memories}
        try:
            credential = self._credential()
            raw_result = self._judge(test, response, relevant_memories, credential)
            passed, reason, evidence_ids = self._validated_result(raw_result, allowed_evidence_ids)
        except (LLMJudgeRequestError, ValueError, KeyError, TypeError, json.JSONDecodeError, httpx.HTTPError):
            return self._fallback_result(test, response, memories)

        return EvaluationResult(
            evaluation_id=f"E{test.test_id[1:]}",
            test_id=test.test_id,
            response_id=response.response_id,
            passed=passed,
            failure_type=None if passed else test.dimension,
            reason=reason,
            evidence_memory_ids=evidence_ids,
            evaluator=f"{self.VERSION_PREFIX}-{self.provider}-v1",
        )

    def _fallback_result(self, test: TestCase, response: TargetResponse, memories: list[Memory]) -> EvaluationResult:
        result = self.fallback.evaluate(test, response, memories)
        # The label is transparent to researchers while exposing no provider
        # failure details (which could include sensitive upstream data).
        return result.model_copy(update={
            "evaluator": "fallback-rule-based-v4",
            "reason": f"LLM judge unavailable; deterministic fallback used. {result.reason}",
        })

    def _credential(self) -> str:
        credential = os.getenv(_CREDENTIAL_ENV[self.provider], "").strip()
        if not credential:
            raise LLMJudgeRequestError("LLM judge is not configured.")
        return credential

    @staticmethod
    def _relevant_memories(test: TestCase, memories: list[Memory]) -> list[Memory]:
        supported = set(test.supporting_memory_ids)
        return [
            memory
            for memory in memories
            if memory.memory_id in supported and memory.status in _GROUND_TRUTH_STATUSES
        ]

    def _judge(self, test: TestCase, response: TargetResponse, memories: list[Memory], credential: str) -> dict[str, Any]:
        prompt = self._judge_prompt(test, response, memories)
        if self.provider == "openai":
            payload = {
                "model": self.model,
                "input": prompt,
                "text": {"format": self._openai_schema()},
            }
            data = self._post("https://api.openai.com/v1/responses", {"Authorization": f"Bearer {credential}"}, payload)
            return self._parse_json(self._openai_text(data))
        if self.provider == "deepseek":
            payload = {
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": self._system_instruction()},
                    {"role": "user", "content": prompt},
                ],
            }
            data = self._post("https://api.deepseek.com/chat/completions", {"Authorization": f"Bearer {credential}"}, payload)
            return self._parse_json(self._deepseek_text(data))
        payload = {
            "system_instruction": {"parts": [{"text": self._system_instruction()}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        data = self._post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            {"x-goog-api-key": credential},
            payload,
        )
        return self._parse_json(self._gemini_text(data))

    @staticmethod
    def _system_instruction() -> str:
        return (
            "You are a careful evaluator for an AI-memory experiment. Evaluate only against the supplied "
            "confirmed ground truth. Return one JSON object and no markdown."
        )

    def _judge_prompt(self, test: TestCase, response: TargetResponse, memories: list[Memory]) -> str:
        memory_records = [
            {"memory_id": memory.memory_id, "canonical_value": memory.canonical_value,
             "source_message_ids": memory.source_message_ids, "timestamp": memory.timestamp.isoformat() if memory.timestamp else None}
            for memory in memories
        ]
        contract = {
            "passed": "boolean",
            "reason": "short English explanation grounded in supplied memories",
            "evidence_memory_ids": "array containing only supplied memory_id values",
        }
        return (
            f"{self._system_instruction()}\n\n"
            f"Test dimension: {test.dimension.value}\n"
            f"Test prompt: {test.prompt}\n"
            f"Expected behaviour: {test.expected_behavior}\n"
            f"Target response: {response.response_text}\n"
            f"Confirmed ground truth: {json.dumps(memory_records, ensure_ascii=False)}\n\n"
            f"Required JSON shape: {json.dumps(contract)}"
        )

    @staticmethod
    def _openai_schema() -> dict[str, Any]:
        return {
            "type": "json_schema",
            "name": "memory_evaluation",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["passed", "reason", "evidence_memory_ids"],
                "properties": {
                    "passed": {"type": "boolean"},
                    "reason": {"type": "string"},
                    "evidence_memory_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        }

    @staticmethod
    def _post(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        """Post with bounded retries and sanitised, non-upstream errors."""
        had_transport_error = False
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = httpx.post(
                    url,
                    headers={"Content-Type": "application/json", **headers},
                    json=payload,
                    timeout=_REQUEST_TIMEOUT_SECONDS,
                )
            except httpx.TransportError:
                had_transport_error = True
            else:
                if response.is_success:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise LLMJudgeRequestError("LLM judge returned invalid JSON.") from exc
                    if isinstance(data, dict):
                        return data
                    raise LLMJudgeRequestError("LLM judge returned an unexpected response.")
                if response.status_code not in _RETRYABLE_STATUS_CODES:
                    raise LLMJudgeRequestError("LLM judge request was rejected.")
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(2**attempt)
        if had_transport_error:
            raise LLMJudgeRequestError("LLM judge could not be reached.")
        raise LLMJudgeRequestError("LLM judge is temporarily unavailable.")

    @staticmethod
    def _openai_text(data: Mapping[str, Any]) -> str:
        text = data.get("output_text")
        if isinstance(text, str):
            return text
        output = data.get("output")
        if isinstance(output, list):
            parts = [
                item.get("text", "")
                for message in output
                if isinstance(message, Mapping) and isinstance(message.get("content"), list)
                for item in message["content"]
                if isinstance(item, Mapping) and isinstance(item.get("text"), str)
            ]
            if parts:
                return "".join(parts)
        raise LLMJudgeRequestError("LLM judge response has no usable text.")

    @staticmethod
    def _deepseek_text(data: Mapping[str, Any]) -> str:
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMJudgeRequestError("LLM judge response has no usable text.") from exc
        if isinstance(text, str):
            return text
        raise LLMJudgeRequestError("LLM judge response has no usable text.")

    @staticmethod
    def _gemini_text(data: Mapping[str, Any]) -> str:
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMJudgeRequestError("LLM judge response has no usable text.") from exc
        if isinstance(parts, list):
            text = "".join(item.get("text", "") for item in parts if isinstance(item, Mapping))
            if text:
                return text
        raise LLMJudgeRequestError("LLM judge response has no usable text.")

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("LLM judge output must be an object.")
        return data

    @staticmethod
    def _validated_result(data: Mapping[str, Any], allowed_evidence_ids: set[str]) -> tuple[bool, str, list[str]]:
        # bool is intentionally checked exactly; Python's integers are not valid
        # evaluator decisions even though they are subclasses of bool.
        passed = data.get("passed")
        reason = data.get("reason")
        evidence = data.get("evidence_memory_ids")
        required_fields = {"passed", "reason", "evidence_memory_ids"}
        if set(data) != required_fields:
            raise ValueError("LLM judge result does not meet the strict output contract.")
        if type(passed) is not bool or not isinstance(reason, str) or not reason.strip() or not isinstance(evidence, list):
            raise ValueError("LLM judge result does not meet the output contract.")
        if not all(isinstance(memory_id, str) for memory_id in evidence):
            raise ValueError("LLM judge evidence is invalid.")
        if any(memory_id not in allowed_evidence_ids for memory_id in evidence):
            raise ValueError("LLM judge cited evidence outside the supplied ground truth.")
        evidence_ids = list(dict.fromkeys(evidence))
        return passed, reason.strip()[:2000], evidence_ids
