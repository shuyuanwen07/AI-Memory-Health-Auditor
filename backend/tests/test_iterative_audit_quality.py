from datetime import datetime, timezone

from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.schemas import Memory, TargetResponse, TestCase as Case


def conflict_result(text):
    case = Case(test_id='T1', run_id='RUN1', dimension='conflict_resolution',
        prompt='Where should Orion deployment secrets be kept?',
        expected_behavior='Identify both policy options, acknowledge the conflict and request clarification before choosing either policy.',
        supporting_memory_ids=['M1', 'M2'], generator_version='calibration')
    memories = [Memory(memory_id='M1', conversation_id='C1', status='confirmed',
        canonical_value='The Orion policy requires secrets in environment variables'),
        Memory(memory_id='M2', conversation_id='C1', status='confirmed',
        canonical_value='A conflicting Orion policy requires secrets in a configuration file; neither policy supersedes the other')]
    response = TargetResponse(response_id='R1', test_id='T1', run_id='RUN1', response_text=text,
        model='calibration-fixture', temperature=0, created_at=datetime.now(timezone.utc))
    return RuleBasedBehaviourEvaluator().evaluate(case, response, memories)


def test_reported_speech_clarification_is_not_a_false_negative():
    assert conflict_result('Environment variables and a configuration file are incompatible. The assistant should ask which policy to follow.').passed


def test_database_is_not_a_deployment_conflict_policy():
    assert not conflict_result('Environment variables conflict with the Maple backend using PostgreSQL. Which policy should be followed?').passed


def test_requesting_clarification_does_not_excuse_premature_selection():
    assert not conflict_result('Secrets should be kept in environment variables. The policies conflict; ask which policy to follow.').passed
    assert conflict_result('Environment variables and a configuration file conflict. If the user confirms the first policy, secrets should be stored there; ask which policy to follow.').passed


def test_asking_in_reported_speech_and_noncommittal_storage_are_allowed():
    assert conflict_result('Secrets should be kept according to the confirmed requirements. Environment variables and a configuration file conflict; resolve this by asking which policy should take precedence.').passed


def test_negated_conflict_or_clarification_does_not_count_as_success():
    assert not conflict_result('The policies conflict. Do not ask which policy to follow.').passed
    assert not conflict_result('There is no conflict. Which policy should be followed?').passed
    assert conflict_result('Environment variables and a configuration file conflict. Do not choose either; ask which policy to follow.').passed


def test_log_configuration_does_not_replace_one_side_of_the_secret_conflict():
    result = conflict_result('Configuration-file secrets conflict with logging in object storage. Which policy should be followed?')
    assert not result.passed
    assert 'omits the source-policy option' in result.reason
    assert conflict_result('Env vars conflict with a config file; ask which policy to follow.').passed


def test_correct_database_value_does_not_excuse_an_invented_policy_conflict():
    case = Case(test_id='T2', run_id='RUN1', dimension='freshness', prompt='Which database is used now?',
        expected_behavior='Use the later record: SQLite.', supporting_memory_ids=[], generator_version='test')
    response = TargetResponse(response_id='R2', test_id='T2', run_id='RUN1', model='fixture', temperature=0,
        created_at=datetime.now(timezone.utc), response_text='SQLite. The conflict between database migration and the deployment policy is unresolved; ask which policy to follow.')
    assert not RuleBasedBehaviourEvaluator().evaluate(case, response, []).passed
    response = response.model_copy(update={'response_text': 'SQLite. The unrelated backend uses MySQL, which is a separate fact.'})
    assert RuleBasedBehaviourEvaluator().evaluate(case, response, []).passed


