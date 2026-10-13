"""Deterministic contracts for research-oriented test-suite extensions."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

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
    MemoryRelationship,
    RelationshipType,
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


@pytest.mark.parametrize('relationship_type', [RelationshipType.UPDATE, RelationshipType.CONTEXTUAL_OVERRIDE, RelationshipType.CONFLICT])
def test_conflict_resolution_requires_both_relationship_endpoints(relationship_type):
    old = Memory(memory_id='old', conversation_id='C', canonical_value='The standard policy requires encrypted archives.', status=MemoryStatus.CONFIRMED)
    current = Memory(memory_id='current', conversation_id='C', canonical_value='The project policy requires signed archives.', status=MemoryStatus.CONFIRMED,
                     relationships=[MemoryRelationship(type=relationship_type, target_memory_id='old')])
    test = TestCase(test_id='T',run_id='R',dimension=Dimension.CONFLICT_RESOLUTION,
        prompt='How should the recorded project setting relate to the earlier setting?',
        expected_behavior='Identify both recorded settings and request clarification before selecting either.',
        supporting_memory_ids=['current'],generator_version='fixture')
    validator = RuleBasedTestQualityValidator()
    assert validator.validate(test,[old,current]).quality_status == TestQualityStatus.REJECTED
    assert validator.validate(test.model_copy(update={'supporting_memory_ids':['old']}),[old,current]).quality_status == TestQualityStatus.REJECTED
    complete = test.model_copy(update={'supporting_memory_ids':['old','current']})
    assert validator.validate(complete,[old,current]).quality_status == TestQualityStatus.ACCEPTED


def test_ordinary_recall_cannot_be_labelled_conflict_resolution_without_a_relationship():
    memory = Memory(memory_id='fact',conversation_id='C',canonical_value='The user prefers short written summaries.',status=MemoryStatus.CONFIRMED)
    test = TestCase(test_id='T',run_id='R',dimension=Dimension.CONFLICT_RESOLUTION,
        prompt="What is the user's preferred feedback method?",expected_behavior='State the recorded general preference.',
        supporting_memory_ids=['fact'],generator_version='fixture')
    validator = RuleBasedTestQualityValidator()
    rejected = validator.validate(test,[memory])
    assert rejected.quality_status == TestQualityStatus.REJECTED
    assert rejected.grounding_status == GroundingStatus.UNGROUNDED
    assert 'Ordinary factual recall' in rejected.reason
    assert validator.validate(test.model_copy(update={'dimension':Dimension.ACCURACY}),[memory]).quality_status == TestQualityStatus.ACCEPTED


def test_scheduled_event_date_question_identifies_event_without_leaking_answer_or_observation_time():
    memories = [Memory(memory_id='launch',conversation_id='C',canonical_value='The Vega launch is scheduled for 2030-01-01.',
        status=MemoryStatus.CONFIRMED,timestamp=datetime(2026,1,1,tzinfo=timezone.utc)),
        Memory(memory_id='review',conversation_id='C',canonical_value='The Lyra review was scheduled for 2031-02-03.',
        status=MemoryStatus.CONFIRMED,timestamp=datetime(2026,1,1,tzinfo=timezone.utc))]
    tests = RuleBasedTestGenerator().generate(memories,_audit(4))
    assert len(tests) == 2
    assert 'Vega launch' in tests[0].prompt
    assert 'Lyra review' in tests[1].prompt
    for test in tests:
        assert test.dimension == Dimension.ACCURACY
        assert '2030' not in test.prompt and '2031' not in test.prompt and '2026' not in test.prompt
        assert 'scheduled for' in test.expected_behavior
        assert RuleBasedTestQualityValidator().validate(test,memories).quality_status == TestQualityStatus.ACCEPTED
    assert RuleBasedTestQualityValidator.validate_suite(tests) is None
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


def test_unresolved_conflict_cannot_select_a_policy_by_recency():
    memories = [
        Memory(memory_id='M1', conversation_id='C', canonical_value='Secrets must be in environment variables.', status=MemoryStatus.CONFIRMED),
        Memory(memory_id='M2', conversation_id='C', canonical_value='Secrets must be in a configuration file.', status=MemoryStatus.CONFIRMED,
               relationships=[MemoryRelationship(type=RelationshipType.CONFLICT, target_memory_id='M1')]),
    ]
    test = TestCase(test_id='T', run_id='R', dimension=Dimension.CONFLICT_RESOLUTION, prompt='Where should project secrets be stored?',
                    expected_behavior='Identify the conflict and use the more recent configuration-file policy.', supporting_memory_ids=['M1', 'M2'], generator_version='fixture')
    assert RuleBasedTestQualityValidator().validate(test, memories).quality_status == TestQualityStatus.REJECTED
    valid = test.model_copy(update={'expected_behavior': 'Identify both recorded policies and request clarification before choosing either.'})
    assert RuleBasedTestQualityValidator().validate(valid, memories).quality_status == TestQualityStatus.ACCEPTED
    missing = valid.model_copy(update={'supporting_memory_ids': ['M2']})
    assert RuleBasedTestQualityValidator().validate(missing, memories).quality_status == TestQualityStatus.REJECTED


def test_small_budget_prioritises_actual_conflicts_over_resolved_updates():
    def memory(id, text, relationships=()):
        return Memory(memory_id=id, conversation_id='C', canonical_value=text, status=MemoryStatus.CONFIRMED, relationships=list(relationships))
    memories = [memory('old', 'Previously used MySQL.'), memory('new', 'Now uses PostgreSQL.', [MemoryRelationship(type=RelationshipType.UPDATE, target_memory_id='old')]),
                memory('python', 'Generally prefers Python.'), memory('java', 'Java is required for the task.', [MemoryRelationship(type=RelationshipType.CONTEXTUAL_OVERRIDE, target_memory_id='python')]),
                memory('env', 'Secrets must be in environment variables.'), memory('file', 'Secrets must be in a configuration file.', [MemoryRelationship(type=RelationshipType.CONFLICT, target_memory_id='env')])]
    tests = RuleBasedTestGenerator().generate(memories, _audit(4))
    conflict = next(test for test in tests if test.dimension == Dimension.CONFLICT_RESOLUTION)
    assert set(conflict.supporting_memory_ids) == {'env', 'file'}
    assert 'clarification' in conflict.expected_behavior


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


@pytest.mark.parametrize('value', ['NC-7492-V', 'nc-7492-v', 'NC_7492_V', 'NC7492V', 'NC 7492 V'])
def test_code_question_revealing_complete_value_is_rejected(value):
    memory = _confirmed_memory().model_copy(update={'canonical_value': 'The Nacre project access code is NC-7492-V.'})
    test = TestCase(test_id='T-CODE', run_id='RUN', dimension=Dimension.ACCURACY,
        prompt=f'Which project uses {value}?', expected_behavior=memory.canonical_value,
        supporting_memory_ids=[memory.memory_id], generator_version='fixture')
    assessment = RuleBasedTestQualityValidator().validate(test, [memory])
    assert assessment.quality_status == TestQualityStatus.REJECTED
    assert assessment.grounding_status == GroundingStatus.GROUNDED
    assert 'copies a supporting canonical memory value' in assessment.reason


@pytest.mark.parametrize('prompt', [
    'What is the access code for the Nacre project?',
    'Which project uses NC-0000-V?',
    'Which project uses NC-7492-V2?',
    'Which project uses XNC-7492-V?',
])
def test_code_leak_check_does_not_match_subject_or_different_code(prompt):
    assert not RuleBasedTestQualityValidator._answer_leaked('The Nacre project access code is NC-7492-V.', prompt)


def test_code_question_without_answer_is_accepted():
    memory = _confirmed_memory().model_copy(update={'canonical_value': 'The Nacre project access code is NC-7492-V.'})
    test = TestCase(test_id='T-CODE', run_id='RUN', dimension=Dimension.ACCURACY,
        prompt='What is the access code for the Nacre project?', expected_behavior=memory.canonical_value,
        supporting_memory_ids=[memory.memory_id], generator_version='fixture')
    assert RuleBasedTestQualityValidator().validate(test, [memory]).quality_status == TestQualityStatus.ACCEPTED


def test_question_revealing_either_code_in_multi_value_reference_is_rejected():
    canonical = 'The previous code was OLD-7492-V and the current code is NC-7492-V.'
    assert RuleBasedTestQualityValidator._answer_leaked(canonical, 'Is OLD-7492-V still valid?')
    assert RuleBasedTestQualityValidator._answer_leaked(canonical, 'Is NC-7492-V currently valid?')


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


def test_user_location_cannot_be_relabelled_as_ai_location():
    memory=_confirmed_memory()
    question=TestCase(test_id='T-SUBJECT', run_id='R', dimension=Dimension.ACCURACY,
                     prompt='Where are you located?', expected_behavior='The AI is based in Sydney.',
                     supporting_memory_ids=['M001'],generator_version='fixture')
    check=RuleBasedTestQualityValidator()
    assert check.validate(question,[memory]).quality_status==TestQualityStatus.REJECTED
    assert check.validate(question.model_copy(update={'expected_behavior':'The user is based in Sydney.'}),[memory]).quality_status==TestQualityStatus.REJECTED
    valid=question.model_copy(update={'prompt':'Where is the user based?', 'expected_behavior':'The user is based in Sydney.'})
    assert check.validate(valid,[memory]).quality_status==TestQualityStatus.ACCEPTED



def test_suite_uniqueness_preserves_non_latin_questions():
    base = TestCase(test_id='T1', run_id='R', dimension=Dimension.ACCURACY,
        prompt='用户目前住在哪里？', expected_behavior='State the recorded city.',
        supporting_memory_ids=['M1'], generator_version='fixture')
    another = base.model_copy(update={'test_id':'T2','prompt':'这个项目现在使用什么数据库？'})
    assert RuleBasedTestQualityValidator.validate_suite([base, another]) is None
    duplicate = base.model_copy(update={'test_id':'T3','prompt':'用户目前住在哪里 ?'})
    assert 'Duplicate' in RuleBasedTestQualityValidator.validate_suite([base, duplicate])
    punctuation = base.model_copy(update={'prompt':'？？？'})
    assert 'readable' in RuleBasedTestQualityValidator.validate_suite([punctuation])
    assert 'Duplicate' in RuleBasedTestQualityValidator.validate_suite([base.model_copy(update={'prompt':'ＡＢＣ？'}),base.model_copy(update={'test_id':'T4','prompt':'abc!'})])



def test_freshness_cannot_use_receipt_time_or_unrelated_requirement_as_source():
    memories = [
        Memory(memory_id='old',conversation_id='C',canonical_value='Cedar used SQLite.',status=MemoryStatus.CONFIRMED),
        Memory(memory_id='current',conversation_id='C',canonical_value='Cedar now uses MariaDB.',status=MemoryStatus.CONFIRMED,
               relationships=[MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id='old')]),
        Memory(memory_id='task',conversation_id='C',canonical_value='Cedar assignment requires TypeScript.',status=MemoryStatus.CONFIRMED),
    ]
    test = TestCase(test_id='T',run_id='R',dimension=Dimension.FRESHNESS,
        prompt="When was the last update to Cedar's database information?",
        expected_behavior='Provide its last update timestamp.',supporting_memory_ids=['old','current'],generator_version='fixture')
    validator=RuleBasedTestQualityValidator()
    assert validator.validate(test,memories).quality_status==TestQualityStatus.REJECTED
    unrelated=test.model_copy(update={'prompt':'What language is required for the assignment?',
        'expected_behavior':'Use TypeScript.','supporting_memory_ids':['task']})
    assert validator.validate(unrelated,memories).quality_status==TestQualityStatus.REJECTED
    current=test.model_copy(update={'prompt':'Which database should Cedar use now?', 'expected_behavior':'Use MariaDB.'})
    assert validator.validate(current,memories).quality_status==TestQualityStatus.ACCEPTED
    missing_prior=current.model_copy(update={'supporting_memory_ids':['current']})
    assert validator.validate(missing_prior,memories).quality_status==TestQualityStatus.REJECTED


def test_explicit_source_update_date_can_support_a_date_question():
    memory=Memory(memory_id='dated',conversation_id='C',canonical_value='Cedar database was updated on September 12.',status=MemoryStatus.CONFIRMED)
    test=TestCase(test_id='T',run_id='R',dimension=Dimension.ACCURACY,
        prompt='When was the last update to the project database?',expected_behavior='September 12.',
        supporting_memory_ids=['dated'],generator_version='fixture')
    assert RuleBasedTestQualityValidator().validate(test,[memory]).quality_status==TestQualityStatus.ACCEPTED


def test_neutral_location_reference_does_not_become_assistant_location():
    memory=Memory(memory_id='M-neutral',conversation_id='C',status=MemoryStatus.CONFIRMED,canonical_value='Location: Oslo')
    test=TestCase(test_id='T-neutral',run_id='R',dimension=Dimension.ACCURACY,prompt='Where are you based?',expected_behavior='State Oslo.',supporting_memory_ids=[memory.memory_id],generator_version='fixture')
    assessment=RuleBasedTestQualityValidator().validate(test,[memory])
    assert assessment.quality_status==TestQualityStatus.REJECTED
    assert 'identify the subject explicitly' in assessment.reason


def test_model_canonical_preferences_and_project_platforms_generate_specific_valid_questions():
    memories = [
        Memory(memory_id='go',conversation_id='C',status=MemoryStatus.CONFIRMED,canonical_value='Prefers Go for personal tools'),
        Memory(memory_id='language',conversation_id='C',status=MemoryStatus.CONFIRMED,canonical_value='For the Willow project, must use TypeScript',relationships=[MemoryRelationship(type=RelationshipType.CONTEXTUAL_OVERRIDE,target_memory_id='go')]),
        Memory(memory_id='zoom',conversation_id='C',status=MemoryStatus.CONFIRMED,canonical_value='Willow review must use Zoom only'),
        Memory(memory_id='teams',conversation_id='C',status=MemoryStatus.CONFIRMED,canonical_value='Willow review must use Teams only',relationships=[MemoryRelationship(type=RelationshipType.CONFLICT,target_memory_id='zoom')]),
        Memory(memory_id='style',conversation_id='C',status=MemoryStatus.CONFIRMED,canonical_value='Prefers short written summaries'),
    ]
    tests = RuleBasedTestGenerator().generate(memories,_audit(8))
    assert tests
    assert all(RuleBasedTestQualityValidator().validate(test,memories).quality_status == TestQualityStatus.ACCEPTED for test in tests)
    assert any('meeting platform' in test.prompt and 'Willow' in test.prompt for test in tests if test.dimension == Dimension.CONFLICT_RESOLUTION)
    assert any('generally prefer' in test.prompt for test in tests if test.supporting_memory_ids == ['go'])
    assert any('communication style' in test.prompt for test in tests if test.supporting_memory_ids == ['style'])
    assert all('Zoom' not in test.prompt and 'Teams' not in test.prompt for test in tests)


def test_canonical_subject_fragments_do_not_make_ai_personal_profile_questions_valid():
    validator = RuleBasedTestQualityValidator()
    for fact in ('Based in Bergen','Located in Bergen','Lives in Bergen'):
        memory = Memory(memory_id='location',conversation_id='C',status=MemoryStatus.CONFIRMED,canonical_value=fact)
        test = TestCase(test_id='T',run_id='R',dimension=Dimension.ACCURACY,prompt='Where are you currently based?',expected_behavior='The AI should state it is based in Bergen.',supporting_memory_ids=['location'],generator_version='fixture')
        assert validator.validate(test,[memory]).quality_status == TestQualityStatus.REJECTED
        indirect = test.model_copy(update={'prompt':'What is the current city where you are based?'})
        assert validator.validate(indirect,[memory]).quality_status == TestQualityStatus.REJECTED
        corrected = test.model_copy(update={'prompt':"Where is the user currently based?",'expected_behavior':'The user is based in Bergen.'})
        assert validator.validate(corrected,[memory]).quality_status == TestQualityStatus.ACCEPTED
    memory = memory.model_copy(update={'memory_id':'preference','canonical_value':'Prefers short written summaries'})
    test = test.model_copy(update={'prompt':'What is your preferred method for receiving feedback?','expected_behavior':'The AI should state a preference for short written summaries.','supporting_memory_ids':['preference']})
    assert validator.validate(test,[memory]).quality_status == TestQualityStatus.REJECTED
    corrected = test.model_copy(update={'prompt':"What is the user's preferred feedback method?",'expected_behavior':'The user prefers short written summaries.'})
    assert validator.validate(corrected,[memory]).quality_status == TestQualityStatus.ACCEPTED


def test_general_preference_probe_cannot_demand_a_contextual_override():
    memories=[Memory(memory_id='P',conversation_id='C',canonical_value='I generally prefer Python.',status=MemoryStatus.CONFIRMED),Memory(memory_id='J',conversation_id='C',canonical_value='For the Nacre project, Java is required.',status=MemoryStatus.CONFIRMED,relationships=[MemoryRelationship(type=RelationshipType.CONTEXTUAL_OVERRIDE,target_memory_id='P')])]
    test=TestCase(test_id='T',run_id='R',dimension=Dimension.CONFLICT_RESOLUTION,prompt='What programming language is generally preferred?',expected_behavior='State the general preference and explain the project-specific requirement overrides it.',supporting_memory_ids=['P','J'],generator_version='fixture')
    rejected=RuleBasedTestQualityValidator().validate(test,memories)
    assert rejected.quality_status==TestQualityStatus.REJECTED
    assert 'explicitly asks' in rejected.reason
    generic_tasks=test.model_copy(update={'prompt':'What programming language does the user prefer for general tasks?'})
    assert RuleBasedTestQualityValidator().validate(generic_tasks,memories).quality_status==TestQualityStatus.REJECTED
    implicit_general=test.model_copy(update={'prompt':'What programming language do you prefer?'})
    assert RuleBasedTestQualityValidator().validate(implicit_general,memories).quality_status==TestQualityStatus.REJECTED
    valid=test.model_copy(update={'prompt':'How does the project-specific language requirement relate to the general preference when choosing for this task?'})
    assert RuleBasedTestQualityValidator().validate(valid,memories).quality_status==TestQualityStatus.ACCEPTED
    general_only=test.model_copy(update={'dimension':Dimension.ACCURACY,'expected_behavior':'State the recorded general preference.'})
    assert RuleBasedTestQualityValidator().validate(general_only,memories).quality_status==TestQualityStatus.ACCEPTED


@pytest.mark.parametrize('field',['prompt','expected_behavior'])
def test_hidden_audit_memory_ids_cannot_be_target_answer_obligations(field):
    memory=_confirmed_memory()
    test=TestCase(test_id='T',run_id='R',dimension=Dimension.ACCURACY,
        prompt='Where is the user based?',expected_behavior='The user is based in Sydney.',
        supporting_memory_ids=[memory.memory_id],generator_version='fixture')
    hidden=test.model_copy(update={field:getattr(test,field)+' Cite memory M001.'})
    rejected=RuleBasedTestQualityValidator().validate(hidden,[memory])
    assert rejected.quality_status==TestQualityStatus.REJECTED
    assert 'hidden audit memory identifiers' in rejected.reason
    assert RuleBasedTestQualityValidator().validate(test,[memory]).quality_status==TestQualityStatus.ACCEPTED
    actual=memory.model_copy(update={'canonical_value':'The user asset code is M001.'})
    legitimate=test.model_copy(update={'prompt':'What is the user asset code?',
        'expected_behavior':'The user asset code is M001.'})
    assert RuleBasedTestQualityValidator().validate(legitimate,[actual]).quality_status==TestQualityStatus.ACCEPTED
