"""Auditor configuration and evidence integrity, independent of target repairs."""
from app.database.session import get_db
from app.main import app
from test_input_and_relationship_guards import client_for


def test_explicit_extractor_overrides_unavailable_server_default_and_freezes_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPELINE_PROVIDER', 'openrouter')
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    with client_for(tmp_path) as client:
        try:
            cid = client.post('/api/v1/conversations', json={'authorised': True, 'messages': [{'role': 'user', 'content': 'I am based in Sydney.'}]}).json()['conversation_id']
            endpoint = f'/api/v1/conversations/{cid}'
            invalid = client.post(endpoint + '/extract', json={'provider': 'ollama'})
            assert invalid.status_code == 422
            memories = client.post(endpoint + '/extract', json={'provider': 'rule_based'})
            assert memories.status_code == 200
            mid = memories.json()[0]['memory_id']
            assert client.post(endpoint + '/confirm-ground-truth', json={'confirmed_memory_ids': [mid]}).status_code == 200
            experiment = client.post('/api/v1/experiments', json={'conversation_id': cid, 'label': 'Integrity check', 'test_suite_configuration': {'evaluator_provider': 'rule_based', 'evaluator_model': 'obsolete-v1'}})
            from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
            assert experiment.json()['test_suite_configuration']['evaluator_model'] == RuleBasedBehaviourEvaluator.VERSION
            audit = client.post('/api/v1/audits', json={'conversation_id': cid, 'target_configuration': 'weak', 'provider': 'rule_based', 'pipeline_provider': 'rule_based', 'evaluator_provider': 'rule_based'})
            assert audit.status_code == 201, audit.text
            assert client.patch(f'/api/v1/memories/{mid}', json={'canonical_value': 'I am based in Oslo.'}).status_code == 409
            assert client.delete(f'/api/v1/memories/{mid}').status_code == 409
            assert client.post('/api/v1/memories', json={'conversation_id': cid, 'canonical_value': 'Other answer'}).status_code == 409
            assert client.post(endpoint + '/confirm-ground-truth', json={'confirmed_memory_ids': [mid]}).status_code == 409
            assert client.get(endpoint + '/memories').json()[0]['canonical_value'] == memories.json()[0]['canonical_value']
        finally:
            app.dependency_overrides.pop(get_db, None)


def test_local_semantic_evaluator_freezes_separately_from_rule_pipeline(tmp_path, monkeypatch):
    from app.evaluator.llm_judge import LLMBehaviourEvaluator

    monkeypatch.setattr(LLMBehaviourEvaluator, '_post', staticmethod(lambda *_: {
        'done': True, 'message': {'content': '{"passed":null,"reason":"Needs independent review","evidence_memory_ids":[]}'},
    }))
    with client_for(tmp_path) as client:
        try:
            cid = client.post('/api/v1/conversations', json={'authorised': True, 'messages': [{'role': 'user', 'content': 'I prefer Python.'}]}).json()['conversation_id']
            endpoint = f'/api/v1/conversations/{cid}'
            mid = client.post(endpoint + '/extract', json={'provider': 'rule_based'}).json()[0]['memory_id']
            client.post(endpoint + '/confirm-ground-truth', json={'confirmed_memory_ids': [mid]})
            suite = {'pipeline_provider': 'rule_based', 'evaluator_provider': 'ollama', 'evaluator_model': 'qwen3:1.7b'}
            experiment = client.post('/api/v1/experiments', json={'conversation_id': cid, 'label': 'Local semantic contract', 'test_suite_configuration': suite})
            assert experiment.status_code == 201, experiment.text
            assert experiment.json()['test_suite_configuration']['evaluator_provider'] == 'ollama'
            audit = client.post('/api/v1/audits', json={'conversation_id': cid, 'experiment_id': experiment.json()['experiment_id'], 'target_configuration': 'strong', 'provider': 'rule_based'})
            assert audit.status_code == 201, audit.text
            assert audit.json()['evaluator_provider'] == 'ollama'
            assert audit.json()['evaluator_model'] == 'qwen3:1.7b'
            assert audit.json()['pipeline_provider'] == 'rule_based'
            endpoint = f"/api/v1/audits/{audit.json()['run_id']}"
            assert client.post(endpoint + '/generate-tests').status_code == 200
            assert client.post(endpoint + '/execute').status_code == 200
            evaluated = client.post(endpoint + '/evaluate')
            assert evaluated.status_code == 200, evaluated.text
            assert evaluated.json()[0]['judge_execution']['verdict_status'] == 'abstained'
            restored = client.get(endpoint + '/evaluation-review').json()
            assert restored[0]['automated']['judge_execution'] == evaluated.json()[0]['judge_execution']
            blind = client.get(endpoint + '/blind-review').json()
            assert list(blind[0]['automated']) == ['evaluation_id']
        finally:
            app.dependency_overrides.pop(get_db, None)
