"""Executable contracts for reliability, profiles and diagnostic studies."""
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database.session import Base, get_db
from app.models import AuditRunModel, EvaluationResultModel, TestCaseModel
from app.schemas import TargetMemoryProfile


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    monkeypatch.setenv("EVALUATOR_PROVIDER", "rule_based")
    monkeypatch.setenv("TARGET_MEMORY_WRITER", "rule_based")
    engine = create_engine(f"sqlite:///{tmp_path/'quality.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    def database():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = database
    with TestClient(app) as browser:
        browser.sessions = sessions
        yield browser
    app.dependency_overrides.clear()
    engine.dispose()


def history(client, text):
    response = client.post("/api/v1/conversations", json={"authorised": True, "pasted_text": text})
    assert response.status_code == 201, response.text
    identity = response.json()["conversation_id"]
    memories = client.post(f"/api/v1/conversations/{identity}/extract", json={"provider":"rule_based"}).json()
    assert client.post(f"/api/v1/conversations/{identity}/confirm-ground-truth", json={"confirmed_memory_ids":[item['memory_id'] for item in memories]}).status_code == 200
    return identity


def test_manual_fact_uses_its_authorised_source_timestamp(client):
    source=client.post('/api/v1/conversations',json={'authorised':True,'messages':[{'message_id':'dated-source','role':'user','content':'我在家办公。','timestamp':'2025-02-03T10:20:00Z'}]}).json()
    result=client.post('/api/v1/memories',json={'conversation_id':source['conversation_id'],'canonical_value':'I work from home.','source_message_ids':['dated-source']})
    assert result.status_code==201,result.text
    assert result.json()['timestamp'].startswith('2025-02-03T10:20:00')
    invalid=client.post('/api/v1/memories',json={'conversation_id':source['conversation_id'],'canonical_value':'An unsupported reference.','source_message_ids':['another-history']})
    assert invalid.status_code==422


def run(client, *, paired=False, profile=None, capacity=50, strategy="weak_first_hit"):
    identity=history(client,"[User] Atlas project used MySQL before.\n[User] Atlas project now uses PostgreSQL.\n[User] Birch project uses MongoDB.\n[User] I prefer Python.\n[User] The assignment requires Java.")
    group=client.post('/api/v1/experiments',json={'conversation_id':identity,'label':'Unit fixture only','test_suite_configuration':{'suite_mode':'paired_contextual' if paired else 'behavioural','test_budget':6}}).json()
    body={'conversation_id':identity,'experiment_id':group['experiment_id'],'target_configuration':'weak','provider':'rule_based','memory_strategy':strategy,'target_memory_capacity':capacity}
    if profile:
        body['target_memory_profile']=profile
    audit=client.post('/api/v1/audits',json=body)
    assert audit.status_code==201,audit.text
    key=audit.json()['run_id']
    generated=client.post(f'/api/v1/audits/{key}/generate-tests')
    assert generated.status_code==200,generated.text
    assert client.post(f'/api/v1/audits/{key}/execute').status_code==200
    assert client.post(f'/api/v1/audits/{key}/evaluate').status_code==200
    return audit.json(),generated.json()


def test_frozen_profile_and_server_blindness(client):
    audit,tests=run(client,profile={'label':'Scoped v2','version':2,'isolate_project_scope':True,'prefer_current_state':True,'additional_instructions':'Never invent project history.'})
    assert audit['target_memory_profile']['label']=='Scoped v2'
    assert audit['reproducibility']['target_memory_profile']['additional_instructions']=='Never invent project history.'
    original=client.get(f"/api/v1/audits/{audit['run_id']}/evaluation-review").json()
    blind=client.get(f"/api/v1/audits/{audit['run_id']}/blind-review").json()
    assert len(blind)==len(tests)
    assert set(blind[0]['test']) == {'test_id', 'prompt', 'expected_behavior'}
    assert set(blind[0]['automated'])=={'evaluation_id'}
    assert set(blind[0]['response'])=={'response_text'}
    assert blind[0]['human_reviews']==[]
    assert blind[0]['source_statements']
    assert set(blind[0]['source_statements'][0]) == {'content','timestamp'}
    assert original[0]['automated']['passed'] in (True,False)
    report=client.get('/api/v1/auditor-quality').json()
    assert report['resolved_reference_count']==0
    assert report['accuracy']['percentage'] is None
    assert report['evidence_status']=='not_calibrated'


def test_paired_grouping_and_repair_preserves_exact_questions(client):
    audit,tests=run(client,paired=True)
    assert len(tests)%2==0
    assert all(item['probe_group_id'] for item in tests)
    key=audit['run_id']
    diagnostic=client.get(f'/api/v1/audits/{key}/diagnosis')
    assert diagnostic.status_code==200,diagnostic.text
    assert diagnostic.json()['paired_probes']['complete_groups']==len(tests)//2
    package=client.post(f'/api/v1/audits/{key}/repair-experiment',json={'targeted_profile':diagnostic.json()['suggested_profile'],'diagnosis_note':'Use current facts within the matching project.'})
    assert package.status_code==201,package.text
    for condition in package.json()['runs']:
        reviewed=client.get(f"/api/v1/audits/{condition['run_id']}/tests").json()
        assert sorted((item['prompt'],item['expected_behavior'],item['probe_group_id']) for item in reviewed)==sorted((item['prompt'],item['expected_behavior'],item['probe_group_id']) for item in tests)
        assert client.post(f"/api/v1/audits/{condition['run_id']}/execute").status_code==200
        assert client.post(f"/api/v1/audits/{condition['run_id']}/evaluate").status_code==200
    left,right=package.json()['runs'][0]['run_id'],package.json()['runs'][-1]['run_id']
    comparison=client.get(f'/api/v1/audit-comparisons?before={left}&after={right}')
    assert comparison.status_code==200,comparison.text
    assert len(comparison.json()['paired_tests'])==len(tests)


def test_uncertain_is_not_a_failure_or_a_scored_case(client):
    audit,tests=run(client)
    with client.sessions() as db:
        row=db.scalar(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id==audit['run_id']))
        row.passed=None;row.failure_type=None;db.commit()
    result=client.get(f"/api/v1/audits/{audit['run_id']}/results").json()
    assert result['uncertain_count']==1
    assert result['evaluated_count']==len(tests)
    assert result['tests_total']==len(tests)-1
    assert all(item['evaluation']['passed'] is False for item in result['failures'])


