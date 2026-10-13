"""Focused contracts for Experiment A's contextual/indirect third arm."""
from datetime import datetime, timezone

import pytest

from app.extraction.llm import PipelineRequestError
from app.schemas import (
    AuditRun,
    AuditStatus,
    Dimension,
    Memory,
    MemoryRelationship,
    MemoryStatus,
    RelationshipType,
    TargetConfiguration,
    TargetProvider,
    TestType,
    TestSuiteMode,
)
from app.test_generator.baselines import ContextualIndirectTestGenerator, get_suite_generator
from app.test_generator.llm_generator import LLMTestGenerator, _TestPayload
from app.test_generator.quality import RuleBasedTestQualityValidator


def _audit(budget: int = 8) -> AuditRun:
    return AuditRun(
        run_id="RUN-CONTEXTUAL", conversation_id="HISTORY-CONTEXTUAL",
        status=AuditStatus.CREATED, target_configuration=TargetConfiguration.STRONG,
        provider=TargetProvider.RULE_BASED, model="synthetic-target", temperature=0,
        random_seed=42, test_budget=budget, prompt_template_version="test-v1",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _update_memories() -> list[Memory]:
    previous = Memory(
        memory_id="M001", conversation_id="HISTORY-CONTEXTUAL",
        canonical_value="The Atlas project database used SQLite.",
        status=MemoryStatus.CONFIRMED, source_message_ids=["MSG001"],
    )
    current = Memory(
        memory_id="M002", conversation_id="HISTORY-CONTEXTUAL",
        canonical_value="The Atlas project database now uses PostgreSQL.",
        status=MemoryStatus.CONFIRMED, source_message_ids=["MSG002"],
        relationships=[MemoryRelationship(type=RelationshipType.UPDATE, target_memory_id="M001")],
    )
    return [previous, current]


def test_rule_backed_contextual_suite_has_only_answer_independent_contextual_items():
    memories = _update_memories()
    generator = get_suite_generator(TestSuiteMode.CONTEXTUAL_INDIRECT)
    assert isinstance(generator, ContextualIndirectTestGenerator)

    tests = generator.generate(memories, _audit(6))

    assert len(tests) <= 6
    assert tests
    assert {test.generator_version for test in tests} == {ContextualIndirectTestGenerator.VERSION}
    assert all(test.test_type in {TestType.CONTEXTUAL, TestType.INDIRECT} for test in tests)
    assert all("SQLite" not in test.prompt and "PostgreSQL" not in test.prompt for test in tests)
    validator = RuleBasedTestQualityValidator()
    assert all(validator.validate(test, memories).quality_status.value == "accepted" for test in tests)
    assert any(test.dimension == Dimension.FRESHNESS for test in tests)


def test_contextual_mode_keeps_model_agent_and_rejects_direct_output():
    generator = LLMTestGenerator(client=object())
    selected = get_suite_generator(TestSuiteMode.CONTEXTUAL_INDIRECT, generator)
    assert selected is generator
    assert generator.allowed_test_types == frozenset({TestType.CONTEXTUAL, TestType.INDIRECT})

    direct = _TestPayload(
        dimension=Dimension.ACCURACY, test_type=TestType.DIRECT,
        prompt="What database technology does the user use?",
        expected_behavior="State the current database.", supporting_memory_ids=["M002"],
    )
    with pytest.raises(PipelineRequestError, match="outside this suite's frozen mode"):
        generator._validate_tests(
            [direct], _update_memories(), _audit(),
            allowed_test_types=generator.allowed_test_types,
        )
