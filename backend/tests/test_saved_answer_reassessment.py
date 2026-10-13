from app.main import app
from app.api import routes
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from test_input_and_relationship_guards import client_for


def test_selected_assessors_get_distinct_idempotent_runs_with_exact_saved_answers(tmp_path, monkeypatch):
    import app.services.reassessment as service
    with client_for(tmp_path) as client:
        try:
            cid = client.post('/api/v1/conversations', json={'authorised':True,
                'messages':[{'role':'user','content':'I prefer Rust.'}]}).json()['conversation_id']
            memories = client.post(f'/api/v1/conversations/{cid}/extract', json={'provider':'rule_based'}).json()
            client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth',
                json={'confirmed_memory_ids':[m['memory_id'] for m in memories]})
            source = client.post('/api/v1/audits', json={'conversation_id':cid,'provider':'rule_based',
                'pipeline_provider':'rule_based','evaluator_provider':'rule_based','target_configuration':'strong'}).json()['run_id']
            path = f'/api/v1/audits/{source}'
            client.post(path+'/generate-tests'); client.post(path+'/execute'); client.post(path+'/evaluate')
            before = client.get(path+'/evaluation-review').json()
            original_result = client.get(path+'/results').json()
            monkeypatch.setattr(service, 'configured', lambda provider: True)
            def no_target(*args, **kwargs):
                raise AssertionError('Assessor comparison cannot call the target again')
            monkeypatch.setattr(routes,'get_target_system_adapter',no_target)
            selections = [{'evaluator_provider':'openrouter','evaluator_model':'openai/fixed-gpt-test'},
                          {'evaluator_provider':'openrouter','evaluator_model':'anthropic/fixed-claude-test'}]
            prepared = []
            for choice in selections:
                response = client.post(path+'/reassessment',json=choice)
                assert response.status_code == 201,response.text
                new = response.json()
                assert new['evaluator_model'] == choice['evaluator_model']
                assert new['evaluator_provider'] == 'openrouter'
                assert new['status'] == 'TESTS_EXECUTED'
                assert client.post(path+'/reassessment',json=choice).json()['run_id'] == new['run_id']
                assert client.post(f"/api/v1/audits/{new['run_id']}/execute").status_code == 409
                # Inspect saved test/answer rows before any paid reviewer call.
                from app.database.session import get_db
                from app.models import TargetResponseModel, TestCaseModel
                from sqlalchemy import select
                iterator = app.dependency_overrides[get_db]()
                db = next(iterator)
                try:
                    tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == new['run_id'])).all()
                    answers = db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == new['run_id'])).all()
                    assert len(tests) == len(before) == len(answers)
                    originals = {item['test']['test_id']:item for item in before}
                    for test in tests:
                        answer = next(answer for answer in answers if answer.test_id == test.id)
                        item = originals[test.suite_test_id]
                        assert test.prompt == item['test']['prompt']
                        assert test.expected_behavior == item['test']['expected_behavior']
                        assert answer.response_text == item['response']['response_text']
                        assert answer.execution_metadata['request_attempts'] == 0
                        assert answer.execution_metadata['shared_source_response_id'] == item['response']['response_id']
                finally:
                    iterator.close()
                prepared.append(new['run_id'])
            assert prepared[0] != prepared[1]
            assert client.post(f'/api/v1/audits/{prepared[0]}/reassessment',json=selections[1]).json()['run_id'] == prepared[1]
            assert client.get(path+'/evaluation-review').json() == before
            assert client.get(path+'/results').json() == original_result
            monkeypatch.setattr(service, 'configured', lambda provider: False)
            unavailable = client.post(path+'/reassessment',json=selections[0])
            assert unavailable.status_code == 422
            assert 'unavailable' in unavailable.json()['detail']
            for invalid in [
                {'evaluator_provider':'unknown','evaluator_model':'fixed'},
                {'evaluator_provider':'openrouter','evaluator_model':'  '},
                {'evaluator_provider':'openrouter','evaluator_model':'openai/gpt-sol-latest'},
                {'evaluator_provider':'openrouter','evaluator_model':'openrouter/auto'},
                {'evaluator_provider':'openrouter','evaluator_model':'fixed','temperature':1},
            ]:
                assert client.post(path+'/reassessment',json=invalid).status_code == 422
        finally:
            app.dependency_overrides.clear()


