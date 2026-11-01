"""Conflict-preserving seeds for current agent planning; legacy seeds stay versioned."""
import re

from app.schemas import Dimension, RelationshipType, TestType
from app.test_generator.rule_based import RuleBasedTestGenerator


class ConflictPreservingTestGenerator(RuleBasedTestGenerator):
    VERSION = "rule-based-conflict-preserving-v1"

    def generate(self, memories, audit):
        self._planning_memories = {memory.memory_id: memory for memory in memories}
        return super().generate(memories, audit)

    def _conflict_partners(self, memory_id):
        partners = set()
        for memory in self._planning_memories.values():
            for relation in memory.relationships:
                if relation.type != RelationshipType.CONFLICT or relation.target_memory_id not in self._planning_memories:
                    continue
                if memory.memory_id == memory_id:
                    partners.add(relation.target_memory_id)
                elif relation.target_memory_id == memory_id:
                    partners.add(memory.memory_id)
        return [self._planning_memories[mid] for mid in sorted(partners) if mid != memory_id]

    def _freshness(self, current, prior):
        disputed = self._conflict_partners(current.memory_id)
        if not disputed:
            return super()._freshness(current, prior)
        return (Dimension.FRESHNESS,
                f"For the recorded {self._scoped_topic(current, prior)}, what changed from the earlier record, and what must be clarified before deciding the current state?",
                "Explain the recorded update, identify both conflicting current records and ask the user to clarify which applies.",
                list(dict.fromkeys([prior.memory_id, current.memory_id, *[m.memory_id for m in disputed]])),
                TestType.CONTEXTUAL)

    def _appropriate_use(self, contextual, preference):
        disputed = self._conflict_partners(contextual.memory_id) + self._conflict_partners(preference.memory_id)
        candidate = super()._appropriate_use(contextual, preference)
        if not disputed:
            return candidate
        dimension, prompt, _, evidence, kind = candidate
        return (dimension,
                prompt + " If the recorded preferences conflict, identify both and request clarification before deciding the general preference.",
                "Apply the task-specific requirement where it is unambiguous; identify both conflicting general records and ask the user to clarify the general preference.",
                list(dict.fromkeys(evidence + [m.memory_id for m in disputed])), kind)

    @staticmethod
    def _source_subject(memory):
        match = re.match(r"^\s*(the (?:user['’]s\s+)?[A-Za-z][A-Za-z -]{0,60}?)\s+(?:is|was|has|have|uses|contains)\b", memory.canonical_value, re.I)
        if not match:
            return None
        subject = match.group(1).strip()
        if len(subject.split()) > 7 or re.search(r"\b(?:and|or|because|but|not|only|approved|permitted|prohibited|required|preferred|final|current)\b", subject, re.I):
            return None
        predicate = memory.canonical_value[match.end():].lower()
        words = [word.lower() for word in re.findall(r"[A-Za-z]+", subject) if len(word) >= 4]
        if any(re.search(r"\b" + re.escape(word) + r"\b", predicate) for word in words):
            return None
        return subject

    @classmethod
    def _scoped_topic(cls, *memories):
        if cls._topic(*memories) == "stored information" and len(memories) > 1:
            subjects = [re.search(r"\b(the user['’]s\s+[A-Za-z][A-Za-z -]{0,45}?)\s+(?:is|was|has|uses|contains)\b", m.canonical_value, re.I) for m in memories]
            if all(subjects):
                values = {match.group(1).strip().lower() for match in subjects}
                if len(values) == 1:
                    value = next(iter(values))
                    if len(value.split()) <= 7 and not re.search(r"\b(?:and|or|not|only|current|final|preferred|required)\b", value):
                        return value
        return super()._scoped_topic(*memories)