def test_validation_rejects_reused_history_before_creating_runs(client):
    audit,_=run(client)
    with client.sessions() as db:
        before=db.query(AuditRunModel).count()
    response=client.post(f"/api/v1/audits/{audit['run_id']}/repair-experiment",json={'targeted_profile':TargetMemoryProfile().model_dump(),'diagnosis_note':'General repair rules only, no expected answers.','validation_conversation_id':audit['conversation_id']})
    assert response.status_code==422
    with client.sessions() as db:
        assert db.query(AuditRunModel).count()==before


def test_three_intervention_conditions_keep_separate_evidence(client):
    audit,tests=run(client)
    response=client.post(f"/api/v1/audits/{audit['run_id']}/interventions")
    assert response.status_code==201,response.text
    runs=response.json()['runs']
    assert len(runs)==3
    for item in runs:
        key=item['run_id']
        execution=client.post(f'/api/v1/audits/{key}/execute')
        assert execution.status_code==200,execution.text
        if item['label']=='Remove supplied memory':
            assert all(answer['execution_metadata']['memory_input']['record_count']==0 for answer in execution.json())
        if item['label']=='Supplement source evidence':
            assert all(answer['execution_metadata']['memory_input']['record_count']==1 for answer in execution.json())
            assert client.get(f'/api/v1/audits/{key}').json()['target_configuration'] == audit['target_configuration']
        assert client.post(f'/api/v1/audits/{key}/evaluate').status_code==200
        saved=client.get(f'/api/v1/audits/{key}').json()
        assert saved['reproducibility']['study_role']=='diagnostic_intervention'
        if item['label']=='Supplement source evidence':
            trace=client.get(f'/api/v1/audits/{key}/target-memory-trace').json()
            packets={record['memory_id'] for record in trace['records'] if record['lifecycle_state']=='DIAGNOSTIC_ONLY'}
            assert packets
            assert all(not entry['eligible'] for retrieval in trace['retrievals'] for entry in retrieval['ranking_evidence'] if entry['memory_id'] in packets)


