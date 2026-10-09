from datetime import datetime, timezone

import pytest

from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.schemas import Dimension, Memory, MemoryStatus, TargetResponse, TestCase as DomainTestCase


def _test_case() -> DomainTestCase:
    return DomainTestCase(
        test_id="T007", run_id="RUN1", dimension=Dimension.FRESHNESS,
        prompt="Which database should be used?", expected_behavior="Use the later record: PostgreSQL.",
        supporting_memory_ids=["M001", "M002"], generator_version="rule-based-v2",
    )


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
        [Memory(memory_id="M001", conversation_id="C1", canonical_value="Old database: MySQL", status=MemoryStatus.CONFIRMED)],
    )
    assert not result.passed
    assert result.failure_type == Dimension.FRESHNESS
    assert "postgresql" in result.reason.lower()
    assert result.evidence_memory_ids == ["M001"]


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
        assert 'causal explanation' in result.reason

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
