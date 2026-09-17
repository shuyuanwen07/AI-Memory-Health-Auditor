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

    VERSION = "rule-based-v4"
    _STOP_WORDS = frozenset({
        "about", "after", "before", "current", "fact", "from", "later", "record",
        "should", "state", "that", "the", "this", "with", "would",
    })

    def evaluate(self, test: TestCase, response: TargetResponse, memories: list[Memory]) -> EvaluationResult:
        expected = self._expected_statement(test.expected_behavior)
        response_words = set(self._words(response.response_text))
        required_terms = self._required_terms(expected)
        matched_terms = [
            term for term in required_terms
            if term in response_words and not self._term_is_negated(term, response.response_text)
        ]
        missing_terms = [term for term in required_terms if term not in matched_terms]
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
        """Select the answer-bearing part of a generated expectation.

        ``expected_behavior`` is written for a human reviewer, so phrases
        such as "generally prefer" or "is required" explain *why* an answer
        is right rather than being text that a target must parrot.  The
        evaluator therefore checks the concrete tail value, with an explicit
        ``X is required`` rule for contextual requirements.  This deliberately
        stays lexical and deterministic; an LLM judge remains a separate,
        optional evaluator implementation.
        """
        requirement = re.search(
            r"\b([a-z0-9][a-z0-9_+-]*)\s+is\s+(?:required|mandatory)\b",
            expected.lower(),
        )
        if requirement:
            return [requirement.group(1)]
        # A constraint such as "must use PostgreSQL rather than SQLite" has
        # one positive answer and one explicitly rejected alternative. The
        # answer is the first value, not the final word of the sentence.
        preference = re.search(
            r"\b(?:use|uses|using)\s+([a-z0-9][a-z0-9_+-]*)\s+(?:rather\s+than|instead\s+of)\s+[a-z0-9][a-z0-9_+-]*\b",
            expected.lower(),
        )
        if preference:
            return [preference.group(1)]
        candidates = [word for word in cls._words(expected) if len(word) > 2 and word not in cls._STOP_WORDS]
        # The tail is the answer value in the generated templates, for example
        # "Use the later record: PostgreSQL".  Requiring surrounding prose
        # would incorrectly fail a concise, correct answer such as "Python".
        selected = candidates[-1:] or cls._words(expected)[-1:]
        return list(dict.fromkeys(selected))

    @staticmethod
    def _term_is_negated(term: str, response_text: str) -> bool:
        """Reject a value explicitly described as the wrong answer.

        This is a narrow deterministic guard, not a replacement for semantic
        LLM judging. It prevents clear false positives such as "do not use
        PostgreSQL" while retaining a concise factual answer like
        "PostgreSQL".
        """
        quoted = re.escape(term)
        text = response_text.lower()
        before = rf"\b(?:not|never|avoid|without|rather\s+than|instead\s+of)\b(?:\s+[a-z0-9_+-]+){{0,3}}\s+{quoted}\b"
        after = rf"\b{quoted}\b(?:\s+[a-z0-9_+-]+){{0,2}}\s+\b(?:not|never|incorrect|wrong)\b"
        return bool(re.search(before, text) or re.search(after, text))

    @staticmethod
    def _evidence_ids(test: TestCase, memories: list[Memory]) -> list[str]:
        available = {memory.memory_id for memory in memories}
        return [memory_id for memory_id in test.supporting_memory_ids if memory_id in available]
