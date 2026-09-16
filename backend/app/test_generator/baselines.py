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

    VERSION = "direct-ground-truth-v1"

    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
        confirmed = [memory for memory in memories if memory.status in {MemoryStatus.CONFIRMED, MemoryStatus.EDITED}]
        tests: list[TestCase] = []
        for index, memory in enumerate(confirmed[:audit.test_budget], start=1):
            tests.append(TestCase(
                test_id=f"T{index:03d}", run_id=audit.run_id, dimension=Dimension.ACCURACY,
                prompt=f"What is the user's recorded {RuleBasedTestGenerator._topic(memory)}? Answer with the relevant fact only.",
                expected_behavior=f"State the recorded fact: {memory.canonical_value}.",
                supporting_memory_ids=[memory.memory_id], generator_version=self.VERSION,
                test_type=TestType.DIRECT,
                target_memory_context=[memory.canonical_value],
            ))
        return tests


class FixedTemplateTestGenerator(RuleBasedTestGenerator):
    """Baseline B: standard deterministic templates with explicit provenance."""

    VERSION = "fixed-template-v1"

    def generate(self, memories: list[Memory], audit: AuditRun) -> list[TestCase]:
        tests = super().generate(memories, audit)
        return [test.model_copy(update={"generator_version": self.VERSION}) for test in tests]


def get_suite_generator(mode: TestSuiteMode, behavioural_generator: TestGenerator | None = None) -> TestGenerator:
    """Choose a baseline or a supplied personalised generator.

    A behavioural generator may be LLM-backed.  Baselines stay local and
    deterministic even if the standard suite generator is not.
    """
    if mode == TestSuiteMode.DIRECT_GROUND_TRUTH:
        return DirectGroundTruthTestGenerator()
    if mode == TestSuiteMode.FIXED_TEMPLATE:
        return FixedTemplateTestGenerator()
    return behavioural_generator or RuleBasedTestGenerator()
