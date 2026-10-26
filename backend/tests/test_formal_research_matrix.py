"""Research-source permissions use simulated fixtures, never real human evidence."""
from copy import deepcopy

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models import AuditRunModel

import pytest
from app.schemas.annotation import AnnotationDataset
from app.schemas.research import annotation_fingerprint
from test_formal_history_split import request
from test_formal_study_design import DESIGN
from test_formal_synthetic_matrix import DATASET
from test_input_and_relationship_guards import client_for


def research_request():
    development = deepcopy(DATASET)
    for history in development['conversations']:
        for message in history['messages']:
            message['content'] += ' Distinct development-only context.'
    payload = deepcopy(request(development))
    payload['dataset']['data_origin'] = 'deidentified_research'
    fingerprint = annotation_fingerprint(AnnotationDataset.model_validate(payload['dataset']))
    payload['pilot']['dataset_fingerprint_sha256'] = fingerprint
    payload.update(synthetic_data_confirmation=False, study_design=DESIGN, repetitions=3,
        conditions=[{'label':'Weak','provider':'rule_based','memory_strategy':'weak_first_hit'},
                    {'label':'Strong','provider':'rule_based','memory_strategy':'strong_rule_based'}],
        source_release={'release_id':'fixture-only-permission','dataset_fingerprint_sha256':fingerprint,
            'permission_reference':'Simulated contract fixture; no research permission is asserted.',
            'licence_or_consent_scope':'Simulated research/storage permission for isolated contract testing.',
            'reviewed_by':'simulated-reviewer','reviewed_at':'2026-01-01T00:00:00Z',
            'deidentified':True,'research_use_authorised':True,'operational_storage_authorised':True,
            'cloud_processing_authorised':False,'user_history_demo_only':False})
    return payload


@pytest.mark.parametrize('change', ['missing_receipt','wrong_hash','demo','not_deidentified','no_research','no_storage','cloud','wrong_origin','short_repeats','no_split','changed_target'])
def test_research_source_guards_reject_before_persistence(tmp_path, change):
    payload = research_request()
    if change=='missing_receipt': payload.pop('source_release')
    elif change=='wrong_hash': payload['source_release']['dataset_fingerprint_sha256']='a'*64
    elif change=='demo': payload['source_release']['user_history_demo_only']=True
    elif change=='not_deidentified': payload['source_release']['deidentified']=False
    elif change=='no_research': payload['source_release']['research_use_authorised']=False
    elif change=='no_storage': payload['source_release']['operational_storage_authorised']=False
    elif change=='cloud':
        for condition in payload['conditions']: condition['provider']='openrouter'
    elif change=='wrong_origin': payload['dataset']['data_origin']='authorised'
    elif change=='short_repeats': payload['repetitions']=1
    elif change=='no_split': payload['development_dataset']=None
    elif change=='changed_target': payload['conditions'][1]['model']='different-base-model'
    with client_for(tmp_path) as client:
        response=client.post('/api/v1/research/formal/research-matrix',json=payload)
        assert response.status_code==422, response.text
        assert client.get('/api/v1/audits').json()==[]


def test_research_matrix_preserves_source_receipt_and_executes_frozen_suite(tmp_path):
    payload=research_request()
    with client_for(tmp_path) as client:
        created=client.post('/api/v1/research/formal/research-matrix',json=payload)
        assert created.status_code==201,created.text
        plan=created.json()
        receipt=plan['acceptance_protocol']['source_release']
        assert receipt['dataset_fingerprint_sha256']==plan['dataset_fingerprint_sha256']
        assert receipt['cloud_processing_authorised'] is False
        run_id=plan['scenarios'][0]['run_ids'][0]
        audit=client.get(f'/api/v1/audits/{run_id}').json()
        conversation=client.get(f"/api/v1/conversations/{audit['conversation_id']}").json()
        assert conversation['source_origin']=='deidentified'
        with Session(create_engine(f"sqlite:///{tmp_path / 'guards.db'}")) as db:
            assert db.get(AuditRunModel,run_id).reproducibility_metadata['suite_kind']=='frozen_human_labelled_deidentified'
        assert client.get(f'/api/v1/research/formal/{run_id}/plan').json()==plan
        assert client.post(f'/api/v1/audits/{run_id}/execute').status_code==200
        assert client.post(f'/api/v1/audits/{run_id}/evaluate').status_code==200
        assert 'caller declarations' in plan['notice']


def test_synthetic_route_does_not_accept_research_receipt(tmp_path):
    with client_for(tmp_path) as client:
        response=client.post('/api/v1/research/formal/synthetic-matrix',json=research_request())
        assert response.status_code==422
        assert client.get('/api/v1/audits').json()==[]


def test_research_permission_receipt_is_part_of_frozen_inputs(tmp_path):
    with client_for(tmp_path) as client:
        created=client.post('/api/v1/research/formal/research-matrix',json=research_request())
        assert created.status_code==201,created.text
        run_id=created.json()['scenarios'][0]['run_ids'][0]
        with Session(create_engine(f"sqlite:///{tmp_path / 'guards.db'}")) as db:
            run=db.get(AuditRunModel,run_id)
            changed=deepcopy(run.reproducibility_metadata)
            changed['formal_acceptance_protocol']['source_release']['cloud_processing_authorised']=True
            run.reproducibility_metadata=changed
            db.commit()
        result=client.post(f'/api/v1/audits/{run_id}/execute')
        assert result.status_code==409,result.text
        assert 'frozen' in result.text.lower()
