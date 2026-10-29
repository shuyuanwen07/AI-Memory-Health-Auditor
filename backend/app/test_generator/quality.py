"""Deterministic quality and grounding checks for generated behavioural tests.

The check is deliberately local and inspectable.  An LLM or human-review
implementation can replace it through ``TestQualityValidator`` without
changing generators, test cases, or audit execution.
"""
from __future__ import annotations

import re
import unicodedata
from app.services.location_facts import location_value
from app.services.deployment_facts import deployment_region_value

from app.schemas import (
    GroundingStatus,
    Dimension,
    RelationshipType,
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

    VERSION = "rule-based-quality-v24"
    _STOP_WORDS = {"a", "an", "the", "is", "are", "was", "were", "to", "of", "in", "on", "for", "that"}

    @staticmethod
    def normalize_prompt(prompt: str) -> str:
        """Return the same Unicode-aware key used by the suite duplicate gate."""
        return "".join(
            char for char in unicodedata.normalize("NFKC", prompt).lower()
            if unicodedata.category(char)[0] in {"L", "N"}
        )

    @staticmethod
    def validate_suite(tests: list[TestCase]) -> str | None:
        seen: set[str] = set()
        for test in tests:
            # Preserve non-Latin text; ASCII-only normalisation collapsed every
            # Chinese-only question to the same empty key.
            prompt = RuleBasedTestQualityValidator.normalize_prompt(test.prompt)
            if not prompt:
                return "Question wording must contain readable letters or numbers."
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
        for memory in support:
            identity = memory.memory_id
            if not re.fullmatch(r'M(?:\d{3}|[A-Fa-f0-9]{16,})', identity):
                continue
            identity_pattern = r'(?<!\w)' + re.escape(identity) + r'(?!\w)'
            # A real identifier supplied by the user can legitimately be an
            # answer. Auditor-only row identities cannot be target obligations.
            if any(re.search(identity_pattern, item.canonical_value) for item in support):
                continue
            if re.search(identity_pattern, test.prompt + '\n' + test.expected_behavior):
                return self._result(False, True,
                    "Questions and expected answers must not require hidden audit memory identifiers. "
                    "Use source facts and relationships; keep memory identifiers only in supporting evidence metadata.")
        if re.search(r"\brecorded\s+stored\s+information\b", test.prompt, re.I):
            return self._result(False, True, "The question does not identify the fact or event being tested; replace the generic stored-information wording before execution.")
        # User-derived profile facts must not become claims about the answering AI.
        # This is a bounded subject check, not a semantic correctness guarantee.
        user_profile = [memory for memory in support if memory is not None
                        and (re.search(r"\b(?:I am|I live|I generally prefer|the user|user is)\b", memory.canonical_value, re.I)
                             or re.match(r"\s*(?:prefers?\b|(?:based|located|living|resides?|lives?)\s+(?:in|at)\b|Location\s*:)", memory.canonical_value, re.I))]
        if user_profile and re.search(r"\b(?:the AI|the assistant|the model)\s+(?:is|lives|prefers|uses|requires)\b", test.expected_behavior, re.I):
            return self._result(False, False, "The expected answer attributes user evidence to the AI; preserve the original subject.")
        if any(location_value(memory.canonical_value) for memory in user_profile + [memory for memory in support if memory is not None and re.match(r"\s*Location\s*:", memory.canonical_value, re.I)]) and re.search(
            r"\bwhere\b[^?!]{0,80}\byou\b|\b(?:which|what)\s+(?:is\s+)?(?:your\s+)?(?:current\s+)?(?:city|location|place)\b[^?!]{0,60}\byou\b|\byour own location\b", test.prompt, re.I
        ) and not re.search(r"\buser\b", test.prompt, re.I):
            return self._result(False, False, "The question asks about the AI's location while the evidence describes the user; identify the subject explicitly.")
        if test.dimension == Dimension.ACCURACY and user_profile and not re.search(r"\buser\b", test.prompt, re.I) and re.search(
            r"\byour\s+(?:general\s+|usual\s+)?(?:preferred|preference|favourite|favorite)\b|\b(?:what|which|how)\b[^?!]{0,100}\byou\s+(?:generally\s+)?prefer\b", test.prompt, re.I
        ):
            return self._result(False, False, "The question asks for the AI's personal preference while the evidence describes the user; identify the user explicitly.")
        # A recorded edge is provenance, not proof of a coherent relationship.
        # Reject known cross-topic endpoints rather than certifying any edge
        # merely because both records were accepted in the memory review.
        for memory in support:
            for relation in memory.relationships:
                prior = evidence.get(relation.target_memory_id)
                if (relation.type not in {RelationshipType.UPDATE, RelationshipType.CONFLICT}
                    or prior is None or prior.memory_id not in test.supporting_memory_ids):
                    continue
                texts = (memory.canonical_value, prior.canonical_value)
                if any(re.search(r"\b(?:food|diet|lunch)\b", text, re.I)
                       and re.search(r"\b(?:separate|no need|distinct|unrelated)\b", text, re.I)
                       and re.search(r"\b(?:technical|programming|databases?|deployment)\b", text, re.I)
                       for text in texts):
                    return self._result(False, False,
                        "Relationship endpoints identify different topics: a food/technical separation instruction is not a changed or conflicting technical requirement.")
                current_topic = RuleBasedMemoryExtractor._category(memory.canonical_value)
                prior_topic = RuleBasedMemoryExtractor._category(prior.canonical_value)
                if current_topic and prior_topic and current_topic != prior_topic:
                    return self._result(False, False,
                        "Relationship endpoints identify different topics; review the source relationship before generating a test.")
        question_topic = RuleBasedMemoryExtractor._category(test.prompt)
        answer_topic = RuleBasedMemoryExtractor._category(test.expected_behavior)
        if question_topic and answer_topic and question_topic != answer_topic:
            return self._result(False, False, "Question and expected answer identify different topics; review the memory relationship.")
        if test.dimension == Dimension.FRESHNESS:
            # Memory.timestamp is a receipt/observation time, not necessarily
            # a source fact about when a real-world change occurred.
            asks_metadata = re.search(r"\btimestamp\b|\bwhen\b[^?!]{0,140}\blast\s+update|\b(?:date|time)\b[^?!]{0,80}\b(?:last|most recent)\s+update", test.prompt, re.I)
            source_text = " ".join(memory.canonical_value for memory in support if memory is not None)
            explicit_date = re.search(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\b", source_text, re.I)
            if asks_metadata and not explicit_date:
                return self._result(False, False, "The question asks for an update timestamp absent from the source facts. Observation timestamps cannot substitute for a real-world update date.")
            available_updates = [
                (memory, evidence.get(relation.target_memory_id))
                for memory in memories for relation in memory.relationships
                if relation.type == RelationshipType.UPDATE
                and relation.target_memory_id in evidence
                and relation.target_memory_id != memory.memory_id
            ]
            if not available_updates:
                return self._result(False, False, "Freshness requires a confirmed UPDATE relationship between a current record and the historical record it replaces.")
            updates = [(memory, prior) for memory, prior in available_updates
                       if memory.memory_id in test.supporting_memory_ids
                       and prior is not None and prior.memory_id in test.supporting_memory_ids]
            if not updates:
                return self._result(False, False, "The freshness question must cite both records in an explicit UPDATE relationship.")
            if any(prior is None or prior.memory_id not in test.supporting_memory_ids for _, prior in updates):
                return self._result(False, False, "A freshness question must cite both the current and replaced records so its temporal reference can be checked.")
        if test.dimension == Dimension.CONFLICT_RESOLUTION:
            # A dimension label cannot turn ordinary recall into conflict
            # resolution. Require a complete declared relationship within the
            # question's evidence, including resolved updates and overrides.
            support_ids = set(test.supporting_memory_ids)
            complete_relation = any(
                relation.type in {RelationshipType.CONFLICT, RelationshipType.UPDATE, RelationshipType.CONTEXTUAL_OVERRIDE}
                and relation.target_memory_id != memory.memory_id
                and relation.target_memory_id in support_ids
                for memory in support if memory is not None for relation in memory.relationships
            )
            if not complete_relation:
                return self._result(False, False, "A conflict-resolution question must cite both endpoints of a recorded conflict, update or contextual override. Ordinary factual recall belongs to accuracy.")
            contextual = any(relation.type == RelationshipType.CONTEXTUAL_OVERRIDE
                             and (memory.memory_id in test.supporting_memory_ids or relation.target_memory_id in test.supporting_memory_ids)
                             for memory in memories for relation in memory.relationships)
            general_preference = re.search(r"\bprefer\w*\b", test.prompt, re.I)
            scope_prompt = re.sub(r"\b(?:for|in)\s+general\s+tasks?\b", "", test.prompt, flags=re.I)
            context_requested = re.search(r"\b(?:project|task|assignment|requirement|override|conflict|constraint|compare|contrast|exception|restriction|specific|instead|versus|appl)\w*\b", scope_prompt, re.I)
            if contextual and general_preference and not context_requested:
                return self._result(False, False, "A general-preference question cannot test a project-specific override unless it explicitly asks about that context.")
            conflicts = [(memory, evidence.get(relation.target_memory_id)) for memory in support if memory is not None
                         for relation in memory.relationships if relation.type == RelationshipType.CONFLICT]
            if conflicts:
                if any(prior is None or prior.memory_id not in test.supporting_memory_ids for _, prior in conflicts):
                    return self._result(False, False, "An unresolved conflict probe must cite both conflicting records.")
                expected = test.expected_behavior.lower()
                asks_clarification = re.search(
                    r"\b(?:clarif\w*|ask\w*\s+(?:the\s+)?user|seek\w*\s+guidance)\b"
                    r"|\buser\s+(?:(?:must|should|will|can|needs to)\s+)?(?:be|is)\s+(?:asked|consulted)\b",
                    expected,
                )
                recency_wins = re.search(r"\b(?:more recent|most recent|newer|latest|higher priority)\b", expected)
                negates_selection = re.search(r"\b(?:not|never|without|rather than|do not)\b[^.!?]{0,70}\b(?:select|choos|prioriti|rely|pick|use)\w*\b", expected)
                if not asks_clarification or (recency_wins and not negates_selection):
                    return self._result(False, False, "An unresolved conflict needs clarification; source recency alone cannot establish which policy wins.")
        if test.dimension == Dimension.APPROPRIATE_USE:
            support_ids = set(test.supporting_memory_ids)
            complete_override = any(
                relation.type == RelationshipType.CONTEXTUAL_OVERRIDE
                and relation.target_memory_id != memory.memory_id
                and relation.target_memory_id in support_ids
                for memory in support if memory is not None for relation in memory.relationships
            )
            if not complete_override:
                return self._result(False, False, "Appropriate Use requires both confirmed records in an explicit CONTEXTUAL_OVERRIDE relationship.")
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
        from app.evaluator.rule_based import RuleBasedBehaviourEvaluator

        # A question can reveal a complete code without repeating the subject
        # or the rest of the reference sentence. Formatting variants still
        # give away the answer even when they would not pass exact grading.
        for identifier in RuleBasedBehaviourEvaluator._identifier_values(canonical_value):
            pieces = re.split(r"[-_]", identifier)
            pattern = r"(?<!\w)" + r"[-_\s]*".join(re.escape(piece) for piece in pieces) + r"(?!\w)"
            if re.search(pattern, prompt, re.I):
                return True
        def terms(value: str) -> set[str]:
            return {word for word in re.findall(r"[a-z0-9]+", value.lower()) if word not in cls._STOP_WORDS}
        answer_terms, prompt_terms = terms(canonical_value), terms(prompt)
        # Derive locations from the evidence rather than a fixed city whitelist.
        location = location_value(canonical_value)
        if location:
            location_terms = terms(location)
            if location_terms and location_terms.issubset(prompt_terms):
                return True
        region = deployment_region_value(canonical_value)
        if region and terms(region).issubset(prompt_terms):
            return True
        concrete_values = {"mysql", "postgresql", "postgres", "mongodb", "sqlite", "python", "java", "rust", "javascript", "typescript", "kotlin", "swift", "golang", "redis", "mariadb", "cassandra", "dynamodb", "sydney", "melbourne", "london"}
        if answer_terms & prompt_terms & concrete_values:
            return True
        return bool(answer_terms) and answer_terms.issubset(prompt_terms)
