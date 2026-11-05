pytest_plugins = ("test_quality_workflows",)

from app.services.maple_demo_cache import _cache


def test_cached_maple_questions_keep_review_and_source_guards(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-test-key')
    import app.api.routes as routes
    monkeypatch.setattr(routes, 'get_memory_extractor', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('unexpected model call')))
    source = client.post('/api/v1/conversations', json={'authorised': True, 'source_origin': 'synthetic',
        'messages': _cache()['messages']})
    assert source.status_code == 201, source.text
    cid = source.json()['conversation_id']
    extracted = client.post(f'/api/v1/conversations/{cid}/extract', json={'provider':'openai', 'model':'gpt-6-astra'})
    assert extracted.status_code == 200, extracted.text
    memories = extracted.json()
    assert len(memories) == 2 and all(m['status'] == 'candidate' for m in memories)
    confirmed = client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth',
                            json={'confirmed_memory_ids':[m['memory_id'] for m in memories]})
    assert confirmed.status_code == 200, confirmed.text
    group = client.post('/api/v1/experiments', json={'conversation_id':cid,'label':'synthetic cache fixture',
        'test_suite_configuration':{'test_budget':8,'pipeline_provider':'openai','pipeline_model':'gpt-6-astra',
        'coverage_policy':'evidence_supported_only_v1','evaluator_provider':'rule_based'}})
    assert group.status_code == 201, group.text
    audit = client.post('/api/v1/audits', json={'conversation_id':cid, 'experiment_id':group.json()['experiment_id'],
        'target_configuration':'weak','provider':'rule_based'})
    assert audit.status_code == 201, audit.text
    rid = audit.json()['run_id']
    generated = client.post(f'/api/v1/audits/{rid}/generate-tests')
    assert generated.status_code == 200, generated.text
    tests = generated.json()
    assert len(tests) == 1 and tests[0]['dimension'] == 'conflict_resolution'
    assert tests[0]['quality_status'] == 'pending'
    assert client.post(f'/api/v1/audits/{rid}/execute').status_code == 409
    accepted = client.patch(f"/api/v1/audits/{rid}/tests/{tests[0]['test_id']}/review",
                            json={'quality_status':'accepted', 'note':'Synthetic fixture review'})
    assert accepted.status_code == 200, accepted.text
    execution = client.post(f'/api/v1/audits/{rid}/execute')
    assert execution.status_code == 200, execution.text
    evaluation = client.post(f'/api/v1/audits/{rid}/evaluate')
    assert evaluation.status_code == 200, evaluation.text
    report = client.get(f'/api/v1/audits/{rid}/results')
    assert report.status_code == 200, report.text
    assert report.json()['tests_total'] == 1
