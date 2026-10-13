from concurrent.futures import ThreadPoolExecutor
import threading
import httpx
import pytest
from app.extraction.llm import PipelineLLMClient,PipelineRequestError


def call(client):
    return client.complete_json(instructions='Return JSON.',prompt='Synthetic input.',schema_name='fixture',schema={'type':'object'})


def test_retry_and_usage_are_recorded_even_when_returned_model_text_is_invalid(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','synthetic-secret')
    replies=iter([httpx.Response(503),httpx.Response(200,json={'model':'resolved-model',
        'choices':[{'message':{'content':'not JSON'}}],'usage':{'prompt_tokens':10,'completion_tokens':3,'cost':0.02}})])
    monkeypatch.setattr('app.extraction.llm.httpx.post',lambda *args,**kwargs:next(replies))
    monkeypatch.setattr('app.extraction.llm.time.sleep',lambda _:None)
    client=PipelineLLMClient('openrouter','fixed-model')
    with pytest.raises(PipelineRequestError):call(client)
    receipt=client.last_execution
    assert receipt['request_attempts']==2 and receipt['failed_http_attempts']==1
    assert receipt['reported_total_tokens']==13 and receipt['reported_cost_credits']==0.02
    assert receipt['reported_model']=='resolved-model' and receipt['status']=='failed'
    assert receipt['last_http_status']==200
    assert 'synthetic-secret' not in str(receipt) and 'not JSON' not in str(receipt)


def test_usage_resets_and_missing_credentials_mean_no_observed_http_request(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','synthetic-secret')
    replies=iter([httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}],'usage':{'cost':0,'total_tokens':3}}),
        httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}],'usage':{'cost':True,'prompt_tokens':False,'completion_tokens':-1}})])
    monkeypatch.setattr('app.extraction.llm.httpx.post',lambda *args,**kwargs:next(replies))
    client=PipelineLLMClient('openrouter','fixed-model')
    assert call(client)=={} and client.last_execution['reported_cost_credits']==0
    assert call(client)=={} and client.last_execution['reported_cost_credits'] is None
    assert client.last_execution['reported_total_tokens'] is None
    monkeypatch.delenv('OPENROUTER_API_KEY')
    with pytest.raises(PipelineRequestError):call(client)
    assert client.last_execution['request_attempts']==0
    assert client.last_execution['reported_total_tokens'] is None


def test_concurrent_pipeline_clients_keep_separate_http_receipts(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','synthetic-secret')
    barrier=threading.Barrier(2)
    def post(*args,**kwargs):
        model=kwargs['json']['model'];barrier.wait(timeout=10)
        return httpx.Response(200,json={'model':model,'choices':[{'message':{'content':'{}'}}],
            'usage':{'total_tokens':11 if model=='first-model' else 22}})
    monkeypatch.setattr('app.extraction.llm.httpx.post',post)
    clients=[PipelineLLMClient('openrouter','first-model'),PipelineLLMClient('openrouter','second-model')]
    with ThreadPoolExecutor(max_workers=2) as executor:assert list(executor.map(call,clients))==[{},{}]
    assert [client.last_execution['reported_total_tokens'] for client in clients]==[11,22]
    assert [client.last_execution['request_attempts'] for client in clients]==[1,1]
