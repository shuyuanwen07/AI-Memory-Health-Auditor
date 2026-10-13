from sqlalchemy import select
import pytest
from app.main import app
from app.api import routes
from app.database.session import get_db
from app.models import EvaluationResultModel, MemoryModel, TestCaseModel, TargetResponseModel
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from test_input_and_relationship_guards import client_for


@pytest.mark.parametrize('changed_input', ['reference', 'copied_question', 'copied_answer'])
def test_reference_change_during_judge_call_cannot_be_saved_as_completed(tmp_path, monkeypatch, changed_input):
    with client_for(tmp_path) as client:
        try:
            cid=client.post('/api/v1/conversations',json={'authorised':True,
                'messages':[{'role':'user','content':'I prefer Rust. I am based in Sydney.'}]}).json()['conversation_id']
            memories=client.post(f'/api/v1/conversations/{cid}/extract',json={'provider':'rule_based'}).json()
            client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth',json={'confirmed_memory_ids':[m['memory_id'] for m in memories]})
            source=client.post('/api/v1/audits',json={'conversation_id':cid,'provider':'rule_based',
                'pipeline_provider':'rule_based','evaluator_provider':'rule_based','target_configuration':'strong'}).json()['run_id']
            path=f'/api/v1/audits/{source}'
            assert len(client.post(path+'/generate-tests').json()) >= 2
            client.post(path+'/execute');client.post(path+'/evaluate')
            prepared=client.post(path+'/reassessment').json()['run_id']
            original=RuleBasedBehaviourEvaluator.evaluate
            calls=[]
            def changing_reference(self,*args):
                calls.append(args[0].test_id)
                result=original(self,*args)
                iterator=app.dependency_overrides[get_db]()
                db=next(iterator)
                try:
                    if changed_input == 'reference':
                        memory=db.get(MemoryModel,memories[0]['memory_id'])
                        memory.canonical_value='A changed reference during evaluation.'
                    elif changed_input == 'copied_question':
                        question=db.scalar(select(TestCaseModel).where(TestCaseModel.run_id==prepared))
                        question.prompt='A different question during evaluation.'
                    else:
                        answer=db.scalar(select(TargetResponseModel).where(TargetResponseModel.run_id==prepared))
                        answer.response_text='An altered saved answer during evaluation.'
                    db.commit()
                finally:
                    iterator.close()
                return result
            monkeypatch.setattr(RuleBasedBehaviourEvaluator,'evaluate',changing_reference)
            def no_target(*args,**kwargs):
                raise AssertionError('Reassessment cannot execute the target')
            monkeypatch.setattr(routes,'get_target_system_adapter',no_target)
            response=client.post(f'/api/v1/audits/{prepared}/evaluate')
            assert response.status_code==409,response.text
            expected = 'reference data changed' if changed_input == 'reference' else 'in this assessment changed'
            assert expected in response.json()['detail']
            assert len(calls)==1
            assert client.get(f'/api/v1/audits/{prepared}').json()['status']=='FAILED'
            iterator=app.dependency_overrides[get_db]()
            db=next(iterator)
            try:
                assert not db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id==prepared)).all()
            finally:
                iterator.close()
        finally:
            app.dependency_overrides.clear()
