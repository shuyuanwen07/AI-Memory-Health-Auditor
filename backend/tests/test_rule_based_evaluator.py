from datetime import datetime, timezone

import pytest

from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.schemas import Dimension, Memory, MemoryRelationship, MemoryStatus, RelationshipType, TargetResponse, TestCase as DomainTestCase


def _test_case() -> DomainTestCase:
    return DomainTestCase(
        test_id="T007", run_id="RUN1", dimension=Dimension.FRESHNESS,
        prompt="Which database should be used?", expected_behavior="Use the later record: PostgreSQL.",
        supporting_memory_ids=["M001", "M002"], generator_version="rule-based-v2",
    )


@pytest.mark.parametrize('reference',[
    'The Nacre project access code is NC-7492-V.',
    'Return the recorded code: NC-7492-V.',
    'The code=NC-7492-V, for the Nacre project.',
])
@pytest.mark.parametrize('answer,passed',[
    ('NC-7492-V',True),('The access code is "NC-7492-V".',True),
    ('7492',False),('WRONG-7492-V',False),('NC-0000-V',False),('NC-7492-X',False),
    ('NC-7492-V2',False),('XNC-7492-V',False),('NC_7492_V',False),('nc-7492-v',False),
    ('Not NC-7492-V.',False),
])
def test_compound_access_code_requires_the_complete_literal(reference,answer,passed):
    case = _test_case().model_copy(update={'dimension':Dimension.ACCURACY,
        'prompt':'What is the recorded access code for the Nacre project?',
        'expected_behavior':reference,'supporting_memory_ids':['M001']})
    memory = Memory(memory_id='M001',conversation_id='C',status='confirmed',canonical_value='The Nacre project access code is NC-7492-V.')
    response = TargetResponse(response_id='R',test_id=case.test_id,run_id=case.run_id,
        response_text=answer,model='fixture',temperature=0,created_at=datetime.now(timezone.utc))
    result = RuleBasedBehaviourEvaluator().evaluate(case,response,[memory])
    assert result.passed is passed
    if not passed:
        assert 'NC-7492-V' in result.reason


@pytest.mark.parametrize('reference',[
    'The previous code was OLD-7492-V and the current code is NC-7492-V.',
    'The old code was OLD-7492-V. Return the current code: NC-7492-V.',
])
@pytest.mark.parametrize('answer',['7492','OLD-7492-V','NC-7492-V'])
def test_multiple_code_values_are_not_reduced_to_an_arbitrary_old_or_new_fragment(reference,answer):
    case=_test_case().model_copy(update={'dimension':Dimension.ACCURACY,
        'prompt':'Which recorded code applies to this project?',
        'expected_behavior':reference})
    response=TargetResponse(response_id='R',test_id=case.test_id,run_id=case.run_id,response_text=answer,
        model='fixture',temperature=0,created_at=datetime.now(timezone.utc))
    memories=[Memory(memory_id='M001',conversation_id='C',status='confirmed',canonical_value='The old code was OLD-7492-V.'),
        Memory(memory_id='M002',conversation_id='C',status='confirmed',canonical_value='The current code is NC-7492-V.')]
    result=RuleBasedBehaviourEvaluator().evaluate(case,response,memories)
    assert result.passed is None
    assert 'multiple identifier values' in result.reason


@pytest.mark.parametrize('answer,classified', [
    ('MySQL',True), ('The project currently uses MySQL.',True), ('The current database is MySQL.',True),
    ('Use MySQL.',True), ('MySQL is used now.',True),
    ('The current database is not specified. It previously used MySQL.',False),
    ('It previously used MySQL and now uses another database system.',False),
    ('The historical record says use MySQL; the current system is unknown.',False),
    ('MySQL appears in the records.',False),
])
def test_stale_classification_requires_selecting_old_value_not_just_reporting_history(answer,classified):
    case = _test_case().model_copy(update={'prompt':'Which database does the Lyra project currently use?',
                                         'expected_behavior':'The current database is PostgreSQL.'})
    memories = [Memory(memory_id='M001',conversation_id='C',canonical_value='The Lyra project previously used MySQL.',status='confirmed'),
        Memory(memory_id='M002',conversation_id='C',canonical_value='The Lyra project now uses PostgreSQL.',status='confirmed',
               relationships=[MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id='M001')])]
    response = TargetResponse(response_id='R',test_id=case.test_id,run_id=case.run_id,response_text=answer,
                              model='fixture',temperature=0,created_at=datetime.now(timezone.utc))
    result = RuleBasedBehaviourEvaluator().evaluate(case,response,memories)
    assert result.passed is False
    assert (result.failure_classification.status == 'classified') is classified
    assert result.failure_type == (Dimension.FRESHNESS if classified else None)
    if classified:
        # Two independent facts do not establish a replacement chronology.
        memories[1].relationships = []
        unrelated = RuleBasedBehaviourEvaluator().evaluate(case,response,memories)
        assert unrelated.failure_classification.status == 'unclassified'
        assert unrelated.failure_type is None


