from types import SimpleNamespace
import pytest
from app.main import app
from app.api import routes
from app.database.session import get_db
from app.models import ExtractionComparisonModel, MemoryModel
from app.extraction.llm import PipelineRequestError
from app.extraction.rule_based import RuleBasedMemoryExtractor
from test_input_and_relationship_guards import client_for


def source(client):
    cid=client.post('/api/v1/conversations',json={'authorised':True,'messages':[{'role':'user','content':'I prefer Rust.'}]}).json()['conversation_id']
    memories=client.post(f'/api/v1/conversations/{cid}/extract',json={'provider':'rule_based'}).json()
    client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth',json={'confirmed_memory_ids':[m['memory_id'] for m in memories]})
    rid=client.post('/api/v1/audits',json={'conversation_id':cid,'provider':'rule_based','pipeline_provider':'rule_based',
        'evaluator_provider':'rule_based','target_configuration':'strong'}).json()['run_id']
    path=f'/api/v1/audits/{rid}'
    client.post(path+'/generate-tests');client.post(path+'/execute');client.post(path+'/evaluate')
    return cid,rid,memories


def request(rid):
    return {'creation_request_key':'extract_comparison_fixture','source_run_id':rid,
            'extractors':[{'provider':'rule_based'},{'provider':'openrouter','model':'fixed-extractor'}]}


@pytest.mark.parametrize('mode',['failure_then_retry','midcall_drift'])
def test_isolated_extraction_durable_failure_and_source_protection(tmp_path,monkeypatch,mode):
    with client_for(tmp_path) as client:
        try:
            cid,rid,memories=source(client)
            created=client.post('/api/v1/extraction-comparisons',json=request(rid))
            assert created.status_code==201,created.text
            plan=created.json()['comparison_id']; url=f'/api/v1/extraction-comparisons/{plan}'
            assert client.post('/api/v1/extraction-comparisons',json=request(rid)).json()['comparison_id']==plan
            changed={**request(rid),'extractors':[{'provider':'rule_based'},{'provider':'openrouter','model':'other-model'}]}
            assert client.post('/api/v1/extraction-comparisons',json=changed).status_code==409
            before=client.get(f'/api/v1/conversations/{cid}/memories').json()
            base=client.post(url+'/entries/0/extract');assert base.status_code==200,base.text
            assert base.json()['entries'][0]['checks']['fact_coverage_percent']==100
            assert base.json()['entries'][0]['checks']['relationship_coverage_percent'] is None
            assert client.post(url+'/entries/0/extract').json()['entries'][0]['operations']==base.json()['entries'][0]['operations']
            calls=[]
            class FakeExtractor:
                VERSION='fixture-extractor'
                def __init__(self):self.client=SimpleNamespace(last_execution=None)
                def extract(self,conversation):
                    calls.append(1)
                    iterator=app.dependency_overrides[get_db]();db=next(iterator)
                    try:
                        row=db.get(ExtractionComparisonModel,plan)
                        assert row.entries[1]['status']=='started'
                        assert row.entries[1]['operations'][-1]['status']=='started'
                        if mode=='midcall_drift':
                            db.get(MemoryModel,memories[0]['memory_id']).canonical_value='The user prefers Python.'
                            db.commit()
                    finally:iterator.close()
                    self.client.last_execution={'version':'pipeline-http-meter-v1','provider':'openrouter','model':'fixed-extractor',
                        'status':'failed' if mode=='failure_then_retry' and len(calls)==1 else 'parsed',
                        'request_attempts':1,'failed_http_attempts':0,'elapsed_ms':200,'reported_total_tokens':10,'reported_cost_credits':0.02}
                    if mode=='failure_then_retry' and len(calls)==1:raise PipelineRequestError('Safe fixture failure.')
                    return RuleBasedMemoryExtractor().extract(conversation)
            monkeypatch.setattr(routes,'get_memory_extractor',lambda *args:FakeExtractor())
            result=client.post(url+'/entries/1/extract')
            assert result.status_code==(409 if mode=='midcall_drift' else 502),result.text
            observed=client.get(url).json();entry=observed['entries'][1]
            assert entry['status']=='failed' and entry['candidates'] is None
            assert entry['usage']['observed_cost_credits']==0.02
            assert len(entry['operations'])==1
            if mode=='midcall_drift':
                assert not observed['inputs_match']
                assert observed['reference_memories'][0]['canonical_value']==before[0]['canonical_value']
                assert client.post(url+'/entries/1/extract').status_code==409
                assert len(calls)==1
            else:
                retried=client.post(url+'/entries/1/extract');assert retried.status_code==200,retried.text
                entry=retried.json()['entries'][1]
                assert entry['status']=='completed' and len(entry['operations'])==2
                assert entry['operations'][0]['status']=='failed'
                assert entry['usage']['request_attempts']==2
                assert entry['usage']['observed_cost_credits']==0.04
                assert client.get(f'/api/v1/conversations/{cid}/memories').json()==before
            exported=client.get(f'/api/v1/conversations/{cid}/export').json()
            assert exported['extraction_comparisons'][0]['id']==plan
            assert client.request('DELETE',f'/api/v1/conversations/{cid}',json={'confirmation':cid}).status_code==200
            assert client.get(url).status_code==404
        finally:app.dependency_overrides.clear()


def test_reference_checks_do_not_label_a_paraphrase_as_semantically_wrong():
    from app.schemas import Memory
    from app.services.extraction_comparison import exact_reference_checks
    reference=[Memory(memory_id='R',conversation_id='C',canonical_value='The user prefers Rust.',status='confirmed')]
    candidate=Memory(memory_id='M001',conversation_id='C',canonical_value='Rust is the user favourite language.',status='candidate')
    observed=exact_reference_checks([candidate.model_dump(mode='json')],reference)
    assert observed['fact_coverage_percent']==0
    assert 'Not semantic accuracy' in observed['scope']
    assert exact_reference_checks(None,reference) is None
