"""Deterministic, evidence-aware evaluator for Foundation v0.1."""
from __future__ import annotations

import re
from app.services.location_facts import location_value
from app.services.meeting_facts import PLATFORM_NAMES, PLATFORM_PATTERN, platform_value, exclusive_platform_value

from app.schemas import Dimension, EvaluationResult, FailureClassification, Memory, MemoryStatus, TargetResponse, TestCase
from app.services.memory_topics import LANGUAGE_WORDS, language_words
from app.services.interfaces import BehaviourEvaluator


class RuleBasedBehaviourEvaluator(BehaviourEvaluator):
    """Judge a response against the test's declared ground truth.

    The evaluator is deliberately deterministic for reproducible demonstrations.
    It has the same interface that a future rule-and-LLM evaluator will use.
    """

    VERSION = "rule-based-v65"
    _GENERIC_REFERENCE_TERMS = frozenset({
        "language", "system", "information", "value", "fact", "record", "requirement",
        "preference", "answer", "response", "behavior", "behaviour", "details", "detail", "data", "context", "managed",
        "previously", "formerly", "historically", "earlier", "check", "checks", "required",
    })
    _STOP_WORDS = frozenset({
        "about", "after", "before", "current", "fact", "from", "later", "record",
        "should", "state", "that", "the", "this", "with", "would",
    })

    def evaluate(self, test: TestCase, response: TargetResponse, memories: list[Memory]) -> EvaluationResult:
        from app.evaluator.output_completion import incomplete_output_evaluation
        incomplete = incomplete_output_evaluation(test, response, self.VERSION)
        if incomplete is not None:
            return incomplete
        from app.services.relationship_bindings import explicit_owner_conflicts
        owner_issues = explicit_owner_conflicts(response.response_text, [
            memory.canonical_value for memory in memories
            if memory.memory_id in test.supporting_memory_ids
            and memory.status in {MemoryStatus.CONFIRMED, MemoryStatus.EDITED}])
        if owner_issues:
            return EvaluationResult(
                evaluation_id=f"E{test.test_id[1:]}", test_id=test.test_id,
                response_id=response.response_id, passed=False, failure_type=Dimension.ACCURACY,
                reason="Failed source attribution: " + "; ".join(owner_issues) + ".",
                failure_classification=FailureClassification(status="classified", method="source-owner-binding-v1",
                    reason="An explicit affirmative relationship changes the source owner for the same named person and predicate."),
                evidence_memory_ids=self._evidence_ids(test, memories), evaluator=self.VERSION)
        expected = self._expected_statement(test.expected_behavior)
        response_words = set(self._words(response.response_text))
        required_terms = self._required_terms(expected, reject_generic_tail=True)
        identifiers = self._identifier_values(test.expected_behavior)
        identifier = next(iter(identifiers)) if len(identifiers) == 1 else self._literal_identifier(expected)
        if len(identifiers) > 1 and required_terms != ['conflict', 'clarification']:
            return EvaluationResult(
                evaluation_id=f"E{test.test_id[1:]}",test_id=test.test_id,response_id=response.response_id,
                passed=None,failure_type=None,evaluator=self.VERSION,
                evidence_memory_ids=self._evidence_ids(test,memories),
                reason="Uncertain: the reference contains multiple identifier values. A single-value lexical check cannot establish this verdict; review the question and reference.",
            )
        if identifier and required_terms != ['conflict', 'clarification']:
            required_terms = [identifier]
        if not required_terms:
            return EvaluationResult(
                evaluation_id=f"E{test.test_id[1:]}", test_id=test.test_id, response_id=response.response_id,
                passed=None, failure_type=None,
                reason="Uncertain: the reference provides no concrete answer value for a lexical check. A generic description word cannot demonstrate factual recall. Excluded from scoring; review the question and reference.",
                evidence_memory_ids=self._evidence_ids(test, memories), evaluator=self.VERSION,
            )
        matched_terms = [
            term for term in required_terms
            if ((term == identifier and re.search(r'(?<![\w-])'+re.escape(term)+r'(?![\w-])',response.response_text))
                or (term != identifier and term in response_words))
            and not self._term_is_negated(term, response.response_text)
        ]
        if required_terms == ["conflict", "clarification"]:
            text = response.response_text.lower()
            if (re.search(r"\b(?:conflict\w*|incompatible|contradict\w*|disagree\w*)\b", text)
                or self._deployment_alternatives_acknowledged(test, response.response_text, memories)):
                if "conflict" not in matched_terms:
                    matched_terms.append("conflict")
            if (re.search(r"\b(?:request(?:s|ing)?|ask(?:s|ing)?|seek(?:s|ing)?|requires?|needs?)\b[^.!?\n]{0,50}\bclarification\b|\b(?:please\s+)?clarify\s+(?:which|whether|what)\b|\b(?:ask(?:s|ing)?|inquire)\s+which\s+policy\b", text)
                or re.search(r"\b(?:must|should|needs?\s+to)\s+(?:be\s+)?[^.!?\n]{0,45}\bclarified\b", text)
                or re.search(r"\b(?:do\s+not|must\s+not|should\s+not)\s+(?:use|choose|select)\b[^.!?\n]{0,60}\buntil\s+clarification\s+is\s+(?:received|provided)\b", text)
                or re.search(r"\bwhich\s+policy\b[^.!?\n]{0,60}\?", text)):
                if "clarification" not in matched_terms:
                    matched_terms.append("clarification")
        missing_terms = [term for term in required_terms if term not in matched_terms]
        evidence_ids = self._evidence_ids(test, memories)
        passed = bool(required_terms) and not missing_terms
        contradictory = self._contradictory_requirement(expected, response.response_text, required_terms)
        rejection_notes = []
        if self._contradictory_database_answer(test, response.response_text, required_terms):
            contradictory = True
            rejection_notes.append("The stated database answer is a different value; mentioning the expected value elsewhere does not repair that assertion.")
        if self._contradictory_platform_answer(test, response.response_text, required_terms, memories):
            contradictory = True
            rejection_notes.append("The answer selects a different meeting platform; mentioning the current platform elsewhere does not repair that instruction.")
        if self._required_database_replacement_missing(test, response.response_text):
            contradictory = True
            rejection_notes.append("The question requires the database replacement, but the response omits or reverses its current and earlier values.")
        if self._unsupported_database_history(test, response.response_text, memories):
            contradictory = True
            rejection_notes.append("The answer attributes an unsupported database value to the earlier source record.")
        if self._denied_known_location_history(test, response.response_text, memories):
            contradictory = True
            rejection_notes.append("The answer describes the earlier location as unknown, but the linked source records an explicit earlier location. Check whether that historical record was supplied before attributing the error to the model.")
        if self._omitted_required_location_history(test, response.response_text, memories):
            contradictory = True
            rejection_notes.append("The question requires explaining the location replacement, but the answer omits the explicitly linked earlier location. A current-location keyword alone does not satisfy this question. Check supplied history before attributing the failure to the model.")
        if required_terms != ["conflict", "clarification"]:
            text = response.response_text.lower()
            mixed_topics = (re.search(r"\bconflict\b", text)
                and re.search(r"\b(?:database|backend|migration|postgresql|mysql|sqlite|mongodb)\b", text)
                and re.search(r"\b(?:deployment|logging|secrets?)\b", text))
            separates_topics = re.search(r"\b(?:separate|unrelated|not related)\b", text)
            actual_secret_pair = 'environment variables' in text and bool(re.search(r'config(?:uration)?\s+file', text))
            if mixed_topics and not separates_topics and not actual_secret_pair:
                contradictory = True
                rejection_notes.append("The response mixes database facts with a policy conflict without separating the topics.")
        if required_terms == ["conflict", "clarification"]:
            if re.search(r"\b(?:(?:must|should)\s+not\s+(?:be\s+)?clarif\w*|(?:not|never)\s+clarif\w*|no\s+(?:unresolved\s+)?(?:conflict|contradiction|disagreement)|not\s+(?:in\s+)?(?:conflict|incompatible)|(?:not|never)\s+(?:ask|request|seek)|without\s+(?:asking|clarification)|no\s+clarification\s+(?:is\s+)?(?:needed|required)|clarification\s+(?:is\s+)?not\s+(?:needed|required)|no\s+need\s+to\s+(?:ask|clarify))\b", response.response_text.lower()):
                contradictory = True
            for choice in re.finditer(r"\b(?:secrets?\s+(?:should|must)\s+be\s+(?:kept|stored)\s+in|(?:use|choose|follow)\s+(?:the\s+)?(?:first|earlier)\s+policy)\b", response.response_text.lower()):
                prefix = response.response_text.lower()[max(0, choice.start() - 100):choice.start()]
                attributed = re.search(r"\b(?:policy|record|source|statement)\b[^.!?\n]{0,60}\b(?:states?|says?|specifies|reports?)\b[^.!?\n]*$", prefix)
                if not attributed and not re.search(r"\b(?:if|unless|not|never|avoid)\b[^.!?\n]*$", prefix):
                    contradictory = True
                    rejection_notes.append("The response recommends one unresolved policy instead of reporting it as a source statement.")
            support = [m.canonical_value.lower() for m in memories if m.memory_id in test.supporting_memory_ids]
            deployment_issues = self._unresolved_deployment_conflict_issues(response.response_text, support)
            if deployment_issues:
                contradictory = True
                rejection_notes.extend(deployment_issues)
            platform_issues = self._unresolved_platform_conflict_issues(expected, response.response_text, support)
            if platform_issues:
                contradictory = True
                rejection_notes.extend(platform_issues)
            if support and all(re.search(r"\bsecrets?\b", value) for value in support) and re.search(r"\bboth\b", expected, re.I):
                source_text = " ".join(support)
                for option, pattern in [
                    ('environment variables', r'\b(?:environment\s+variables?|env\s+vars?)\b'),
                    ('configuration file', r'\bconfig(?:uration)?\s+files?\b'),
                ]:
                    if option in source_text and not re.search(pattern, response.response_text.lower()):
                        contradictory = True
                        rejection_notes.append(f"Conflict answer omits the source-policy option: {option}.")
                databases = {"mysql", "postgresql", "sqlite", "mongodb"}
                unsupported = databases.intersection(response_words).difference(self._words(" ".join(support)))
                if any(not self._term_is_negated(value, response.response_text) for value in unsupported):
                    contradictory = True
                    rejection_notes.append("Unrelated database facts were attributed to the deployment-policy conflict.")
            # Reporting both requirements does not excuse choosing one while
            # the reference explicitly says the conflict is unresolved.
            options = language_words(" ".join(support))
            for option in options:
                if re.search(r"\b(?:applicable|recommended|selected|chosen)\s+(?:programming[- ]language\s+)?(?:choice|language)\s+is\s+(?:\*\*)?" + re.escape(option) + r"\b", response.response_text.lower()):
                    contradictory = True
                    rejection_notes.append("The response selects a programming language despite unresolved requirements.")
            recency_choices = re.finditer(
                r"\b(?:follow|select|choose|use|comply with)\b[^.!?\n]{0,140}\b(?:last updated|more recent(?:ly)?|most recent|higher priority|later record)\b",
                response.response_text.lower(),
            )
            contradictory = contradictory or any(
                not re.search(r"\b(?:not|never|avoid)\b[^.!?\n]{0,20}$", response.response_text.lower()[max(0, choice.start()-30):choice.start()])
                for choice in recency_choices
            )
        scoped_languages = self._scoped_language_values(expected)
        if scoped_languages and self._scoped_language_scope_missing(response.response_text, scoped_languages):
            contradictory = True
            rejection_notes.append("The response does not preserve the task requirement and general preference in their separate scopes.")
        if contradictory:
            passed = False

        if passed:
            reason = (
                f"Passed {test.dimension.value}: the response matched all required ground-truth terms "
                f"({', '.join(matched_terms)}). {len(evidence_ids)} gold evidence record(s) are linked; "
                "this lexical verdict does not establish target memory use."
            )
        else:
            required_label = ", ".join(required_terms) if required_terms else "a testable expected behaviour"
            missing_label = ", ".join(missing_terms) if missing_terms else required_label
            reason = (
                f"Failed {test.dimension.value}: expected behaviour was '{expected}'. "
                f"The response did not demonstrate: {missing_label}. "
                f"Evidence records: {', '.join(evidence_ids) if evidence_ids else 'none linked to this test'}."
            )
            if not missing_terms and required_terms:
                reason = f"Failed {test.dimension.value}: required terms were present, but the response contradicts the expected behaviour. "
            if contradictory:
                reason = "Failed: the answer contradicts or omits a required part of the expected behaviour. " + reason
            if rejection_notes:
                reason += " " + " ".join(rejection_notes)

        receipt = response.execution_metadata.memory_input
        if passed and receipt is not None and receipt.record_count == 0:
            reason += " Correct answer with zero supplied memory: memory grounding is unsupported; human review required."

        # An answer keyword cannot validate an invented version requirement.
        # Abstain rather than treating unsupported details as proved false:
        # the source may simply be incomplete. Independent review decides.
        unsupported_versions = self._unsupported_language_versions(test, response.response_text, memories)
        if passed and unsupported_versions:
            return EvaluationResult(
                evaluation_id=f"E{test.test_id[1:]}", test_id=test.test_id, response_id=response.response_id,
                passed=None, failure_type=None,
                reason=("Uncertain: the answer contains programming-language version details absent from the linked source "
                        f"({', '.join(unsupported_versions)}). Keyword agreement alone cannot validate these requirements. "
                        "Excluded from scoring; independent review required."),
                evidence_memory_ids=evidence_ids, evaluator=self.VERSION,
            )

        unsupported_causes = self._unsupported_quality_causes(test, response.response_text, memories)
        unsupported_causes += self._unsupported_memory_policy_claims(test, response.response_text, memories)
        if passed and unsupported_causes:
            return EvaluationResult(
                evaluation_id=f"E{test.test_id[1:]}", test_id=test.test_id, response_id=response.response_id,
                passed=None, failure_type=None,
                reason=("Uncertain: the answer adds explanatory or memory-policy claims "
                        f"not supported by the linked source ({', '.join(unsupported_causes)}). "
                        "A correct answer keyword cannot establish the stated reason. "
                        "Excluded from scoring; independent review required."),
                evidence_memory_ids=evidence_ids, evaluator=self.VERSION,
            )

        failure_type, classification = self._classify_failure(test, response, memories) if not passed else (None, FailureClassification())
        return EvaluationResult(
            evaluation_id=f"E{test.test_id[1:]}", test_id=test.test_id, response_id=response.response_id,
            passed=passed, failure_type=failure_type, failure_classification=classification, reason=reason,
            evidence_memory_ids=evidence_ids, evaluator=self.VERSION,
        )

    @staticmethod
    def _contradictory_platform_answer(test: TestCase, response: str, required: list[str], memories: list[Memory]) -> bool:
        """Reject explicit current choices inconsistent with a typed reference.

        Historical source attribution and clearly different named projects do
        not count as a current recommendation for the tested project.
        """
        value = ' '.join(required)
        if value not in PLATFORM_NAMES:
            return False
        from app.services.memory_entities import named_projects
        projects = named_projects(test.prompt)
        support = [m.canonical_value for m in memories if m.memory_id in test.supporting_memory_ids]
        if not any(re.search(r"\b(?:meeting|review|conference|call)\b", source, re.I) for source in support):
            return False
        for sentence in re.split(r'[.!?\n;]', response):
            scopes = named_projects(sentence)
            if projects and scopes and projects.isdisjoint(scopes):
                continue
            for choice in re.finditer(rf"\b(?:use|uses|choose|select|recommend|requires?)\s+(?P<value>{PLATFORM_PATTERN})\b|\b(?P<passive>{PLATFORM_PATTERN})\s+(?:must|should)\s+be\s+used\b", sentence, re.I):
                selected = re.sub(r'^microsoft\s+', '', (choice['value'] or choice['passive']).lower())
                prefix = sentence[:choice.start()].lower()
                attributed = re.search(r"\b(?:record|source|policy|requirement)\b[^.!?]{0,70}\b(?:says?|states?|required|requires?)\b[^.!?]*$", prefix)
                historical = re.search(r"\b(?:previously|formerly|historical|earlier)\b[^.!?]{0,60}$", prefix)
                negated = re.search(r"\b(?:not|never|avoid)\s+(?:\w+\s+){0,2}$", prefix)
                if selected != value and not attributed and not historical and not negated:
                    return True
        return False

    @staticmethod
    def _unresolved_platform_conflict_issues(expected: str, response: str, support: list[str]) -> list[str]:
        """Bounded checks for explicit alternatives, not a semantic classifier.

        A clarification keyword cannot excuse a simultaneous instruction to
        use an unresolved platform. Preserve source attribution, negation and
        conditional instructions awaiting the user's decision.
        """
        platform = r"(?:zoom|(?:microsoft\s+)?teams|webex|google\s+meet)"
        if not any(re.search(r"\b(?:meeting|review|conference|call)\b", value) for value in support):
            return []
        options = {match.group(0).removeprefix('microsoft ') for value in support
                   for match in re.finditer(rf"\b{platform}\b", value)}
        if len(options) < 2:
            return []
        text = response.lower()
        issues = []
        if re.search(r"\b(?:both|each)\b", expected, re.I):
            for option in sorted(options):
                if not re.search(rf"\b{re.escape(option)}\b", text):
                    issues.append(f"The conflict answer omits a recorded meeting-platform option: {option}.")
        choices = re.finditer(
            rf"\b(?:use|choose|select|recommend)\s+(?:only\s+)?(?P<active>{platform})\b"
            rf"|\b(?:meeting|review|conference|call)\s+(?:must|should|will)\s+be\s+held\s+(?:on|via|using)\s+(?P<held>{platform})\b"
            rf"|\b(?P<passive>{platform})\s+(?:must|should|will)\s+be\s+used\b"
            rf"|\b(?:selected|chosen|recommended|correct)\s+platform\s+is\s+(?P<selected>{platform})\b", text,
        )
        for choice in choices:
            prefix = re.split(r'[.!?\n;]', text[:choice.start()])[-1]
            attributed = re.search(r"\b(?:policy|record|source|statement|requirement)\b[^.!?\n]{0,80}\b(?:states?|says?|specifies|reports?|requires?)\b[^.!?\n]*$", prefix)
            # Describing the conflict between source requirements is not a
            # recommendation. A later unqualified choice is still checked.
            described_conflict = re.search(r"\bconflict\s+between\b[^.!?\n]{0,70}\b(?:requirement|constraint)\s+to\s*$", prefix)
            line_prefix = text[:choice.start()].rsplit('\n', 1)[-1]
            numbered_source = (re.match(r"\s*\d+[.)]\s+", line_prefix)
                               and re.search(r"\b(?:recorded|source|stored)\s+(?:constraints|requirements|policies)\b[^.!?]{0,100}:\s*(?:\n|$)", text[max(0, choice.start()-400):choice.start()]))
            negated = re.search(r"\b(?:not|never|avoid)\s+(?:\w+\s+){0,2}$", prefix)
            conditional = re.search(r"\b(?:if|unless)\b[^.!?\n]{0,100}\b(?:user|confirm\w*|clarif\w*|resolv\w*)\b[^.!?\n]*$", prefix)
            if not attributed and not described_conflict and not numbered_source and not conditional and not negated:
                issues.append("The answer selects a meeting platform while its requirements remain unresolved.")
                break
        return issues

    @staticmethod
    def _denied_known_location_history(test: TestCase, response: str, memories: list[Memory]) -> bool:
        support = {memory.memory_id: memory for memory in memories
                   if memory.memory_id in test.supporting_memory_ids}
        # Only an explicit update linking two concrete locations establishes
        # known history; two unrelated locations do not establish chronology.
        known_old = any(location_value(memory.canonical_value) and
                        any(relation.type.value == 'UPDATE' and relation.target_memory_id in support
                            and location_value(support[relation.target_memory_id].canonical_value)
                            for relation in memory.relationships)
                        for memory in support.values())
        text = re.sub(r'[\"\u201c\u201d*]', '', response.lower())
        return bool(known_old and re.search(
            r"\b(?:historical|previous|earlier|old)\s+(?:location|value)\s+(?:of|was|is)\s+(?:unknown|unrecorded|not\s+(?:known|recorded|provided))\b", text))

    @staticmethod
    def _omitted_required_location_history(test: TestCase, response: str, memories: list[Memory]) -> bool:
        """Require source-backed history only when the question asks for it.

        A current-value-only question can still pass without the old place.
        Unrelated locations cannot establish a historical replacement.
        """
        requirement = f"{test.prompt} {test.expected_behavior}".lower()
        if not (re.search(r"\bexplain\b[^.!?\n]{0,160}\b(?:replac\w*|historical|previous|earlier)\b", requirement)):
            return False
        support = {memory.memory_id: memory for memory in memories
                   if memory.memory_id in test.supporting_memory_ids}
        for current in support.values():
            new_place = location_value(current.canonical_value)
            if not new_place:
                continue
            for relation in current.relationships:
                old = support.get(relation.target_memory_id)
                old_place = location_value(old.canonical_value) if old else None
                if relation.type.value == 'UPDATE' and old_place and old_place.casefold() != new_place.casefold():
                    pattern = r"(?<!\w)" + re.escape(old_place).replace(r"\ ", r"\s+") + r"(?!\w)"
                    if not re.search(pattern, response, re.I):
                        return True
        return False

    def _classify_failure(self, test: TestCase, response: TargetResponse, memories: list[Memory]):
        """Conservative observed-error rules; never copy the test dimension.

        Missing lexical matches alone cannot establish the failure's cause.
        Temporal diagnosis requires both a supported old value and a supported
        current value, not just an expected-answer string.
        """
        support = [m for m in memories if m.memory_id in test.supporting_memory_ids
                   and m.status in {MemoryStatus.CONFIRMED, MemoryStatus.EDITED}]
        terms = self._required_terms(self._expected_statement(test.expected_behavior))
        if support and self._unsupported_database_history(test, response.response_text, support):
            return Dimension.ACCURACY, FailureClassification(
                status="classified", method="evidence-rules-v1",
                reason="The answer attributes an unsupported database value to an explicit historical source.")
        by_id = {m.memory_id: m for m in support}
        replacements = [(current, by_id[relation.target_memory_id])
                        for current in support for relation in current.relationships
                        if relation.type.value == 'UPDATE' and relation.target_memory_id in by_id
                        and relation.target_memory_id != current.memory_id
                        and any(t in self._words(current.canonical_value) for t in terms)]
        answer_words = set(self._words(response.response_text))
        # A linked contextual override plus an affirmative restatement of the
        # general preference can establish inappropriate use. Missing keywords
        # alone, or the requested test dimension, cannot establish this cause.
        for requirement in support:
            required = self._explicit_requirement_terms(requirement.canonical_value)
            if not required or any(word in answer_words for word in required):
                continue
            for relation in requirement.relationships:
                general = by_id.get(relation.target_memory_id)
                if relation.type.value != 'CONTEXTUAL_OVERRIDE' or general is None:
                    continue
                preference = re.search(r"\b(?:prefer|prefers)\s+([^.;!?]+)", general.canonical_value, re.I)
                values = self._words(preference.group(1)) if preference else []
                if values and all(word in answer_words and not self._term_is_negated(word, response.response_text)
                                  for word in values):
                    return Dimension.APPROPRIATE_USE, FailureClassification(
                        status="classified", method="evidence-rules-v3",
                        reason="The answer repeats a linked general preference while omitting the explicit task-specific requirement that overrides it.")
        if replacements:
            for _, m in replacements:
                obsolete = set(self._required_terms(m.canonical_value)) - set(terms)
                # Only typed database/language values: arbitrary source words
                # do not prove stale recall, and reporting history is allowed.
                obsolete &= {"mysql", "postgresql", "sqlite", "mongodb", *LANGUAGE_WORDS}
                for term in obsolete & answer_words:
                    if (not any(t in answer_words and not self._term_is_negated(t, response.response_text) for t in terms)
                            and not self._term_is_negated(term, response.response_text)
                            and self._asserts_current_value(term, response.response_text)):
                        return Dimension.FRESHNESS, FailureClassification(
                            status="classified", method="evidence-rules-v2",
                            reason="The answer selects an obsolete value as current despite a source-supported explicit replacement.")
        from app.evaluator.source_abstention import classify_source_abstention
        omission = classify_source_abstention(test.prompt, response.response_text, support)
        if omission is not None:
            category, explanation = omission
            return category, FailureClassification(status="classified", method="source-abstention-v1",
                reason=explanation + " This describes the observed missing answer, not its internal cause.")
        return None, FailureClassification(method="evidence-rules-v2",
            reason="A rule failure was detected, but the supplied evidence does not identify a unique observed error category.")

    @staticmethod
    def _asserts_current_value(value: str, answer: str) -> bool:
        """Require an active selection; accurate history is not stale recall."""
        text = re.sub(r'[\"\u201c\u201d*`]', '', answer.lower()).strip()
        term = re.escape(value)
        if re.fullmatch(rf"{term}\s*[.!?]*", text):
            return True
        selection = (rf"\b(?:use|uses|using)\s+{term}\b"
                     rf"|\b(?:current|chosen|recommended|required)\s+(?:database(?:\s+system)?|language|value)\s+(?:is|:)\s*{term}\b"
                     rf"|\b{term}\s+is\s+(?:the\s+)?(?:current|chosen|recommended|required)\b"
                     rf"|\b{term}\s+is\s+(?:currently\s+)?used\s+now\b")
        for match in re.finditer(selection, text):
            prefix = re.split(r'[.!?;\n]|\b(?:but|whereas|while)\b', text[:match.start()])[-1]
            if not re.search(r"\b(?:previously|formerly|earlier|historical|used to|old)\b", prefix) and not re.search(
                r"\b(?:record|source|statement|policy)\b[^.!?]{0,80}\b(?:says?|states?|reports?)\b", prefix
            ):
                return True
        return False

    @staticmethod
    def _unsupported_quality_causes(test: TestCase, response: str, memories: list[Memory]) -> list[str]:
        """Narrow abstention guard for asserted benefit-based explanations.

        This does not certify other prose, entailment or paraphrases. Merely
        mentioning a property in the source cannot establish migration cause.
        Unknown causal provenance requires review, not a fabricated failure.
        """
        support = [m.canonical_value.lower() for m in memories if m.memory_id in test.supporting_memory_ids]
        if not support:
            return []
        properties = r"\b(?:robust(?:ness)?|scalab(?:le|ility)|modern|reliab(?:le|ility)|efficien(?:t|cy)|secure|security|faster|cheaper|cost|lightweight)\b"
        causal = r"\b(?:because|since|due to|as it|as the|reason|caused|motivated|in order to)\b"
        supported_causes = ' '.join(sentence for text in support for sentence in re.split(r'[.!?\n]', text)
                                    if re.search(causal, sentence))
        supported_terms = {m.group(0) for m in re.finditer(properties, supported_causes)}
        database_answer = bool({'mysql','postgresql','sqlite','mongodb'}.intersection(
            RuleBasedBehaviourEvaluator._words(test.expected_behavior)))
        supported_languages = language_words(supported_causes)
        claims = []
        for sentence in re.split(r'[.!?\n]', response.lower()):
            if not re.search(causal, sentence):
                continue
            # An explicitly unknown/hypothetical cause is not asserted fact.
            if re.search(r"\b(?:might|could|possibly|hypothetical)\b", sentence) or re.search(
                r"\b(?:reason|cause)\b[^.!?]{0,45}\b(?:unknown|not stated|not recorded|not provided)\b", sentence):
                continue
            claims.extend(m.group(0) for m in re.finditer(properties, sentence)
                          if m.group(0) not in supported_terms)
            if database_answer:
                cause = re.search(causal, sentence)
                claims.extend(f'language requirement: {language}' for language in
                              language_words(sentence[cause.end():]) - supported_languages)
        return sorted(set(claims))

    @staticmethod
    def _unsupported_memory_policy_claims(test: TestCase, response: str, memories: list[Memory]) -> list[str]:
        """Abstain on explicit claims about an unobserved target memory policy.

        A source update establishes current state, not the target's internal
        policy or implementation. General explanations of recency remain valid.
        """
        support = [m.canonical_value.lower() for m in memories if m.memory_id in test.supporting_memory_ids]
        if not support:
            return []
        pattern = r"\b(?:newer|new|current|updated|explicit)\s+memory\s+polic(?:y|ies)\b"
        if not re.search(pattern, " ".join(support)):
            for sentence in re.split(r'[.!?\n]', response.lower()):
                if re.search(pattern, sentence) and not re.search(
                    r"\b(?:no|not|unknown|unrecorded|unstated|hypothetical|if|might|could)\b", sentence
                ):
                    return ["unrecorded memory policy"]
        return []

    @staticmethod
    def _unsupported_language_versions(test: TestCase, response: str, memories: list[Memory]) -> list[str]:
        support = " ".join(m.canonical_value for m in memories if m.memory_id in test.supporting_memory_ids)
        if not support:
            return []
        languages = language_words(support)
        if not languages:
            return []
        def claims(text: str) -> set[str]:
            return {f"{match.group(1).lower()} {match.group(2)}" for match in re.finditer(
                r"\b(" + "|".join(re.escape(language) for language in sorted(languages)) +
                r")\s+(?:version\s+)?v?(\d+(?:\.\d+){0,3})\b", text, re.I)}
        return sorted(claims(response) - claims(support))

    @staticmethod
    def _expected_statement(expected_behavior: str) -> str:
        return expected_behavior.split(":", 1)[-1].strip()

    @classmethod
    def _words(cls, text: str) -> list[str]:
        # Keep complete ISO dates available as lexical atoms. A matching year
        # alone cannot demonstrate the recorded month and day.
        return re.findall(r"[a-z0-9]+", text.lower()) + re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)

    @staticmethod
    def _identifier_values(expected: str) -> set[str]:
        """Recognise explicit compound codes without splitting or case folding.

        Only labelled identifiers or an entire bare literal qualify. This is
        an exact lexical check, not a semantic interpretation of prose.
        """
        atom = r'[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+'
        bare = re.fullmatch(rf'\s*[\"\x27`]?({atom})[\"\x27`]?\s*[.!?]?\s*',expected)
        labelled = re.finditer(rf'\b(?:access\s+code|verification\s+code|code|token|identifier|pin)\s*(?:(?:is|equals)\s+|[:=]\s*|\s+)[\"\x27`]?({atom})(?![\w-])',expected,re.I)
        values={match.group(1) for match in labelled}
        if bare:
            values.add(bare.group(1))
        if re.search(r'\b(?:code|token|identifier|pin)\b',expected,re.I):
            values.update(value for value in re.findall(rf'\b{atom}\b',expected) if any(char.isdigit() for char in value))
        return {value for value in values if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value)}

    @classmethod
    def _literal_identifier(cls, expected: str) -> str | None:
        values=cls._identifier_values(expected)
        return next(iter(values)) if len(values)==1 else None

    @classmethod
    def _explicit_requirement_terms(cls, expected: str) -> list[str] | None:
        """Preserve a bounded positive requirement's answer-bearing qualifiers.

        A shared container noun such as 'charts' cannot prove 'grayscale
        charts'. Do not interpret negatives, alternatives or scoped clauses
        with this short-value parser; they retain the existing specialised
        checks and semantic-review boundary.
        """
        match = re.search(
            r"\b(?:requires?|must\s+use)\s+(?P<value>[a-z0-9][a-z0-9_+-]*(?:\s+[a-z0-9][a-z0-9_+-]*){1,4})\s*[.!?]*$",
            expected, re.I,
        )
        if match is None:
            return None
        words = cls._words(match['value'])
        if set(words) & {'not', 'no', 'without', 'unless', 'except', 'if', 'or', 'and', 'for', 'to', 'by', 'than'}:
            return None
        containers = {'the', 'a', 'an', 'charts', 'chart', 'pages', 'page', 'documents', 'document',
                      'files', 'file', 'backups', 'backup'}
        # Only handle the concrete container patterns covered here. Abstract
        # references (e.g. "a specific programming language") must keep the
        # existing UNCERTAIN boundary rather than becoming literal demands.
        if not set(words) & (containers - {'the', 'a', 'an'}):
            return None
        values = list(dict.fromkeys(word for word in words if word not in containers))
        return values or None

    @classmethod
    def _required_terms(cls, expected: str, *, reject_generic_tail: bool = False) -> list[str]:
        """Select the answer-bearing part of a generated expectation.

        ``expected_behavior`` is written for a human reviewer, so phrases
        such as "generally prefer" or "is required" explain *why* an answer
        is right rather than being text that a target must parrot.  The
        evaluator therefore checks the concrete tail value, with an explicit
        ``X is required`` rule for contextual requirements.  This deliberately
        stays lexical and deterministic; an LLM judge remains a separate,
        optional evaluator implementation.
        """
        # Check mandatory conflict actions before removing explanatory prose;
        # an explanation can precede a later clarification requirement.
        if re.search(r"request clarification|ask.*clarif|ask(?:\s+the)?\s+user\s+which\s+(?:constraint|requirement|policy)\s+(?:controls?|takes?\s+precedence|applies?)", expected.lower()) or (re.search(r"\bconflict", expected, re.I) and re.search(r"\bclarification\s+(?:is\s+)?(?:needed|required)\b", expected, re.I)):
            return ["conflict", "clarification"]
        dates = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", expected))
        if len(dates) == 1:
            return sorted(dates)
        identifier = cls._literal_identifier(expected)
        if identifier:
            return [identifier]
        # Resolved replacement references can end in the old value. Select
        # the explicitly replacing database, never the historical sentence tail.
        database = r"(?:mysql|postgresql|postgres|sqlite|mongodb|redis|mariadb|cassandra|dynamodb)"
        current_database = re.search(rf"\b(?P<current>{database})\s+is\s+(?:the\s+)?current\b", expected, re.I)
        current_database = current_database or re.search(
            rf"\bcurrent\s+(?:database(?:\s+system)?|system|engine|datastore)\s+is\s+(?P<current>{database})\b",
            expected, re.I,
        )
        # A source-reference summary may put the active value before "is
        # used" and end with a historical sentence. Require an explicit current
        # record plus an affirmative present-tense assertion; do not select the
        # historical tail or a negated/previously-used value.
        current_database = current_database or re.search(
            rf"\bcurrent\s+record\s+(?:says|states|indicates|confirms)\s+(?P<current>{database})\s+is\s+(?:currently\s+)?used\b(?!\s+(?:previously|formerly|historically|earlier)\b)",
            expected, re.I,
        )
        current_database = current_database or re.search(
            rf"\b(?:migrated?|switched?)\b[^.!?;]{{0,100}}?\bto\s+(?P<current>{database})\b", expected, re.I)
        if current_database:
            return [current_database.group('current').lower()]
        scoped_languages = cls._scoped_language_values(expected)
        if scoped_languages:
            return list(scoped_languages)
        replaced = re.search(rf"\b(?P<current>{database})\s*,?\s+(?:which\s+)?replaced\s+{database}\b", expected, re.I)
        updated = re.search(rf"\b(?:use|uses|using)(?:\s+of)?\s+(?P<current>{database})\b[^.!?]{{0,60}}\bupdate\s+to\b[^.!?]{{0,60}}\b{database}\b", expected, re.I)
        if replaced or updated:
            return [(replaced or updated).group('current').lower()]
        # Human-facing references can explain why a value is current after a
        # comma. Those modifiers are not answer values (e.g. "information").
        # Keep additive requirements such as "as well as" intact.
        expected = re.split(
            r",\s*(?:because\b|since\b|as\s+(?:this|it|that|these|the)\b|reflecting\b|replacing\b|superseding\b|overriding\b|consistent\s+with\b|in\s+line\s+with\b)",
            expected, maxsplit=1, flags=re.I,
        )[0]
        platform = platform_value(expected) or exclusive_platform_value(expected)
        if platform:
            return cls._words(platform)
        # Preserve short values and all words of a location/preference.
        value = re.search(r"\b(?:prefer|prefers|favour|favors?)\s+([^.;!?]+)", expected, re.I)
        # A noun-form reference is the fact only at the start of the answer
        # clause. A later "preference for ..." can explain why a project
        # requirement overrides it and must not replace the required value.
        value = value or re.search(r"(?:^|:\s*)(?:(?:the\s+)?(?:user's\s+|general\s+))?preferences?\s+for\s+([^.;!?]+)", expected, re.I)
        location = location_value(expected)
        if location or value:
            return list(dict.fromkeys(cls._words(location or re.split(r'\s+for\b', value.group(1), maxsplit=1, flags=re.I)[0])))
        action_value = re.search(
            r"\b([a-z0-9][a-z0-9_+-]*)\s+(?:should|must)\s+be\s+used\b|\b(?:suggest|recommend|use|uses)\s+([a-z0-9][a-z0-9_+-]*)\s*[.!?]*$",
            expected, re.I,
        )
        if action_value:
            return cls._words(action_value.group(1) or action_value.group(2))
        # A multiword value cannot be reduced to a generic last word.
        if "object storage" in expected.lower():
            return ["object", "storage"]
        requirement = re.search(
            r"\b([a-z0-9][a-z0-9_+-]*)\s+is\s+(?:required|mandatory)\b",
            expected.lower(),
        )
        if requirement:
            return [requirement.group(1)]
        short_requirement = re.search(r"\b(?:requires?|must\s+use)\s+(?:(?:the\s+)?use\s+of\s+)?([a-z0-9][a-z0-9_+-]*)(?=\s*(?:[.!?,;]|$)|\s+(?:for|instead|rather|on|by)\b)", expected, re.I)
        if short_requirement:
            return [short_requirement.group(1).lower()]
        qualified_requirement = cls._explicit_requirement_terms(expected)
        if qualified_requirement:
            return qualified_requirement
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
        if reject_generic_tail and len(cls._words(expected)) > 1 and selected and selected[0] in cls._GENERIC_REFERENCE_TERMS:
            return []
        return list(dict.fromkeys(selected))

    @staticmethod
    def _term_is_negated(term: str, response_text: str) -> bool:
        """Reject a value explicitly described as the wrong answer.

        This is a narrow deterministic guard, not a replacement for semantic
        LLM judging. It prevents clear false positives such as "do not use
        PostgreSQL" while retaining a concise factual answer like
        "PostgreSQL".
        """
        quoted = re.escape(term.lower())
        text = response_text.lower()
        # A following explanatory/contrast clause is outside the negation:
        # "instead of MariaDB because PostgreSQL ..." does not negate PG.
        clause_word = r"(?!(?:because|but|whereas|while|yet|then)\b)[a-z0-9_+-]+"
        before = rf"\b(?:not|never|avoid|without|rather\s+than|instead\s+of)\b(?:\s+{clause_word}){{0,3}}\s+{quoted}\b"
        # Negation must govern the answer value, rather than an alternative
        # in a comparison such as "PostgreSQL is not MySQL". Also preserve
        # double negatives such as "PostgreSQL is not wrong".
        after = (
            rf"\b{quoted}\b\s+(?:(?:is|was|would\s+be|should\s+be)\s+)?"
            r"(?:incorrect|wrong|(?:not|never)\s+(?:(?:the|a|an)\s+)?"
            r"(?:correct|right|answer|preferred|required|mandatory|allowed|used|suitable))\b"
        )
        return bool(re.search(before, text) or re.search(after, text))

    @staticmethod
    def _unsupported_database_history(test: TestCase, response: str, memories: list[Memory]) -> bool:
        databases = {"mysql", "postgresql", "sqlite", "mongodb"}
        support = " ".join(memory.canonical_value.lower() for memory in memories if memory.memory_id in test.supporting_memory_ids)
        source_values = databases.intersection(RuleBasedBehaviourEvaluator._words(support))
        if not source_values:
            return False
        # A current value somewhere in the reference cannot validate a claim
        # that the same value was stated in the earlier record. Use explicit
        # past assertions when present; unknown temporal roles stay unknown.
        database_pattern = '|'.join(sorted(databases))
        past_values = {match.group(1) for match in re.finditer(
            rf'\bused\s+(?:to\s+use\s+)?({database_pattern})\b', support)}
        historical_values = past_values or source_values
        # Inspect only assertions about what an earlier record said. Mentioning
        # a different project's current database remains a valid comparison.
        from app.services.memory_entities import named_projects
        project_names = set().union(*(named_projects(memory.canonical_value) for memory in memories if memory.memory_id in test.supporting_memory_ids))
        named_values = databases | project_names
        value_pattern = "|".join(re.escape(value) for value in sorted(named_values, key=len, reverse=True))
        historical_claims = re.finditer(
            rf"\b(?:earlier|older|previous)\s+(?:memory|record|statement)\b[^.!?\n]{{0,100}}?\b(?:uses?|used|using)\s+({value_pattern})\b",
            response.lower(),
        )
        if any(claim.group(1) not in historical_values
               and not RuleBasedBehaviourEvaluator._term_is_negated(claim.group(1), claim.group(0))
               for claim in historical_claims):
            return True
        # A noun phrase can assert the old value without a "record used X"
        # clause. Require explicit source history and retain project isolation.
        if past_values:
            for sentence in re.split(r'[.!?\n]', response.lower()):
                sentence_projects = named_projects(sentence)
                if sentence_projects and project_names and sentence_projects.isdisjoint(project_names):
                    continue
                for claim in re.finditer(
                    rf"\b(?:old(?:er)?|previous|historical|former)\s+({database_pattern})\s+(?:implementation|database|backend)\b",
                    sentence,
                ):
                    if claim.group(1) not in past_values and not RuleBasedBehaviourEvaluator._term_is_negated(claim.group(1), sentence):
                        return True
        return False

    @staticmethod
    def _unresolved_deployment_conflict_issues(response: str, support: list[str]) -> list[str]:
        from app.services.deployment_facts import deployment_region_value
        values = {value.lower() for source in support if (value := deployment_region_value(source))}
        if len(values) < 2:
            return []
        missing = [value for value in sorted(values) if not re.search(rf"(?<![\w-]){re.escape(value)}(?![\w-])", response, re.I)]
        if missing:
            return ["Conflict answer omits the source-region option: " + ", ".join(missing) + "."]
        option = '|'.join(re.escape(value) for value in sorted(values, key=len, reverse=True))
        text = response.lower()
        for choice in re.finditer(rf"\b(?:use|choose|select|deploy\s+(?:in|to))\s+(?:the\s+)?(?:{option})\b|\b(?:{option})\s+is\s+(?:the\s+)?(?:chosen|recommended|correct)\s+(?:production\s+)?region\b", text):
            prefix = re.split(r'[.!?;\n]', text[:choice.start()])[-1]
            if re.search(r"\b(?:if|unless|not|never|avoid|whether)\b[^.!?\n]*$",prefix):
                continue
            if re.search(r"\b(?:plan|brief|source|record)\b[^.!?\n]{0,60}\b(?:says?|states?|requires?)\b[^.!?\n]*$",prefix):
                continue
            return ["The response chooses a deployment region while its source constraints remain unresolved."]
        return []

    @staticmethod
    def _deployment_alternatives_acknowledged(test: TestCase, response: str, memories: list[Memory]) -> bool:
        from app.services.deployment_facts import deployment_region_value
        values = {value.lower() for memory in memories if memory.memory_id in test.supporting_memory_ids
                  if (value := deployment_region_value(memory.canonical_value))}
        text = response.lower()
        return (len(values) >= 2
                and all(re.search(rf"(?<![\w-]){re.escape(value)}(?![\w-])", text) for value in values)
                and bool(re.search(r"\b(?:whether|while|versus|or)\b", text))
                and bool(re.search(r"\bclarify\s+(?:which|whether|what)\b|\bwhich\b[^.!?\n]{0,60}\b(?:controls?|takes?\s+precedence)\b", text)))

    @staticmethod
    def _required_database_replacement_missing(test: TestCase, response: str) -> bool:
        if test.dimension != Dimension.FRESHNESS or not re.search(r"\b(?:replac\w*|earlier|previous|historical)\b", test.prompt, re.I):
            return False
        database = r"(?:mysql|postgresql|postgres|sqlite|mongodb|redis|mariadb|cassandra|dynamodb)"
        prior = re.search(rf"\breplaced\s+({database})\b", test.expected_behavior, re.I)
        if prior is None:
            return False
        # Mere mention of the old value does not demonstrate replacement.
        return not bool(re.search(rf"\b(?:replaced|replaces|replacing|instead\s+of)\s+{re.escape(prior[1])}\b|\b{re.escape(prior[1])}\s+(?:was|is)\s+(?:the\s+)?(?:previous|earlier|old|former)\b", response, re.I))

    @staticmethod
    def _scoped_language_values(expected: str) -> tuple[str, str] | None:
        """Read explicit dual-scope language requirements, never arbitrary prose tails."""
        language = '|'.join(re.escape(value) for value in sorted(LANGUAGE_WORDS | {'go'}, key=len, reverse=True))
        task = re.search(rf"\b(?:recommend|use)\s+({language})\b", expected, re.I)
        general = re.search(rf"\b(?:general\s+)?preference\s+for\s+({language})\b", expected, re.I)
        if task and general and task[1].lower() != general[1].lower() and re.search(r"\b(?:other|outside|general)\b", expected, re.I):
            return task[1].lower(), general[1].lower()
        return None

    @staticmethod
    def _scoped_language_scope_missing(response: str, values: tuple[str, str]) -> bool:
        task, general = values
        text = response.lower()
        # The stable preference must remain explicitly general/outside the task.
        general_scope = any(
            re.search(rf"\b{re.escape(general)}\b", clause)
            and re.search(r"\b(?:general|other|outside)\b", clause)
            and re.search(r"\b(?:prefer\w*|recommend\w*|use)\b", clause)
            and not RuleBasedBehaviourEvaluator._term_is_negated(general, clause)
            for clause in re.split(r'[.;!\n]', text)
        )
        task_choice = bool(re.search(rf"\b(?:use|recommend|requires?)\s+{re.escape(task)}\b|\b{re.escape(task)}\s+(?:is\s+)?(?:required|mandatory)\b", text))
        first = re.split(r'[.;!\n]', text, maxsplit=1)[0]
        wrong_task_choice = bool(re.search(rf"\b(?:use|recommend)\s+{re.escape(general)}\b", first))
        return not general_scope or not task_choice or wrong_task_choice

    @staticmethod
    def _contradictory_database_answer(test: TestCase, response: str, required: list[str]) -> bool:
        """Check an explicit answer assertion, without rejecting historical comparisons."""
        from app.services.memory_entities import named_projects
        databases = {"mysql", "postgresql", "sqlite", "mongodb"}
        if not databases.intersection(required):
            return False
        first = re.split(r"[.!?;\n]", response.strip(), maxsplit=1)[0].lower()
        answer_projects = named_projects(response.strip().split(".", 1)[0])
        question_projects = named_projects(test.prompt)
        if answer_projects and question_projects and answer_projects.isdisjoint(question_projects):
            return False
        # A past or negated value is explanatory evidence, not the chosen answer.
        if re.search(r"\b(?:previously|earlier|formerly|used to)\b", first):
            return False
        alternatives = databases.difference(required)
        for value in alternatives:
            if RuleBasedBehaviourEvaluator._term_is_negated(value, first):
                continue
            if first.strip(" *`#:") == value or re.search(
                rf"\b(?:should\s+(?:now\s+)?use|must\s+use|now\s+uses?|currently\s+uses?|uses?|(?:answer|database)(?:\s+technology)?\s+is)\s+{value}\b", first
            ) or re.search(rf"\b{value}\s+(?:is\s+(?:the\s+)?(?:current|correct|required|recommended|chosen)|is\s+(?:currently\s+)?used\s+(?:now|currently)|applies\s+now)\b", first):
                return True
        return False

    @staticmethod
    def _contradictory_requirement(expected: str, response: str, required: list[str]) -> bool:
        if not re.search(r"\bis\s+(?:required|mandatory)\b", expected.lower()):
            return False
        languages = LANGUAGE_WORDS | {"go"}
        if not languages.intersection(required):
            return False
        alternatives = languages.difference(required)
        first = response.strip().splitlines()[0].strip(" .!*`#").lower()
        if first in alternatives:
            return True
        return any(re.search(rf"\b{word}\s+(?:must\s+be\s+used|is\s+(?:required|mandatory))\b", response.lower())
                   and not RuleBasedBehaviourEvaluator._term_is_negated(word, response)
                   for word in alternatives)

    @staticmethod
    def _evidence_ids(test: TestCase, memories: list[Memory]) -> list[str]:
        available = {memory.memory_id for memory in memories}
        return [memory_id for memory_id in test.supporting_memory_ids if memory_id in available]
