from sqlalchemy import select
from app.main import app
from app.api import routes
from app.database.session import get_db
from app.models import AuditRunModel, MemoryModel, TestCaseModel
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from test_input_and_relationship_guards import client_for


def test_generator_variants_preserve_controls_and_do_not_share_different_questions(tmp_path,monkeypatch):
    import app.services.generator_comparison as service
    with client_for(tmp_path) as client:
        try:
            cid=client.post('/api/v1/conversations',json={'authorised':True,'messages':[{'role':'user','content':'I prefer Rust.'}]}).json()['conversation_id']
            memories=client.post(f'/api/v1/conversations/{cid}/extract',json={'provider':'rule_based'}).json()
            client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth',json={'confirmed_memory_ids':[m['memory_id'] for m in memories]})
            source=client.post('/api/v1/audits',json={'conversation_id':cid,'provider':'rule_based','pipeline_provider':'rule_based',
                'semantic_review_provider':'openrouter','semantic_review_model':'openai/fixed-reviewer',
                'evaluator_provider':'rule_based','target_configuration':'strong','target_memory_writer':'rule_based'}).json()['run_id']
            path=f'/api/v1/audits/{source}'
            client.post(path+'/generate-tests');client.post(path+'/execute');client.post(path+'/evaluate')
            original=client.get(path).json()
            request={'creation_request_key':'generator_fixture_0001','source_run_id':source,
                'generators':[{'provider':'rule_based'},{'provider':'openrouter','model':'openai/fixed-generator'}]}
            created=client.post('/api/v1/generator-comparisons',json=request)
            assert created.status_code==201,created.text
            plan=created.json()['comparison_id'];url=f'/api/v1/generator-comparisons/{plan}'
            assert client.post('/api/v1/generator-comparisons',json=request).json()['comparison_id']==plan
            changed={**request,'generators':[{'provider':'rule_based'},{'provider':'openrouter','model':'anthropic/fixed-generator'}]}
            assert client.post('/api/v1/generator-comparisons',json=changed).status_code==409
            monkeypatch.setattr(service,'configured',lambda provider:provider=='rule_based')
            assert client.post(url+'/prepare').status_code==422
            first=client.get(url).json()['entries'][0]['run']['run_id']
            monkeypatch.setattr(service,'configured',lambda _:True)
            prepared=client.post(url+'/prepare').json()
            assert prepared['entries'][0]['run']['run_id']==first
            assert client.post(url+'/prepare').json()==prepared
            ids=[entry['run']['run_id'] for entry in prepared['entries']]
            assert len(set(ids))==2 and source not in ids
            for entry in prepared['entries']:
                run=entry['run']
                for field in ['conversation_id','provider','model','temperature','random_seed','test_budget','memory_strategy',
                    'memory_maintenance_policy','target_memory_capacity','target_memory_writer','target_system_adapter']:
                    assert run[field]==original[field]
                assert run['experiment_id'] is None and run['evaluator_model']==RuleBasedBehaviourEvaluator.VERSION
                assert entry['quality']['accepted_percentage'] is None
                assert not entry['quality']['initial_candidates_measured']
            tests=client.post(f'/api/v1/audits/{first}/generate-tests')
            assert tests.status_code==200,tests.text
            summary=client.get(url).json()['entries'][0]['quality']
            assert summary['accepted']==1 and summary['dimensions']['accuracy']==1
            iterator=app.dependency_overrides[get_db]();db=next(iterator)
            try:
                assert db.get(AuditRunModel,ids[1]).pipeline_model=='openai/fixed-generator'
                assert not db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==ids[1])).all()
                db.get(MemoryModel,memories[0]['memory_id']).canonical_value='Changed reference.'
                db.commit()
            finally:iterator.close()
            assert client.get(url).json()['inputs_match'] is False
            assert client.post(url+'/prepare').status_code==409
            def no_target(*_,**__):raise AssertionError('Changed reference cannot reach target execution')
            monkeypatch.setattr(routes,'get_target_system_adapter',no_target)
            assert client.post(f'/api/v1/audits/{first}/execute').status_code==409
            question_id=tests.json()[0]['test_id']
            assert client.post(f'/api/v1/audits/{first}/tests/{question_id}/regenerate').status_code==409
            assert client.patch(f'/api/v1/audits/{first}/tests/{question_id}/review',json={'quality_status':'accepted'}).status_code==409
            assert client.post(f'/api/v1/audits/{ids[1]}/generate-tests').status_code==409
            assert client.get(path).json()==original
            iterator=app.dependency_overrides[get_db]();db=next(iterator)
            try:
                db.get(AuditRunModel,source).target_memory_writer='llm_structured';db.commit()
            finally:iterator.close()
            assert client.post('/api/v1/generator-comparisons',json={**request,'creation_request_key':'generator_fixture_0002'}).status_code==422
        finally:app.dependency_overrides.clear()
