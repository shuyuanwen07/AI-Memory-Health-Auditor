"""Reproducible baselines for formal memory-audit experiments.

The baselines use the ordinary TestCase contract so they can be compared with
personalised test suites.  Route integration intentionally happens later in
the experiment service via ``TestSuiteConfiguration.suite_mode``.
"""
from __future__ import annotations

import re
from app.schemas import AuditRun, Dimension, Memory, MemoryStatus, RelationshipType, TestCase, TestSuiteMode, TestType
from app.services.interfaces import TestGenerator
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.test_generator.topic_scoped_v41 import TopicScopedRuleBasedTestGenerator
from app.test_generator.topic_scoped_v42 import TopicScopedV42
from app.test_generator.quality import RuleBasedTestQualityValidator


def _source_scope(memories: list[Memory], support_ids: list[str]) -> str | None:
    """Return a bounded task reference only when explicit in the scoped source."""
    scoped=next((m for m in memories if m.memory_id in support_ids and any(
        r.type==RelationshipType.CONTEXTUAL_OVERRIDE and r.target_memory_id in support_ids for r in m.relationships)),None)
    if scoped is None:
        return None
    text=scoped.canonical_value.strip()
    match=re.match(r'^for\s+(?:this(?:\s+particular)?|the)\s+([A-Za-z][A-Za-z -]{0,50}?)(?=\s+only\s*,|\s*,|\s+the\s+[A-Za-z]+\s+(?:requires?|must|needs?|should)\b)',text,re.I)
    if match:
        scope=match.group(1).strip()
        if 1 <= len(scope.split()) <= 5 and not re.search(r'\b(?:and|or|not|only|current|former|other)\b',scope,re.I):
            return f'the {scope}'
    match=re.match(r'^for\s+([A-Za-z][A-Za-z -]{0,50}?)(?=\s+[A-Za-z]+\s+(?:must|should|needs?)\b)',text,re.I)
    if match:
        scope=match.group(1).strip()
        if 1 <= len(scope.split()) <= 5 and not re.search(r'\b(?:and|or|not|only|current|former|other)\b',scope,re.I):
            return f'the {scope}'
    match=re.match(r'^for\s+(?:the\s+)?project\s+([A-Za-z][A-Za-z0-9-]{0,30})\s*,',text,re.I)
    if match:
        return f'the {match.group(1)} project'
    match=re.match(r'^the\s+(assignment|project|task|study)\s+(?:requires?|must|needs?)\b',text,re.I)
    return f'the {match.group(1)}' if match else None


