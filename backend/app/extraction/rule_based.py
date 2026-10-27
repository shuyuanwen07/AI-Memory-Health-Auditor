"""Deterministic, explainable memory extraction for the Foundation baseline.

The extractor favours conservative user-authored facts. It handles common
English transitions ("moved from X to Y"), contrast clauses, task-specific
requirements, and produces inspectable relationship evidence without an LLM.
"""
from __future__ import annotations

import re
from app.services.location_facts import location_value
from app.services.deployment_facts import deployment_region_value
from dataclasses import dataclass

from app.schemas import Conversation, Memory, MemoryRelationship, MemoryStatus, RelationshipType
from app.services.memory_topics import is_language_topic
from app.services.interfaces import MemoryExtractor
from app.services.fact_identity import fact_fingerprint
from app.services.meeting_facts import PLATFORM_PATTERN, exclusive_platform_value, is_meeting_platform_topic, equivalent_exclusive_platform_rules

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")
_TITLE_END = re.compile(r"\b(?:St|Dr|Mr|Mrs|Ms|Prof|Sr|Jr)\.$")
_WORD = re.compile(r"[a-z0-9][a-z0-9_+-]*")
_STOP_WORDS = {"a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for", "from", "has", "have", "i", "in", "is", "it", "my", "of", "on", "or", "our", "that", "the", "their", "this", "to", "was", "we", "with", "you", "your", "use", "used", "uses", "using", "now", "currently", "previously", "before", "later", "earlier", "generally", "really", "very"}
_MEMORY_SIGNALS = (" i ", " my ", " we ", " our ", "prefer", "favour", "favorite", "favourite", "require", "must", "need ", "uses ", " use ", "used ", "migrat", "switch", "chang", "moved ", "live ", "work ", "study", "assigned", "current ", "previous", "former", "now ", "based in", "located in", "my name is")
_UPDATE_SIGNALS = (" now", "currently", "current city", "current location", "no longer", "migrat", "switch", "chang", "moved", "relocat", "replaced", "updated", "instead of", "these days", "from now on", "latest")
_CONTEXT_SIGNALS = ("current ", "currently", "this assignment", "this project", "for this task", "in this task", "for this assignment", "in this assignment", "for this project", "in this project", "in this context", "for now", "today's", "today s")
_PREFERENCE_SIGNALS = ("prefer", "preference", "rather", "favour", "favorite", "favourite")
_REQUIREMENT_SIGNALS = ("require", "must", "need", "should", "assigned", "mandatory", "avoid")
_CONFLICT_SIGNALS = ("conflict", "contradict", "inconsistent", "instead", "however", "but ")
_TEMPORAL_PAST = ("before", "previously", "formerly", "used to", "old ", "earlier")
_PLATFORM = PLATFORM_PATTERN
_WITHDRAWN_PLATFORM = re.compile(rf"\b(?P<old>{_PLATFORM})\s+requirement\s+(?:is|has\s+been)\s+(?:withdrawn|revoked|cancelled|canceled)\b", re.I)
_PLATFORM_REPLACEMENT = re.compile(
    _WITHDRAWN_PLATFORM.pattern + rf"\s*;\s*(?:please\s+)?use\s+(?P<new>{_PLATFORM})\s+instead\s*[.!?]*$", re.I,
)


@dataclass(frozen=True)
class _Candidate:
    value: str
    source_message_ids: tuple[str, ...]
    timestamp: object