@pytest.mark.parametrize('dimension,reference', [
    (Dimension.FRESHNESS, 'The Lyra project currently uses PostgreSQL, which replaced MySQL.'),
    (Dimension.CONFLICT_RESOLUTION, "The Lyra project's use of PostgreSQL is an update to its previous use of MySQL."),
])
@pytest.mark.parametrize('answer,passed', [
    ('The Lyra project currently uses a database system that is not specified in the retrieved records. It previously used MySQL.',False),
    ("The Lyra project previously used MySQL and now uses another database system. The change is resolved by migrating the project's database configuration from MySQL to the new system.",False),
    ('The Lyra project now uses PostgreSQL, replacing MySQL.',True),
])
def test_replacement_reference_cannot_pass_by_matching_only_the_old_database(dimension,reference,answer,passed):
    case = _test_case().model_copy(update={'dimension':dimension,'expected_behavior':reference,
        'prompt':'What database is currently used for the Lyra project and how did it replace the earlier value?'})
    memories = [Memory(memory_id='M001',conversation_id='C',canonical_value='The Lyra project previously used MySQL.',status='confirmed'),
        Memory(memory_id='M002',conversation_id='C',canonical_value='The Lyra project now uses PostgreSQL.',status='confirmed',
               relationships=[MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id='M001')])]
    response = TargetResponse(response_id='R',test_id=case.test_id,run_id=case.run_id,response_text=answer,
                              model='fixture',temperature=0,created_at=datetime.now(timezone.utc))
    verdict = RuleBasedBehaviourEvaluator().evaluate(case,response,memories)
    assert verdict.passed is passed
    if not passed:
        assert 'postgresql' in verdict.reason


@pytest.mark.parametrize('answer,passed', [
    ('2031-02-03',True), ('The launch is scheduled for 2031-02-03.',True),
    ('2031',False), ('2031-02-04',False), ('2031-03-02',False),
    ('Not 2031-02-03.',False),
])
def test_iso_event_date_requires_the_complete_date_not_just_its_year(answer,passed):
    case = _test_case().model_copy(update={'dimension':Dimension.ACCURACY,'prompt':'When is the Lyra launch scheduled?',
        'expected_behavior':'The Lyra launch is scheduled for 2031-02-03.','supporting_memory_ids':['M001']})
    memory = Memory(memory_id='M001',conversation_id='C',canonical_value='The Lyra launch is scheduled for 2031-02-03.',status='confirmed')
    response = TargetResponse(response_id='R',test_id=case.test_id,run_id=case.run_id,response_text=answer,
                              model='fixture',temperature=0,created_at=datetime.now(timezone.utc))
    assert RuleBasedBehaviourEvaluator().evaluate(case,response,[memory]).passed is passed


@pytest.mark.parametrize('answer',['Project requirements override a general preference for another language.','I do not know the recorded requirement.'])
def test_abstract_reference_cannot_be_scored_by_matching_generic_language_tail(answer):
    case=_test_case().model_copy(update={'dimension':Dimension.CONFLICT_RESOLUTION,
        'prompt':'For the Nacre project, how does the requirement relate to the general language preference?',
        'expected_behavior':'The system should explain that the Nacre project requires a specific programming language, overriding the general preference.'})
    memories=[Memory(memory_id='M001',conversation_id='C1',status='confirmed',canonical_value='The user generally prefers Python.'),
              Memory(memory_id='M002',conversation_id='C1',status='confirmed',canonical_value='The Nacre project requires Java.',
                     relationships=[MemoryRelationship(type=RelationshipType.CONTEXTUAL_OVERRIDE,target_memory_id='M001')])]
    response=TargetResponse(response_id='R',test_id=case.test_id,run_id=case.run_id,response_text=answer,
                            model='fixture',temperature=0,created_at=datetime.now(timezone.utc))
    verdict=RuleBasedBehaviourEvaluator().evaluate(case,response,memories)
    assert verdict.passed is None
    assert verdict.failure_type is None
    assert 'generic description word' in verdict.reason


def test_explicit_generic_looking_literal_remains_a_testable_answer_value():
    case=_test_case().model_copy(update={'dimension':Dimension.ACCURACY,'prompt':'What is the recorded code word?',
                                       'expected_behavior':'State the code word: language.'})
    response=TargetResponse(response_id='R',test_id=case.test_id,run_id=case.run_id,response_text='language',
                            model='fixture',temperature=0,created_at=datetime.now(timezone.utc))
    memory=Memory(memory_id='M001',conversation_id='C1',status='confirmed',canonical_value='The code word is language.')
    assert RuleBasedBehaviourEvaluator().evaluate(case,response,[memory]).passed is True


@pytest.mark.parametrize('modifier',['replacing the previous MySQL system','superseding the previous MySQL system','overriding the previous MySQL system'])
@pytest.mark.parametrize('answer,passed',[('The Nacre project now uses PostgreSQL.',True),('The Nacre project uses MySQL.',False)])
def test_reference_explanation_does_not_turn_generic_system_word_into_the_required_database(modifier,answer,passed):
    case=_test_case().model_copy(update={'prompt':'What database system does the Nacre project use?',
        'expected_behavior':'The AI should state that the Nacre project now uses PostgreSQL, '+modifier+'.'})
    memories=[Memory(memory_id='M001',conversation_id='C1',status='confirmed',canonical_value='The Nacre project used MySQL.'),
              Memory(memory_id='M002',conversation_id='C1',status='confirmed',canonical_value='The Nacre project now uses PostgreSQL.',
                     relationships=[MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id='M001')])]
    response=TargetResponse(response_id='R',test_id=case.test_id,run_id=case.run_id,response_text=answer,
                            model='fixture',temperature=0,created_at=datetime.now(timezone.utc))
    evaluated=RuleBasedBehaviourEvaluator().evaluate(case,response,memories)
    assert evaluated.passed is passed
    assert 'did not demonstrate: system' not in evaluated.reason


@pytest.mark.parametrize('answer,passed', [
    ('PostgreSQL. The newer memory policy explicitly overrides the older policy.', None),
    ('PostgreSQL replaces the historical MySQL database as explicitly stated.', True),
    ('PostgreSQL. No new memory policy is recorded; the source explicitly updates the database.', True),
    ('PostgreSQL. A new memory policy might exist, but its implementation is unknown.', True),
])
def test_unrecorded_policy_claim_requires_review_without_rejecting_grounded_recency(answer, passed):
    memories = [Memory(memory_id='M001', conversation_id='C1', status=MemoryStatus.CONFIRMED,
                       canonical_value='The backend previously used MySQL.'),
                Memory(memory_id='M002', conversation_id='C1', status=MemoryStatus.CONFIRMED,
                       canonical_value='The backend now uses PostgreSQL.')]
    response = TargetResponse(response_id='R', test_id='T007', run_id='RUN1', response_text=answer,
                              model='fixture', temperature=0, created_at=datetime.now(timezone.utc))
    assert RuleBasedBehaviourEvaluator().evaluate(_test_case(), response, memories).passed is passed


