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
        assert plan['acceptance_protocol']['format'] == 'formal-acceptance-protocol-v2'
        assert plan['acceptance_protocol']['reader_control'] == 'fixed_strong_reader'
        assert plan['repetition_count'] == 3
        assert design == {**DESIGN, 'analysis_unit': 'source_history', 'incomplete_results': 'report_without_imputing_scores'}
        run_id = plan['scenarios'][0]['run_ids'][0]
        audit = client.get(f'/api/v1/audits/{run_id}').json()
        assert audit['status'] == 'TESTS_GENERATED'
        assert client.get(f'/api/v1/research/formal/{run_id}/plan').json() == plan
        for scenario in plan['scenarios']:
            for condition_run_id in scenario['run_ids']:
                condition = client.get(f'/api/v1/audits/{condition_run_id}').json()
                assert condition['target_configuration'] == 'strong'


def test_strategy_conditions_keep_one_strong_reader():
    from app.schemas.domain import MemoryStrategy, TargetConfiguration
    from app.schemas.formal_experiment import FormalMatrixCondition

    for strategy in MemoryStrategy:
        condition = FormalMatrixCondition(label=strategy.value, memory_strategy=strategy)
        assert condition.target_configuration == TargetConfiguration.STRONG


def test_historical_protocol_does_not_gain_reader_control_from_new_defaults():
    from datetime import datetime, timezone
    from app.schemas.formal_experiment import FormalAcceptanceProtocol
    from test_formal_synthetic_matrix import CRITERIA

    historical = FormalAcceptanceProtocol(
        study_mode='formal_experiment_b', frozen_at=datetime.now(timezone.utc),
        criteria=CRITERIA, dataset_fingerprint_sha256='a' * 64,
        runtime_source_sha256='b' * 64,
    )
    assert historical.reader_control is None


@pytest.mark.parametrize('protocol,configuration', [
    ({'study_mode': 'formal_experiment_b'}, 'strong'),
    ({'study_mode': 'formal_experiment_b', 'reader_control': 'fixed_strong_reader'}, 'weak'),
])
def test_direct_frozen_input_guard_rejects_formal_reader_confounds(protocol, configuration):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.services.formal_freeze import assert_formal_inputs_frozen

    audit = SimpleNamespace(target_configuration=configuration, reproducibility_metadata={
        'formal_matrix_version': 'historical-or-current', 'formal_acceptance_protocol': protocol,
    })
    with pytest.raises(HTTPException, match='frozen Strong reader') as rejected:
        assert_formal_inputs_frozen(SimpleNamespace(scalars=lambda statement: []), audit)
    assert rejected.value.status_code == 409


def test_formal_restore_rejects_legacy_reader_confounded_plan_without_changing_records(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.models import AuditRunModel

    development = deepcopy(DATASET)
    for history in development['conversations']:
        for message in history['messages']:
            message['content'] += ' Development-only reader control history.'
    payload = request(development)
    payload.update(study_design=DESIGN, repetitions=3, conditions=[
        {'label': 'Weak', 'provider': 'rule_based', 'memory_strategy': 'weak_first_hit'},
        {'label': 'Strong', 'provider': 'rule_based', 'memory_strategy': 'strong_rule_based'},
    ])
    with client_for(tmp_path) as client:
        created = client.post('/api/v1/research/formal/synthetic-matrix', json=payload)
        assert created.status_code == 201, created.text
        plan = created.json()
        run_id = plan['scenarios'][0]['run_ids'][0]
        with Session(create_engine(f"sqlite:///{tmp_path / 'guards.db'}")) as db:
            run = db.get(AuditRunModel, run_id)
            metadata = deepcopy(run.reproducibility_metadata)
            metadata['formal_matrix_manifest']['acceptance_protocol'].pop('reader_control')
            metadata['formal_acceptance_protocol'].pop('reader_control')
            run.reproducibility_metadata = metadata
            run.target_configuration = 'weak'
            db.commit()
        restored = client.get(f'/api/v1/research/formal/{run_id}/plan')
        assert restored.status_code == 409
        assert 'one Strong reader' in restored.text
        preserved = client.get(f'/api/v1/audits/{run_id}').json()
        assert preserved['target_configuration'] == 'weak'
        assert preserved['status'] == 'TESTS_GENERATED'


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
