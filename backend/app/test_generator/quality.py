"""Deterministic quality and grounding checks for generated behavioural tests.

The check is deliberately local and inspectable.  An LLM or human-review
implementation can replace it through ``TestQualityValidator`` without
changing generators, test cases, or audit execution.
"""
from __future__ import annotations

import re
from app.services.location_facts import location_value

from app.schemas import (
    GroundingStatus,
    Memory,
    MemoryStatus,
    TestCase,
    TestQualityAssessment,
    TestQualityStatus,
)
from app.services.interfaces import TestQualityValidator
from app.extraction.rule_based import RuleBasedMemoryExtractor


class RuleBasedTestQualityValidator(TestQualityValidator):
    """Validate evidence provenance and basic answer-independence deterministically."""

    VERSION = "rule-based-quality-v7"
    _STOP_WORDS = {"a", "an", "the", "is", "are", "was", "were", "to", "of", "in", "on", "for", "that"}

    @staticmethod
    def validate_suite(tests: list[TestCase]) -> str | None:
        seen: set[str] = set()
        for test in tests:
            prompt = " ".join(re.findall(r"[a-z0-9]+", test.prompt.lower()))
            if prompt in seen:
                return "Duplicate question wording; regenerate a specific, unambiguous suite before execution."
            seen.add(prompt)
        return None

    def validate(self, test: TestCase, memories: list[Memory]) -> TestQualityAssessment:
        evidence = {memory.memory_id: memory for memory in memories}
        support = [evidence.get(memory_id) for memory_id in test.supporting_memory_ids]
        missing = sorted(memory_id for memory_id in test.supporting_memory_ids if memory_id not in evidence)
        if not test.supporting_memory_ids:
            return self._result(False, False, "No supporting ground-truth memory was declared.")
        if missing:
            return self._result(False, False, f"Referenced memory IDs are unavailable: {', '.join(missing)}.")
        if any(memory is None or memory.status not in {MemoryStatus.CONFIRMED, MemoryStatus.EDITED} for memory in support):
            return self._result(False, False, "Supporting evidence must be confirmed or edited ground truth.")
        if not test.prompt.strip() or not test.expected_behavior.strip():
            return self._result(False, True, "A test needs both a prompt and expected behaviour.")
        if re.search(r"\brecorded\s+stored\s+information\b", test.prompt, re.I):
            return self._result(False, True, "The question does not identify the fact or event being tested; replace the generic stored-information wording before execution.")
        question_topic = RuleBasedMemoryExtractor._category(test.prompt)
        answer_topic = RuleBasedMemoryExtractor._category(test.expected_behavior)
        if question_topic and answer_topic and question_topic != answer_topic:
            return self._result(False, False, "Question and expected answer identify different topics; review the memory relationship.")
        if any(self._answer_leaked(memory.canonical_value, test.prompt) for memory in support if memory is not None):
            return self._result(False, True, "The prompt copies a supporting canonical memory value.")
        return self._result(True, True, "Declared evidence is confirmed and the prompt is answer-independent.")

    def _result(self, quality_ok: bool, grounded: bool, reason: str) -> TestQualityAssessment:
        return TestQualityAssessment(
            quality_status=TestQualityStatus.ACCEPTED if quality_ok else TestQualityStatus.REJECTED,
            grounding_status=GroundingStatus.GROUNDED if grounded else GroundingStatus.UNGROUNDED,
            reason=reason,
            validator_version=self.VERSION,
        )

    @classmethod
    def _answer_leaked(cls, canonical_value: str, prompt: str) -> bool:
        def terms(value: str) -> set[str]:
            return {word for word in re.findall(r"[a-z0-9]+", value.lower()) if word not in cls._STOP_WORDS}
        answer_terms, prompt_terms = terms(canonical_value), terms(prompt)
        # Derive locations from the evidence rather than a fixed city whitelist.
        location = location_value(canonical_value)
        if location:
            location_terms = terms(location)
            if location_terms and location_terms.issubset(prompt_terms):
                return True
        concrete_values = {"mysql", "postgresql", "postgres", "mongodb", "sqlite", "python", "java", "rust", "javascript", "typescript", "kotlin", "swift", "golang", "redis", "mariadb", "cassandra", "dynamodb", "sydney", "melbourne", "london"}
        if answer_terms & prompt_terms & concrete_values:
            return True
        return bool(answer_terms) and answer_terms.issubset(prompt_terms)
