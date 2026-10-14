"""Configured budget changes do not replace evidence or bypass contracts."""
import httpx
import pytest
from app.extraction.llm import PipelineLLMClient, PipelineRequestError
from app.services.formal_freeze import formal_runtime_signature
from app.target_ai.openrouter import completion_error


@pytest.mark.parametrize('requested,effective', [(None,1800),(4096,1800),(512,512)])
def test_openrouter_budget_cap_is_explicit_and_receipted(monkeypatch,requested,effective):
    monkeypatch.setenv('PIPELINE_MAX_OUTPUT_TOKENS','1800')
    monkeypatch.setenv('OPENROUTER_API_KEY','synthetic-secret')
    sent=[]
    def post(*args,**kwargs):
        sent.append(kwargs['json'])
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]})
    monkeypatch.setattr('app.extraction.llm.httpx.post',post)
    client=PipelineLLMClient('openrouter','openai/gpt-6-luna')
    assert client.complete_json(instructions='Return JSON.',prompt='Synthetic.',schema_name='fixture',schema={'type':'object'},max_output_tokens=requested)=={'ok':True}
    assert sent[0]['max_tokens']==effective
    assert sent[0]['model']=='openai/gpt-6-luna'
    assert client.last_execution['requested_output_token_limit']==effective
    assert client.last_execution['declared_output_token_limit']==requested
    assert client.last_execution['configured_output_token_cap']==1800


@pytest.mark.parametrize('value',['0','255','12001','oops','1.5','１２３４'])
def test_invalid_cap_fails_before_dispatch(monkeypatch,value):
    monkeypatch.setenv('PIPELINE_MAX_OUTPUT_TOKENS',value)
    monkeypatch.setattr('app.extraction.llm.httpx.post',lambda *a,**k:pytest.fail('Must not dispatch'))
    with pytest.raises(PipelineRequestError,match='PIPELINE_MAX_OUTPUT_TOKENS'):
        PipelineLLMClient('openrouter','synthetic').complete_json(instructions='JSON.',prompt='Synthetic.',schema_name='fixture',schema={})


def test_budget_cap_is_in_frozen_formal_runtime(monkeypatch):
    monkeypatch.delenv('PIPELINE_MAX_OUTPUT_TOKENS',raising=False)
    original=formal_runtime_signature()
    monkeypatch.setenv('PIPELINE_MAX_OUTPUT_TOKENS','1800')
    revised=formal_runtime_signature()
    assert original['source_sha256']==revised['source_sha256']
    assert original!=revised
    assert revised['pipeline_output_token_cap']=='1800'


def test_peak_capacity_error_classifies_without_retaining_message():
    result=completion_error({'error':{'code':502,'message':'High demand: maximum usage size allowed during peak load. synthetic-secret'}})
    assert result=={'provider_error_scope':'top_level','provider_error_status':502,'provider_error_category':'capacity_limit'}
    assert 'synthetic-secret' not in str(result)


def test_extraction_provider_failure_keeps_actionable_summary(monkeypatch):
    from app.extraction.llm_extractor import LLMMemoryExtractor
    from app.schemas import Conversation
    from datetime import datetime,timezone
    monkeypatch.setenv('OPENROUTER_API_KEY','synthetic-secret')
    monkeypatch.setattr('app.extraction.llm.httpx.post',lambda *a,**k:httpx.Response(200,json={'error':{'code':502,'message':'High demand: maximum usage size allowed during peak load.'}}))
    client=PipelineLLMClient('openrouter','openai/gpt-6-luna')
    extractor=LLMMemoryExtractor(client)
    conversation=Conversation(conversation_id='SYNTHETIC',created_at=datetime.now(timezone.utc),authorised=True,source_origin='synthetic',messages=[{'message_id':'SYN1','role':'user','content':'I live in Adelaide.','timestamp':datetime.now(timezone.utc)}])
    with pytest.raises(PipelineRequestError):
        extractor.extract(conversation)
    stage=extractor.last_agent_stages[-1]
    assert 'peak load' in stage['error_summary']
    assert 'Correct the source' not in stage['error_summary']
    assert stage['execution']['provider_error_category']=='capacity_limit'
