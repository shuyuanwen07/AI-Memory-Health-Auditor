"""Deterministic behavioural test generation from confirmed ground truth."""
from __future__ import annotations

import re

from app.schemas import AuditRun, Dimension, Memory, RelationshipType, TestCase, TestType
from app.services.interfaces import TestGenerator


class RuleBasedTestGenerator(TestGenerator):
    """Generate traceable tests without leaking a canonical value into prompts.

    The evaluator-facing ``expected_behavior`` keeps the canonical value. The
    target-facing prompt asks only about an abstract topic, so a passing model
    must rely on its controlled memory rather than copy an answer from a prompt.
    """

    # Changed prompt wording is a protocol change; retain a distinct version
    # so pre-change and post-change runs are never compared as one template.
    VERSION = "rule-based-v4"

    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
        by_id = {memory.memory_id: memory for memory in memories}
        candidates: list[tuple[Dimension, str, str, list[str], TestType]] = []
        for memory in memories:
            for relationship in memory.relationships:
                prior = by_id.get(relationship.target_memory_id)
                if prior is None:
                    continue
                if relationship.type == RelationshipType.UPDATE:
                    candidates.extend((self._freshness(memory, prior), self._update_conflict_resolution(memory, prior)))
                elif relationship.type == RelationshipType.CONFLICT:
                    candidates.append(self._explicit_conflict_resolution(memory, prior))
                elif relationship.type == RelationshipType.CONTEXTUAL_OVERRIDE:
                    candidates.append(self._appropriate_use(memory, prior))

        superseded = {relationship.target_memory_id for memory in memories for relationship in memory.relationships if relationship.type == RelationshipType.UPDATE}
        for memory in memories:
            if memory.memory_id not in superseded and not memory.relationships:
                candidates.append(self._accuracy(memory))

        unique = self._deduplicate(self._balanced_order(candidates))
        return [TestCase(test_id=f"T{index:03d}", run_id=audit.run_id, dimension=dimension,
                         prompt=prompt, expected_behavior=expected, supporting_memory_ids=memory_ids,
                         generator_version=self.VERSION, test_type=test_type,
                         target_memory_context=[by_id[memory_id].canonical_value for memory_id in memory_ids])
                for index, (dimension, prompt, expected, memory_ids, test_type) in enumerate(unique[:audit.test_budget], start=1)]

    @classmethod
    def _accuracy(cls, memory: Memory) -> tuple[Dimension, str, str, list[str], TestType]:
        topic = cls._topic(memory)
        if topic == "programming-language choice" and re.search(r"\b(?:prefer|preference|favour|favorite|favourite)\b", memory.canonical_value, re.I):
            prompt = "What programming language does the user generally prefer? State the language only."
        else:
            prompt = f"What is the user's recorded {topic}? State the relevant fact only."
        return (Dimension.ACCURACY, prompt,
                f"State the recorded fact: {memory.canonical_value}.", [memory.memory_id], TestType.DIRECT)

    @classmethod
    def _freshness(cls, current: Memory, prior: Memory) -> tuple[Dimension, str, str, list[str], TestType]:
        return (Dimension.FRESHNESS,
                f"Which {cls._topic(current, prior)} should the user use now? State the concrete value first, then explain in one short sentence why the newer memory overrides the older one.",
                f"Use the later record: {current.canonical_value}.", [prior.memory_id, current.memory_id], TestType.CONTEXTUAL)

    @classmethod
    def _update_conflict_resolution(cls, current: Memory, prior: Memory) -> tuple[Dimension, str, str, list[str], TestType]:
        return (Dimension.CONFLICT_RESOLUTION,
                f"The user's earlier and later memories about {cls._topic(current, prior)} conflict. Which concrete value should be used now? State it first, then explain in one sentence how the later update resolves the conflict.",
                f"Explain that the later record takes precedence: {current.canonical_value}.", [prior.memory_id, current.memory_id], TestType.INDIRECT)

    @classmethod
    def _explicit_conflict_resolution(cls, current: Memory, prior: Memory) -> tuple[Dimension, str, str, list[str], TestType]:
        return (Dimension.CONFLICT_RESOLUTION,
                f"Two remembered constraints about the user's {cls._topic(current, prior)} conflict. How should the conflict be handled before answering?",
                "Acknowledge the conflict and request clarification before relying on either record.", [prior.memory_id, current.memory_id], TestType.INDIRECT)

    @classmethod
    def _appropriate_use(cls, contextual: Memory, preference: Memory) -> tuple[Dimension, str, str, list[str], TestType]:
        return (Dimension.APPROPRIATE_USE,
                f"For the current {cls._topic(contextual, preference)}, a general preference conflicts with a current requirement. State the requirement that applies now first, then briefly explain why it overrides the preference.",
                f"Follow the contextual requirement: {contextual.canonical_value}.", [preference.memory_id, contextual.memory_id], TestType.PARAPHRASED)

    @staticmethod
    def _deduplicate(candidates: list[tuple[Dimension, str, str, list[str], TestType]]) -> list[tuple[Dimension, str, str, list[str], TestType]]:
        unique: list[tuple[Dimension, str, str, list[str], TestType]] = []
        seen: set[tuple[Dimension, tuple[str, ...]]] = set()
        for candidate in candidates:
            key = (candidate[0], tuple(candidate[3]))
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        return unique

    @staticmethod
    def _balanced_order(candidates: list[tuple[Dimension, str, str, list[str], TestType]]) -> list[tuple[Dimension, str, str, list[str], TestType]]:
        """Round-robin dimensions, preserving coverage whenever the budget allows."""
        groups = {dimension: [item for item in candidates if item[0] == dimension] for dimension in Dimension}
        result: list[tuple[Dimension, str, str, list[str], TestType]] = []
        while any(groups.values()):
            for dimension in Dimension:
                if groups[dimension]:
                    result.append(groups[dimension].pop(0))
        return result

    @staticmethod
    def _topic(*memories: Memory) -> str:
        text = " ".join(memory.canonical_value.lower() for memory in memories)
        if re.search(r"\b(?:mysql|postgres(?:ql)?|mongodb|sqlite|database|sql)\b", text): return "database technology"
        if re.search(r"\b(?:python|java|rust|javascript|typescript|(?:programming|scripting)\s+languages?)\b", text): return "programming-language choice"
        if re.search(r"\b(?:based in|located in|live in|sydney|melbourne|london)\b", text): return "location"
        if re.search(r"\b(?:remote|from home|office|hybrid)\b", text): return "working arrangement"
        if re.search(r"\b(?:assignment|project|task|require|must|need|mandatory)\b", text): return "current task"
        if re.search(r"\b(?:prefer|preference|favour|favorite|favourite)\b", text): return "preference"
        return "stored information"
