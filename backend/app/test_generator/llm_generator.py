"""LLM-backed behavioural-test generation with local contract validation."""
from __future__ import annotations

import json
import re
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.extraction.llm import PipelineLLMClient, PipelineRequestError
from app.schemas import AuditRun, Dimension, Memory, TestCase, TestType
from app.services.interfaces import TestGenerator


class _TestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    dimension: Dimension
    test_type: TestType = TestType.CONTEXTUAL
    prompt: Annotated[str, Field(min_length=8, max_length=3000)]
    expected_behavior: Annotated[str, Field(min_length=8, max_length=3000)]
    supporting_memory_ids: Annotated[list[str], Field(min_length=1)]


class _GenerationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tests: list[_TestPayload]


_TEST_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["tests"],
    "properties": {"tests": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["dimension", "prompt", "expected_behavior", "supporting_memory_ids"],
        "properties": {
            "dimension": {"type": "string", "enum": [item.value for item in Dimension]},
            "test_type": {"type": "string", "enum": [item.value for item in TestType]},
            "prompt": {"type": "string"}, "expected_behavior": {"type": "string"},
            "supporting_memory_ids": {"type": "array", "items": {"type": "string"}},
        },
    }}},
}


class LLMTestGenerator(TestGenerator):
    """Generate natural behavioural tests from confirmed ground truth memories."""

    VERSION = "llm-structured-v1"

    def __init__(self, client: PipelineLLMClient | None = None) -> None:
        self.client = client or PipelineLLMClient()

    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
        if not memories:
            return []
        payload = self.client.complete_json(
            instructions=(
                "You design traceable behavioural tests for a conversational AI memory audit. Return only "
                "the requested JSON object. Make tests natural and answer-independent: never copy a canonical "
                "memory value into prompt. expected_behavior may state the expected fact and reasoning. Cover "
                "accuracy, freshness, conflict_resolution, and appropriate_use when the supplied evidence supports them."
            ),
            prompt=self._prompt(memories, audit),
            schema_name="memory_audit_tests",
            schema=_TEST_SCHEMA,
        )
        try:
            generated = _GenerationPayload.model_validate(payload)
        except ValidationError as exc:
            raise PipelineRequestError("The configured pipeline model returned test data that does not match the required contract.") from exc
        self._validate_tests(generated.tests, memories, audit)
        memory_by_id = {memory.memory_id: memory for memory in memories}
        return [
            TestCase(
                test_id=f"T{index:03d}", run_id=audit.run_id, dimension=item.dimension,
                prompt=item.prompt, expected_behavior=item.expected_behavior,
                supporting_memory_ids=item.supporting_memory_ids, generator_version=self.VERSION,
                test_type=item.test_type,
                target_memory_context=[memory_by_id[memory_id].canonical_value for memory_id in item.supporting_memory_ids],
            )
            for index, item in enumerate(generated.tests, start=1)
        ]

    @staticmethod
    def _prompt(memories: list[Memory], audit: AuditRun) -> str:
        evidence = [
            {"memory_id": memory.memory_id, "canonical_value": memory.canonical_value,
             "timestamp": memory.timestamp.isoformat() if memory.timestamp else None,
             "relationships": [{"type": relation.type.value, "target_memory_id": relation.target_memory_id} for relation in memory.relationships]}
            for memory in memories
        ]
        return (
            f"Generate at most {audit.test_budget} valid tests for this controlled audit. Prefer broad "
            "dimension coverage before additional tests. Label test_type as direct, contextual, paraphrased, "
            "or indirect. Every supporting_memory_id must exist below. "
            "Return {\"tests\":[...]} exactly.\n\nCONFIRMED GROUND TRUTH:\n"
            f"{json.dumps(evidence, ensure_ascii=False)}"
        )

    @staticmethod
    def _validate_tests(tests: list[_TestPayload], memories: list[Memory], audit: AuditRun) -> None:
        if len(tests) > audit.test_budget:
            raise PipelineRequestError("The configured pipeline model exceeded the configured test budget.")
        allowed_ids = {memory.memory_id for memory in memories}
        canonical_values = [memory.canonical_value.strip().lower() for memory in memories if len(memory.canonical_value.strip()) >= 4]
        seen: set[tuple[Dimension, tuple[str, ...], str]] = set()
        for test in tests:
            if not set(test.supporting_memory_ids).issubset(allowed_ids):
                raise PipelineRequestError("The configured pipeline model referenced a memory outside confirmed ground truth.")
            if any(LLMTestGenerator._answer_leaked(value, test.prompt) for value in canonical_values):
                raise PipelineRequestError("The configured pipeline model leaked a ground-truth answer into a test prompt.")
            key = (test.dimension, tuple(sorted(test.supporting_memory_ids)), test.prompt.strip().lower())
            if key in seen:
                raise PipelineRequestError("The configured pipeline model returned duplicate behavioural tests.")
            seen.add(key)

    @staticmethod
    def _answer_leaked(canonical_value: str, prompt: str) -> bool:
        """Reject a copied answer even if punctuation or articles changed."""
        normalised = lambda value: {
            word for word in re.findall(r"[a-z0-9]+", value.lower())
            if word not in {"a", "an", "the", "is", "are", "was", "were", "to", "of", "in", "on", "for", "that"}
        }
        answer_terms, prompt_terms = normalised(canonical_value), normalised(prompt)
        return bool(answer_terms) and answer_terms.issubset(prompt_terms)