@pytest.mark.parametrize('answer,passed', [
    ('The Marigold backend now uses PostgreSQL, overriding the older PostgreSQL implementation.', False),
    ('The Marigold backend now uses PostgreSQL, replacing the older MySQL implementation.', True),
    ('Marigold now uses PostgreSQL. The Birch project used an older SQLite implementation.', True),
])
def test_old_database_noun_phrase_must_match_explicit_source_history(answer, passed):
    case = _test_case().model_copy(update={'prompt': 'Which database for the Marigold project applies now?'})
    memories = [Memory(memory_id='M001', conversation_id='C1', status=MemoryStatus.CONFIRMED,
                       canonical_value='Our Marigold backend used MySQL before.'),
                Memory(memory_id='M002', conversation_id='C1', status=MemoryStatus.CONFIRMED,
                       canonical_value='Our Marigold backend now uses PostgreSQL.')]
    response = TargetResponse(response_id='R', test_id=case.test_id, run_id=case.run_id, response_text=answer,
                              model='fixture', temperature=0, created_at=datetime.now(timezone.utc))
    assert RuleBasedBehaviourEvaluator().evaluate(case, response, memories).passed is passed


@pytest.mark.parametrize('answer,passed', [
    ('There is an unresolved conflict. One policy states that secrets must be stored in environment variables. Another policy states that secrets must be stored in a configuration file. Clarification is needed to determine which policy to follow.', True),
    ('The records conflict. Secrets must be stored in environment variables. Please provide clarification.', False),
    ('One policy states that secrets must be stored in environment variables. The conflict requires clarification. I will follow the first policy.', False),
])
def test_conflicting_policy_source_attribution_is_not_a_recommendation(answer, passed):
    test = _test_case().model_copy(update={'dimension': Dimension.CONFLICT_RESOLUTION,
        'expected_behavior': 'Identify both conflicting recorded constraints, acknowledge the conflict and request clarification before relying on either record.'})
    memories = [Memory(memory_id='M001', conversation_id='C1', status=MemoryStatus.CONFIRMED, canonical_value='The deployment policy requires secrets in environment variables.'),
        Memory(memory_id='M002', conversation_id='C1', status=MemoryStatus.CONFIRMED, canonical_value='A conflicting deployment policy requires secrets in a configuration file; neither policy supersedes the other.')]
    response = TargetResponse(response_id='R', test_id=test.test_id, run_id=test.run_id,
        response_text=answer, model='test', temperature=0, created_at=datetime.now(timezone.utc))
    assert RuleBasedBehaviourEvaluator().evaluate(test, response, memories).passed is passed


@pytest.mark.parametrize('answer,passed', [
    ('Zoom and Teams are conflicting requirements. Please clarify which applies. Meanwhile use Zoom.', False),
    ('Zoom and Teams conflict; clarification is needed. The meeting should be held on Teams.', False),
    ('Zoom and Teams conflict; clarification is needed. Zoom must be used.', False),
    ('The records conflict. Clarification is needed.', False),
    ('One record requires Zoom only; another requires Teams only. The requirements conflict and should be clarified before selecting a platform.', True),
    ('The source says the meeting must use Zoom; the other source requires Teams. The conflict requires clarification.', True),
    ('Zoom and Teams conflict. Do not use Zoom until clarification is received.', True),
    ('Zoom and Teams conflict. If the user confirms the Zoom requirement, use Zoom. Otherwise request clarification.', True),
    ('There are two recorded constraints about the Alder meeting platform:\n1. Alder review must use Zoom only\n2. Alder review must use Teams only\nThese requirements conflict and should be clarified before providing an answer.', True),
    ('Zoom and Teams conflict. If Zoom is convenient, use Zoom. Clarification is needed.', False),
    ('The source requires Zoom and Teams; the conflict needs clarification. I am not sure, but use Zoom.', False),
    ('The recorded constraints require Zoom only and Teams only. These requirements conflict. The conflict between the requirement to use Zoom only and Teams only must be clarified before a final decision can be made.', True),
    ('The conflict between the requirement to use Zoom and Teams needs clarification. Meanwhile use Zoom.', False),
])
def test_unresolved_meeting_conflicts_cannot_be_repaired_by_clarification_keywords(answer, passed):
    case = _test_case().model_copy(update={
        'dimension': Dimension.CONFLICT_RESOLUTION,
        'prompt': 'Which meeting platform should the user use for the Alder review?',
        'expected_behavior': 'Identify both conflicting recorded constraints, acknowledge the conflict and request clarification before relying on either record.',
    })
    memories = [
        Memory(memory_id='M001', conversation_id='C1', status=MemoryStatus.CONFIRMED,
               canonical_value='The Alder review meeting must use Zoom only.'),
        Memory(memory_id='M002', conversation_id='C1', status=MemoryStatus.CONFIRMED,
               canonical_value='The Alder review meeting must use Teams only; neither requirement supersedes the other.'),
    ]
    response = TargetResponse(response_id='R', test_id=case.test_id, run_id=case.run_id,
                              response_text=answer, model='fixture', temperature=0,
                              created_at=datetime.now(timezone.utc))
    assert RuleBasedBehaviourEvaluator().evaluate(case, response, memories).passed is passed