def test_method_comparison_has_distinct_suites_equal_caps(client):
    audit,_=run(client)
    response=client.post(f"/api/v1/audits/{audit['run_id']}/method-comparison")
    assert response.status_code==201,response.text
    suites=[]
    for condition in response.json()['runs']:
        generated=client.post(f"/api/v1/audits/{condition['run_id']}/generate-tests")
        assert generated.status_code==200,generated.text
        suites.append(generated.json())
        saved=client.get(f"/api/v1/audits/{condition['run_id']}").json()
        assert saved['test_budget']==audit['test_budget']
    assert len({suite[0]['generator_version'] for suite in suites})==3


def test_replay_review_never_mutates_completed_source(client):
    audit, tests = run(client, paired=True)
    key = audit['run_id']
    before = client.get(f'/api/v1/audits/{key}/tests').json()
    profile = client.get(f'/api/v1/audits/{key}/diagnosis').json()['suggested_profile']
    package = client.post(f'/api/v1/audits/{key}/repair-experiment', json={
        'targeted_profile': profile, 'diagnosis_note': 'General retrieval change without copying expected values.'}).json()
    replay = package['runs'][0]['run_id']
    cases = client.get(f'/api/v1/audits/{replay}/tests').json()
    changed = client.patch(f"/api/v1/audits/{replay}/tests/{cases[0]['test_id']}/review", json={'quality_status':'rejected'})
    assert changed.status_code == 200, changed.text
    assert client.get(f'/api/v1/audits/{key}/tests').json() == before
    for condition in package['runs'][1:]:
        other = client.get(f"/api/v1/audits/{condition['run_id']}/tests").json()
        assert sum(item['quality_status'] == 'rejected' for item in other) == 1
    assert client.patch(f"/api/v1/audits/{replay}/tests/{cases[0]['test_id']}/review", json={'quality_status':'accepted'}).status_code == 200
    assert client.post(f'/api/v1/audits/{replay}/execute').status_code == 200
    pending = package['runs'][1]['run_id']
    readable = client.get(f'/api/v1/audits/{pending}/test-review')
    assert readable.status_code == 200, readable.text
    assert len(readable.json()['tests']) == len(cases)
    frozen = client.patch(f"/api/v1/audits/{pending}/tests/{cases[0]['test_id']}/review", json={'quality_status':'accepted'})
    assert frozen.status_code == 409


def test_paired_minimum_budget_is_explicit():
    from pydantic import ValidationError
    from app.schemas import TestSuiteConfiguration
    with pytest.raises(ValidationError, match='at least two'):
        TestSuiteConfiguration(suite_mode='paired_contextual', test_budget=1)


def test_contextual_requirement_with_unresolved_conflict_demands_clarification(client):
    from app.extraction.rule_based import RuleBasedMemoryExtractor
    from app.test_generator.rule_based import RuleBasedTestGenerator
    from app.schemas import Conversation, ConversationMessage, AuditRun
    now = datetime.now(timezone.utc)
    conversation = Conversation(conversation_id='C', authorised=True, created_at=now, messages=[
        ConversationMessage(message_id=str(index), role='user', content=text, timestamp=now)
        for index, text in enumerate(['I generally prefer Rust.', 'The current assignment requires Rust.',
            'The assignment must not use Rust because its requirements conflict.'])])
    audit = AuditRun(run_id='R', conversation_id='C', status='CREATED', target_configuration='strong',
        provider='rule_based', model='test', temperature=0, random_seed=42, test_budget=20,
        prompt_template_version='test', created_at=now)
    tests = RuleBasedTestGenerator().generate(RuleBasedMemoryExtractor().extract(conversation), audit)
    task = next(test for test in tests if test.dimension.value == 'appropriate_use')
    assert 'clarification' in task.expected_behavior
    assert len(task.supporting_memory_ids) == 3


