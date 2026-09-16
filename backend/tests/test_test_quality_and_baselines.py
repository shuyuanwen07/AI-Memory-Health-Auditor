"""Deterministic contracts for research-oriented test-suite extensions."""
from __future__ import annotations

from datetime import datetime, timezone

from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.schemas import (
    AuditRun,
    AuditStatus,
    Conversation,
    ConversationMessage,
    Dimension,
    GroundingStatus,
    Memory,
    MemoryStatus,
    TargetConfiguration,
    TargetProvider,
    TestCase,
    TestQualityStatus,
    TestSuiteMode,
    TestType,
)
from app.test_generator.baselines import (
    DirectGroundTruthTestGenerator,
    FixedTemplateTestGenerator,
    get_suite_generator,
)
from app.test_generator.quality import RuleBasedTestQualityValidator
from app.test_generator.rule_based import RuleBasedTestGenerator


def _audit(budget: int = 8) -> AuditRun:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return AuditRun(
        run_id="RUN-QUALITY", conversation_id="C-QUALITY", status=AuditStatus.CREATED,
        target_configuration=TargetConfiguration.STRONG, provider=TargetProvider.RULE_BASED,
        model="rule-based-target-ai", temperature=0.0, random_seed=42,
        test_budget=budget, prompt_template_version="v1", created_at=now,
    )


def _confirmed_memory() -> Memory:
    return Memory(
        memory_id="M001", conversation_id="C-QUALITY", canonical_value="The user is based in Sydney.",
        status=MemoryStatus.CONFIRMED, source_message_ids=["MSG001"],
    )


def test_quality_validator_accepts_confirmed_grounded_answer_independent_test():
    memory = _confirmed_memory()
    test = TestCase(
        test_id="T001", run_id="RUN-QUALITY", dimension=Dimension.ACCURACY,
        prompt="What city is recorded as the user's location?", expected_behavior="State Sydney.",
        supporting_memory_ids=[memory.memory_id], generator_version="test", test_type=TestType.DIRECT,
    )

    assessment = RuleBasedTestQualityValidator().validate(test, [memory])

    assert assessment.quality_status == TestQualityStatus.ACCEPTED
    assert assessment.grounding_status == GroundingStatus.GROUNDED
    assert assessment.validator_version == "rule-based-quality-v1"


def test_quality_validator_rejects_leaked_or_ungrounded_evidence():
    memory = _confirmed_memory()
    leaked = TestCase(
        test_id="T001", run_id="RUN-QUALITY", dimension=Dimension.ACCURACY,
        prompt="Is the user based in Sydney?", expected_behavior="Answer yes.",
        supporting_memory_ids=[memory.memory_id], generator_version="test",
    )
    missing = leaked.model_copy(update={"test_id": "T002", "prompt": "What city is recorded?", "supporting_memory_ids": ["M404"]})
    validator = RuleBasedTestQualityValidator()

    assert validator.validate(leaked, [memory]).quality_status == TestQualityStatus.REJECTED
    assessment = validator.validate(missing, [memory])
    assert assessment.quality_status == TestQualityStatus.REJECTED
    assert assessment.grounding_status == GroundingStatus.UNGROUNDED


def test_rule_generator_labels_question_styles_without_changing_dimensions():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conversation = Conversation(
        conversation_id="C-QUALITY", created_at=now, authorised=True,
        messages=[ConversationMessage(
            message_id="MSG001", role="user", timestamp=now,
            content=("I used MySQL before. The backend now uses PostgreSQL. I generally prefer Python. "
                     "This assignment currently requires Java. The assignment must not use Java because requirements conflict. "
                     "I am based in Sydney."),
        )],
    )
    tests = RuleBasedTestGenerator().generate(RuleBasedMemoryExtractor().extract(conversation), _audit(20))

    assert {test.dimension for test in tests} == set(Dimension)
    assert TestType.DIRECT in {test.test_type for test in tests}
    assert TestType.CONTEXTUAL in {test.test_type for test in tests}
    assert TestType.INDIRECT in {test.test_type for test in tests}
    assert TestType.PARAPHRASED in {test.test_type for test in tests}


def test_baselines_are_deterministic_and_selectable_without_a_route():
    memory = _confirmed_memory()
    direct = DirectGroundTruthTestGenerator().generate([memory], _audit())

    assert len(direct) == 1
    assert direct[0].dimension == Dimension.ACCURACY
    assert direct[0].test_type == TestType.DIRECT
    assert direct[0].generator_version == "direct-ground-truth-v1"
    assert isinstance(get_suite_generator(TestSuiteMode.DIRECT_GROUND_TRUTH), DirectGroundTruthTestGenerator)
    assert isinstance(get_suite_generator(TestSuiteMode.FIXED_TEMPLATE), FixedTemplateTestGenerator)
    assert isinstance(get_suite_generator(TestSuiteMode.BEHAVIOURAL), RuleBasedTestGenerator)


def test_fixed_template_baseline_preserves_templates_but_records_its_method():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conversation = Conversation(
        conversation_id="C-FIXED", created_at=now, authorised=True,
        messages=[ConversationMessage(
            message_id="MSG001", role="user", timestamp=now,
            content="I used MySQL before. The backend now uses PostgreSQL. I am based in Sydney.",
        )],
    )
    memories = RuleBasedMemoryExtractor().extract(conversation)
    fixed = FixedTemplateTestGenerator().generate(memories, _audit())
    regular = RuleBasedTestGenerator().generate(memories, _audit())

    assert [test.prompt for test in fixed] == [test.prompt for test in regular]
    assert {test.generator_version for test in fixed} == {"fixed-template-v1"}
