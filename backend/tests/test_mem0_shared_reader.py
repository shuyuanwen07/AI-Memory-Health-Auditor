from copy import deepcopy
import pytest
from app.benchmarks import mem0
from app.benchmarks.live import LiveBenchmarkRunner
from app.benchmarks.longmemeval import LongMemEvalAdapter
from app.schemas.benchmark import LiveBenchmarkRequest
from app.target_ai.providers import HttpTargetAIConnector
from test_live_benchmark import source


def test_native_same_reader_and_gold_isolation(monkeypatch):
    monkeypatch.setenv('MEM0_TARGET_URL','http://native-test.invalid')
    seen=[]; requests=[]
    def native(operation,payload):
        requests.append(payload)
        if operation=='ingest':return {'namespace':payload['namespace'],'ready':True,'inference':True}
        record={'id':'native-one','memory':'The backend now uses PostgreSQL instead of MySQL'}
        return {'namespace':payload['namespace'],'request_id':payload['request_id'],'retrieved':[record],
            'supplied':[record],'stored':[record],'sdk_version':'2.2.1','target_service':'mem0-oss-target-v1','stored_listing_limit':500}
    monkeypatch.setattr(mem0,'call',native)
    def reader(self,audit,test,instructions,credential):
        assert test.expected_behavior=='' and test.supporting_memory_ids==[]
        seen.append((instructions,test.prompt,audit.model,audit.temperature,audit.target_configuration.value));return 'PostgreSQL'
    monkeypatch.setattr(HttpTargetAIConnector,'_execute_provider',reader)
    request=LiveBenchmarkRequest(payload=source(),source_authorised=True,strategies=['scope_aware'],include_mem0=True)
    first=LiveBenchmarkRunner().run(request)
    assert seen[0]==seen[1]
    assert 'GOLD_SECRET' not in str(requests) and 'GOLD_SESSION_SECRET' not in str(requests)
    native_result=first.conditions[1].cases[0]
    assert native_result.execution_metadata.memory_input.sent_memory_ids==['native-one']
    assert native_result.memory_evidence[0]['source_message_ids']==[]
    assert native_result.memory_preparation['native_llm_calls'] is None
    assert native_result.memory_preparation['embedding_calls'] is None
    changed=deepcopy(source());changed[0]['answer']='another gold';changed[0]['question_type']='conflict_resolution'
    second=LiveBenchmarkRunner().run(request.model_copy(update={'payload':changed}))
    assert seen[:2]==seen[2:]
    assert first.configuration_fingerprint_sha256==second.configuration_fingerprint_sha256


def test_invalid_native_supply_is_rejected_before_reader(monkeypatch):
    def native(operation,payload):
        if operation=='ingest':return {'namespace':payload['namespace'],'ready':True,'inference':True}
        return {'namespace':payload['namespace'],'request_id':payload['request_id'],'retrieved':[],
            'supplied':[{'id':'wrong','memory':'not retrieved'}],'stored':[]}
    monkeypatch.setattr(mem0,'call',native)
    def forbidden(*args):raise AssertionError('No reader')
    monkeypatch.setattr(HttpTargetAIConnector,'execute',forbidden)
    case=LongMemEvalAdapter().adapt(source())[0][0]
    with pytest.raises(ValueError,match='do not match'):
        mem0.run_case(LiveBenchmarkRequest(payload=source(),source_authorised=True),case,None,'unit')