@pytest.mark.parametrize("answer,passed", [
    ("The user should now use MongoDB for the Atlas project. The Atlas backend is now using PostgreSQL.", False),
    ("MongoDB. Atlas now uses PostgreSQL.", False),
    ("Use MySQL. PostgreSQL is also mentioned in the memories.", False),
    ("The Atlas backend uses MongoDB. PostgreSQL is the right value.", False),
    ("The Atlas backend now uses PostgreSQL. Birch now uses MongoDB.", True),
    ("PostgreSQL replaces the earlier MySQL database.", True),
    ("Do not use MongoDB. Use PostgreSQL for Atlas.", True),
])
def test_database_answer_assertion_cannot_be_repaired_by_keyword_mention(answer, passed):
    test = _test_case().model_copy(update={"prompt": "Which database technology for the Atlas project should the user use now?"})
    response = TargetResponse(response_id="R", test_id=test.test_id, run_id=test.run_id,
                              response_text=answer, model="test", temperature=0, created_at=datetime.now(timezone.utc))
    result = RuleBasedBehaviourEvaluator().evaluate(test, response, [])
    assert result.passed is passed


@pytest.mark.parametrize("answer,passed", [
    ("The later memory uses PostgreSQL, while the earlier memory incorrectly stated it uses MongoDB.", False),
    ("The later memory uses PostgreSQL, replacing the earlier memory using MySQL.", True),
    ("Atlas now uses PostgreSQL. The Birch project currently uses MongoDB.", True),
    ("The earlier memory did not use MongoDB. It used MySQL; PostgreSQL is current.", True),
])
def test_explanation_must_not_fabricate_the_earlier_source_database(answer, passed):
    test = _test_case().model_copy(update={"dimension": Dimension.CONFLICT_RESOLUTION})
    memories = [Memory(memory_id="M001", conversation_id="C1", status=MemoryStatus.CONFIRMED, canonical_value="The Atlas backend previously used MySQL."),
                Memory(memory_id="M002", conversation_id="C1", status=MemoryStatus.CONFIRMED, canonical_value="The Atlas backend now uses PostgreSQL.")]
    response = TargetResponse(response_id="R", test_id=test.test_id, run_id=test.run_id, response_text=answer, model="test", temperature=0, created_at=datetime.now(timezone.utc))
    assert RuleBasedBehaviourEvaluator().evaluate(test, response, memories).passed is passed


def test_evaluator_returns_traceable_pass_reason():
    result = RuleBasedBehaviourEvaluator().evaluate(
        _test_case(),
        TargetResponse(response_id="R007", test_id="T007", run_id="RUN1", response_text="Use PostgreSQL.", model="test", temperature=0, created_at=datetime.now(timezone.utc)),
        [Memory(memory_id="M001", conversation_id="C1", canonical_value="Old database: MySQL", status=MemoryStatus.CONFIRMED), Memory(memory_id="M002", conversation_id="C1", canonical_value="New database: PostgreSQL", status=MemoryStatus.CONFIRMED)],
    )
    assert result.passed
    assert result.failure_type is None
    assert result.evidence_memory_ids == ["M001", "M002"]
    assert "Passed freshness" in result.reason
    assert result.evaluator == RuleBasedBehaviourEvaluator.VERSION


def test_evaluator_explains_missing_ground_truth_terms():
    result = RuleBasedBehaviourEvaluator().evaluate(
        _test_case(),
        TargetResponse(response_id="R007", test_id="T007", run_id="RUN1", response_text="Use MySQL.", model="test", temperature=0, created_at=datetime.now(timezone.utc)),
        [Memory(memory_id="M001", conversation_id="C1", canonical_value="Old database: MySQL", status=MemoryStatus.CONFIRMED), Memory(memory_id="M002", conversation_id="C1", canonical_value="Current database: PostgreSQL", status=MemoryStatus.CONFIRMED,
            relationships=[MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id="M001")])],
    )
    assert not result.passed
    assert result.failure_type == Dimension.FRESHNESS
    assert "postgresql" in result.reason.lower()
    assert result.evidence_memory_ids == ["M001", "M002"]


def test_evaluator_accepts_a_concise_value_without_requiring_explanatory_words():
    test = DomainTestCase(
        test_id="T008", run_id="RUN1", dimension=Dimension.ACCURACY,
        prompt="What language does the user prefer?", expected_behavior="State the recorded fact: I generally prefer Python.",
        supporting_memory_ids=["M003"], generator_version="rule-based-v3",
    )
    result = RuleBasedBehaviourEvaluator().evaluate(
        test,
        TargetResponse(response_id="R008", test_id="T008", run_id="RUN1", response_text="Python", model="test", temperature=0, created_at=datetime.now(timezone.utc)),
        [Memory(memory_id="M003", conversation_id="C1", canonical_value="I generally prefer Python", status=MemoryStatus.CONFIRMED)],
    )
    assert result.passed


def test_evaluator_extracts_the_required_value_from_contextual_requirement():
    test = DomainTestCase(
        test_id="T009", run_id="RUN1", dimension=Dimension.APPROPRIATE_USE,
        prompt="Which language applies to this assignment?", expected_behavior="Follow the contextual requirement: For this assignment, Java is required.",
        supporting_memory_ids=["M004"], generator_version="rule-based-v3",
    )
    result = RuleBasedBehaviourEvaluator().evaluate(
        test,
        TargetResponse(response_id="R009", test_id="T009", run_id="RUN1", response_text="Java", model="test", temperature=0, created_at=datetime.now(timezone.utc)),
        [Memory(memory_id="M004", conversation_id="C1", canonical_value="For this assignment, Java is required", status=MemoryStatus.CONFIRMED)],
    )
    assert result.passed


