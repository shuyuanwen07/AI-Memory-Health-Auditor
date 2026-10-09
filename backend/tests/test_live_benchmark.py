from app.extraction.rule_based import RuleBasedMemoryExtractor
from copy import deepcopy
from threading import Event

import pytest
from fastapi.testclient import TestClient

from app.benchmarks.longmemeval import LongMemEvalAdapter
from app.benchmarks.live import LiveBenchmarkRunner
from app.schemas.benchmark import LiveBenchmarkRequest
from app.target_ai.providers import HttpTargetAIConnector
from app.main import app


def source():
    return [{"question_id":"official-layout-synthetic", "question_type":"knowledge-update",
        "question":"Which database does the backend use now?", "answer":"GOLD_SECRET",
        "question_date":"2025/08/21 (Thu) 12:00",
        "haystack_session_ids":["new-session", "old-session"],
        "haystack_dates":["2025/08/20 (Wed) 12:00", "2025/07/20 (Sun) 12:00"],
        "haystack_sessions":[[{"role":"user", "content":"The backend now uses PostgreSQL instead of MySQL.", "has_answer":True},
                              {"role":"assistant", "content":"I suggested SQLite."}],
                             [{"role":"user", "content":"The backend uses MySQL."}]],
        "answer_session_ids":["GOLD_SESSION_SECRET"]}]


def test_official_session_arrays_preserve_dates_roles_and_reject_corrupt_alignment():
    cases, _ = LongMemEvalAdapter().adapt(source())
    assert len(cases[0].messages)==3
    assert cases[0].messages[0].source_session_id=='new-session'
    assert cases[0].messages[0].timestamp.month==8
    assert cases[0].messages[-1].timestamp.month==7
    assert cases[0].messages[1].role=='assistant'
    assert cases[0].question_timestamp.day==21
    assert 'has_answer' not in cases[0].messages[0].model_dump()
    bad=source();bad[0]['haystack_dates'].pop()
    with pytest.raises(ValueError, match='align'):LongMemEvalAdapter().adapt(bad)
    bad=source();bad[0]['haystack_dates'][0]='not-a-date'
    with pytest.raises(ValueError, match='Unrecognised'):LongMemEvalAdapter().adapt(bad)


def test_live_calls_use_controlled_policy_without_reference_leakage(monkeypatch):
    seen=[]
    def provider(self,audit,test,instructions,credential):
        assert audit.target_configuration.value=='strong'
        seen.append((audit.memory_strategy.value,test.expected_behavior,test.supporting_memory_ids,instructions,test.prompt))
        return 'PostgreSQL'
    monkeypatch.setattr(HttpTargetAIConnector,'_execute_provider',provider)
    first=LiveBenchmarkRunner().run(LiveBenchmarkRequest(payload=source(),source_authorised=True))
    changed=deepcopy(source());changed[0]['answer']='DIFFERENT_GOLD';changed[0]['answer_session_ids']=['OTHER_SECRET']
    changed[0]['haystack_sessions'][0][0]['has_answer']=False
    changed[0]['question_type']='conflict_resolution';changed[0]['dimension_hint']='conflict_resolution'
    second=LiveBenchmarkRunner().run(LiveBenchmarkRequest(payload=changed,source_authorised=True))
    assert seen[:2]==seen[2:]
    assert all(expected=='' and ids==[] for _,expected,ids,_,_ in seen)
    assert all('GOLD' not in instructions and 'SECRET' not in instructions for _,_,_,instructions,_ in seen)
    assert 'MySQL' in seen[0][3] and 'PostgreSQL' in seen[1][3]
    assert first.conditions[0].cases[0].response_text=='PostgreSQL'
    assert first.conditions[0].cases[0].execution_metadata.response_source=='ollama'
    assert first.conditions[0].cases[0].assistant_message_count==1
    assert first.conditions[0].cases[0].stored_memory_count==2
    assert first.conditions[0].cases[0].supplied_memory_ids
    assert len(first.conditions[0].cases[0].memory_evidence)==2
    assert any(m['supplied'] and 'MySQL' in m['canonical_value'] for m in first.conditions[0].cases[0].memory_evidence)
    assert first.writer_version==RuleBasedMemoryExtractor.VERSION
    assert first.source_fingerprint_sha256!=second.source_fingerprint_sha256
    assert first.configuration_fingerprint_sha256==second.configuration_fingerprint_sha256


def test_rejects_no_consent_duplicates_or_oversize_before_model_calls(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('No upstream call allowed')
    monkeypatch.setattr(HttpTargetAIConnector,'execute',forbidden)
    runner=LiveBenchmarkRunner()
    for kwargs,match in [({},'authorised'),({'source_authorised':True,'provider':'rule_based'},'Real-model'),
                         ({'source_authorised':True,'strategies':['no_memory','no_memory']},'only once'),
                         ({'source_authorised':True,'max_cases':1,'payload':source()+[{**source()[0],'question_id':'second'}]},'No cases')]:
        values={'payload':source(),**kwargs}
        with pytest.raises(ValueError,match=match):runner.run(LiveBenchmarkRequest(**values))
    cancelled=Event();cancelled.set()
    with pytest.raises(ValueError,match='cancelled'):runner.run(LiveBenchmarkRequest(payload=source(),source_authorised=True),cancelled)


def test_live_route_uses_real_connector_and_does_not_persist_operational_rows(monkeypatch):
    monkeypatch.setattr(HttpTargetAIConnector,'_execute_provider',lambda *args:'PostgreSQL')
    with TestClient(app) as client:
        no_consent=client.post('/api/v1/research/benchmarks/longmemeval/live',json={'payload':source()})
        assert no_consent.status_code==422
        ignored_setting=client.post('/api/v1/research/benchmarks/longmemeval/live',json={'payload':source(),'source_authorised':True,'memory_strategy':'no_memory'})
        assert ignored_setting.status_code==422  # plural strategies are explicit; never silently ignore a setting
        response=client.post('/api/v1/research/benchmarks/longmemeval/live',json={'payload':source(),'source_authorised':True})
        assert response.status_code==200,response.text
        assert len(response.json()['conditions'])==2
        assert 'not official LongMemEval' in response.json()['notice']


def test_cancellation_stops_before_next_provider_call(monkeypatch):
    cancelled=Event();calls=[]
    def provider(*args):calls.append(1);cancelled.set();return 'PostgreSQL'
    monkeypatch.setattr(HttpTargetAIConnector,'_execute_provider',provider)
    with pytest.raises(ValueError,match='cancelled'):
        LiveBenchmarkRunner().run(LiveBenchmarkRequest(payload=source(),source_authorised=True),cancelled)
    assert len(calls)==1
