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
    assert assessment.validator_version == RuleBasedTestQualityValidator.VERSION


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
    assert direct[0].generator_version == "direct-ground-truth-v3"
    assert isinstance(get_suite_generator(TestSuiteMode.DIRECT_GROUND_TRUTH), DirectGroundTruthTestGenerator)
    assert isinstance(get_suite_generator(TestSuiteMode.FIXED_TEMPLATE), FixedTemplateTestGenerator)
    assert isinstance(get_suite_generator(TestSuiteMode.BEHAVIOURAL), RuleBasedTestGenerator)


def test_meeting_question_identifies_the_event_without_revealing_person_or_date():
    memory = _confirmed_memory().model_copy(update={'canonical_value': 'I met Dr. Chen on September 12'})
    test = RuleBasedTestGenerator().generate([memory], _audit())[0]
    assert test.prompt == 'Who did the user meet, and when? State the person and recorded date.'
    assert 'Chen' not in test.prompt and 'September' not in test.prompt and '12' not in test.prompt
    assert RuleBasedTestQualityValidator().validate(test, [memory]).quality_status == TestQualityStatus.ACCEPTED
    ambiguous = test.model_copy(update={'prompt': "What is the user's recorded stored information? State the relevant fact only."})
    assessment = RuleBasedTestQualityValidator().validate(ambiguous, [memory])
    assert assessment.quality_status == TestQualityStatus.REJECTED
    assert assessment.grounding_status == GroundingStatus.GROUNDED


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
    assert {test.generator_version for test in fixed} == {"fixed-template-v2"}


def test_location_leak_detection_handles_cities_outside_the_builtin_examples():
    for city in ("Oslo", "Dublin", "New York", "Wellington"):
        canonical = f"The user is based in {city}."
        assert RuleBasedTestQualityValidator._answer_leaked(canonical, f"Is the user based in {city}?")
        assert not RuleBasedTestQualityValidator._answer_leaked(canonical, "What city is the user based in?")


def test_suite_quality_rejects_duplicate_prompts_with_different_answers():
    first = TestCase(test_id='TD1', run_id='RUN', dimension='accuracy', prompt='Which task?',
        expected_behavior='Policy A', supporting_memory_ids=['M1'], generator_version='test')
    second = first.model_copy(update={'test_id': 'TD2', 'prompt': 'Which task!', 'expected_behavior': 'Policy B'})
    assert RuleBasedTestQualityValidator.validate_suite([first, second]) is not None


def test_unresolved_secret_conflict_does_not_generate_an_ambiguous_fact_question():
    from app.schemas import MemoryRelationship
    first = Memory(memory_id='M1', conversation_id='C', status='confirmed', canonical_value='I require deployment secrets in environment variables')
    second = Memory(memory_id='M2', conversation_id='C', status='confirmed', canonical_value='I require deployment secrets in a configuration file',
        relationships=[MemoryRelationship(type='CONFLICT', target_memory_id='M1')])
    tests = RuleBasedTestGenerator().generate([first, second], _audit())
    assert len(tests) == 1
    assert tests[0].dimension == Dimension.CONFLICT_RESOLUTION
    assert 'deployment secret storage' in tests[0].prompt
    assert 'current task' not in tests[0].prompt
    assert 'clarification' in tests[0].expected_behavior


def test_go_preference_is_a_programming_language_question():
    memory = Memory(memory_id='M1', conversation_id='C', status='confirmed', canonical_value='I generally prefer Go')
    tests = RuleBasedTestGenerator().generate([memory], _audit())
    assert 'programming language' in tests[0].prompt
    assert 'Go' not in tests[0].prompt