def test_evaluator_rejects_a_response_that_negates_the_expected_value():
    result = RuleBasedBehaviourEvaluator().evaluate(
        _test_case(),
        TargetResponse(response_id="R010", test_id="T007", run_id="RUN1", response_text="Do not use PostgreSQL; use MySQL instead.", model="test", temperature=0, created_at=datetime.now(timezone.utc)),
        [Memory(memory_id="M001", conversation_id="C1", canonical_value="Old database: MySQL", status=MemoryStatus.CONFIRMED), Memory(memory_id="M002", conversation_id="C1", canonical_value="New database: PostgreSQL", status=MemoryStatus.CONFIRMED)],
    )
    assert not result.passed


def test_evaluator_uses_the_positive_value_in_a_rather_than_constraint():
    test = DomainTestCase(
        test_id="T011", run_id="RUN1", dimension=Dimension.ACCURACY,
        prompt="Which database should be used?", expected_behavior="State the recorded fact: The assignment must use PostgreSQL rather than SQLite.",
        supporting_memory_ids=["M005"], generator_version="rule-based-v4",
    )
    result = RuleBasedBehaviourEvaluator().evaluate(
        test,
        TargetResponse(response_id="R011", test_id="T011", run_id="RUN1", response_text="PostgreSQL", model="test", temperature=0, created_at=datetime.now(timezone.utc)),
        [Memory(memory_id="M005", conversation_id="C1", canonical_value="The assignment must use PostgreSQL rather than SQLite", status=MemoryStatus.CONFIRMED)],
    )
    assert result.passed


def test_generic_last_word_is_insufficient_for_a_multiword_value():
    test = _test_case().model_copy(update={'expected_behavior': 'Use the later record: The Beacon logs now remain in object storage.'})
    response = TargetResponse(response_id='R1', test_id=test.test_id, run_id=test.run_id,
        response_text='Use the newer memory technology for storage.', model='test', temperature=0,
        created_at=datetime.now(timezone.utc))
    assert not RuleBasedBehaviourEvaluator().evaluate(test, response, []).passed


def test_unresolved_conflict_requires_clarification_not_generic_record_word():
    test = _test_case().model_copy(update={'expected_behavior': 'Acknowledge the conflict and request clarification before relying on either record.'})
    response = TargetResponse(response_id='R1', test_id=test.test_id, run_id=test.run_id,
        response_text='Use the latest record.', model='test', temperature=0,
        created_at=datetime.now(timezone.utc))
    assert not RuleBasedBehaviourEvaluator().evaluate(test, response, []).passed


@pytest.mark.parametrize('text, passed', [
    ('Python\n\nThe assignment requires the use of Java.', False),
    ('Java is required, but Python must be used.', False),
    ('Java is required; the user generally prefers Python.', True),
    ('Java, not Python.', True),
])
def test_conflicting_requirement_answers(text, passed):
    test = _test_case().model_copy(update={'expected_behavior': 'Follow the contextual requirement: Java is required.'})
    response = TargetResponse(response_id='R1', test_id=test.test_id, run_id=test.run_id,
        response_text=text, model='test', temperature=0, created_at=datetime.now(timezone.utc))
    assert RuleBasedBehaviourEvaluator().evaluate(test, response, []).passed is passed


def test_correct_without_memory_remains_correct_but_is_not_grounded():
    from app.target_ai.rule_based import memory_input_evidence, private_context_instruction
    from app.schemas import TargetConfiguration
    test = _test_case()
    receipt = memory_input_evidence(test, TargetConfiguration.STRONG, private_context_instruction(test, TargetConfiguration.STRONG))
    response = TargetResponse(response_id='R1', test_id=test.test_id, run_id=test.run_id,
        response_text='PostgreSQL', model='test', temperature=0, created_at=datetime.now(timezone.utc),
        execution_metadata={'memory_input': receipt})
    result = RuleBasedBehaviourEvaluator().evaluate(test, response, [])
    assert result.passed
    assert 'zero supplied memory' in result.reason
    assert 'grounding is unsupported' in result.reason


def test_clarification_keyword_does_not_excuse_selecting_an_unresolved_policy_by_recency():
    test = _test_case().model_copy(update={'expected_behavior': 'Acknowledge the conflict and request clarification before choosing either policy.'})
    response = TargetResponse(response_id='R1', test_id=test.test_id, run_id=test.run_id,
        response_text='The conflict requires clarification. Follow the policy that is more recently stated.',
        model='test', temperature=0, created_at=datetime.now(timezone.utc))
    assert not RuleBasedBehaviourEvaluator().evaluate(test, response, []).passed


@pytest.mark.parametrize('text', [
    'The policies are incompatible; clarify which policy to follow.',
    'There is an unresolved conflict. Which policy should the assistant follow?',
    'The records conflict. Do not choose the most recent policy; request clarification.',
    'The policies conflict; the assistant should ask which policy to follow.',
])
def test_conflict_clarification_can_be_a_direct_question_or_paraphrase(text):
    test = _test_case().model_copy(update={'expected_behavior': 'Acknowledge the conflict and request clarification before choosing either policy.'})
    response = TargetResponse(response_id='R1', test_id=test.test_id, run_id=test.run_id,
        response_text=text, model='test', temperature=0, created_at=datetime.now(timezone.utc))
    assert RuleBasedBehaviourEvaluator().evaluate(test, response, []).passed


