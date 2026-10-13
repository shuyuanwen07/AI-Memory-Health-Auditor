from app.main import app
from app.api import routes
from app.extraction.llm import PipelineRequestError
from app.test_generator.llm_generator import LLMTestGenerator
from test_input_and_relationship_guards import client_for


def test_failed_candidates_remain_in_history_after_successful_retry(tmp_path,monkeypatch):
    with client_for(tmp_path) as client:
        try:
            cid=client.post('/api/v1/conversations',json={'authorised':True,'messages':[{'role':'user','content':'I am based in Sydney.'}]}).json()['conversation_id']
            memories=client.post(f'/api/v1/conversations/{cid}/extract',json={'provider':'rule_based'}).json()
            client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth',json={'confirmed_memory_ids':[m['memory_id'] for m in memories]})
            run=client.post('/api/v1/audits',json={'conversation_id':cid,'provider':'rule_based','pipeline_provider':'rule_based','evaluator_provider':'rule_based','target_configuration':'strong'}).json()['run_id']
            class Model:
                good=False
                def complete_json(self,**kwargs):
                    from app.database.session import get_db
                    from app.models import AuditRunModel
                    iterator=app.dependency_overrides[get_db]();db=next(iterator)
                    try:
                        pending=db.get(AuditRunModel,run).reproducibility_metadata['generation_observations'][-1]
                        assert pending['status']=='started' and pending['attempts'][-1]['status']=='requesting'
                        assert pending['attempts'][-1]['candidate_count'] is None
                        assert pending['operation_id']
                    finally:iterator.close()
                    return {'tests':[{'dimension':'accuracy','prompt':"What city is recorded as the user's location?" if self.good else 'Is the user based in Sydney?',
                        'expected_behavior':'State that the user is based in Sydney.','supporting_memory_ids':[memories[0]['memory_id']]}]}
            model=Model();generator=LLMTestGenerator(model)
            monkeypatch.setattr(routes,'get_test_generator',lambda *args,**kwargs:generator)
            path=f'/api/v1/audits/{run}'
            failed=client.post(path+'/generate-tests')
            assert failed.status_code==502,failed.text
            first=client.get(path).json()['reproducibility']['generation_observations']
            assert len(first)==1 and not first[0]['saved_suite']
            assert len(first[0]['attempts'])==2 and first[0]['status']=='failed'
            assert first[0]['attempts'][0]['leaked_candidates']==1
            assert client.get(path+'/tests').json()==[]
            model.good=True
            assert client.post(path+'/generate-tests').status_code==200
            history=client.get(path).json()['reproducibility']['generation_observations']
            assert len(history)==2
            assert history[0]==first[0]
            assert history[1]['saved_suite'] and len(history[1]['attempts'])==1
            assert history[1]['attempts'][0]['leaked_candidates']==0
            assert generator.progress_observer is None
            assert client.post(path+'/generate-tests').status_code==200
            assert client.get(path).json()['reproducibility']['generation_observations']==history
        finally:app.dependency_overrides.clear()


def test_request_failure_has_unknown_candidate_checks():
    from test_llm_pipeline import _audit
    from app.schemas import Memory
    class Model:
        def complete_json(self,**kwargs):raise PipelineRequestError('Synthetic unavailable service.')
    generator=LLMTestGenerator(Model())
    try:generator.generate([Memory(memory_id='M1',conversation_id='C',canonical_value='The user is based in Sydney.',status='confirmed')],_audit())
    except PipelineRequestError:pass
    else:raise AssertionError('Request failure must propagate')
    attempt=generator.last_observation['attempts'][0]
    assert attempt['status']=='request_failed'
    assert attempt['candidate_count'] is None and attempt['local_accepted'] is None and attempt['leaked_candidates'] is None