def test_targeted_strategy_changes_only_candidate_and_freezes_profile(client):
    audit,_=run(client)
    profile=client.get(f"/api/v1/audits/{audit['run_id']}/diagnosis").json()['suggested_profile']
    package=client.post(f"/api/v1/audits/{audit['run_id']}/repair-experiment",json={
        'targeted_profile':profile,'targeted_memory_strategy':'scope_aware',
        'diagnosis_note':'Retrieve all relevant constraints within the current task scope.'}).json()
    strategies=[client.get(f"/api/v1/audits/{item['run_id']}").json()['memory_strategy'] for item in package['runs']]
    assert strategies==['weak_first_hit','weak_first_hit','scope_aware']
    configurations=[client.get(f"/api/v1/audits/{item['run_id']}").json()['target_configuration'] for item in package['runs']]
    assert configurations==['weak','weak','strong']


def test_failure_reports_expose_ordered_original_source_only_from_own_history(client):
    audit, _ = run(client)
    # The other history deliberately reuses pasted message IDs.
    assert client.post('/api/v1/conversations', json={'authorised': True, 'pasted_text': '[User] Private unrelated project uses SecretStore.'}).status_code == 201
    report = client.get(f"/api/v1/audits/{audit['run_id']}/results").json()
    assert report['failures']
    for failure in report['failures']:
        assert failure['source_statements']
        assert all(set(source) == {'role', 'content', 'timestamp'} for source in failure['source_statements'])
        assert all('SecretStore' not in source['content'] for source in failure['source_statements'])
        dates = [source['timestamp'] for source in failure['source_statements']]
        assert dates == sorted(dates)
        assert len(dates) == len(set(dates))


def test_formal_overall_requires_every_core_dimension(client):
    audit, _ = run(client)
    with client.sessions() as db:
        for test in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == audit['run_id'])):
            test.dimension = 'accuracy'
        db.commit()
    report = client.get(f"/api/v1/audits/{audit['run_id']}/results").json()
    assert report['overall_score'] is not None
    assert report['formal_overall_score'] is None


def test_ruby_preference_and_go_requirement_generate_appropriate_use_probe(client):
    identity = history(client, '[User] I prefer Ruby.\n[User] The Lantern assignment requires Go.')
    memories = client.get(f'/api/v1/conversations/{identity}/memories').json()
    assert any(relation['type'] == 'CONTEXTUAL_OVERRIDE' for memory in memories for relation in memory['relationships'])
    audit = client.post('/api/v1/audits', json={'conversation_id':identity,'target_configuration':'weak','provider':'rule_based','memory_strategy':'weak_first_hit'}).json()
    tests = client.post(f"/api/v1/audits/{audit['run_id']}/generate-tests").json()
    applicable = [test for test in tests if test['dimension'] == 'appropriate_use']
    assert applicable
    assert all('Go' not in test['prompt'] and 'Ruby' not in test['prompt'] for test in applicable)


def test_diagnosis_does_not_equate_shared_source_with_shared_fact(client):
    from app.models import TargetAgentMemoryModel, MemoryModel
    audit, _ = run(client)
    with client.sessions() as db:
        references = db.scalars(select(MemoryModel)).all()
        sources = sorted({source for r in references for source in r.source_message_ids})
        for row in db.scalars(select(TargetAgentMemoryModel).where(TargetAgentMemoryModel.run_id==audit['run_id'])).all():
            row.source_message_ids=sources
            row.canonical_value='Different fact from the same source'
        db.commit()
    result=client.get(f"/api/v1/audits/{audit['run_id']}/diagnosis").json()
    assert result['diagnosis_version']=='fact-aware-diagnosis-v8'
    failures=[v for v in result['cases'] if v['automated_passed'] is False]
    assert failures
    assert all(v['layer']=='fact_correspondence_review' for v in failures)
    assert all(v['fact_correspondence']['stored_fact_units']==0 for v in failures)
    assert all(v['stored_source_coverage']==v['supporting_source_count'] for v in failures)