class RuleBasedMemoryExtractor(MemoryExtractor):
    """Extract durable-looking user statements and explicit relationships."""

    VERSION = "rule-based-memory-extractor-v27"

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
        # Mixed known/unknown timezones cannot establish absolute chronology.
        # Preserve supplied message order rather than guessing a server zone.
        offsets = {message.timestamp.utcoffset() is not None for message in conversation.messages}
        ordered = (list(enumerate(conversation.messages)) if len(offsets) > 1 else
                   sorted(enumerate(conversation.messages), key=lambda item: (item[1].timestamp, item[0])))
        candidates: list[_Candidate] = []
        positions: dict[str, int] = {}
        for _, message in ordered:
            # Assistant text is never evidence of the user's real-world state.
            if message.role.strip().lower() != "user":
                continue
            for sentence in self._sentences(message.content):
                for fragment in self._statement_fragments(sentence):
                    value = self._normalise(fragment)
                    replacement = self._resolved_platform_replacement(value, candidates)
                    sources = (message.message_id,)
                    if replacement:
                        value, inherited_sources = replacement
                        sources = tuple(dict.fromkeys((*inherited_sources, message.message_id)))
                    if not self._is_memory_statement(value):
                        continue
                    key = fact_fingerprint(value)
                    if key in positions:
                        prior = candidates[positions[key]]
                        candidates[positions[key]] = _Candidate(prior.value, tuple(dict.fromkeys((*prior.source_message_ids, *sources))), prior.timestamp)
                    else:
                        positions[key] = len(candidates)
                        candidates.append(_Candidate(value, sources, message.timestamp))
        return candidates

    @classmethod
    def _resolved_platform_replacement(cls, value: str, prior: list[_Candidate]) -> tuple[str, tuple[str, ...]] | None:
        """Resolve only explicit replacements with one identifiable source scope.

        Preserve the replacement clause and its provenance; never guess which
        project an unscoped correction belongs to when multiple projects match.
        Conditional and denied withdrawals remain unmodified review candidates.
        """
        match = _PLATFORM_REPLACEMENT.search(value)
        if not match or re.search(r"\b(?:if|unless|might|may|could|hypothetical)\b", value[:match.start()], re.I):
            return None
        from app.services.memory_entities import named_projects
        projects = named_projects(value)
        applicable = [candidate for candidate in prior
                      if cls._category(candidate.value) == 'meeting-platform'
                      and re.search(rf"\b(?:must\s+use|should\s+use|requires?|uses?)\s+{re.escape(match['old'])}\b", candidate.value, re.I)
                      and (not projects or named_projects(candidate.value) == projects)]
        if len(applicable) != 1:
            return None
        source = applicable[0]
        subject = re.split(r"\s+(?:must\s+use|should\s+use|requires?|uses?)\s+", source.value, maxsplit=1, flags=re.I)[0]
        return (f"{subject} now requires {match['new']} instead of {match['old']}; the {match['old']} requirement has been withdrawn", source.source_message_ids)

    @staticmethod
    def _sentences(text: str) -> list[str]:
        """Keep common titles inside named entities, preserving original text."""
        start = 0
        sentences: list[str] = []
        for boundary in _SENTENCE_BOUNDARY.finditer(text):
            # Newlines remain explicit boundaries. Protect only a title followed
            # by a capitalised name; ordinary periods still end sentences.
            if ("\n" not in boundary.group() and _TITLE_END.search(text[:boundary.start()])
                    and re.match(r"[A-Z]", text[boundary.end():])):
                continue
            sentences.append(text[start:boundary.start()])
            start = boundary.end()
        sentences.append(text[start:])
        return sentences

    @classmethod
    def _statement_fragments(cls, sentence: str) -> list[str]:
        """Split only contrast/transition clauses, leaving ordinary lists alone."""
        sentence = sentence.strip()
        migration = re.match(r"^(?P<subject>(?:I|we|my\s+\w+|the\s+\w+|our\s+\w+))\s+(?:have\s+)?(?:migrated|switched|moved|changed)\s+from\s+(?P<old>[^,;.]+?)\s+to\s+(?P<new>[^,;.]+?)[.!?]*$", sentence, flags=re.IGNORECASE)
        if migration:
            subject, old, new = migration.group("subject"), migration.group("old").strip(), migration.group("new").strip()
            return [f"{subject} previously used {old}", f"{subject} now uses {new}"]
        # A temporal contrast may repeat the verb while omitting its subject.
        # Complete only this narrow form; explicit second subjects remain intact.
        elided = re.match(
            r"^(?P<subject>.+?)\s+(?:used|uses|use)\s+[^,;.]+,\s*(?:but|however|while)\s+"
            r"(?P<clause>(?:now|currently)\s+(?:uses|use)\s+[^,;.]+)[.!?]*$",
            sentence, flags=re.IGNORECASE,
        )
        if elided:
            first = re.split(r",\s*(?:but|however|while)\s+", sentence, maxsplit=1, flags=re.IGNORECASE)[0]
            return [first, f"{elided.group('subject')} {elided.group('clause')}"]
        although = re.match(r"^although\s+(.+?),\s*(.+)$", sentence, flags=re.IGNORECASE)
        if although:
            return [although.group(1), although.group(2)]
        # Resolution metadata belongs to the policy it qualifies. Splitting
        # this clause loses the explicit statement that chronology cannot
        # resolve the contradiction.
        if re.search(r";\s*neither\b.*\bsupersedes\b", sentence, re.IGNORECASE):
            return [sentence]
        if re.search(r"\b(?:withdrawn|revoked|cancelled|canceled)\b[^.!?]*;\s*(?:please\s+)?use\b[^.!?]*\binstead\b", sentence, re.I):
            return [sentence]
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
        from app.services.memory_entities import named_projects
        subject = bool(re.search(r"\b(?:i|we|my|our|the|this)\b", lower)) or bool(named_projects(value))
        explicit_policy = bool(re.search(r"\b(?:policy|requirement|rule)\b.*\b(?:requires?|must|mandates?)\b", lower))
        return (any(signal in lower for signal in _MEMORY_SIGNALS) or exclusive_platform_value(value) is not None or deployment_region_value(value) is not None) and (subject or explicit_policy)

    def _relationships(self, current: Memory, prior_memories: list[Memory]) -> list[MemoryRelationship]:
        lower = current.canonical_value.lower()
        relationships: list[MemoryRelationship] = []
        # A statement denying a change or separating unrelated topics is not
        # an UPDATE/CONFLICT merely because it contains change/negation words.
        if (re.search(r"\b(?:not|never)\s+(?:a\s+)?database\s+change\b|\bnone\s+of\s+that\s+was\s+a\s+database\s+change\b", lower)
            or (re.search(r"\b(?:food|diet|lunch)\b", lower)
                and re.search(r"\b(?:separate|no need|distinct|unrelated)\b", lower)
                and re.search(r"\b(?:technical|programming|databases?|deployment)\b", lower))):
            return []
        from app.services.memory_entities import named_projects
        withdrawal = _WITHDRAWN_PLATFORM.search(current.canonical_value)
        if withdrawal:
            scopes = named_projects(current.canonical_value)
            matching = [memory for memory in prior_memories
                        if self._category(memory.canonical_value) == 'meeting-platform'
                        and re.search(rf"\b(?:must\s+use|should\s+use|requires?|uses?)\s+{re.escape(withdrawal['old'])}\b", memory.canonical_value, re.I)
                        and (not scopes or named_projects(memory.canonical_value) == scopes)]
            if len(matching) > 1:
                return []
            # An elided source correction retains the original full wording.
            # No relationship is asserted until its scope is unambiguous.
            if not scopes and not self._has_any(lower, _UPDATE_SIGNALS):
                return []
        related = self._best_related(current, prior_memories)
        if withdrawal and matching and self._has_any(lower, _UPDATE_SIGNALS):
            related = matching[0]
        if (self._has_any(lower, _CONTEXT_SIGNALS) or re.search(r"\b(?:assignment|task|project)\b", lower)) and self._has_any(lower, _REQUIREMENT_SIGNALS):
            preference = self._best_preference(current, prior_memories)
            if preference and self._context_compatible(current, preference):
                relationships.append(MemoryRelationship(type=RelationshipType.CONTEXTUAL_OVERRIDE, target_memory_id=preference.memory_id))
        # A task-specific requirement overrides a preference only for that
        # task. Wording such as "instead of my usual preference" must not
        # retire the general preference from the memory store.
        if (related and self._has_any(lower, _UPDATE_SIGNALS)
            and self._is_temporally_compatible(current, related)
            and not any(item.type == RelationshipType.CONTEXTUAL_OVERRIDE
                        and item.target_memory_id == related.memory_id for item in relationships)):
            relationships.insert(0, MemoryRelationship(type=RelationshipType.UPDATE, target_memory_id=related.memory_id))
        if related and self._is_conflict(current, related) and all(item.target_memory_id != related.memory_id for item in relationships):
            relationships.append(MemoryRelationship(type=RelationshipType.CONFLICT, target_memory_id=related.memory_id))
        return relationships

    def _best_related(self, current: Memory, prior_memories: list[Memory]) -> Memory | None:
        from app.services.memory_entities import named_projects
        current_projects = named_projects(current.canonical_value)
        current_terms, category = self._topic_terms(current.canonical_value), self._category(current.canonical_value)
        # Generic topic overlap ("I need", "I didn't know", "service") does
        # not identify a fact field whose value changed. Unknown domains need
        # semantic review; guessing relationships here protects unrelated
        # records as conflicts and can evict the actual remembered facts.
        if category is None or category == "software-system":
            return None
        choices: list[tuple[int, Memory]] = []
        for memory in prior_memories:
            prior_projects = named_projects(memory.canonical_value)
            if current_projects and prior_projects and current_projects.isdisjoint(prior_projects):
                continue
            prior_category = self._category(memory.canonical_value)
            if prior_category != category:
                continue
            score = self._overlap(current_terms, self._topic_terms(memory.canonical_value))
            if category and category == self._category(memory.canonical_value):
                score += 3
            if score:
                choices.append((score, memory))
        return max(choices, key=lambda item: (item[0], item[1].memory_id))[1] if choices else None

    def _best_preference(self, current: Memory, prior_memories: list[Memory]) -> Memory | None:
        category = self._category(current.canonical_value)
        preferences = [memory for memory in prior_memories
                       if self._has_any(memory.canonical_value.lower(), _PREFERENCE_SIGNALS)
                       and self._context_compatible(current, memory)]
        if not preferences:
            return None
        category, terms = self._category(current.canonical_value), self._topic_terms(current.canonical_value)
        return max(preferences, key=lambda memory: (self._overlap(terms, self._topic_terms(memory.canonical_value)) + (3 if category and category == self._category(memory.canonical_value) else 0), memory.memory_id))

    def _is_temporally_compatible(self, current: Memory, prior: Memory) -> bool:
        current_topic, prior_topic = self._category(current.canonical_value), self._category(prior.canonical_value)
        if current_topic is None or current_topic == "software-system" or current_topic != prior_topic:
            return False
        # A shared project or person name is not a shared fact field.
        if current_topic and prior_topic and current_topic != prior_topic:
            return False
        if self._overlap(self._topic_terms(current.canonical_value), self._topic_terms(prior.canonical_value)):
            return True
        current_category, prior_category = self._category(current.canonical_value), self._category(prior.canonical_value)
        return bool(current_category and current_category == prior_category) or self._has_any(prior.canonical_value.lower(), _TEMPORAL_PAST)

    def _context_compatible(self, current: Memory, preference: Memory) -> bool:
        current_topic, prior_topic = self._category(current.canonical_value), self._category(preference.canonical_value)
        if current_topic is None or current_topic == "software-system" or current_topic != prior_topic:
            return False
        # A shared project or person name is not a shared fact field.
        if current_topic and prior_topic and current_topic != prior_topic:
            return False
        current_category, preference_category = self._category(current.canonical_value), self._category(preference.canonical_value)
        return bool(current_category and current_category == preference_category) or bool(self._overlap(self._topic_terms(current.canonical_value), self._topic_terms(preference.canonical_value)))

    def _is_conflict(self, current: Memory, prior: Memory) -> bool:
        current_topic, prior_topic = self._category(current.canonical_value), self._category(prior.canonical_value)
        if current_topic is None or current_topic == "software-system" or current_topic != prior_topic:
            return False
        # A shared project or person name is not a shared fact field.
        if current_topic and prior_topic and current_topic != prior_topic:
            return False
        current_text, prior_text = current.canonical_value.lower(), prior.canonical_value.lower()
        current_region, prior_region = deployment_region_value(current_text), deployment_region_value(prior_text)
        if current_region and prior_region:
            return current_region != prior_region
        if equivalent_exclusive_platform_rules(current_text, prior_text):
            return False
        same_topic = bool(self._overlap(self._topic_terms(current_text), self._topic_terms(prior_text))) or (self._category(current_text) is not None and self._category(current_text) == self._category(prior_text))
        explicit = self._has_any(current_text, _CONFLICT_SIGNALS)
        polarity_changed = self._negated(current_text) != self._negated(prior_text)
        both_requirements = (self._has_any(current_text, _REQUIREMENT_SIGNALS) or exclusive_platform_value(current_text) is not None) and (self._has_any(prior_text, _REQUIREMENT_SIGNALS) or exclusive_platform_value(prior_text) is not None)
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
        if deployment_region_value(value): return "deployment-region"
        if re.search(r"\b(?:mysql|postgres(?:ql)?|mongodb|sqlite|redis|mariadb|cassandra|dynamodb|database|sql)\b", text): return "database"
        if re.search(r"\b(?:logs?|logging|object storage|storage bucket)\b", text): return "log-storage"
        if re.search(r"\b(?:secrets?|credentials?|environment variables?|config(?:uration)? files?)\b", text): return "secret-configuration"
        if is_meeting_platform_topic(text): return "meeting-platform"
        if is_language_topic(text): return "programming-language"
        if location_value(text) or re.search(r"\b(?:sydney|melbourne|london|relocat)\b", text): return "location"
        if re.search(r"\b(?:remote|from home|office|hybrid)\b", text): return "working-arrangement"
        if re.search(r"\b(?:concise|detailed|verbose|brief|short|long)\s+(?:output|responses?|answers?)\b", text): return "output-style"
        if re.search(r"\b(?:older|newer|current|previous|software|development)\s+tools?\b", text): return "tool-choice"
        if re.search(r"\b(?:backend|service|application|system)\b", text): return "software-system"
        return None
