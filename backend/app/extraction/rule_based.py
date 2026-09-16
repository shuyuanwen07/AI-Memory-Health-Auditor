"""Deterministic, explainable memory extraction for the Foundation baseline.

The extractor favours conservative user-authored facts. It handles common
English transitions ("moved from X to Y"), contrast clauses, task-specific
requirements, and produces inspectable relationship evidence without an LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas import Conversation, Memory, MemoryRelationship, MemoryStatus, RelationshipType
from app.services.interfaces import MemoryExtractor

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD = re.compile(r"[a-z0-9][a-z0-9_+-]*")
_STOP_WORDS = {"a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for", "from", "has", "have", "i", "in", "is", "it", "my", "of", "on", "or", "our", "that", "the", "their", "this", "to", "was", "we", "with", "you", "your", "use", "used", "uses", "using", "now", "currently", "previously", "before", "later", "earlier", "generally", "really", "very"}
_MEMORY_SIGNALS = (" i ", " my ", " we ", " our ", "prefer", "favour", "favorite", "favourite", "require", "must", "need ", "uses ", " use ", "used ", "migrat", "switch", "chang", "moved ", "live ", "work ", "study", "assigned", "current ", "previous", "former", "now ", "based in", "located in", "my name is")
_UPDATE_SIGNALS = (" now", "currently", "no longer", "migrat", "switch", "chang", "moved", "replaced", "updated", "instead of", "these days", "from now on", "latest")
_CONTEXT_SIGNALS = ("current ", "currently", "this assignment", "this project", "for this task", "in this task", "for this assignment", "in this assignment", "for this project", "in this project", "in this context", "for now", "today's", "today s")
_PREFERENCE_SIGNALS = ("prefer", "preference", "rather", "favour", "favorite", "favourite")
_REQUIREMENT_SIGNALS = ("require", "must", "need", "should", "assigned", "mandatory", "avoid")
_CONFLICT_SIGNALS = ("conflict", "contradict", "inconsistent", "instead", "however", "but ")
_TEMPORAL_PAST = ("before", "previously", "formerly", "used to", "old ", "earlier")


@dataclass(frozen=True)
class _Candidate:
    value: str
    source_message_ids: tuple[str, ...]
    timestamp: object


class RuleBasedMemoryExtractor(MemoryExtractor):
    """Extract durable-looking user statements and explicit relationships."""

    VERSION = "rule-based-memory-extractor-v1"

    def extract(self, conversation: Conversation) -> list[Memory]:
        candidates = self._candidates(conversation)
        memories = [Memory(memory_id=f"M{index:03d}", conversation_id=conversation.conversation_id,
                           canonical_value=candidate.value, status=MemoryStatus.CANDIDATE,
                           source_message_ids=list(candidate.source_message_ids), timestamp=candidate.timestamp)
                    for index, candidate in enumerate(candidates, start=1)]
        for index, memory in enumerate(memories):
            memory.relationships = self._relationships(memory, memories[:index])
        return memories

    def _candidates(self, conversation: Conversation) -> list[_Candidate]:
        ordered = sorted(enumerate(conversation.messages), key=lambda item: (item[1].timestamp, item[0]))
        candidates: list[_Candidate] = []
        positions: dict[str, int] = {}
        for _, message in ordered:
            # Assistant text is never evidence of the user's real-world state.
            if message.role.strip().lower() != "user":
                continue
            for sentence in _SENTENCE_BOUNDARY.split(message.content):
                for fragment in self._statement_fragments(sentence):
                    value = self._normalise(fragment)
                    if not self._is_memory_statement(value):
                        continue
                    key = re.sub(r"\W+", " ", value.lower()).strip()
                    if key in positions:
                        prior = candidates[positions[key]]
                        if message.message_id not in prior.source_message_ids:
                            candidates[positions[key]] = _Candidate(prior.value, prior.source_message_ids + (message.message_id,), prior.timestamp)
                    else:
                        positions[key] = len(candidates)
                        candidates.append(_Candidate(value, (message.message_id,), message.timestamp))
        return candidates

    @classmethod
    def _statement_fragments(cls, sentence: str) -> list[str]:
        """Split only contrast/transition clauses, leaving ordinary lists alone."""
        sentence = sentence.strip()
        migration = re.match(r"^(?P<subject>(?:I|we|my\s+\w+|the\s+\w+|our\s+\w+))\s+(?:have\s+)?(?:migrated|switched|moved|changed)\s+from\s+(?P<old>[^,;.]+?)\s+to\s+(?P<new>[^,;.]+?)[.!?]*$", sentence, flags=re.IGNORECASE)
        if migration:
            subject, old, new = migration.group("subject"), migration.group("old").strip(), migration.group("new").strip()
            return [f"{subject} previously used {old}", f"{subject} now uses {new}"]
        although = re.match(r"^although\s+(.+?),\s*(.+)$", sentence, flags=re.IGNORECASE)
        if although:
            return [although.group(1), although.group(2)]
        return [part for part in re.split(r"\s*(?:;|,\s*(?:but|however|while)\s+)\s*", sentence, flags=re.IGNORECASE) if part]

    @staticmethod
    def _normalise(fragment: str) -> str:
        value = re.sub(r"\s+", " ", fragment).strip(" -•\t\"'")
        value = re.sub(r"^(?:please\s+)?remember\s+(?:that\s+)?", "", value, flags=re.IGNORECASE)
        return value.rstrip(".")

    @staticmethod
    def _is_memory_statement(value: str) -> bool:
        if len(value) < 8 or "?" in value:
            return False
        lower = f" {value.lower()} "
        if lower.strip() in {"hello", "thanks", "thank you", "okay", "ok"}:
            return False
        return any(signal in lower for signal in _MEMORY_SIGNALS) and bool(re.search(r"\b(?:i|we|my|our|the|this)\b", lower))

    def _relationships(self, current: Memory, prior_memories: list[Memory]) -> list[MemoryRelationship]:
        lower = current.canonical_value.lower()
        relationships: list[MemoryRelationship] = []
        related = self._best_related(current, prior_memories)
        if related and self._has_any(lower, _UPDATE_SIGNALS) and self._is_temporally_compatible(current, related):
            relationships.append(MemoryRelationship(type=RelationshipType.UPDATE, target_memory_id=related.memory_id))
        if self._has_any(lower, _CONTEXT_SIGNALS) and self._has_any(lower, _REQUIREMENT_SIGNALS):
            preference = self._best_preference(current, prior_memories)
            if preference and self._context_compatible(current, preference):
                relationships.append(MemoryRelationship(type=RelationshipType.CONTEXTUAL_OVERRIDE, target_memory_id=preference.memory_id))
        if related and self._is_conflict(current, related) and all(item.target_memory_id != related.memory_id for item in relationships):
            relationships.append(MemoryRelationship(type=RelationshipType.CONFLICT, target_memory_id=related.memory_id))
        return relationships

    def _best_related(self, current: Memory, prior_memories: list[Memory]) -> Memory | None:
        current_terms, category = self._topic_terms(current.canonical_value), self._category(current.canonical_value)
        choices: list[tuple[int, Memory]] = []
        for memory in prior_memories:
            score = self._overlap(current_terms, self._topic_terms(memory.canonical_value))
            if category and category == self._category(memory.canonical_value):
                score += 3
            if score:
                choices.append((score, memory))
        return max(choices, key=lambda item: (item[0], item[1].memory_id))[1] if choices else None

    def _best_preference(self, current: Memory, prior_memories: list[Memory]) -> Memory | None:
        preferences = [memory for memory in prior_memories if self._has_any(memory.canonical_value.lower(), _PREFERENCE_SIGNALS)]
        if not preferences:
            return None
        category, terms = self._category(current.canonical_value), self._topic_terms(current.canonical_value)
        return max(preferences, key=lambda memory: (self._overlap(terms, self._topic_terms(memory.canonical_value)) + (3 if category and category == self._category(memory.canonical_value) else 0), memory.memory_id))

    def _is_temporally_compatible(self, current: Memory, prior: Memory) -> bool:
        if self._overlap(self._topic_terms(current.canonical_value), self._topic_terms(prior.canonical_value)):
            return True
        current_category, prior_category = self._category(current.canonical_value), self._category(prior.canonical_value)
        return bool(current_category and current_category == prior_category) or self._has_any(prior.canonical_value.lower(), _TEMPORAL_PAST)

    def _context_compatible(self, current: Memory, preference: Memory) -> bool:
        current_category, preference_category = self._category(current.canonical_value), self._category(preference.canonical_value)
        return bool(current_category and current_category == preference_category) or bool(self._overlap(self._topic_terms(current.canonical_value), self._topic_terms(preference.canonical_value)))

    def _is_conflict(self, current: Memory, prior: Memory) -> bool:
        current_text, prior_text = current.canonical_value.lower(), prior.canonical_value.lower()
        same_topic = bool(self._overlap(self._topic_terms(current_text), self._topic_terms(prior_text))) or (self._category(current_text) is not None and self._category(current_text) == self._category(prior_text))
        explicit = self._has_any(current_text, _CONFLICT_SIGNALS)
        polarity_changed = self._negated(current_text) != self._negated(prior_text)
        both_requirements = self._has_any(current_text, _REQUIREMENT_SIGNALS) and self._has_any(prior_text, _REQUIREMENT_SIGNALS)
        return same_topic and (explicit or polarity_changed or both_requirements)

    @staticmethod
    def _negated(text: str) -> bool:
        return bool(re.search(r"\b(?:no|not|never|avoid|without|cannot|can't|don't|do not)\b", text))

    @staticmethod
    def _has_any(text: str, signals: tuple[str, ...]) -> bool:
        return any(signal in text for signal in signals)

    @staticmethod
    def _topic_terms(value: str) -> set[str]:
        return {token.rstrip("s") if len(token) > 4 and token.endswith("s") else token for token in _WORD.findall(value.lower()) if len(token) > 2 and token not in _STOP_WORDS}

    @staticmethod
    def _overlap(left: set[str], right: set[str]) -> int:
        return len(left & right)

    @staticmethod
    def _category(value: str) -> str | None:
        text = value.lower()
        if re.search(r"\b(?:mysql|postgres(?:ql)?|mongodb|sqlite|database|sql)\b", text): return "database"
        if re.search(r"\b(?:python|java|rust|javascript|typescript|(?:programming|scripting)\s+languages?)\b", text): return "programming-language"
        if re.search(r"\b(?:sydney|melbourne|london|based in|located in|live in|relocat)\b", text): return "location"
        if re.search(r"\b(?:remote|from home|office|hybrid)\b", text): return "working-arrangement"
        if re.search(r"\b(?:backend|service|application|system)\b", text): return "software-system"
        return None