def test_supplied_current_fact_and_excluded_history_reviews_both_answer_and_context(client):
    audit, _ = run(client, strategy='full_context')
    with client.sessions() as db:
        case = db.scalar(select(TestCaseModel).where(
            TestCaseModel.run_id == audit['run_id'], TestCaseModel.dimension == 'freshness'))
        case_id = case.id
        verdict = db.scalar(select(EvaluationResultModel).where(EvaluationResultModel.test_id == case_id))
        verdict.passed = False
        verdict.reason = 'Wrong database value despite the supplied current fact.'
        db.commit()
    result = client.get(f"/api/v1/audits/{audit['run_id']}/diagnosis").json()
    case = next(row for row in result['cases'] if row['test_id'] == case_id)
    assert case['fact_correspondence']['supplied_fact_units'] == 1
    assert case['memory_availability']['other_excluded_fact_units'] == 1
    assert case['layer'] == 'answer_and_history_review'
    assert 'newer' in case['explanation'] and 'assessment' in case['explanation']
    assert result['suggested_memory_strategy'] == 'full_context'
    assert result['suggested_memory_capacity'] == 50
    assert result['suggested_profile'] == audit['target_memory_profile']


@pytest.mark.parametrize('eligibility', ['unknown', 'capacity', 'current_missing', 'no_update_link'])
def test_history_review_never_conceals_other_missing_evidence(client, eligibility):
    from app.models import TargetAgentMemoryModel, TargetAgentRetrievalModel, TargetResponseModel, MemoryRelationshipModel
    audit, _ = run(client, strategy='full_context')
    with client.sessions() as db:
        test = db.scalar(select(TestCaseModel).where(
            TestCaseModel.run_id == audit['run_id'], TestCaseModel.dimension == 'freshness'))
        test_id = test.id
        db.scalar(select(EvaluationResultModel).where(EvaluationResultModel.test_id == test_id)).passed = False
        trace = db.scalar(select(TargetAgentRetrievalModel).where(TargetAgentRetrievalModel.test_id == test_id))
        rows = list(db.scalars(select(TargetAgentMemoryModel).where(TargetAgentMemoryModel.run_id == audit['run_id'])))
        old = next(row for row in rows if 'Atlas project used MySQL' in row.canonical_value)
        assert any('Atlas project now uses PostgreSQL' in row.canonical_value for row in rows)
        if eligibility == 'no_update_link':
            for relationship in db.scalars(select(MemoryRelationshipModel).where(
                    MemoryRelationshipModel.memory_id.in_(test.supporting_memory_ids))):
                db.delete(relationship)
        elif eligibility == 'current_missing':
            response = db.get(TargetResponseModel, trace.final_response_id)
            metadata = dict(response.execution_metadata)
            receipt = dict(metadata['memory_input'])
            receipt['sent_memory_ids'] = [old.id]
            receipt['record_count'] = 1
            metadata['memory_input'] = receipt
            response.execution_metadata = metadata
        else:
            ranking = [dict(row) for row in trace.ranking_evidence]
            if eligibility == 'unknown':
                ranking = [row for row in ranking if row['memory_id'] != old.id]
            else:
                next(row for row in ranking if row['memory_id'] == old.id)['reason'] = 'capacity_evicted_excluded'
            trace.ranking_evidence = ranking
        db.commit()
    result = client.get(f"/api/v1/audits/{audit['run_id']}/diagnosis").json()
    case = next(row for row in result['cases'] if row['test_id'] == test_id)
    assert case['layer'] != 'answer_and_history_review'


