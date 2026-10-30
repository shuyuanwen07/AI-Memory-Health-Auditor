"""Reproducible baselines for formal memory-audit experiments.

The baselines use the ordinary TestCase contract so they can be compared with
personalised test suites.  Route integration intentionally happens later in
the experiment service via ``TestSuiteConfiguration.suite_mode``.
"""
from __future__ import annotations

from app.schemas import AuditRun, Dimension, Memory, MemoryStatus, RelationshipType, TestCase, TestSuiteMode, TestType
from app.services.interfaces import TestGenerator
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.test_generator.quality import RuleBasedTestQualityValidator


class DirectGroundTruthTestGenerator(TestGenerator):
    """Baseline A: ask a direct question for each confirmed memory."""

    VERSION = "direct-ground-truth-v10"

    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
        # Match the current facts/relationships used by other suite methods.
        # Asking an unscoped current question about a superseded record would
        # create an invalid baseline, not evidence of a memory defect.
        confirmed = [memory for memory in memories if memory.status in {MemoryStatus.CONFIRMED, MemoryStatus.EDITED}]
        by_id = {memory.memory_id: memory for memory in confirmed}
        base = RuleBasedTestGenerator().generate(confirmed, audit)
        tests = []
        seen = set()
        seen_prompts = set()
        for case in base:
            family = tuple(sorted(case.supporting_memory_ids))
            if family in seen:
                continue
            support = [by_id[key] for key in case.supporting_memory_ids]
            topic = RuleBasedTestGenerator._scoped_topic(*support)
            prompt = case.prompt if case.dimension == Dimension.ACCURACY else f"For {'the current task requirement' if case.dimension == Dimension.APPROPRIATE_USE else 'the latest applicable record'}, what is the user's {topic}? If conflicting constraints are unresolved, state them and request clarification."
            prompt_key = RuleBasedTestQualityValidator.normalize_prompt(prompt)
            if not prompt_key or prompt_key in seen_prompts:
                continue
            seen.add(family)
            seen_prompts.add(prompt_key)
            tests.append(case.model_copy(update={"test_id": f"T{len(tests)+1:03d}",
                "prompt": prompt,
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

    VERSION = "contextual-indirect-auditor-v8"
    ALLOWED_TEST_TYPES = frozenset({TestType.CONTEXTUAL, TestType.INDIRECT})

    def __init__(self, generator: TestGenerator | None = None) -> None:
        self.generator = generator or RuleBasedTestGenerator()

    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
        generated = self.generator.generate(memories, audit)
        by_id = {memory.memory_id: memory for memory in memories}
        result = []
        seen_prompts = set()
        for test in generated[:audit.test_budget]:
            supporting = [by_id[memory_id] for memory_id in test.supporting_memory_ids if memory_id in by_id]
            topic = RuleBasedTestGenerator._scoped_topic(*supporting)
            relationships = {
                relation.type
                for memory in supporting
                for relation in memory.relationships
                if relation.target_memory_id in test.supporting_memory_ids
            }
            prompt = self._contextual_prompt(test.dimension, topic, relationships)
            if test.dimension == Dimension.ACCURACY and any(
                    edge.type == RelationshipType.UPDATE for memory in supporting for edge in memory.relationships):
                prompt = f"Prepare an up-to-date profile for the user. Include the current {topic} as a concrete fact."
            prompt_key = RuleBasedTestQualityValidator.normalize_prompt(prompt)
            if not prompt_key or prompt_key in seen_prompts:
                continue
            seen_prompts.add(prompt_key)
            kind = TestType.CONTEXTUAL if test.dimension == Dimension.ACCURACY else TestType.INDIRECT
            result.append(test.model_copy(update={
                "test_id": f"T{len(result)+1:03d}",
                "prompt": prompt,
                "generator_version": self.VERSION,
                "test_type": kind,
                "target_memory_context": [],
                "probe_group_id": None,
                "probe_variant": None,
            }))
        return result

    @staticmethod
    def _contextual_prompt(dimension: Dimension, topic: str, relationships: set[RelationshipType]) -> str:
        if dimension == Dimension.ACCURACY:
            return f"Prepare a concise profile for the user. Include the remembered {topic} as a concrete fact."
        if dimension == Dimension.FRESHNESS:
            return (f"Prepare an up-to-date profile for the user. Use the current recorded {topic}, "
                    "distinguish it from the historical record it replaced, and explain the replacement.")
        if dimension == Dimension.CONFLICT_RESOLUTION:
            if RelationshipType.CONFLICT in relationships:
                return (f"Before responding to the user about {topic}, identify the recorded conflicting "
                        "constraints and ask for clarification before relying on either one.")
            if RelationshipType.CONTEXTUAL_OVERRIDE in relationships:
                return (f"Prepare the user's current task about {topic}. Apply its task-specific requirement "
                        "instead of the general preference, and ask for clarification if task requirements conflict.")
            return (f"Prepare the user's current task about {topic}. Use the explicitly updated value and "
                    "distinguish it from the historical record it replaced.")
        if dimension == Dimension.APPROPRIATE_USE:
            return (f"Prepare the user's current project task involving {topic}. Apply the task-specific "
                    "requirement while keeping the general preference for other contexts.")
        return f"Prepare a response for the user that uses the remembered {topic} in its relevant context."


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
