"""Review evidence must preserve complete original context, ordered and isolated."""
from app.main import app
from test_input_and_relationship_guards import client_for


def test_source_history_preserves_original_sequence_and_excludes_unrelated_conversations(tmp_path):
    with client_for(tmp_path) as client:
        try:
            messages = [
                {'role': 'user', 'content': 'I prefer Rust.', 'timestamp': '2026-01-03T00:00:00Z'},
                {'role': 'assistant', 'content': 'Would Python suit this project?', 'timestamp': '2026-01-01T00:00:00Z'},
                {'role': 'user', 'content': 'Keep Rust for personal tools.', 'timestamp': '2026-01-02T00:00:00Z'},
            ]
            created = client.post('/api/v1/conversations', json={'authorised': True, 'messages': messages})
            assert created.status_code == 201, created.text
            cid = created.json()['conversation_id']
            assert client.post('/api/v1/conversations', json={'authorised': True, 'messages': [
                {'role': 'user', 'content': 'Unrelated synthetic private statement.'},
            ]}).status_code == 201
            path = f'/api/v1/conversations/{cid}'
            memories = client.post(path + '/extract', json={'provider': 'rule_based'}).json()
            assert client.post(path + '/confirm-ground-truth', json={
                'confirmed_memory_ids': [m['memory_id'] for m in memories],
            }).status_code == 200
            audit = client.post('/api/v1/audits', json={
                'conversation_id': cid, 'target_configuration': 'strong', 'provider': 'rule_based',
                'pipeline_provider': 'rule_based', 'evaluator_provider': 'rule_based',
            })
            assert audit.status_code == 201, audit.text
            path = '/api/v1/audits/' + audit.json()['run_id']
            before = client.get(path).json()
            response = client.get(path + '/source-history')
            assert response.status_code == 200
            assert [m['content'] for m in response.json()] == [m['content'] for m in messages]
            assert [m['role'] for m in response.json()] == ['user', 'assistant', 'user']
            assert all(set(m) == {'role', 'content', 'timestamp'} for m in response.json())
            assert 'Unrelated' not in response.text
            assert client.get(path).json() == before
            assert client.get('/api/v1/audits/unknown/source-history').status_code == 404
        finally:
            app.dependency_overrides.clear()
