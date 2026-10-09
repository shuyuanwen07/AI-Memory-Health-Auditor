"""Deterministic, evidence-aware evaluator for Foundation v0.1."""
from __future__ import annotations

import re
from app.services.location_facts import location_value

from app.schemas import EvaluationResult, Memory, TargetResponse, TestCase
from app.services.memory_topics import LANGUAGE_WORDS, language_words
from app.services.interfaces import BehaviourEvaluator


class RuleBasedBehaviourEvaluator(BehaviourEvaluator):
    """Judge a response against the test's declared ground truth.

    The evaluator is deliberately deterministic for reproducible demonstrations.
    It has the same interface that a future rule-and-LLM evaluator will use.
    """

    VERSION = "rule-based-v34"
    _STOP_WORDS = frozenset({
        "about", "after", "before", "current", "fact", "from", "later", "record",
        "should", "state", "that", "the", "this", "with", "would",
    })

    def evaluate(self, test: TestCase, response: TargetResponse, memories: list[Memory]) -> EvaluationResult:
        from app.evaluator.output_completion import incomplete_output_evaluation
        incomplete = incomplete_output_evaluation(test, response, self.VERSION)
        if incomplete is not None:
            return incomplete
        expected = self._expected_statement(test.expected_behavior)
        response_words = set(self._words(response.response_text))
        required_terms = self._required_terms(expected)
        matched_terms = [
            term for term in required_terms
            if term in response_words and not self._term_is_negated(term, response.response_text)
        ]
        if required_terms == ["conflict", "clarification"]:
            text = response.response_text.lower()
            if re.search(r"\b(?:conflict\w*|incompatible|contradict\w*|disagree\w*)\b", text):
                if "conflict" not in matched_terms:
                    matched_terms.append("conflict")
            if (re.search(r"\b(?:request(?:s|ing)?|ask(?:s|ing)?|seek(?:s|ing)?|requires?|needs?)\b[^.!?\n]{0,50}\bclarification\b|\b(?:please\s+)?clarify\s+(?:which|whether|what)\b|\b(?:ask(?:s|ing)?|inquire)\s+which\s+policy\b", text)
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
        if self._unsupported_database_history(test, response.response_text, memories):
            contradictory = True
            rejection_notes.append("The answer attributes an unsupported database value to the earlier source record.")
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
            if re.search(r"\b(?:no\s+(?:unresolved\s+)?(?:conflict|contradiction|disagreement)|not\s+(?:in\s+)?(?:conflict|incompatible)|(?:not|never)\s+(?:ask|request|seek)|without\s+(?:asking|clarification)|no\s+clarification\s+(?:is\s+)?(?:needed|required)|clarification\s+(?:is\s+)?not\s+(?:needed|required)|no\s+need\s+to\s+(?:ask|clarify))\b", response.response_text.lower()):
                contradictory = True
            for choice in re.finditer(r"\b(?:secrets?\s+(?:should|must)\s+be\s+(?:kept|stored)\s+in|(?:use|choose|follow)\s+(?:the\s+)?(?:first|earlier)\s+policy)\b", response.response_text.lower()):
                prefix = response.response_text.lower()[max(0, choice.start() - 100):choice.start()]
                attributed = re.search(r"\b(?:policy|record|source|statement)\b[^.!?\n]{0,60}\b(?:states?|says?|specifies|reports?)\b[^.!?\n]*$", prefix)
                if not attributed and not re.search(r"\b(?:if|unless|not|never|avoid)\b[^.!?\n]*$", prefix):
                    contradictory = True
                    rejection_notes.append("The response recommends one unresolved policy instead of reporting it as a source statement.")
            support = [m.canonical_value.lower() for m in memories if m.memory_id in test.supporting_memory_ids]
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
        if passed and unsupported_causes:
            return EvaluationResult(
                evaluation_id=f"E{test.test_id[1:]}", test_id=test.test_id, response_id=response.response_id,
                passed=None, failure_type=None,
                reason=("Uncertain: a causal explanation attributes the answer to properties or requirements "
                        f"not linked to that cause in the source ({', '.join(unsupported_causes)}). "
                        "A correct answer keyword cannot establish the stated reason. "
                        "Excluded from scoring; independent review required."),
                evidence_memory_ids=evidence_ids, evaluator=self.VERSION,
            )

        return EvaluationResult(
            evaluation_id=f"E{test.test_id[1:]}", test_id=test.test_id, response_id=response.response_id,
            passed=passed, failure_type=None if passed else test.dimension, reason=reason,
            evidence_memory_ids=evidence_ids, evaluator=self.VERSION,
        )

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
        # Explicit conflict tests require the action as well as the topic.
        if re.search(r"request clarification|ask.*clarif", expected.lower()):
            return ["conflict", "clarification"]
        # Preserve short values and all words of a location/preference.
        value = re.search(r"\b(?:prefer|prefers|favour|favors?)\s+([^.;!?]+)", expected, re.I)
        location = location_value(expected)
        if location or value:
            return list(dict.fromkeys(cls._words(location or value.group(1))))
        # A multiword value cannot be reduced to a generic last word.
        if "object storage" in expected.lower():
            return ["object", "storage"]
        requirement = re.search(
            r"\b([a-z0-9][a-z0-9_+-]*)\s+is\s+(?:required|mandatory)\b",
            expected.lower(),
        )
        if requirement:
            return [requirement.group(1)]
        short_requirement = re.search(r"\b(?:requires?|must\s+use)\s+([a-z0-9][a-z0-9_+-]*)\s*[.!?]*$", expected, re.I)
        if short_requirement:
            return [short_requirement.group(1).lower()]
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
        return any(claim.group(1) not in historical_values
                   and not RuleBasedBehaviourEvaluator._term_is_negated(claim.group(1), claim.group(0))
                   for claim in historical_claims)

    @staticmethod
    def _contradictory_database_answer(test: TestCase, response: str, required: list[str]) -> bool:
        """Check an explicit answer assertion, without rejecting historical comparisons."""
        from app.services.memory_entities import named_projects
        databases = {"mysql", "postgresql", "sqlite", "mongodb"}
        if not databases.intersection(required):
            return False
        first = re.split(r"[.!?\n]", response.strip(), maxsplit=1)[0].lower()
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
            ) or re.search(rf"\b{value}\s+is\s+(?:the\s+)?(?:current|correct|required|recommended|chosen)\b", first):
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
