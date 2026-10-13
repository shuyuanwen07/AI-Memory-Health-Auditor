"""Supplied split checks detect content reuse, without certifying independence."""
from copy import deepcopy

import pytest

from app.schemas.annotation import AnnotationDataset
from app.schemas.research import annotation_fingerprint
from test_formal_synthetic_matrix import DATASET, PILOT, CRITERIA
from test_input_and_relationship_guards import client_for


def request(development):
    return {'dataset': DATASET, 'pilot': PILOT, 'development_dataset': development,
            'synthetic_data_confirmation': True, 'success_criteria': CRITERIA,
            'conditions': [{'label': 'None', 'provider': 'rule_based', 'memory_strategy': 'no_memory'},
                           {'label': 'All', 'provider': 'rule_based', 'memory_strategy': 'full_context'}]}


@pytest.mark.parametrize('disguise', ['unchanged', 'ids', 'dates', 'spacing_and_case'])
def test_reused_history_is_rejected_before_any_persistence(tmp_path, disguise):
    development = deepcopy(DATASET)
    development['dataset_id'] = 'development-only'
    for scenario in development['conversations']:
        if disguise == 'ids':
            scenario['conversation_id'] = 'DEV-' + scenario['conversation_id']
        for message in scenario['messages']:
            if disguise == 'dates':
                message['timestamp'] = '2020-01-01T00:00:00Z'
            if disguise == 'spacing_and_case':
                message['content'] = '  ' + message['content'].upper().replace(' ', '\n   ') + '  '
    with client_for(tmp_path) as client:
        response = client.post('/api/v1/research/exploratory/synthetic-matrix', json=request(development))
        assert response.status_code == 422
        assert 'share conversation content' in response.text
        assert client.get('/api/v1/audits').json() == []


def test_distinct_histories_are_bound_and_recovered_without_development_text(tmp_path):
    development = deepcopy(DATASET)
    for scenario in development['conversations']:
        for message in scenario['messages']:
            message['content'] += ' Development history only, never part of the formal target input.'
    with client_for(tmp_path) as client:
        response = client.post('/api/v1/research/exploratory/synthetic-matrix', json=request(development))
        assert response.status_code == 201, response.text
        plan = response.json()
        protocol = plan['acceptance_protocol']
        assert protocol['study_mode'] == 'exploratory'
        assert protocol['distinct_history_check'] == 'no_normalized_history_overlap'
        assert protocol['development_dataset_fingerprint_sha256'] == annotation_fingerprint(AnnotationDataset.model_validate(development))
        run_id = plan['scenarios'][0]['run_ids'][0]
        recovered = client.get(f'/api/v1/research/formal/{run_id}/plan')
        assert recovered.status_code == 200
        assert recovered.json() == plan
        assert 'Development history only' not in recovered.text
        assert 'Development history only' not in client.get(f'/api/v1/audits/{run_id}').text


def test_duplicate_formal_histories_cannot_be_counted_as_distinct_scenarios(tmp_path):
    development = deepcopy(DATASET)
    for scenario in development['conversations']:
        for message in scenario['messages']:
            message['content'] += ' Independent fixture context.'
    payload = request(development)
    payload['dataset'] = deepcopy(DATASET)
    first = payload['dataset']['conversations'][0]['messages']
    second = payload['dataset']['conversations'][1]['messages']
    assert len(first) == len(second)
    for left, right in zip(first, second):
        right['content'] = left['content']
        right['role'] = left['role']
    payload['pilot'] = deepcopy(PILOT)
    payload['pilot']['dataset_fingerprint_sha256'] = annotation_fingerprint(AnnotationDataset.model_validate(payload['dataset']))
    with client_for(tmp_path) as client:
        response = client.post('/api/v1/research/exploratory/synthetic-matrix', json=payload)
        assert response.status_code == 422
        assert 'duplicate conversation content' in response.text
        assert client.get('/api/v1/audits').json() == []