def _distinct_accuracy_candidates(generator, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
    """Prefer an independent fact over an accuracy repeat of a scoped override."""
    upper=max(audit.test_budget, len(memories)+2*sum(len(m.relationships) for m in memories))
    pool=generator.generate(memories,audit.model_copy(update={'test_budget':upper}))
    selected=pool[:audit.test_budget]
    scoped_ids={mid for test in selected if test.dimension==Dimension.APPROPRIATE_USE for mid in test.supporting_memory_ids}
    for idx,test in enumerate(selected):
        if test.dimension!=Dimension.ACCURACY or not scoped_ids.intersection(test.supporting_memory_ids):
            continue
        other=next((item for item in pool if item.dimension==Dimension.ACCURACY
                    and not scoped_ids.intersection(item.supporting_memory_ids)
                    and item not in selected),None)
        if other is not None:
            selected[idx]=other
    return selected


class DirectGroundTruthTestGenerator(TestGenerator):
    """Baseline A: ask a direct question for each confirmed memory."""

    VERSION = "direct-ground-truth-v13"

    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
        # Match the current facts/relationships used by other suite methods.
        # Asking an unscoped current question about a superseded record would
        # create an invalid baseline, not evidence of a memory defect.
        confirmed = [memory for memory in memories if memory.status in {MemoryStatus.CONFIRMED, MemoryStatus.EDITED}]
        by_id = {memory.memory_id: memory for memory in confirmed}
        base = _distinct_accuracy_candidates(TopicScopedV42(), confirmed, audit)
        tests = []
        seen = set()
        seen_prompts = set()
        for case in base:
            family = tuple(sorted(case.supporting_memory_ids))
            if family in seen:
                continue
            support = [by_id[key] for key in case.supporting_memory_ids]
            topic = TopicScopedV42._scoped_topic(*support)
            scope = _source_scope(confirmed,list(family)) if case.dimension == Dimension.APPROPRIATE_USE else None
            if case.dimension == Dimension.APPROPRIATE_USE and scope is None:
                continue
            if case.dimension == Dimension.ACCURACY:
                prompt=case.prompt
            elif case.dimension == Dimension.FRESHNESS:
                prompt=f"What is the current recorded {topic}?"
            elif case.dimension == Dimension.APPROPRIATE_USE:
                prompt=f"What {topic} applies to {scope}?"
            else:
                prompt=f"What is the recorded {topic}?"
            expected=case.expected_behavior
            if case.dimension == Dimension.FRESHNESS:
                current=next((m for m in support if any(r.type==RelationshipType.UPDATE and r.target_memory_id in family for r in m.relationships)),None)
                if current: expected=f"State the current recorded fact: {current.canonical_value.rstrip('.!?')}."
            if case.dimension == Dimension.APPROPRIATE_USE:
                scoped=next((m for m in support if any(r.type==RelationshipType.CONTEXTUAL_OVERRIDE and r.target_memory_id in family for r in m.relationships)),None)
                if scoped: expected=f"Apply the scoped recorded fact: {scoped.canonical_value.rstrip('.!?')}."
            prompt_key = RuleBasedTestQualityValidator.normalize_prompt(prompt)
            if not prompt_key or prompt_key in seen_prompts:
                continue
            seen.add(family)
            seen_prompts.add(prompt_key)
            tests.append(case.model_copy(update={"test_id": f"T{len(tests)+1:03d}",
                "prompt": prompt, "expected_behavior": expected,
                "generator_version": self.VERSION, "test_type": TestType.DIRECT, "target_memory_context": []}))
        return tests



class FixedTemplateTestGenerator(RuleBasedTestGenerator):
    """Baseline B: standard deterministic templates with explicit provenance."""

    VERSION = "fixed-template-v9"

    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
        tests = super().generate(memories, audit)
        return [test.model_copy(update={"generator_version": self.VERSION}) for test in tests]


class ContextualIndirectTestGenerator(TestGenerator):
    """Experiment A auditor arm with contextual/indirect probes only.

    Model-backed generators retain their normal Agent workflow and receive a
    strict allowed-type contract. The deterministic fallback turns the same
    evidence-grounded slots into task prompts without exposing fact values.
    """

    VERSION = "contextual-indirect-auditor-v13"
    ALLOWED_TEST_TYPES = frozenset({TestType.CONTEXTUAL, TestType.INDIRECT})

    def __init__(self, generator: TestGenerator | None = None) -> None:
        self.generator = generator or TopicScopedV42()

    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
        generated = _distinct_accuracy_candidates(self.generator, memories, audit)
        by_id = {memory.memory_id: memory for memory in memories}
        result = []
        seen_prompts = set()
        for test in generated[:audit.test_budget]:
            supporting = [by_id[memory_id] for memory_id in test.supporting_memory_ids if memory_id in by_id]
            topic = TopicScopedV42._scoped_topic(*supporting)
            scope = _source_scope(supporting,test.supporting_memory_ids) if test.dimension == Dimension.APPROPRIATE_USE else None
            if test.dimension == Dimension.APPROPRIATE_USE and scope is None:
                continue
            relationships = {
                relation.type
                for memory in supporting
                for relation in memory.relationships
                if relation.target_memory_id in test.supporting_memory_ids
            }
            prompt = self._contextual_prompt(test.dimension, topic, relationships, scope)
            if test.dimension == Dimension.ACCURACY and len(supporting) == 1:
                subject=TopicScopedRuleBasedTestGenerator.third_party_location_subject(supporting[0])
                if subject:
                    prompt=f"Draft an entry for a shared contact sheet that records where {subject} is based."
            if test.dimension == Dimension.ACCURACY and any(
                    edge.type == RelationshipType.UPDATE for memory in supporting for edge in memory.relationships):
                prompt = f"Draft a current reference-sheet entry for {topic}."
            expected=test.expected_behavior
            if test.dimension == Dimension.FRESHNESS:
                current=next((m for m in supporting if any(r.type==RelationshipType.UPDATE and r.target_memory_id in test.supporting_memory_ids for r in m.relationships)),None)
                if current: expected=f"State the current recorded fact: {current.canonical_value.rstrip('.!?')}."
            if test.dimension == Dimension.APPROPRIATE_USE:
                scoped=next((m for m in supporting if any(r.type==RelationshipType.CONTEXTUAL_OVERRIDE and r.target_memory_id in test.supporting_memory_ids for r in m.relationships)),None)
                if scoped: expected=f"Apply the task-specific recorded requirement: {scoped.canonical_value.rstrip('.!?')}."
            prompt_key = RuleBasedTestQualityValidator.normalize_prompt(prompt)
            if not prompt_key or prompt_key in seen_prompts:
                continue
            seen_prompts.add(prompt_key)
            kind = TestType.CONTEXTUAL if test.dimension == Dimension.ACCURACY else TestType.INDIRECT
            result.append(test.model_copy(update={
                "test_id": f"T{len(result)+1:03d}",
                "prompt": prompt,
                "expected_behavior": expected,
                "generator_version": self.VERSION,
                "test_type": kind,
                "target_memory_context": [],
                "probe_group_id": None,
                "probe_variant": None,
            }))
        return result

    @staticmethod
    def _contextual_prompt(dimension: Dimension, topic: str, relationships: set[RelationshipType], scope: str | None = None) -> str:
        if dimension == Dimension.ACCURACY:
            return f"Draft a shared reference-sheet entry about {topic} for this situation."
        if dimension == Dimension.FRESHNESS:
            return f"Draft a current planning note about {topic} that the team can use."
        if dimension == Dimension.APPROPRIATE_USE:
            return f"Draft an instruction for colleagues about {topic} for {scope}."
        return f"Draft an action note for colleagues planning around {topic}: what should it include and what action follows?"


class HumanReviewedFixedTemplateGenerator(TestGenerator):
    """Instantiate a source-bound rule draft after a researcher reviewed its release."""

    VERSION = "human-reviewed-fixed-template-v1"

    def __init__(self, questions):
        self.questions = questions

    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
        return [TestCase(
            test_id=question.template_id,
            run_id=audit.run_id,
            dimension=question.dimension,
            prompt=question.prompt,
            expected_behavior=question.expected_behavior,
            supporting_memory_ids=list(question.supporting_memory_ids),
            generator_version=self.VERSION,
            test_type=question.test_type,
            target_memory_context=[],
        ) for question in self.questions]


def get_suite_generator(mode: TestSuiteMode, behavioural_generator: TestGenerator | None = None) -> TestGenerator:
    """Choose a frozen suite method and its eligible generator.

    Direct and fixed baselines stay deterministic. The contextual/indirect mode
    constrains a model-backed generator or applies contextual task wording to
    deterministic fallback candidates.
    """
    if mode == TestSuiteMode.PAIRED_CONTEXTUAL:
        from app.test_generator.paired import PairedContextualTestGenerator
        return PairedContextualTestGenerator()
    if mode == TestSuiteMode.CONTEXTUAL_INDIRECT:
        if behavioural_generator is not None:
            from app.test_generator.llm_generator import LLMTestGenerator
            if isinstance(behavioural_generator, LLMTestGenerator):
                behavioural_generator.allowed_test_types = ContextualIndirectTestGenerator.ALLOWED_TEST_TYPES
                return behavioural_generator
        return ContextualIndirectTestGenerator(behavioural_generator)
    if mode == TestSuiteMode.DIRECT_GROUND_TRUTH:
        return DirectGroundTruthTestGenerator()
    if mode == TestSuiteMode.FIXED_TEMPLATE:
        return FixedTemplateTestGenerator()
    return behavioural_generator or RuleBasedTestGenerator()