def test_evicted_support_is_retention_hypothesis_not_retrieval(client):
    audit, _ = run(client,capacity=1)
    from app.models import TargetAgentMemoryModel
    with client.sessions() as db:
        assert any(r.lifecycle_state=='EVICTED' for r in db.scalars(select(TargetAgentMemoryModel).where(TargetAgentMemoryModel.run_id==audit['run_id'])))
    result=client.get(f"/api/v1/audits/{audit['run_id']}/diagnosis").json()
    candidates=[r for r in result['cases'] if r['automated_passed'] is False and r['fact_correspondence']['complete_stored_match'] and not r['fact_correspondence']['complete_supplied_match']]
    assert candidates
    assert any(r['layer']=='retention_hypothesis' for r in candidates),candidates
    assert result['source_memory_capacity']==1
    assert result['suggested_memory_capacity']>1
    assert result['suggested_memory_strategy']=='weak_first_hit'


def test_capacity_repair_changes_only_candidate_budget_and_keeps_reader(client):
    audit,_=run(client,capacity=1)
    # A source can intentionally use a strong reader with first-hit retrieval;
    # selecting its same strategy must not silently switch the reader to weak.
    with client.sessions() as db:
        db.get(AuditRunModel,audit['run_id']).target_configuration='strong'
        db.commit()
    profile=client.get(f"/api/v1/audits/{audit['run_id']}/diagnosis").json()['suggested_profile']
    package=client.post(f"/api/v1/audits/{audit['run_id']}/repair-experiment",json={
        'targeted_profile':profile,'targeted_memory_strategy':'weak_first_hit','targeted_memory_capacity':5,
        'diagnosis_note':'Restore capacity only; do not change retrieval or reader policy.'})
    assert package.status_code==201,package.text
    runs=[client.get(f"/api/v1/audits/{r['run_id']}").json() for r in package.json()['runs']]
    assert [r['target_memory_capacity'] for r in runs]==[1,1,5]
    assert all(r['target_configuration']=='strong' and r['memory_strategy']=='weak_first_hit' for r in runs)
    assert client.get(f"/api/v1/audits/{audit['run_id']}").json()['target_memory_capacity']==1
    for invalid in [0,501,1.2,True,'5']:
        assert client.post(f"/api/v1/audits/{audit['run_id']}/repair-experiment",json={
            'targeted_profile':profile,'targeted_memory_capacity':invalid,'diagnosis_note':'Invalid candidate capacity must not start an experiment.'}).status_code==422


def test_legacy_eligibility_does_not_infer_retention_from_current_evicted_state(client):
    from app.models import TargetAgentRetrievalModel
    audit,_=run(client,capacity=1)
    with client.sessions() as db:
        for row in db.scalars(select(TargetAgentRetrievalModel).where(TargetAgentRetrievalModel.run_id==audit['run_id'])):
            row.ranking_evidence=[]
        db.commit()
    result=client.get(f"/api/v1/audits/{audit['run_id']}/diagnosis").json()
    candidates=[r for r in result['cases'] if r['automated_passed'] is False and r['fact_correspondence']['complete_stored_match'] and not r['fact_correspondence']['complete_supplied_match']]
    assert candidates and all(r['layer']=='availability_review' for r in candidates)


@pytest.mark.parametrize('defect', ['missing_reference', 'partial_reference', 'missing_source', 'unknown_source', 'empty_fact'])
@pytest.mark.parametrize('verdict', [True, False, None])
def test_diagnosis_preserves_cases_with_incomplete_reference_provenance(client, defect, verdict):
    """Legacy/corrupt reference evidence must not disappear or imply an internal cause."""
    from app.models import MemoryModel
    audit, _ = run(client)
    with client.sessions() as db:
        case = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == audit['run_id']).order_by(TestCaseModel.id))
        case_id = case.id
        evaluation = db.scalar(select(EvaluationResultModel).where(EvaluationResultModel.test_id == case_id))
        evaluation.passed = verdict
        evaluation.failure_type = None
        if defect == 'missing_reference':
            case.supporting_memory_ids = ['nonexistent-reference']
        elif defect == 'partial_reference':
            case.supporting_memory_ids = [*case.supporting_memory_ids, 'nonexistent-reference']
        else:
            reference = db.get(MemoryModel, case.supporting_memory_ids[0])
            if defect == 'missing_source':
                reference.source_message_ids = []
            elif defect == 'unknown_source':
                reference.source_message_ids = ['not-an-authorised-source']
            else:
                reference.canonical_value = ''
        db.commit()
    response = client.get(f"/api/v1/audits/{audit['run_id']}/diagnosis")
    assert response.status_code == 200, response.text
    cases = [case for case in response.json()['cases'] if case['test_id'] == case_id]
    assert len(cases) == 1
    assert cases[0]['automated_passed'] is verdict
    assert cases[0]['layer'] == ('unobserved_pass' if verdict is True else 'unobserved' if verdict is False else 'uncertain_assessment')
    assert cases[0]['reference_provenance']['complete'] is False


