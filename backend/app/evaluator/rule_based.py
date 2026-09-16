"""Deterministic, evidence-aware evaluator for Foundation v0.1."""
from __future__ import annotations

import re

from app.schemas import EvaluationResult, Memory, TargetResponse, TestCase
from app.services.interfaces import BehaviourEvaluator


class RuleBasedBehaviourEvaluator(BehaviourEvaluator):
    """Judge a response against the test's declared ground truth.

    The evaluator is deliberately deterministic for reproducible demonstrations.
    It has the same interface that a future rule-and-LLM evaluator will use.
    """

    VERSION = "rule-based-v2"
    _STOP_WORDS = frozenset({
        "about", "after", "before", "current", "fact", "from", "later", "record",
        "should", "state", "that", "the", "this", "with", "would",
    })

    def evaluate(self, test: TestCase, response: TargetResponse, memories: list[Memory]) -> EvaluationResult:
        expected = self._expected_statement(test.expected_behavior)
        response_words = set(self._words(response.response_text))
        required_terms = self._required_terms(expected)
        matched_terms = [term for term in required_terms if term in response_words]
        missing_terms = [term for term in required_terms if term not in response_words]
        evidence_ids = self._evidence_ids(test, memories)
        passed = bool(required_terms) and not missing_terms

        if passed:
            reason = (
                f"Passed {test.dimension.value}: the response matched all required ground-truth terms "
                f"({', '.join(matched_terms)}) using {len(evidence_ids)} linked evidence record(s)."
            )
        else:
            required_label = ", ".join(required_terms) if required_terms else "a testable expected behaviour"
            missing_label = ", ".join(missing_terms) if missing_terms else required_label
            reason = (
                f"Failed {test.dimension.value}: expected behaviour was '{expected}'. "
                f"The response did not demonstrate: {missing_label}. "
                f"Evidence records: {', '.join(evidence_ids) if evidence_ids else 'none linked to this test'}."
            )

        return EvaluationResult(
            evaluation_id=f"E{test.test_id[1:]}", test_id=test.test_id, response_id=response.response_id,
            passed=passed, failure_type=None if passed else test.dimension, reason=reason,
            evidence_memory_ids=evidence_ids, evaluator=self.VERSION,
        )

    @staticmethod
    def _expected_statement(expected_behavior: str) -> str:
        return expected_behavior.split(":", 1)[-1].strip()

    @classmethod
    def _words(cls, text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    @classmethod
    def _required_terms(cls, expected: str) -> list[str]:
        candidates = [word for word in cls._words(expected) if len(word) > 2 and word not in cls._STOP_WORDS]
        # The tail usually contains the actual fact/value after an explanatory
        # prefix, for example "Use the later record: PostgreSQL".
        selected = candidates[-3:] or cls._words(expected)[-1:]
        return list(dict.fromkeys(selected))

    @staticmethod
    def _evidence_ids(test: TestCase, memories: list[Memory]) -> list[str]:
        available = {memory.memory_id for memory in memories}
        return [memory_id for memory_id in test.supporting_memory_ids if memory_id in available]