def test_correct_with_only_old_memory_is_flagged_separately_from_correctness():
    from app.services.memory_grounding import annotate_memory_grounding
    from app.target_ai.rule_based import memory_input_evidence, private_context_instruction
    from app.schemas import TargetConfiguration
    test = _test_case().model_copy(update={'target_memory_context': ['Previously used MySQL']})
    receipt = memory_input_evidence(test, TargetConfiguration.STRONG, private_context_instruction(test, TargetConfiguration.STRONG))
    response = TargetResponse(response_id='R1', test_id=test.test_id, run_id=test.run_id,
        response_text='PostgreSQL', model='test', temperature=0, created_at=datetime.now(timezone.utc),
        execution_metadata={'memory_input': receipt})
    evaluation = RuleBasedBehaviourEvaluator().evaluate(test, response, [])
    result = annotate_memory_grounding(evaluation, test, response, test.target_memory_context)
    assert result.passed
    assert 'Expected concrete answer absent from supplied memory' in result.reason
    assert annotate_memory_grounding(evaluation, test, response, ['Now uses PostgreSQL']).reason == evaluation.reason


@pytest.mark.parametrize("answer, passed", [
    ("The requirements conflict: Rust is required and Rust must not be used. Please clarify whether the prohibition or the assignment requirement applies.", True),
    ("The applicable programming-language choice is **Rust**. The requirements conflict: Rust is required and must not be used. Clarification is needed.", False),
])
def test_unresolved_language_requirements_need_a_question_without_a_concrete_choice(answer, passed):
    test = _test_case().model_copy(update={"expected_behavior": "Identify both conflicting recorded constraints, acknowledge the conflict and request clarification before relying on either record."})
    memories = [Memory(memory_id="M001", conversation_id="C1", status=MemoryStatus.CONFIRMED, canonical_value="The assignment requires Rust."), Memory(memory_id="M002", conversation_id="C1", status=MemoryStatus.CONFIRMED, canonical_value="The assignment must not use Rust because the requirements conflict.")]
    response = TargetResponse(response_id="R", test_id=test.test_id, run_id=test.run_id, model="test", temperature=0, response_text=answer, created_at=datetime.now(timezone.utc))
    assert RuleBasedBehaviourEvaluator().evaluate(test, response, memories).passed is passed


@pytest.mark.parametrize("source,answer,verdict", [
    ("This assignment requires Swift.", "The requirement is Swift 5.3 and later, replacing a preference for Swift 5.2.", None),
    ("This assignment requires Swift 5.3.", "Swift 5.3 is required for this assignment.", True),
    ("This assignment requires Swift.", "Swift is required. It overrides the general preference.", True),
    ("This assignment requires Swift.", "Swift version 5.3 is required.", None),
    ("This assignment requires Swift.", "Swift v5.3 is required.", None),
    ("This assignment requires Swift 5.3.", "Swift 5.3 is required; the earlier policy specified Swift 5.2.", None),
    ("This assignment requires Swift.", "Python 3.12 is required.", False),
])
def test_unsupported_version_detail_requires_independent_review(source, answer, verdict):
    case = _test_case().model_copy(update={"dimension": Dimension.APPROPRIATE_USE,
        "expected_behavior": "Follow the contextual requirement: This assignment requires Swift."})
    memories = [Memory(memory_id="M001", conversation_id="C1", canonical_value=source, status=MemoryStatus.CONFIRMED)]
    response = TargetResponse(response_id="R", test_id=case.test_id, run_id=case.run_id,
        response_text=answer, model="test", temperature=0, created_at=datetime.now(timezone.utc))
    result = RuleBasedBehaviourEvaluator().evaluate(case, response, memories)
    assert result.passed is verdict
    if verdict is None:
        assert result.failure_type is None
        assert "Excluded from scoring" in result.reason
        assert "version details absent" in result.reason


@pytest.mark.parametrize('answer,passed', [
    ('PostgreSQL. The project now uses PostgreSQL instead of MariaDB because PostgreSQL is required.', True),
    ('Use PostgreSQL rather than MariaDB because PostgreSQL is current.', True),
    ('The project does not use MariaDB but PostgreSQL is current.', True),
    ('Do not use PostgreSQL. Use MariaDB.', False),
    ('Use MariaDB instead of PostgreSQL.', False),
    ('PostgreSQL is not the correct answer.', False),
    ('Do not use the current PostgreSQL database.', False),
])
def test_negation_does_not_cross_explanatory_or_contrast_clause(answer, passed):
    response = TargetResponse(response_id='R',test_id='T007',run_id='RUN1',response_text=answer,
                              model='test',temperature=0,created_at=datetime.now(timezone.utc))
    assert RuleBasedBehaviourEvaluator().evaluate(_test_case(),response,[]).passed is passed


@pytest.mark.parametrize('source,answer,verdict', [
    ('The backend now uses PostgreSQL rather than SQLite.',
     'PostgreSQL is current because it provides a more robust and scalable solution.', None),
    ('The backend now uses PostgreSQL rather than SQLite.',
     'PostgreSQL. The newer memory overrides the older one because the current requirement prioritizes a more reliable and modern database system.', None),
    ('The backend now uses PostgreSQL rather than SQLite.',
     'PostgreSQL, because the later update replaces the old SQLite record.', True),
    ('The backend now uses PostgreSQL because it is more scalable.',
     'PostgreSQL is used because it is more scalable.', True),
    ('The backend now uses PostgreSQL rather than SQLite; PostgreSQL is scalable.',
     'PostgreSQL is current because scalability caused the migration.', None),
    ('The backend now uses PostgreSQL rather than SQLite.',
     'PostgreSQL is current. A more robust system might be a reason, but the migration reason is not stated in the source.', True),
    ('The backend now uses PostgreSQL rather than SQLite.',
     'SQLite is current because it is cheaper; PostgreSQL appears in the old record.', False),
])
def test_unsupported_quality_migration_reason_is_not_keyword_pass(source, answer, verdict):
    case = _test_case().model_copy(update={'supporting_memory_ids': ['M001']})
    memories = [Memory(memory_id='M001', conversation_id='C1', canonical_value=source,
                       status=MemoryStatus.CONFIRMED)]
    response = TargetResponse(response_id='R', test_id=case.test_id, run_id=case.run_id,
                              model='test', temperature=0, response_text=answer,
                              created_at=datetime.now(timezone.utc))
    result = RuleBasedBehaviourEvaluator().evaluate(case, response, memories)
    assert result.passed is verdict, result.reason
    if verdict is None:
        assert result.failure_type is None
        assert 'not supported by the linked source' in result.reason