def test_uncertain_diagnosis_does_not_propose_unrelated_policy_changes(client):
    profile = TargetMemoryProfile(label='Existing reviewed rules', version=3,
        additional_instructions='Keep customer boundaries intact. Do not disclose another customer record.')
    audit, _ = run(client, profile=profile.model_dump())
    with client.sessions() as db:
        for row in db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id == audit['run_id'])):
            row.passed = None
            row.failure_type = None
        db.commit()
    result = client.get(f"/api/v1/audits/{audit['run_id']}/diagnosis").json()
    assert result['suggested_profile'] == profile.model_dump()
    assert result['suggested_memory_strategy'] == 'weak_first_hit'
    assert result['suggested_memory_capacity'] == audit['target_memory_capacity']
    assert result['repair_recommendation']['status'] == 'requires_review'


def test_retrieved_support_omitted_from_final_input_is_not_a_retrieval_miss(client):
    from app.models import TargetAgentMemoryModel, TargetAgentRetrievalModel, TargetResponseModel
    audit, _ = run(client)
    with client.sessions() as db:
        case = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == audit['run_id']).order_by(TestCaseModel.id))
        key = case.id
        records = db.scalars(select(TargetAgentMemoryModel).where(TargetAgentMemoryModel.run_id == audit['run_id'])).all()
        retrieval = db.scalar(select(TargetAgentRetrievalModel).where(TargetAgentRetrievalModel.test_id == key))
        retrieval.selected_memory_ids = [record.id for record in records]
        response = db.get(TargetResponseModel, retrieval.final_response_id)
        metadata = dict(response.execution_metadata)
        metadata['memory_input'] = {**metadata['memory_input'], 'sent_memory_ids': [], 'record_count': 0}
        response.execution_metadata = metadata
        verdict = db.scalar(select(EvaluationResultModel).where(EvaluationResultModel.test_id == key))
        verdict.passed = False
        db.commit()
    result = client.get(f"/api/v1/audits/{audit['run_id']}/diagnosis").json()
    case = next(item for item in result['cases'] if item['test_id'] == key)
    assert case['layer'] == 'input_delivery_review'
    assert case['input_delivery']['complete_retrieved_match'] is True
    assert case['input_delivery']['selected_not_supplied_fact_units'] > 0


