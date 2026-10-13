import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import service


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('TARGET_STORAGE', str(tmp_path / 'memory.sqlite'))
    monkeypatch.setattr(service, 'generate', lambda payload, prompt, selected: '|'.join(selected) or 'No remembered evidence.')
    return TestClient(service.app)


def payload(namespace='one'):
    return {'namespace': namespace, 'messages': [{'message_id': 'm1', 'role': 'user', 'content': 'Oak project uses Redis.', 'timestamp': '2026-01-01T00:00:00Z'}], 'target': {'provider': 'ollama', 'model': 'qwen3:1.7b', 'temperature': 0}, 'memory_profile': {'max_retrieved_records': 1, 'context_character_budget': 100}, 'memory_strategy': 'full_context'}


def test_namespace_and_question_idempotency(client):
    data = payload()
    assert client.post('/ingest', json=data).status_code == 200
    assert client.post('/ingest', json=data).status_code == 200
    changed = {**data, 'memory_strategy': 'no_memory'}
    assert client.post('/ingest', json=changed).status_code == 409
    question = {'namespace': 'one', 'request_id': 'q1', 'prompt': 'What database does Oak project use?'}
    first = client.post('/answer', json=question)
    assert first.status_code == 200
    assert 'Redis' in first.json()['response_text']
    assert client.post('/answer', json=question).json() == first.json()
    assert client.post('/answer', json={**question, 'prompt': 'Another question'}).status_code == 409
    assert client.post('/answer', json={**question, 'namespace': 'two'}).status_code == 404


def test_no_reference_answer_contract_and_memory_budget(client):
    data = payload()
    assert client.post('/ingest', json={**data, 'expected_behaviour': 'Redis'}).status_code == 422
    assert client.post('/ingest', json=data).status_code == 200
    assert client.post('/answer', json={'namespace': 'one', 'request_id': 'q', 'prompt': 'Question', 'supporting_memory_ids': ['oracle']}).status_code == 422
    data['memory_strategy'] = 'no_memory'
    data['namespace'] = 'empty'
    assert service.memories(data, 'Question') == []
    data['memory_strategy'] = 'full_context'
    data['memory_profile']['context_character_budget'] = 1
    assert service.memories(data, 'Question') == []


@pytest.mark.parametrize('field,value', [('max_retrieved_records', -1), ('context_character_budget', 0), ('additional_instructions', 'x' * 4001), ('expected_answer', 'Redis')])
def test_nested_profile_rejects_invalid_or_reference_fields(client, field, value):
    data = payload()
    data['memory_profile'][field] = value
    assert client.post('/ingest', json=data).status_code == 422


def test_unknown_provider_and_strategy_are_rejected(client):
    data = payload()
    data['target']['provider'] = 'unknown'
    assert client.post('/ingest', json=data).status_code == 422
    data = payload()
    data['memory_strategy'] = 'unknown'
    assert client.post('/ingest', json=data).status_code == 422
