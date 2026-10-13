"""Analysis choices are frozen declarations, not independent research proof."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas.formal_experiment import FormalStudyDesign
from test_formal_history_split import request
from test_formal_synthetic_matrix import DATASET
from test_input_and_relationship_guards import client_for

DESIGN = {'sampling_rule': 'Select all five histories from the permitted fixture inventory before target execution; exclude none.',
          'primary_outcome': 'freshness'}


@pytest.mark.parametrize('change', [
    {'sampling_rule': ' ' * 25}, {'sampling_rule': 'short'},
    {'primary_outcome': 'best_after_inspection'},
    {'analysis_unit': 'individual_repeated_answer'},
    {'incomplete_results': 'discard_failed_runs'},
])
def test_analysis_choices_reject_empty_or_unsupported_protocols(change):
    with pytest.raises(ValidationError):
        FormalStudyDesign.model_validate({**DESIGN, **change})


def test_study_design_requires_a_development_inventory_before_persistence(tmp_path):
    payload = request(None)
    payload['conditions'] = [{'label':'Weak','provider':'rule_based','memory_strategy':'weak_first_hit'},
                             {'label':'Strong','provider':'rule_based','memory_strategy':'strong_rule_based'}]
    payload['study_design'] = DESIGN
    with client_for(tmp_path) as client:
        response = client.post('/api/v1/research/formal/synthetic-matrix', json=payload)
        assert response.status_code == 422
        assert 'development dataset' in response.text
        assert client.get('/api/v1/audits').json() == []


def test_declared_plan_is_saved_before_calls_and_restored(tmp_path):
    development = deepcopy(DATASET)
    for history in development['conversations']:
        for message in history['messages']:
            message['content'] += ' Development-only context.'
    payload = request(development)
    payload['conditions'] = [{'label':'Weak','provider':'rule_based','memory_strategy':'weak_first_hit'},
                             {'label':'Strong','provider':'rule_based','memory_strategy':'strong_rule_based'}]
    payload['study_design'] = DESIGN
    payload['repetitions'] = 3
    with client_for(tmp_path) as client:
        created = client.post('/api/v1/research/formal/synthetic-matrix', json=payload)
        assert created.status_code == 201, created.text
        plan = created.json()
        design = plan['acceptance_protocol']['study_design']
        assert plan['acceptance_protocol']['study_mode'] == 'formal_experiment_b'
        assert plan['repetition_count'] == 3
        assert design == {**DESIGN, 'analysis_unit': 'source_history', 'incomplete_results': 'report_without_imputing_scores'}
        run_id = plan['scenarios'][0]['run_ids'][0]
        audit = client.get(f'/api/v1/audits/{run_id}').json()
        assert audit['status'] == 'TESTS_GENERATED'
        assert client.get(f'/api/v1/research/formal/{run_id}/plan').json() == plan


def test_formal_plan_requires_a_paired_weak_strong_same_model_comparison():
    from pydantic import ValidationError
    from app.schemas.formal_experiment import FormalMatrixCreateRequest
    development = deepcopy(DATASET)
    for conversation in development['conversations']:
        for message in conversation['messages']:
            message['content'] += ' Development-only statement.'
    payload = request(development)
    payload['study_design'] = DESIGN
    with pytest.raises(ValidationError,match='both the predeclared Weak'):
        FormalMatrixCreateRequest.model_validate(payload)
    payload['conditions'] = [{'label':'Weak','provider':'ollama','model':'qwen3:1.7b','memory_strategy':'weak_first_hit'},
                             {'label':'Strong','provider':'ollama','model':'qwen3:4b','memory_strategy':'strong_rule_based'}]
    with pytest.raises(ValidationError,match='one target provider, model and temperature'):
        FormalMatrixCreateRequest.model_validate(payload)
    payload['conditions'][1]['model']='qwen3:1.7b'
    payload['conditions'][0]['provider']='openrouter'
    with pytest.raises(ValidationError,match='one target provider, model and temperature'):
        FormalMatrixCreateRequest.model_validate(payload)


@pytest.mark.parametrize(('provider', 'repetitions', 'accepted'), [
    ('rule_based', 1, False),
    ('ollama', 1, False),
    ('openrouter', 1, False),
    ('rule_based', 3, True),
    ('ollama', 3, True),
    ('openrouter', 3, True),
])
def test_formal_b_requires_three_repetitions_for_every_target_provider(provider, repetitions, accepted):
    from app.schemas.formal_experiment import FormalMatrixCreateRequest

    development = deepcopy(DATASET)
    for conversation in development['conversations']:
        for message in conversation['messages']:
            message['content'] += ' Distinct development-only evidence.'
    payload = request(development)
    model = 'rule-based-target-ai' if provider == 'rule_based' else 'qwen3:1.7b' if provider == 'ollama' else 'provider/model-v1'
    payload.update({
        'study_design': DESIGN,
        'repetitions': repetitions,
        'conditions': [
            {'label': 'Weak', 'provider': provider, 'model': model, 'memory_strategy': 'weak_first_hit'},
            {'label': 'Strong', 'provider': provider, 'model': model, 'memory_strategy': 'strong_rule_based'},
        ],
    })

    if accepted:
        FormalMatrixCreateRequest.model_validate(payload)
    else:
        with pytest.raises(ValidationError, match='at least three repetitions'):
            FormalMatrixCreateRequest.model_validate(payload)


def test_formal_b_rejects_missing_plan_and_single_repeat_before_persistence(tmp_path):
    development = deepcopy(DATASET)
    for conversation in development['conversations']:
        for message in conversation['messages']:
            message['content'] += ' Development-only evidence for formal guard.'
    payload = request(development)
    payload['conditions'] = [
        {'label': 'Weak', 'provider': 'ollama', 'model': 'qwen3:1.7b', 'memory_strategy': 'weak_first_hit'},
        {'label': 'Strong', 'provider': 'ollama', 'model': 'qwen3:1.7b', 'memory_strategy': 'strong_rule_based'},
    ]
    payload['repetitions'] = 3

    with client_for(tmp_path) as client:
        missing_plan = client.post('/api/v1/research/formal/synthetic-matrix', json=payload)
        assert missing_plan.status_code == 422
        assert 'study_design' in missing_plan.text
        assert client.get('/api/v1/audits').json() == []

        payload['study_design'] = DESIGN
        payload['repetitions'] = 2
        one_repeat = client.post('/api/v1/research/formal/synthetic-matrix', json=payload)
        assert one_repeat.status_code == 422
        assert 'at least three repetitions' in one_repeat.text
        assert client.get('/api/v1/audits').json() == []