def test_profile_context_limit_is_not_a_retrieval_policy_miss(client):
    audit, _ = run(client, profile=TargetMemoryProfile(max_retrieved_records=1).model_dump())
    from app.models import TargetAgentMemoryModel, TargetAgentRetrievalModel, TargetResponseModel
    with client.sessions() as db:
        # Isolate this diagnostic case: other real first-hit failures in the
        # fixture can legitimately support their own retrieval candidate.
        for evaluation in db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id == audit['run_id'])):
            evaluation.passed = None
            evaluation.failure_type = None
        case = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == audit['run_id']).order_by(TestCaseModel.id))
        key = case.id
        records = db.scalars(select(TargetAgentMemoryModel).where(TargetAgentMemoryModel.run_id == audit['run_id'])).all()
        retrieval = db.scalar(select(TargetAgentRetrievalModel).where(TargetAgentRetrievalModel.test_id == key))
        retrieval.selected_memory_ids = []
        retrieval.ranking_evidence = [{'memory_id':record.id, 'eligible':True, 'selected':False,
            'reason':'profile_context_budget_excluded'} for record in records]
        response = db.get(TargetResponseModel, retrieval.final_response_id)
        metadata = dict(response.execution_metadata)
        metadata['memory_input'] = {**metadata['memory_input'], 'sent_memory_ids':[], 'record_count':0}
        response.execution_metadata = metadata
        verdict = db.scalar(select(EvaluationResultModel).where(EvaluationResultModel.test_id == key))
        verdict.passed = False
        db.commit()
    result = client.get(f"/api/v1/audits/{audit['run_id']}/diagnosis").json()
    case = next(item for item in result['cases'] if item['test_id'] == key)
    assert case['layer'] == 'context_budget_review'
    assert result['suggested_memory_strategy'] == audit['memory_strategy']
    assert result['suggested_profile']['max_retrieved_records'] == 1


def test_declared_no_memory_reference_is_not_a_retrieval_defect(client):
    audit, _ = run(client, strategy='no_memory')
    result = client.get(f"/api/v1/audits/{audit['run_id']}/diagnosis").json()
    assert result['cases']
    assert {case['layer'] for case in result['cases']} == {'no_memory_reference'}
    assert all(case['automated_passed'] is False for case in result['cases'])
    assert result['suggested_memory_strategy'] == 'no_memory'
    assert result['suggested_profile'] == audit['target_memory_profile']
    assert result['repair_recommendation']['status'] == 'baseline_reference'

def test_declared_no_memory_does_not_hide_unobserved_input(client):
    from app.models import TargetResponseModel
    audit, _ = run(client, strategy='no_memory')
    with client.sessions() as db:
        for response in db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == audit['run_id'])):
            metadata = dict(response.execution_metadata)
            metadata.pop('memory_input', None)
            response.execution_metadata = metadata
        db.commit()
    result = client.get(f"/api/v1/audits/{audit['run_id']}/diagnosis").json()
    assert {case['layer'] for case in result['cases']} == {'unobserved'}

def test_correct_no_memory_answer_stays_unattributed_not_a_baseline_failure(client):
    audit, _ = run(client, strategy='no_memory')
    with client.sessions() as db:
        for row in db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id == audit['run_id'])):
            row.passed = True
        db.commit()
    result = client.get(f"/api/v1/audits/{audit['run_id']}/diagnosis").json()
    assert {case['layer'] for case in result['cases']} == {'unattributed_pass'}
    assert all(case['automated_passed'] is True for case in result['cases'])

@pytest.mark.parametrize('attempts,expected,unknown', [(3,3,0),(0,0,0),(None,None,1),(True,None,1),(-1,None,1),('3',None,1)])
def test_method_budget_counts_recorded_attempts_not_saved_answers(client, attempts, expected, unknown):
    from app.models import TargetResponseModel
    source,_=run(client)
    package=client.post(f"/api/v1/audits/{source['run_id']}/method-comparison").json()
    key=package['runs'][0]['run_id']
    assert client.post(f'/api/v1/audits/{key}/generate-tests').status_code==200
    assert client.post(f'/api/v1/audits/{key}/execute').status_code==200
    assert client.post(f'/api/v1/audits/{key}/evaluate').status_code==200
    with client.sessions() as db:
        rows=db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id==key)).all()
        for i,row in enumerate(rows):
            row.execution_metadata={} if i==0 and attempts is None else {'request_attempts': attempts if i==0 else 0}
        answer_count=len(rows)
        db.commit()
    report=client.get(f"/api/v1/audits/{source['run_id']}/method-comparison-results").json()
    condition=next(x for x in report['conditions'] if x['run_id']==key)
    assert condition['actual_calls']==expected
    assert condition['completed_answers']==answer_count
    assert condition['unknown_attempt_records']==unknown
    assert condition['recorded_request_attempts']==expected