@pytest.mark.parametrize('history,passed', [('Lotus', False), ('PostgreSQL', True)])
def test_project_name_is_not_a_supported_earlier_database(history, passed):
    test = _test_case().model_copy(update={'prompt':"Which database for the Lotus project should be used now?", 'expected_behavior':'Use the later record: Our Lotus backend now uses MySQL.'})
    memories = [Memory(memory_id='M001',conversation_id='C1',status=MemoryStatus.CONFIRMED,canonical_value='Our Lotus backend used PostgreSQL before'),
                Memory(memory_id='M002',conversation_id='C1',status=MemoryStatus.CONFIRMED,canonical_value='Our Lotus backend now uses MySQL')]
    response = TargetResponse(response_id='R001',test_id=test.test_id,run_id=test.run_id,model='test',temperature=0,created_at=datetime.now(timezone.utc),response_text=f'The Lotus backend now uses MySQL. The later update replaces the earlier statement that stated the backend used {history}, which was outdated information.')
    assert RuleBasedBehaviourEvaluator().evaluate(test,response,memories).passed is passed


@pytest.mark.parametrize('earlier,verdict', [('SQLite', True), ('MongoDB', False)])
def test_history_values_are_bound_to_past_source_not_current_value(earlier, verdict):
    case = _test_case().model_copy(update={'expected_behavior':'Use the later record: Our Camellia backend now uses MongoDB.'})
    memories = [Memory(memory_id='M001',conversation_id='C1',status=MemoryStatus.CONFIRMED,canonical_value='Our Camellia backend used SQLite before'),
                Memory(memory_id='M002',conversation_id='C1',status=MemoryStatus.CONFIRMED,canonical_value='Our Camellia backend now uses MongoDB')]
    response = TargetResponse(response_id='R',test_id=case.test_id,run_id=case.run_id,model='test',temperature=0,created_at=datetime.now(timezone.utc),response_text=f'The Camellia backend now uses MongoDB. The later update replaces the earlier statement that it used {earlier} with the more recent information.')
    assert RuleBasedBehaviourEvaluator().evaluate(case,response,memories).passed is verdict


@pytest.mark.parametrize('source,answer,verdict', [
    ('The backend now uses MongoDB.', 'MongoDB. The newer memory overrides the older one because the current assignment requires Swift.', None),
    ('The backend now uses MongoDB because the assignment requires Swift.', 'MongoDB is current because the assignment requires Swift.', True),
    ('The backend now uses MongoDB; the assignment requires Swift.', 'MongoDB is current because the assignment requires Swift.', None),
    ('The backend now uses MongoDB.', 'MongoDB. Swift might explain the change, but the reason is not stated.', True),
])
def test_database_language_causal_claim_requires_source_link(source, answer, verdict):
    case = _test_case().model_copy(update={'expected_behavior':'Use the later record: The backend now uses MongoDB.', 'supporting_memory_ids':['M001']})
    memories=[Memory(memory_id='M001',conversation_id='C1',status=MemoryStatus.CONFIRMED,canonical_value=source)]
    response=TargetResponse(response_id='R',test_id=case.test_id,run_id=case.run_id,model='test',temperature=0,created_at=datetime.now(timezone.utc),response_text=answer)
    assert RuleBasedBehaviourEvaluator().evaluate(case,response,memories).passed is verdict


@pytest.mark.parametrize("answer,passed", [
    ("The Cedar project currently uses MariaDB.", True),
    ("The Cedar project currently uses SQLite. It is the most recent record.", False),
    ("A recent record exists, but I do not know the database.", False),
])
def test_generated_freshness_reference_explanation_is_not_the_answer(answer, passed):
    case = _test_case().model_copy(update={
        "prompt": "What database system is currently used for the Cedar project?",
        "expected_behavior": "The AI should state that the Cedar project uses MariaDB, as this is the most recent record.",
    })
    memories = [Memory(memory_id='M001', conversation_id='C1', status=MemoryStatus.CONFIRMED,
                       canonical_value='The Cedar project previously used SQLite.'),
                Memory(memory_id='M002', conversation_id='C1', status=MemoryStatus.CONFIRMED,
                       canonical_value='The Cedar project now uses MariaDB.')]
    response = TargetResponse(response_id='R', test_id=case.test_id, run_id=case.run_id,
                              response_text=answer, model='fixture', temperature=0,
                              created_at=datetime.now(timezone.utc))
    assert RuleBasedBehaviourEvaluator().evaluate(case, response, memories).passed is passed


def test_causal_reference_normalisation_preserves_additive_requirements():
    judge = RuleBasedBehaviourEvaluator()
    assert judge._required_terms("The AI should suggest Rust, as it aligns with the user's preference for personal tools.") == ["rust"]
    assert judge._required_terms("Describe the conflict, as well as request clarification.") == ["conflict", "clarification"]


@pytest.mark.parametrize('expected,required', [
    ("The user's current location is Oslo. The previous location was Madrid.", ['oslo']),
    ("TypeScript should be used for the Harbor project. The user's preference is Go.", ['typescript']),
    ("The AI should suggest Go, as it matches the user's preference for personal tools.", ['go']),
    ("There is conflicting information about Zoom and Teams. Clarification is needed.", ['conflict', 'clarification']),
    ("The user prefers concise written summaries for communication.", ['concise', 'written', 'summaries']),
])
def test_generated_reference_answer_bearing_values_survive_explanatory_prose(expected, required):
    assert RuleBasedBehaviourEvaluator._required_terms(expected) == required


