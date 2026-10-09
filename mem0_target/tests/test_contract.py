import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from mem0_target import service


class FakeMemory:
    def __init__(self): self.records = []; self.add_calls = 0
    def add(self,messages,**kwargs):
        assert kwargs['infer'] is True
        assert 'expected' not in json.dumps(messages)
        self.add_calls += 1
        self.records=[{'id':'native-1','memory':messages[-1]['content']}]
    def get_all(self,**kwargs):
        assert 'user_id' not in kwargs and kwargs['filters']['user_id'] in ('one','two')
        return {'results':self.records}
    def search(self,prompt,**kwargs):
        assert kwargs['filters']['user_id'] in ('one','two')
        return {'results':self.records}


def payload(namespace='one'):
    return {'namespace':namespace,'messages':[{'message_id':'m2','role':'user','content':'I prefer Ruby.','timestamp':'2026-02-02T00:00:00Z'},
        {'message_id':'m1','role':'user','content':'I prefer Python.','timestamp':'2026-02-01T00:00:00Z'}],
        'target':{'provider':'ollama','model':'qwen3:1.7b','temperature':0},
        'memory_strategy':'strong_score_based','memory_profile':{'max_retrieved_records':2,'context_character_budget':100}}


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(service,'ROOT',tmp_path)
    # This contract replaces the SDK with FakeMemory; its version is a fixture
    # too. Real SDK instrumentation is verified in the native service pilot.
    monkeypatch.setattr(service,'version',lambda _: 'fixture-sdk')
    stores = {}
    monkeypatch.setattr(service,'memory_client',lambda key: stores.setdefault(key,FakeMemory()))
    calls=[]
    def reader(config,prompt,records):
        calls.append((prompt,records)); return 'Ruby','same-reader-instructions'
    monkeypatch.setattr(service,'answer_model',reader)
    c=TestClient(service.app);c.stores=stores;c.calls=calls
    return c


def test_idempotent_ingest_answers_and_namespace_isolation(client):
    data=payload(); first=client.post('/ingest',json=data)
    assert first.status_code==200 and first.json()['inference'] is True
    assert client.post('/ingest',json=data).json()==first.json()
    assert next(iter(client.stores.values())).add_calls==1
    assert next(iter(client.stores.values())).records[0]['memory']=='I prefer Ruby.'
    changed=payload();changed['target']['temperature']=1
    assert client.post('/ingest',json=changed).status_code==409
    assert client.post('/ingest',json=payload('two')).status_code==200
    assert len(client.stores)==2
    question={'namespace':'one','request_id':'q1','prompt':'What language do I prefer?'}
    a=client.post('/answer',json=question);assert a.status_code==200
    assert a.json()['supply_evidence']['supplied_count']==1
    assert client.post('/answer',json=question).json()==a.json()
    assert len(client.calls)==1
    assert client.post('/answer',json={**question,'prompt':'Changed question'}).status_code==409
    assert client.post('/answer',json={**question,'namespace':'absent'}).status_code==404


def test_gold_annotations_and_unsupported_controls_are_rejected(client):
    data=payload();data['expected_answer']='private gold'
    assert client.post('/ingest',json=data).status_code==422
    for change in ({'memory_strategy':'weak_first_hit'}, {'target':{'provider':'openrouter','model':'other','temperature':0}},
        {'memory_profile':{'isolate_project_scope':True}}):
        assert client.post('/ingest',json={**payload(),**change}).status_code==422
    assert not client.stores


def test_failed_ingestion_is_not_cached_as_ready(client,monkeypatch):
    def fail(key):raise RuntimeError('private source / credentials')
    monkeypatch.setattr(service,'memory_client',fail)
    answer=client.post('/ingest',json=payload())
    assert answer.status_code==502 and 'private' not in answer.text
    with service.database() as db:assert db.execute('SELECT count(*) FROM namespaces').fetchone()[0]==0


def test_failed_reader_does_not_cache_answer_and_budget_filters_records(client,monkeypatch):
    assert client.post('/ingest',json=payload()).status_code==200
    memory=next(iter(client.stores.values()))
    memory.records=[{'id':'big','memory':'x'*200},{'id':'small','memory':'Ruby'}]
    def fail(*args):raise ValueError('raw upstream private payload')
    monkeypatch.setattr(service,'answer_model',fail)
    question={'namespace':'one','request_id':'q1','prompt':'What language do I prefer?'}
    assert 'raw upstream' not in client.post('/answer',json=question).text
    with service.database() as db:assert db.execute('SELECT count(*) FROM answers').fetchone()[0]==0
    monkeypatch.setattr(service,'answer_model',lambda config,prompt,records:('Ruby',json.dumps(records)))
    answer=client.post('/answer',json=question).json()
    assert answer['supply_evidence']['retrieved_count']==2
    assert answer['supply_evidence']['supplied_count']==1
    assert answer['supply_evidence']['records'][0]['id']=='small'


def test_empty_inference_is_visible_and_does_not_fake_facts(client,monkeypatch):
    def no_facts(self,*args,**kwargs):self.add_calls+=1
    monkeypatch.setattr(FakeMemory,'add',no_facts)
    r=client.post('/ingest',json=payload())
    assert r.status_code==200 and r.json()['stored_count']==0
    assert client.get('/health').json()['model_readiness']=='not checked'


def test_memory_only_endpoint_never_calls_reader(client,monkeypatch):
    assert client.post('/ingest',json=payload()).status_code==200
    def forbidden(*args):raise AssertionError('Memory retrieval must not answer the question')
    monkeypatch.setattr(service,'answer_model',forbidden)
    request={'namespace':'one','request_id':'q1','prompt':'Which language is preferred?'}
    response=client.post('/retrieve',json=request)
    assert response.status_code==200
    assert response.json()['supplied'][0]['memory']=='I prefer Ruby.'
    assert response.json()['native_source_attribution'] is False
    assert client.post('/retrieve',json={**request,'namespace':'missing'}).status_code==404
    assert not client.calls