def test_native_repairs_share_snapshot_and_do_not_change_extraction_or_gold(monkeypatch):
    calls=[]; readers=[]
    memories=[{'id':'P','memory':'User prefers Ruby.'},{'id':'T','memory':'User assignment requires Go.'}]
    def native(operation,payload):
        calls.append((operation,payload))
        usage={'llm_attempts':2 if operation=='ingest' else 0,'embedding_attempts':3 if operation=='ingest' else 1,'llm_failures':0,'embedding_failures':0}
        if operation=='ingest':return {'namespace':payload['namespace'],'ready':True,'inference':True,'inference_usage':usage}
        return {'namespace':payload['namespace'],'request_id':payload['request_id'],'retrieved':memories,'supplied':memories,'stored':memories,'inference_usage':usage}
    def reader(self,audit,test,instructions,credential):
        readers.append((test.target_memory_context,instructions,audit.model,audit.temperature,test.expected_behavior,test.supporting_memory_ids))
        return 'Go'
    monkeypatch.setattr(mem0,'call',native)
    monkeypatch.setattr(HttpTargetAIConnector,'_execute_provider',reader)
    case=LongMemEvalAdapter().adapt(source())[0][0].model_copy(update={'question':'Which language must I use for my assignment?'})
    request=LiveBenchmarkRequest(payload=source(),source_authorised=True)
    results=mem0.run_case_comparison(request,case,None,'unit')
    assert [name for name,_ in calls]==['ingest','retrieve']
    assert all(r.memory_preparation['native_llm_calls']==2 and r.memory_preparation['embedding_calls']==4 for r in results.values())
    assert sum(r.memory_preparation['preparation_charged_here'] for r in results.values())==1
    assert [r[0] for r in readers]==[['User prefers Ruby.','User assignment requires Go.'],['User prefers Ruby.','User assignment requires Go.'],['User assignment requires Go.']]
    assert mem0.GENERIC_INSTRUCTION not in readers[0][1] and mem0.GENERIC_INSTRUCTION in readers[1][1]
    assert mem0.GENERIC_INSTRUCTION not in readers[2][1]
    assert all(r[2:]==('qwen3:1.7b',0,'',[]) for r in readers)
    assert len({r.memory_preparation['shared_snapshot_sha256'] for r in results.values()})==1
    assert sum(r.memory_preparation['preparation_charged_here'] for r in results.values())==1
    assert results['directed'].supplied_memory_ids==['T']
    assert results['directed'].retrieved_memory_ids==['P','T']
    assert results['directed'].intervention['removed_memory_ids']==['P']
    assert 'GOLD_SECRET' not in str(calls)
    assert request.target_memory_profile.additional_instructions==''


def test_task_filter_keeps_preferences_negative_controls_and_bundled_facts():
    preference={'id':'P','memory':'User prefers Rust.'}
    task={'id':'T','memory':'User has a project requiring Go.'}
    bundled={'id':'B','memory':'User prefers Ruby but this assignment requires Swift.'}
    assert mem0.task_supply('Which language do I generally prefer?',[preference,task])==[preference,task]
    assert mem0.task_supply('For the current assignment, a general preference conflicts with a requirement. State the requirement that applies.',[preference,task])==[task]
    assert mem0.task_supply('Which language does my assignment require?',[preference])==[preference]
    assert mem0.task_supply('Which language does my assignment require?',[preference,bundled])==[preference,bundled]
    assert mem0.task_supply('Which language does my assignment require?',[preference,task,bundled])==[task,bundled]


def test_repair_comparison_preflight_refuses_invalid_conditions_before_any_model(monkeypatch):
    def forbidden(*args):raise AssertionError('No upstream operation permitted')
    monkeypatch.setattr(HttpTargetAIConnector,'execute',forbidden)
    monkeypatch.setattr(mem0,'call',forbidden)
    for kwargs,reason in [({'native_repair_comparison':True},'Enable native'),
        ({'native_repair_comparison':True,'include_mem0':True},'Choose one'),
        ({'native_repair_comparison':True,'include_mem0':True,'strategies':['scope_aware'], 'target_memory_profile':{'additional_instructions':'x'*4000}},'Leave room')]:
        with pytest.raises(ValueError,match=reason):
            LiveBenchmarkRunner().run(LiveBenchmarkRequest(payload=source(),source_authorised=True,**kwargs))