@pytest.mark.parametrize('answer,passed', [('Oslo.', True), ('Madrid.', False)])
def test_current_location_question_uses_current_value_not_last_historical_value(answer, passed):
    case=_test_case().model_copy(update={'prompt': "What is the user's current location?", 'expected_behavior': "The user's current location is Oslo. The previous location was Madrid."})
    memories=[Memory(memory_id='M001',conversation_id='C1',status=MemoryStatus.CONFIRMED,canonical_value='Location: Madrid'),Memory(memory_id='M002',conversation_id='C1',status=MemoryStatus.CONFIRMED,canonical_value='Location: Oslo')]
    response=TargetResponse(response_id='R',test_id=case.test_id,run_id=case.run_id,response_text=answer,model='fixture',temperature=0,created_at=datetime.now(timezone.utc))
    assert RuleBasedBehaviourEvaluator().evaluate(case,response,memories).passed is passed

@pytest.mark.parametrize('answer,passed', [
    ('Utrecht replaces the previous location Lyon.', True),
    ('The current location is Utrecht; the historical value was unknown.', False),
    ('The current location is Lyon.', False),
])
def test_location_update_uses_concrete_value_and_keeps_known_history_guard(answer, passed):
    case = _test_case().model_copy(update={
        'dimension': Dimension.FRESHNESS,
        'prompt': 'Where is the user based now? Explain the replacement of the historical state.',
        'expected_behavior': 'Use the recorded current value: I moved to Utrecht and now live there.',
        'supporting_memory_ids': ['M001', 'M002'],
    })
    memories = [Memory(memory_id='M001', conversation_id='C1', status=MemoryStatus.CONFIRMED,
                       canonical_value='I am based in Lyon.'),
                Memory(memory_id='M002', conversation_id='C1', status=MemoryStatus.CONFIRMED,
                       canonical_value='I moved to Utrecht and now live there.',
                       relationships=[{'type':'UPDATE', 'target_memory_id':'M001'}])]
    response = TargetResponse(response_id='R',test_id=case.test_id,run_id=case.run_id,response_text=answer,
                              model='fixture',temperature=0,created_at=datetime.now(timezone.utc))
    result = RuleBasedBehaviourEvaluator().evaluate(case,response,memories)
    assert result.passed is passed
    if 'unknown' in answer:
        assert 'earlier location as unknown' in result.reason
        assert 'whether that historical record was supplied' in result.reason
    else:
        assert 'and, now, live, there' not in result.reason


def test_location_tail_trimming_preserves_conjunctions_in_place_names():
    assert RuleBasedBehaviourEvaluator._required_terms('I moved to Trinidad and Tobago and now live there.') == ['trinidad', 'and', 'tobago']

@pytest.mark.parametrize('answer,ask_history,linked,expected', [
    ('The user is based in Utrecht now. The recorded current state replaces the historical state in which the user moved to Utrecht.', True, True, False),
    ('Utrecht.', True, True, False),
    ('Utrecht replaces Lyon as the current location.', True, True, True),
    ('Utrecht.', False, True, True),
    ('Utrecht.', True, False, True),
])
def test_required_location_replacement_cannot_pass_on_current_keyword_alone(answer, ask_history, linked, expected):
    case = _test_case().model_copy(update={
        'prompt': 'Where is the user based now?' + (' Explain how the current state replaces the historical state.' if ask_history else ' State only the location.'),
        'expected_behavior': 'Use the recorded current value: I moved to Utrecht and now live there.',
    })
    memories = [Memory(memory_id='M001', conversation_id='C1', status=MemoryStatus.CONFIRMED, canonical_value='I am based in Lyon.'),
                Memory(memory_id='M002', conversation_id='C1', status=MemoryStatus.CONFIRMED, canonical_value='I moved to Utrecht and now live there.',
                       relationships=[{'type':'UPDATE', 'target_memory_id':'M001'}] if linked else [])]
    response = TargetResponse(response_id='R', test_id=case.test_id, run_id=case.run_id, response_text=answer,
                              model='fixture', temperature=0, created_at=datetime.now(timezone.utc))
    result = RuleBasedBehaviourEvaluator().evaluate(case, response, memories)
    assert result.passed is expected
    if not expected:
        assert 'omits the explicitly linked earlier location' in result.reason


@pytest.mark.parametrize('explanation', [
    'reflecting the most recent information',
    'consistent with the most recent record',
    'in line with the stated update',
])
@pytest.mark.parametrize('answer,verdict', [
    ('Aster currently uses PostgreSQL.', True),
    ('Aster uses SQLite, reflecting the most recent information.', False),
    ('The most recent information is available.', False),
])
def test_reference_explanation_does_not_become_the_required_database_answer(explanation, answer, verdict):
    case = _test_case().model_copy(update={
        'prompt':'What database does Aster use now?',
        'expected_behavior':f'The AI should state that the Aster backend now uses PostgreSQL, {explanation}.',
    })
    memories = [Memory(memory_id='M001',conversation_id='C1',status=MemoryStatus.CONFIRMED,canonical_value='Aster previously used MySQL.'),
                Memory(memory_id='M002',conversation_id='C1',status=MemoryStatus.CONFIRMED,canonical_value='Aster now uses PostgreSQL.')]
    response = TargetResponse(response_id='R',test_id=case.test_id,run_id=case.run_id,response_text=answer,
                              model='fixture',temperature=0,created_at=datetime.now(timezone.utc))
    assert RuleBasedBehaviourEvaluator().evaluate(case,response,memories).passed is verdict


def test_reference_explanation_cannot_strip_required_conflict_clarification():
    assert RuleBasedBehaviourEvaluator._required_terms('Describe the conflict, reflecting incompatible requirements, and request clarification.') == ['conflict','clarification']
