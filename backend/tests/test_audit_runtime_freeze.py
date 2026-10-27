"""Software drift must stop engines without destroying existing audit evidence."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.main import app
from app.services import runtime_freeze
from test_input_and_relationship_guards import client_for


@pytest.mark.parametrize("stage", ["generate", "regenerate", "execute", "evaluate", "retry"])
def test_software_drift_stops_engine_and_preserves_existing_artifacts(tmp_path, monkeypatch, stage):
    with client_for(tmp_path) as client:
        try:
            cid = client.post('/api/v1/conversations', json={
                'authorised': True, 'messages': [{'role': 'user', 'content': 'I prefer Rust.'}],
            }).json()['conversation_id']
            path = f'/api/v1/conversations/{cid}'
            memories = client.post(path + '/extract', json={'provider': 'rule_based'}).json()
            assert client.post(path + '/confirm-ground-truth', json={
                'confirmed_memory_ids': [m['memory_id'] for m in memories],
            }).status_code == 200
            created = client.post('/api/v1/audits', json={
                'conversation_id': cid, 'target_configuration': 'strong',
                'provider': 'rule_based', 'pipeline_provider': 'rule_based',
                'evaluator_provider': 'rule_based',
            })
            assert created.status_code == 201, created.text
            saved = created.json()['reproducibility']['audit_runtime_signature']
            assert len(saved['source_sha256']) == 64
            assert saved['generator'] and saved['evaluator']
            path = f"/api/v1/audits/{created.json()['run_id']}"
            endpoint = path + '/generate-tests'
            if stage in ('regenerate', 'execute', 'evaluate'):
                generated = client.post(endpoint)
                assert generated.status_code == 200, generated.text
                if stage == 'regenerate':
                    endpoint = path + '/tests/' + generated.json()[0]['test_id'] + '/regenerate'
                else:
                    endpoint = path + '/execute'
                if stage == 'evaluate':
                    assert client.post(endpoint).status_code == 200
                    endpoint = path + '/evaluate'
            if stage == 'retry':
                endpoint = path + '/retry'
            before_run = client.get(path).json()
            before_review = client.get(path + '/test-review').json()
            before_trace = client.get(path + '/target-memory-trace').json()
            monkeypatch.setattr(runtime_freeze, 'audit_runtime_signature',
                                lambda: {**saved, 'source_sha256': 'different-installed-source'})
            recovery = client.get(path + '/retry-plan')
            assert recovery.status_code == 200
            assert not recovery.json()['retryable']
            assert 'Start a new audit' in recovery.json()['resume_blocked_reason']
            blocked = client.post(endpoint)
            assert blocked.status_code == 409, blocked.text
            assert 'Start a new audit' in blocked.json()['detail']
            assert client.get(path).json() == before_run
            assert client.get(path + '/test-review').json() == before_review
            assert client.get(path + '/target-memory-trace').json() == before_trace
            monkeypatch.setattr(runtime_freeze, 'audit_runtime_signature', lambda: saved)
            ready = client.get(path + '/retry-plan').json()
            assert ready['retryable']
            assert ready['resume_blocked_reason'] is None
            resumed = client.post(endpoint)
            if stage == 'regenerate':
                # Runtime recovery succeeds, but a rule generator with only
                # this fact has no distinct replacement to save.
                assert resumed.status_code == 422, resumed.text
                assert 'same question' in resumed.json()['detail']
            else:
                assert resumed.status_code == 200, resumed.text
            if stage == 'evaluate':
                result = client.get(path + '/results')
                assert result.status_code == 200
                assert result.json()['reproducibility']['audit_runtime_signature'] == saved
        finally:
            app.dependency_overrides.clear()


def test_legacy_unknown_snapshot_is_not_invented_and_corruption_is_not_downgraded():
    runtime_freeze.assert_audit_runtime_frozen(SimpleNamespace(reproducibility_metadata={}))
    for value in (None, {}, {'source_sha256': 'invalid'}):
        with pytest.raises(HTTPException) as blocked:
            runtime_freeze.assert_audit_runtime_frozen(SimpleNamespace(
                reproducibility_metadata={'audit_runtime_signature': value}))
        assert blocked.value.status_code == 409
