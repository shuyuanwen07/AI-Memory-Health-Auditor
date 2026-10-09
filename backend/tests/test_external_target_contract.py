from datetime import datetime, timezone
import json
import httpx
import pytest
from fastapi import HTTPException
from app.schemas import AuditRun, Conversation, ConversationMessage, Dimension, TestCase
from app.target_systems.external_http import ExternalHttpTargetSystemAdapter


def fixtures():
    now=datetime.now(timezone.utc)
    audit=AuditRun(run_id='RUN-isolated',conversation_id='C1',status='CREATED',target_configuration='strong',provider='ollama',model='qwen3:1.7b',temperature=0,random_seed=42,test_budget=4,prompt_template_version='v1',created_at=now,target_system_adapter='external-http')
    conversation=Conversation(conversation_id='C1',created_at=now,authorised=True,messages=[ConversationMessage(message_id='m1',role='user',content='Project Orion uses PostgreSQL.',timestamp=now)])
    test=TestCase(test_id='T1',run_id=audit.run_id,dimension=Dimension.ACCURACY,prompt='What database does the Orion project use?',expected_behavior='AUDITOR-PRIVATE-EXPECTED-ANSWER',supporting_memory_ids=['GOLD-PRIVATE-ID'],generator_version='unit')
    return audit,conversation,test


def test_independent_contract_withholds_gold_and_verifies_namespace(monkeypatch):
    audit,conversation,test=fixtures()
    monkeypatch.setenv('EXTERNAL_TARGET_URL','http://isolated-target.invalid')
    monkeypatch.setenv('EXTERNAL_TARGET_API_KEY','backend-only-secret')
    original=httpx.Client
    calls=[]
    def handle(request):
        data=json.loads(request.content);calls.append(data)
        assert request.headers['Authorization']=='Bearer backend-only-secret'
        if request.url.path=='/ingest':
            return httpx.Response(200,json={'namespace':data['namespace'],'ready':True})
        return httpx.Response(200,json={'namespace':data['namespace'],'request_id':data['request_id'],'response_text':'PostgreSQL'})
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))
    adapter=ExternalHttpTargetSystemAdapter(None,audit)
    adapter.ingest(conversation)
    result=adapter.answer(test,audit)
    assert result.response_text=='PostgreSQL'
    assert result.execution_metadata.memory_input is None
    assert 'AUDITOR-PRIVATE' not in json.dumps(calls)
    assert 'GOLD-PRIVATE-ID' not in json.dumps(calls)
    assert 'backend-only-secret' not in str(adapter.trace())
    adapter.reset()
    with pytest.raises(HTTPException):
        adapter.answer(test,audit)


def test_wrong_namespace_and_upstream_error_are_safe(monkeypatch):
    audit,conversation,test=fixtures()
    monkeypatch.setenv('EXTERNAL_TARGET_URL','http://isolated-target.invalid')
    monkeypatch.setattr(ExternalHttpTargetSystemAdapter,'_post',lambda *args:{'namespace':'another-user','ready':True})
    with pytest.raises(HTTPException) as error:
        ExternalHttpTargetSystemAdapter(None,audit).ingest(conversation)
    assert error.value.status_code==502


def test_unconfigured_independent_system_is_explicit(monkeypatch):
    monkeypatch.delenv('EXTERNAL_TARGET_URL',raising=False)
    with pytest.raises(HTTPException) as error:
        ExternalHttpTargetSystemAdapter(None,fixtures()[0])
    assert error.value.status_code==422
