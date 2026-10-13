"""Regenerating one probe must not request an unrelated full suite."""
from app.api import routes
from app.schemas import TestCase
from app.test_generator.llm_generator import LLMTestGenerator
from test_quality_workflows import client as quality_client, history

client = quality_client


def test_single_llm_replacement_uses_one_question_budget_without_editing_saved_config(client, monkeypatch):
    identity = history(client, '[User] I generally prefer Python.\n[User] The assignment requires Java.\n[User] The backend now uses PostgreSQL.')
    created = client.post('/api/v1/audits', json={'conversation_id':identity,'provider':'rule_based','target_configuration':'strong','test_budget':8})
    assert created.status_code == 201, created.text
    run = created.json()['run_id']
    generated = client.post(f'/api/v1/audits/{run}/generate-tests')
    assert generated.status_code == 200, generated.text
    original = TestCase.model_validate(generated.json()[0])
    note='Ask about the relationship, not general preference alone. Keep answer values out of the question.'
    assert client.patch(f'/api/v1/audits/{run}/tests/{original.test_id}/review',json={'quality_status':'rejected','note':note}).status_code==200
    observed = []
    generator = LLMTestGenerator.__new__(LLMTestGenerator)
    def produce(memories, audit, generation_context=None):
        observed.append((audit.test_budget, generation_context))
        return [original.model_copy(update={'prompt':original.prompt + ' Please be concise.'})]
    generator.generate = produce
    monkeypatch.setattr(routes, 'get_test_generator', lambda *args: generator)
    response = client.post(f'/api/v1/audits/{run}/tests/{original.test_id}/regenerate')
    assert response.status_code == 200, response.text
    assert observed[0][0] == 1
    assert 'Return exactly one test' in observed[0][1]
    assert note in observed[0][1]
    assert 'not in the question or answer choices' in observed[0][1]
    assert client.get(f'/api/v1/audits/{run}').json()['test_budget'] == 8
    assert response.json()['quality_status'] == 'pending'
