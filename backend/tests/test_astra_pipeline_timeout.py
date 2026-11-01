import httpx
import pytest

from app.extraction.llm import PipelineLLMClient, PipelineRequestError


def test_astra_max_has_one_long_request_and_preserves_timeout_receipt(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-test-key')
    calls=[]
    def post(url, **kwargs):
        calls.append((url,kwargs['timeout'],kwargs['json']))
        raise httpx.ReadTimeout('synthetic timeout')
    monkeypatch.setattr(httpx,'post',post)
    client=PipelineLLMClient('openai','gpt-6-astra')
    with pytest.raises(PipelineRequestError):
        client.complete_json(instructions='Return JSON.',prompt='Synthetic input.',schema_name='timeout_test',
            schema={'type':'object','additionalProperties':False,'required':['ok'],'properties':{'ok':{'type':'boolean'}}},
            agent_role='test_review')
    assert len(calls)==1
    assert calls[0][0]=='https://api.openai.com/v1/responses'
    assert calls[0][1]==240.0
    assert calls[0][2]['reasoning']=={'effort':'max'}
    assert 'temperature' not in calls[0][2]
    assert client.last_execution['request_attempts']==1
    assert client.last_execution['failed_http_attempts']==1
    assert client.last_execution['transport_timeout_seconds']==240.0
    assert client.last_execution['max_http_attempts']==1


def test_ordinary_pipeline_retains_bounded_retry_policy(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-test-key')
    monkeypatch.setattr('app.extraction.llm.time.sleep',lambda _:None)
    calls=[]
    def post(url, **kwargs):
        calls.append(kwargs['timeout'])
        raise httpx.ConnectError('synthetic connection failure')
    monkeypatch.setattr(httpx,'post',post)
    client=PipelineLLMClient('openai','gpt-4.1')
    with pytest.raises(PipelineRequestError):
        client.complete_json(instructions='Return JSON.',prompt='Synthetic input.',schema_name='timeout_test',
            schema={'type':'object','additionalProperties':False,'required':['ok'],'properties':{'ok':{'type':'boolean'}}})
    assert calls==[60.0,60.0,60.0]
    assert client.last_execution['max_http_attempts']==3