def test_reassessment_scores_exact_answers_without_changing_original_or_recalling_target(tmp_path, monkeypatch):
    with client_for(tmp_path) as client:
        try:
            cid=client.post('/api/v1/conversations',json={'authorised':True,'messages':[{'role':'user','content':'I prefer Rust.'}]}).json()['conversation_id']
            mems=client.post(f'/api/v1/conversations/{cid}/extract',json={'provider':'rule_based'}).json()
            client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth',json={'confirmed_memory_ids':[m['memory_id'] for m in mems]})
            source=client.post('/api/v1/audits',json={'conversation_id':cid,'provider':'rule_based','pipeline_provider':'rule_based','evaluator_provider':'rule_based','target_configuration':'strong'}).json()['run_id']
            path=f'/api/v1/audits/{source}'
            assert client.post(path+'/reassessment').status_code==409
            client.post(path+'/generate-tests');client.post(path+'/execute')
            original=RuleBasedBehaviourEvaluator.evaluate
            def old_assessment(self,*args):
                return original(self,*args).model_copy(update={'passed':False,'reason':'Synthetic historical false alarm.'})
            monkeypatch.setattr(RuleBasedBehaviourEvaluator,'evaluate',old_assessment)
            assert client.post(path+'/evaluate').status_code==200
            monkeypatch.setattr(RuleBasedBehaviourEvaluator,'evaluate',original)
            eid=client.get(path+'/evaluation-review').json()[0]['automated']['evaluation_id']
            assert client.patch(path+'/evaluations/'+eid+'/review',json={'human_passed':True,'reviewer_label':'Synthetic fixture reference','review_role':'reference'}).status_code==200
            before=client.get(path+'/evaluation-review').json()
            old_result=client.get(path+'/results').json()
            def no_target(*args,**kwargs):
                raise AssertionError('Reassessment must not execute the target')
            monkeypatch.setattr(routes,'get_target_system_adapter',no_target)
            prepared=client.post(path+'/reassessment')
            assert prepared.status_code==201,prepared.text
            new=prepared.json()['run_id'];dest=f'/api/v1/audits/{new}'
            assert prepared.json()['status']=='TESTS_EXECUTED'
            assert prepared.json()['reproducibility']['assessment_source_run_id']==source
            assert client.post(path+'/reassessment').json()['run_id']==new
            assert client.post(dest+'/execute').status_code==409
            assert client.post(dest+'/evaluate').status_code==200
            after=client.get(dest+'/evaluation-review').json()
            assert after[0]['automated']['passed'] is True
            assert after[0]['response']['response_text']==before[0]['response']['response_text']
            assert after[0]['response']['execution_metadata']['request_attempts']==0
            assert after[0]['response']['execution_metadata']['shared_source_response_id']==before[0]['response']['response_id']
            assert after[0]['human_reviews']==[]
            assert client.get(path+'/evaluation-review').json()==before
            assert client.get(path+'/results').json()==old_result
            comparison=client.get(f'/api/v1/audit-comparisons?before={source}&after={new}')
            assert comparison.status_code==200,comparison.text
            assert 'not an improvement in the target model' in comparison.text
            assert comparison.json()['answer_provenance'] == 'same_saved_answers'
            assert client.post(path+'/reassessment').json()['run_id']==new
            assert client.post(dest+'/reassessment').json()['run_id']==new
            monkeypatch.setattr(RuleBasedBehaviourEvaluator,'VERSION','rule-based-reassessment-test-next')
            next_version=client.post(path+'/reassessment')
            assert next_version.status_code==201
            assert next_version.json()['run_id']!=new
            assert client.post('/api/v1/audits/unknown/reassessment').status_code==404
        finally:
            app.dependency_overrides.clear()


def test_reassessment_preserves_shared_suite_identity_across_original_conditions(tmp_path, monkeypatch):
    from app.database.session import get_db
    from app.models import TestCaseModel
    with client_for(tmp_path) as client:
        try:
            cid = client.post('/api/v1/conversations', json={'authorised':True, 'messages':[{'role':'user','content':'I prefer Rust.'}]}).json()['conversation_id']
            memories = client.post(f'/api/v1/conversations/{cid}/extract', json={'provider':'rule_based'}).json()
            client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth', json={'confirmed_memory_ids':[m['memory_id'] for m in memories]})
            originals = []
            for _ in range(2):
                run = client.post('/api/v1/audits', json={'conversation_id':cid, 'provider':'rule_based', 'pipeline_provider':'rule_based', 'evaluator_provider':'rule_based', 'target_configuration':'strong', 'test_budget':1}).json()['run_id']
                path = f'/api/v1/audits/{run}'
                generated = client.post(path+'/generate-tests').json()
                # Reproduce distinct condition test instances with one frozen suite identity.
                db_iterator = app.dependency_overrides[get_db]()
                db = next(db_iterator)
                try:
                    db.get(TestCaseModel, generated[0]['test_id']).suite_test_id = 'FROZEN-SHARED-QUESTION'
                    db.commit()
                finally:
                    db_iterator.close()
                client.post(path+'/execute'); client.post(path+'/evaluate')
                originals.append(run)
            def no_target(*args, **kwargs):
                raise AssertionError('No new target calls are allowed during reassessment')
            monkeypatch.setattr(routes, 'get_target_system_adapter', no_target)
            assessed = []
            for run in originals:
                new = client.post(f'/api/v1/audits/{run}/reassessment').json()['run_id']
                assert client.post(f'/api/v1/audits/{new}/evaluate').status_code == 200
                assessed.append(new)
            comparison = client.get(f'/api/v1/audit-comparisons?before={assessed[0]}&after={assessed[1]}').json()
            assert comparison['answer_provenance'] == 'different_saved_executions'
            assert comparison['shared_question_count'] == 1
            assert comparison['comparable_decided_question_count'] == 1
            assert comparison['paired_tests'][0]['suite_test_id'] == 'FROZEN-SHARED-QUESTION'
        finally:
            app.dependency_overrides.clear()
