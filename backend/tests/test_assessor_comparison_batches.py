from app.main import app
from app.api import routes
from test_input_and_relationship_guards import client_for


def test_durable_assessor_plan_recovery_and_same_answer_results(tmp_path, monkeypatch):
    import app.services.reassessment as reassessment
    import app.services.assessor_comparison as batches
    with client_for(tmp_path) as client:
        try:
            cid = client.post('/api/v1/conversations',json={'authorised':True,'messages':[{'role':'user','content':'I prefer Rust.'}]}).json()['conversation_id']
            memories = client.post(f'/api/v1/conversations/{cid}/extract',json={'provider':'rule_based'}).json()
            client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth',json={'confirmed_memory_ids':[m['memory_id'] for m in memories]})
            source = client.post('/api/v1/audits',json={'conversation_id':cid,'provider':'rule_based','pipeline_provider':'rule_based','evaluator_provider':'rule_based','target_configuration':'strong'}).json()['run_id']
            path = f'/api/v1/audits/{source}'
            client.post(path+'/generate-tests');client.post(path+'/execute');client.post(path+'/evaluate')
            original = client.get(path+'/evaluation-review').json()
            request = {'creation_request_key':'batch-fixture','source_run_id':source,
                'assessors':[{'evaluator_provider':'rule_based'},
                             {'evaluator_provider':'openrouter','evaluator_model':'openai/fixed-test'}]}
            response = client.post('/api/v1/assessor-comparisons',json=request)
            assert response.status_code == 201,response.text
            batch = response.json()['comparison_id']; url = f'/api/v1/assessor-comparisons/{batch}'
            assert client.post('/api/v1/assessor-comparisons',json=request).json()['comparison_id'] == batch
            changed = {**request,'assessors':[{'evaluator_provider':'rule_based'}, {'evaluator_provider':'openrouter','evaluator_model':'anthropic/fixed-test'}]}
            assert client.post('/api/v1/assessor-comparisons',json=changed).status_code == 409
            monkeypatch.setattr(reassessment,'configured',lambda provider: provider == 'rule_based')
            assert client.post(url+'/prepare').status_code == 422
            partial = client.get(url).json()
            first = partial['entries'][0]['run']['run_id']
            assert partial['entries'][1]['run'] is None
            assert first != source
            monkeypatch.setattr(reassessment,'configured',lambda provider: True)
            prepared = client.post(url+'/prepare').json()
            assert prepared['entries'][0]['run']['run_id'] == first
            assert all(entry['run'] for entry in prepared['entries'])
            assert client.post(url+'/prepare').json() == prepared
            def no_target(*args, **kwargs):
                raise AssertionError('Batch assessor comparison must not execute the target')
            monkeypatch.setattr(routes,'get_target_system_adapter',no_target)
            for entry in prepared['entries']:
                assert client.post(f"/api/v1/audits/{entry['run']['run_id']}/execute").status_code == 409
            assert client.post(f'/api/v1/audits/{first}/evaluate').status_code == 200
            restored = client.get('/api/v1/assessor-comparisons').json()[0]
            assert restored['entries'][0]['result']['tests_passed'] == 1
            assert restored['entries'][1]['result'] is None
            assert client.get(path+'/evaluation-review').json() == original
            # A changed reference must not reach any selected judge. Old
            # results remain readable and are no longer a controlled chart.
            from app.database.session import get_db
            from app.models import AssessorComparisonModel, MemoryModel, TargetResponseModel
            from sqlalchemy import select
            iterator = app.dependency_overrides[get_db]()
            db = next(iterator)
            try:
                memory = db.get(MemoryModel, memories[0]['memory_id'])
                old_value = memory.canonical_value
                memory.canonical_value = 'The user prefers Go.'
                db.commit()
                assert client.get(url).json()['inputs_match'] is False
                assert client.post(url+'/prepare').status_code == 409
                other = prepared['entries'][1]['run']['run_id']
                assert client.post(f'/api/v1/audits/{other}/evaluate').status_code == 409
                memory.canonical_value = old_value
                db.commit()
                assert client.get(url).json()['inputs_match'] is True
                answer = db.scalar(select(TargetResponseModel).where(TargetResponseModel.run_id == source))
                old_answer = answer.response_text
                answer.response_text = 'Altered saved answer.'
                db.commit()
                assert client.get(url).json()['inputs_match'] is False
                assert client.post(f'/api/v1/audits/{other}/evaluate').status_code == 409
                answer.response_text = old_answer
                db.commit()
                copied = db.scalar(select(TargetResponseModel).where(TargetResponseModel.run_id == first))
                old_copy = copied.response_text
                copied.response_text = 'An altered comparison answer.'
                db.commit()
                assert client.get(url).json()['inputs_match'] is False
                assert client.get(url).json()['entries'][0]['result'] is not None
                assert client.post(url+'/prepare').status_code == 409
                copied.response_text = old_copy
                db.commit()
                assert client.get(url).json()['inputs_match'] is True
                record = db.get(AssessorComparisonModel, batch)
                binding = record.input_fingerprint
                record.input_fingerprint = None
                db.commit()
                assert client.get(url).json()['inputs_match'] is False
                assert client.post(url+'/prepare').status_code == 409
                record.input_fingerprint = binding
                db.commit()
            finally:
                iterator.close()
            monkeypatch.setattr(batches,'audit_runtime_signature',lambda:{'protocol':'changed'})
            assert client.post(url+'/prepare').status_code == 409
            assert client.get(url).status_code == 200
            for model in ['openai/gpt-latest:online','openrouter/auto:online']:
                invalid = {**request,'creation_request_key':'invalid','assessors':[{'evaluator_provider':'rule_based'}, {'evaluator_provider':'openrouter','evaluator_model':model}]}
                assert client.post('/api/v1/assessor-comparisons',json=invalid).status_code == 422
            duplicate = {**request,'creation_request_key':'duplicate','assessors':[{'evaluator_provider':'rule_based'},{'evaluator_provider':'rule_based'}]}
            assert client.post('/api/v1/assessor-comparisons',json=duplicate).status_code == 422
        finally:
            app.dependency_overrides.clear()
