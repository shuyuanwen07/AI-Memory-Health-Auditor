from test_reviewed_acceptance import study as reviewed_study
from app.models import AuditRunModel

# Register the shared isolated fixture under a local name.
study = reviewed_study


def test_saved_formal_index_is_paged_and_legacy_criteria_are_explicit(study):
    client,factory,run,_=study
    with factory() as db:
        original=db.get(AuditRunModel,run)
        db.add(AuditRunModel(id='ORDINARY-RUN',conversation_id=original.conversation_id,target_configuration='weak',provider='rule_based',model='fixture',temperature=0,random_seed=42,test_budget=4,prompt_template_version='fixture',reproducibility_metadata={}))
        metadata=dict(original.reproducibility_metadata);metadata.pop('formal_acceptance_protocol')
        original.reproducibility_metadata=metadata;db.commit()
    first=client.get('/api/v1/research/formal/saved-runs?offset=0&limit=3')
    second=client.get('/api/v1/research/formal/saved-runs?offset=3&limit=3')
    assert first.status_code==second.status_code==200
    assert first.json()['total']==30
    assert len(first.json()['items'])==3
    assert all(item['provider']=='rule_based' for item in first.json()['items'])
    assert all(item['created_at'].endswith('+00:00') for item in first.json()['items'])
    assert not set(item['run_id'] for item in first.json()['items']) & set(item['run_id'] for item in second.json()['items'])
    all_rows=client.get('/api/v1/research/formal/saved-runs?limit=50').json()['items']
    assert any(item['study_mode']=='formal_experiment_b' for item in all_rows)
    legacy=next(item for item in all_rows if item['run_id']==run)
    assert legacy['has_frozen_criteria'] is False
    assert legacy['study_mode']=='exploratory'
    assert 'ORDINARY-RUN' not in [item['run_id'] for item in all_rows]
    assert client.get('/api/v1/research/formal/saved-runs?limit=51').status_code==422
    assert client.get('/api/v1/research/formal/saved-runs?offset=-1').status_code==422


def test_recovery_restores_entire_signed_matrix_without_changing_lifecycle(study):
    client,factory,run,_=study
    recovered=client.get(f'/api/v1/research/formal/{run}/plan')
    assert recovered.status_code==200,recovered.text
    plan=recovered.json()
    assert plan['total_audit_runs']==30
    assert plan['scenario_count']==5
    with factory() as db:
        original=db.get(AuditRunModel,run)
        assert plan==original.reproducibility_metadata['formal_matrix_manifest']
        assert original.status=='COMPLETED'
    assert client.get('/api/v1/research/formal/missing/plan').status_code==404


def test_recovery_refuses_missing_peer_even_when_selected_run_is_intact(study):
    client,factory,run,_=study
    with factory() as db:
        plan=db.get(AuditRunModel,run).reproducibility_metadata['formal_matrix_manifest']
        peer=plan['scenarios'][-1]['run_ids'][-1]
        db.delete(db.get(AuditRunModel,peer));db.commit()
    response=client.get(f'/api/v1/research/formal/{run}/plan')
    assert response.status_code==409
    assert 'missing' in response.json()['detail']


def test_recovery_refuses_changed_manifest_or_legacy_missing_plan(study):
    client,factory,run,_=study
    import copy
    with factory() as db:
        row=db.get(AuditRunModel,run);metadata=copy.deepcopy(row.reproducibility_metadata)
        metadata['formal_matrix_manifest']['total_target_calls']+=1
        row.reproducibility_metadata=metadata;db.commit()
    assert client.get(f'/api/v1/research/formal/{run}/plan').status_code==409
    with factory() as db:
        row=db.get(AuditRunModel,run);metadata=dict(row.reproducibility_metadata);metadata.pop('formal_matrix_manifest');row.reproducibility_metadata=metadata;db.commit()
    response=client.get(f'/api/v1/research/formal/{run}/plan')
    assert response.status_code==409
    assert 'older experiment' in response.json()['detail']


def test_recovery_checks_peer_inputs_not_only_the_selected_run(study):
    client,factory,run,_=study
    with factory() as db:
        plan=db.get(AuditRunModel,run).reproducibility_metadata['formal_matrix_manifest']
        peer=db.get(AuditRunModel,plan['scenarios'][-1]['run_ids'][-1]);peer.model='changed-model';db.commit()
    response=client.get(f'/api/v1/research/formal/{run}/plan')
    assert response.status_code==409
    assert 'settings' in response.json()['detail']


def test_saved_index_exposes_bounded_repeat_position_and_tolerates_legacy_metadata(study):
    client, factory, run, _ = study
    invalid = [(True, 3), (0, 3), (4, 3), (1, 6), ('2', 3), (2, None)]
    for index, count in [(2, 3), *invalid]:
        with factory() as db:
            row = db.get(AuditRunModel, run)
            metadata = dict(row.reproducibility_metadata)
            metadata.update(formal_repetition_index=index, formal_repetition_count=count)
            row.reproducibility_metadata = metadata
            db.commit()
        response = client.get('/api/v1/research/formal/saved-runs?limit=50')
        assert response.status_code == 200
        item = next(item for item in response.json()['items'] if item['run_id'] == run)
        if (index, count) == (2, 3):
            assert (item['repetition_index'], item['repetition_count']) == (2, 3)
        else:
            assert item['repetition_index'] is None
            assert item['repetition_count'] is None


def test_older_signed_plan_without_new_optional_fields_can_still_be_restored(study):
    from copy import deepcopy
    from sqlalchemy import select
    from app.services.formal_freeze import formal_input_signature
    client, factory, run, _ = study
    omitted = ['development_dataset_fingerprint_sha256', 'distinct_history_check', 'study_design']
    with factory() as db:
        rows = list(db.scalars(select(AuditRunModel)))
        for row in rows:
            metadata = deepcopy(row.reproducibility_metadata)
            for field in omitted:
                metadata['formal_acceptance_protocol'].pop(field, None)
                metadata['formal_matrix_manifest']['acceptance_protocol'].pop(field, None)
            row.reproducibility_metadata = metadata
        db.flush()
        # Simulate a valid historical signature over the historical JSON shape.
        for row in rows:
            row.reproducibility_metadata = {**row.reproducibility_metadata, 'formal_input_sha256': formal_input_signature(db, row)}
        db.commit()
    response = client.get(f'/api/v1/research/formal/{run}/plan')
    assert response.status_code == 200, response.text
    assert response.json()['acceptance_protocol']['study_design'] is None
    with factory() as db:
        assert all(field not in db.get(AuditRunModel, run).reproducibility_metadata['formal_matrix_manifest']['acceptance_protocol'] for field in omitted)
