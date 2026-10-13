from sqlalchemy import select
from app.main import app
from app.database.session import get_db
from app.models import AssessorComparisonModel, GeneratorComparisonModel
from test_input_and_relationship_guards import client_for


def test_export_and_confirmed_erasure_include_assessor_and_generator_plans(tmp_path):
    with client_for(tmp_path) as client:
        try:
            cid=client.post('/api/v1/conversations',json={'authorised':True,'messages':[{'role':'user','content':'I prefer Rust.'}]}).json()['conversation_id']
            memories=client.post(f'/api/v1/conversations/{cid}/extract',json={'provider':'rule_based'}).json()
            client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth',json={'confirmed_memory_ids':[m['memory_id'] for m in memories]})
            source=client.post('/api/v1/audits',json={'conversation_id':cid,'provider':'rule_based','pipeline_provider':'rule_based',
                'evaluator_provider':'rule_based','target_configuration':'strong','target_memory_writer':'rule_based'}).json()['run_id']
            path=f'/api/v1/audits/{source}'
            client.post(path+'/generate-tests');client.post(path+'/execute');client.post(path+'/evaluate')
            assessor=client.post('/api/v1/assessor-comparisons',json={'creation_request_key':'assessor_lifecycle','source_run_id':source,
                'assessors':[{'evaluator_provider':'rule_based'},{'evaluator_provider':'openrouter','evaluator_model':'fixed-model'}]}).json()['comparison_id']
            generator=client.post('/api/v1/generator-comparisons',json={'creation_request_key':'generator_lifecycle_01','source_run_id':source,
                'generators':[{'provider':'rule_based'},{'provider':'openrouter','model':'fixed-model'}]}).json()['comparison_id']
            exported=client.get(f'/api/v1/conversations/{cid}/export').json()
            assert exported['assessor_comparisons'][0]['id']==assessor
            assert exported['generator_comparisons'][0]['id']==generator
            assert exported['generator_comparisons'][0]['input_fingerprint']
            assert client.request('DELETE',f'/api/v1/conversations/{cid}',json={'confirmation':'wrong'}).status_code==422
            assert client.get(f'/api/v1/generator-comparisons/{generator}').status_code==200
            deleted=client.request('DELETE',f'/api/v1/conversations/{cid}',json={'confirmation':cid})
            assert deleted.status_code==200,deleted.text
            iterator=app.dependency_overrides[get_db]();db=next(iterator)
            try:
                assert not db.scalars(select(AssessorComparisonModel)).all()
                assert not db.scalars(select(GeneratorComparisonModel)).all()
            finally:iterator.close()
            assert client.get(f'/api/v1/assessor-comparisons/{assessor}').status_code==404
            assert client.get(f'/api/v1/generator-comparisons/{generator}').status_code==404
        finally:app.dependency_overrides.clear()