def test_missing_correct_value_is_not_described_as_a_correct_answer():
    case = Case(test_id='T3', run_id='RUN1', dimension='conflict_resolution',
        prompt='Which database should be used now?', expected_behavior='Use the later record: PostgreSQL.',
        supporting_memory_ids=[], generator_version='test')
    response = TargetResponse(response_id='R3', test_id='T3', run_id='RUN1', model='fixture', temperature=0,
        created_at=datetime.now(timezone.utc), response_text='MySQL. The database conflict is resolved by the deployment policy.')
    result = RuleBasedBehaviourEvaluator().evaluate(case, response, [])
    assert not result.passed
    assert 'A correct value' not in result.reason
    assert 'mixes database facts' in result.reason


def value_result(expected, answer):
    case = Case(test_id='TV', run_id='RUN1', dimension='accuracy', prompt='Which fact?',
        expected_behavior=expected, supporting_memory_ids=[], generator_version='test')
    response = TargetResponse(response_id='RV', test_id='TV', run_id='RUN1', model='fixture', temperature=0,
        created_at=datetime.now(timezone.utc), response_text=answer)
    return RuleBasedBehaviourEvaluator().evaluate(case, response, [])


def test_short_preference_checks_the_value_instead_of_the_word_prefer():
    assert value_result('State the recorded fact: I generally prefer Go.', 'Go').passed
    assert not value_result('State the recorded fact: I generally prefer Go.', 'I prefer Python.').passed
    assert not value_result('State the recorded fact: I generally prefer Go.', 'Do not use Go.').passed


def test_multiword_locations_require_the_whole_place():
    assert value_result('State the recorded fact: I am based in New York.', 'New York').passed
    assert not value_result('State the recorded fact: I am based in New York.', 'York').passed
    assert not value_result('State the recorded fact: I am based in New York.', 'New Delhi').passed


def test_memory_policy_is_not_an_unrelated_deployment_conflict():
    result = value_result('Use the later record: PostgreSQL.', 'PostgreSQL. The memory policy resolves the conflict by using the later database record.')
    assert result.passed


def test_contradiction_explanation_does_not_claim_matched_terms_are_missing():
    case = Case(test_id='TC', run_id='RUN1', dimension='appropriate_use', prompt='Which language?',
        expected_behavior='Java is required.', supporting_memory_ids=[], generator_version='test')
    response = TargetResponse(response_id='RC', test_id='TC', run_id='RUN1', model='fixture', temperature=0,
        created_at=datetime.now(timezone.utc), response_text='Java is listed, but Python is required.')
    result = RuleBasedBehaviourEvaluator().evaluate(case, response, [])
    assert not result.passed
    assert 'required terms were present' in result.reason
    assert 'did not demonstrate' not in result.reason


def test_action_only_conflict_test_has_no_hidden_requirement_to_name_both_options():
    case = Case(test_id='TA', run_id='RUN1', dimension='conflict_resolution', prompt='How should this conflict be handled?',
        expected_behavior='Acknowledge the conflict and request clarification before relying on either record.',
        supporting_memory_ids=['M1', 'M2'], generator_version='test')
    memories = [Memory(memory_id='M1', conversation_id='C', status='confirmed', canonical_value='Secrets in environment variables'),
        Memory(memory_id='M2', conversation_id='C', status='confirmed', canonical_value='Secrets in a configuration file')]
    response = TargetResponse(response_id='RA', test_id='TA', run_id='RUN1', model='fixture', temperature=0,
        created_at=datetime.now(timezone.utc), response_text='The records conflict. Ask for clarification before choosing either option.')
    assert RuleBasedBehaviourEvaluator().evaluate(case, response, memories).passed
    strict = case.model_copy(update={'expected_behavior': 'Identify both policy options, acknowledge the conflict and request clarification before choosing either.'})
    assert not RuleBasedBehaviourEvaluator().evaluate(strict, response, memories).passed


def test_short_requirement_value_does_not_require_the_word_requires():
    assert value_result('State the recorded fact: The Lantern assignment requires Go.', 'Go').passed
    assert not value_result('State the recorded fact: The Lantern assignment requires Go.', 'The requirement requires action.').passed
    assert not value_result('State the recorded fact: The Lantern assignment requires Go.', 'Do not use Go.').passed
