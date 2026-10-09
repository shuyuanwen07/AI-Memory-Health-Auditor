"""Reproducible baselines for formal memory-audit experiments.

The baselines use the ordinary TestCase contract so they can be compared with
personalised test suites.  Route integration intentionally happens later in
the experiment service via ``TestSuiteConfiguration.suite_mode``.
"""
from __future__ import annotations

from app.schemas import AuditRun, Dimension, Memory, MemoryStatus, TestCase, TestSuiteMode, TestType
from app.services.interfaces import TestGenerator
from app.test_generator.rule_based import RuleBasedTestGenerator


class DirectGroundTruthTestGenerator(TestGenerator):
    """Baseline A: ask a direct question for each confirmed memory."""

    VERSION = "direct-ground-truth-v3"

    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
        # Match the current facts/relationships used by other suite methods.
        # Asking an unscoped current question about a superseded record would
        # create an invalid baseline, not evidence of a memory defect.
        confirmed = [memory for memory in memories if memory.status in {MemoryStatus.CONFIRMED, MemoryStatus.EDITED}]
        by_id = {memory.memory_id: memory for memory in confirmed}
        base = RuleBasedTestGenerator().generate(confirmed, audit)
        tests = []
        seen = set()
        for case in base:
            family = tuple(sorted(case.supporting_memory_ids))
            if family in seen:
                continue
            seen.add(family)
            support = [by_id[key] for key in case.supporting_memory_ids]
            topic = RuleBasedTestGenerator._scoped_topic(*support)
            tests.append(case.model_copy(update={"test_id": f"T{len(tests)+1:03d}",
                "prompt": case.prompt if case.dimension == Dimension.ACCURACY else f"For {'the current task requirement' if case.dimension == Dimension.APPROPRIATE_USE else 'the latest applicable record'}, what is the user's {topic}? If conflicting constraints are unresolved, state them and request clarification.",
                "generator_version": self.VERSION, "test_type": TestType.DIRECT, "target_memory_context": []}))
        return tests



class FixedTemplateTestGenerator(RuleBasedTestGenerator):
    """Baseline B: standard deterministic templates with explicit provenance."""

    VERSION = "fixed-template-v2"

    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
        tests = super().generate(memories, audit)
        return [test.model_copy(update={"generator_version": self.VERSION}) for test in tests]


def get_suite_generator(mode: TestSuiteMode, behavioural_generator: TestGenerator | None = None) -> TestGenerator:
    """Choose a baseline or a supplied personalised generator.

    A behavioural generator may be LLM-backed.  Baselines stay local and
    deterministic even if the standard suite generator is not.
    """
    if mode == TestSuiteMode.PAIRED_CONTEXTUAL:
        from app.test_generator.paired import PairedContextualTestGenerator
        return PairedContextualTestGenerator()
    if mode == TestSuiteMode.DIRECT_GROUND_TRUTH:
        return DirectGroundTruthTestGenerator()
    if mode == TestSuiteMode.FIXED_TEMPLATE:
        return FixedTemplateTestGenerator()
    return behavioural_generator or RuleBasedTestGenerator()
