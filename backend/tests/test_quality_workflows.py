"""Executable contracts for reliability, profiles and diagnostic studies."""
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database.session import Base, get_db
from app.models import AuditRunModel, EvaluationResultModel, EvaluationHumanReviewModel, TestCaseModel, MemoryModel
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


def confirm_method_test_validity(client, run_id, reviewer='Synthetic method reviewer'):
    tests = client.get(f'/api/v1/audits/{run_id}/tests').json()
    for test in tests:
        response = client.patch(f"/api/v1/audits/{run_id}/tests/{test['test_id']}/human-validity-review", json={
            'decision': 'accepted', 'reviewer_pseudonym': reviewer,
            'note': 'Synthetic API fixture; not human research evidence.'})
        assert response.status_code == 200, response.text
    return tests


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
    assert set(blind[0]['source_statements'][0]) == {'role','content','timestamp'}
    packet=client.get(f"/api/v1/audits/{audit['run_id']}/blind-review-pack").json()
    assert len(packet['items'])==len(tests)
    assert packet['completed_independently_by_human'] is False
    assert all(item['human_passed'] is None for item in packet['items'])
    assert all(set(item)=={'item_id','question','proposed_reference_behavior','response','human_passed','human_failure_type','corrected_reference_behavior','decision_note'} for item in packet['items'])
    assert packet['packet_sha256']==client.get(f"/api/v1/audits/{audit['run_id']}/blind-review-pack").json()['packet_sha256']
    assert packet['source_statements']==blind[0]['source_statements']
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
        row.passed=None;row.failure_type=None;row.evidence_memory_ids=[];row.reason='The saved target output was truncated; review the original answer.';db.commit()
        uncertain_id=row.id
    result=client.get(f"/api/v1/audits/{audit['run_id']}/results").json()
    assert result['uncertain_count']==1
    assert result['evaluated_count']==len(tests)
    assert result['tests_total']==len(tests)-1
    assert all(item['evaluation']['passed'] is False for item in result['failures'])
    assert len(result['uncertain_answers'])==1
    pending=result['uncertain_answers'][0]
    assert pending['evaluation']['evaluation_id']==uncertain_id
    assert pending['evaluation']['passed'] is None
    assert pending['evaluation']['reason']=='The saved target output was truncated; review the original answer.'
    assert pending['response']['response_text']
    assert pending['source_statements']
    assert pending['evidence']
    assert pending['evaluation']['evidence_memory_ids']==[]
    assert 'target_memory_context' not in pending['test']
    assert 'failure_id' not in pending
    with client.sessions() as db:
        assert db.get(EvaluationResultModel,uncertain_id).passed is None


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
    audit,source_tests=run(client)
    response=client.post(f"/api/v1/audits/{audit['run_id']}/method-comparison")
    assert response.status_code==201,response.text
    plan=response.json()
    # The same-source defect inventory must be frozen before the first suite is generated.
    blocked=client.post(f"/api/v1/audits/{plan['runs'][0]['run_id']}/generate-tests")
    assert blocked.status_code==409
    memories=client.get(f"/api/v1/conversations/{audit['conversation_id']}/memories").json()
    memories_by_id={memory['memory_id']:memory for memory in memories}
    initial_template=plan['inventory_template']['fixed_template_questions'][0]
    supporting_ids=initial_template['supporting_memory_ids']
    source_ids=sorted({source_id for memory_id in supporting_ids for source_id in memories_by_id[memory_id]['source_message_ids']})
    inventory=plan['inventory_template']
    assert inventory['fixed_template_draft_generator_version']=='fixed-template-v2'
    assert len(inventory['fixed_template_draft_fingerprint_sha256'])==64
    assert inventory['fixed_template_review_confirmed'] is False
    inventory.update({"release_id":"test-fixture-release","reviewers":["Reviewer A","Reviewer B"],
        "defects":[{"defect_id":"D001","dimension":initial_template['dimension'],
            "supporting_memory_ids":supporting_ids,"source_message_ids":source_ids,
            "explanation":"A synthetic labelled failure for exercising the frozen inventory contract."},
            {"defect_id":"D002","dimension":initial_template['dimension'],
            "supporting_memory_ids":supporting_ids,"source_message_ids":source_ids,
            "explanation":"A second synthetic incident sharing the same evidence family."}],
        "fixed_template_release_id":"test-fixed-template-v1","fixed_template_reviewers":["Researcher A"],
        "fixed_template_review_confirmed":True,
        "fixed_template_questions":[{"template_id":f"MFT-{index+1:03d}","dimension":test['dimension'],
            "prompt":f"Researcher reviewed and edited: {test['prompt']}","expected_behavior":test['expected_behavior'],
            "supporting_memory_ids":test['supporting_memory_ids'],
            "source_message_ids":sorted({source_id for memory_id in test['supporting_memory_ids'] for source_id in memories_by_id[memory_id]['source_message_ids']}),
            "test_type":test['test_type']} for index,test in enumerate(plan['inventory_template']['fixed_template_questions'])]})
    unconfirmed={**inventory,"fixed_template_review_confirmed":False}
    rejected=client.post(f"/api/v1/audits/{audit['run_id']}/method-comparison-inventory",json=unconfirmed)
    assert rejected.status_code==422
    stale_draft={**inventory,"fixed_template_draft_fingerprint_sha256":"0"*64}
    rejected=client.post(f"/api/v1/audits/{audit['run_id']}/method-comparison-inventory",json=stale_draft)
    assert rejected.status_code==409
    short_templates={**inventory,"fixed_template_questions":inventory['fixed_template_questions'][:-1]}
    rejected=client.post(f"/api/v1/audits/{audit['run_id']}/method-comparison-inventory",json=short_templates)
    assert rejected.status_code==422
    frozen=client.post(f"/api/v1/audits/{audit['run_id']}/method-comparison-inventory",json=inventory)
    assert frozen.status_code==201,frozen.text
    assert frozen.json()['status']=='frozen'
    with client.sessions() as db:
        changed_memory=db.get(MemoryModel,supporting_ids[0])
        original_confidence=changed_memory.confidence
        changed_memory.confidence=0.5 if original_confidence is None else original_confidence+0.01
        db.commit()
    drift=client.post(f"/api/v1/audits/{plan['runs'][0]['run_id']}/generate-tests")
    assert drift.status_code==409
    with client.sessions() as db:
        db.get(MemoryModel,supporting_ids[0]).confidence=original_confidence
        db.commit()
    suites=[]
    for condition in plan['runs']:
        generated=client.post(f"/api/v1/audits/{condition['run_id']}/generate-tests")
        assert generated.status_code==200,generated.text
        suites.append(generated.json())
        if condition['label']=='Fixed templates':
            assert len(generated.json())==audit['test_budget']
            assert all(test['generator_version']=='human-reviewed-fixed-template-v1' for test in generated.json())
            assert generated.json()[0]['prompt']==inventory['fixed_template_questions'][0]['prompt']
        if condition['label']=='Contextual/indirect Auditor tests':
            assert all(test['test_type'] in {'contextual','indirect'} for test in generated.json())
            assert all(test['test_type']!='direct' for test in generated.json())
        saved=client.get(f"/api/v1/audits/{condition['run_id']}").json()
        assert saved['test_budget']==audit['test_budget']
        groups = client.get('/api/v1/experiments').json()
        child = next(item for item in groups if item['experiment_id'] == saved['experiment_id'])
        assert child['test_suite_metadata']['study_role'] == 'audit_method_comparison'
        assert child['test_suite_metadata']['diagnostic_source_run_id'] == audit['run_id']
    assert len({suite[0]['generator_version'] for suite in suites})==3
    report=client.get(f"/api/v1/audits/{audit['run_id']}/method-comparison-results?comparison_id={plan['comparison_id']}")
    assert report.status_code==200,report.text
    assert report.json()['inventory']['status']=='frozen'
    assert report.json()['inventory']['distinct_failure_count']==2
    assert report.json()['inventory']['fixed_template_question_count']==audit['test_budget']
    assert report.json()['inventory']['fixed_template_review_identity_verified'] is False
    assert report.json()['inventory']['fixed_template_review_confirmed'] is True
    assert report.json()['inventory']['fixed_template_draft_generator_version']=='fixed-template-v2'
    assert report.json()['inventory']['fixed_template_draft_fingerprint_sha256']==inventory['fixed_template_draft_fingerprint_sha256']
    assert report.json()['inventory']['fixed_template_final_fingerprint_sha256']
    assert report.json()['planned_test_budgets_equal'] is True
    assert report.json()['conditions'][0]['response_level']['failure_detection_recall'] is None
    unreviewed = report.json()['conditions'][0]
    assert unreviewed['valid_test_count'] == 0
    assert unreviewed['human_validity_reviewed_count'] == 0
    assert unreviewed['human_validity_pending_count'] == unreviewed['test_count']
    assert unreviewed['human_validity_acceptance_rate'] is None
    assert unreviewed['category_coverage']['value'] is None
    assert unreviewed['category_coverage']['status'] == 'awaiting_human_validity_review'
    fixed_condition=next(item for item in plan['runs'] if item['label']=='Fixed templates')
    fixed_run_id=fixed_condition['run_id']
    fixed_tests=client.get(f'/api/v1/audits/{fixed_run_id}/tests').json()
    # Automated quality acceptance cannot substitute for the distinct human
    # validity decision required by Experiment A.
    for test in fixed_tests:
        accepted_quality=client.patch(f"/api/v1/audits/{fixed_run_id}/tests/{test['test_id']}/review",
            json={'quality_status':'accepted','note':'Synthetic fixture quality approval.'})
        assert accepted_quality.status_code==200,accepted_quality.text
    blocked=client.post(f'/api/v1/audits/{fixed_run_id}/execute')
    assert blocked.status_code==409 and 'explicitly confirm every Experiment A question' in blocked.text
    empty_pseudonym=client.patch(f"/api/v1/audits/{fixed_run_id}/tests/{fixed_tests[0]['test_id']}/human-validity-review",
        json={'decision':'accepted','reviewer_pseudonym':'   '})
    assert empty_pseudonym.status_code==422
    for test in fixed_tests:
        validity=client.patch(f"/api/v1/audits/{fixed_run_id}/tests/{test['test_id']}/human-validity-review",
            json={'decision':'accepted','reviewer_pseudonym':'Synthetic reviewer','note':'Synthetic smoke only; not research evidence.'})
        assert validity.status_code==200,validity.text
        assert validity.json()['human_validity_status']=='accepted'
        assert validity.json()['human_validity_reviewer']=='Synthetic reviewer'
        assert validity.json()['human_validity_reviewed_at']
    assert client.post(f'/api/v1/audits/{fixed_run_id}/execute').status_code==200
    assert client.post(f'/api/v1/audits/{fixed_run_id}/evaluate').status_code==200
    known_template=inventory['fixed_template_questions'][0]
    known_signature=(known_template['dimension'],tuple(sorted(known_template['supporting_memory_ids'])))
    with client.sessions() as db:
        evaluations=db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id==fixed_run_id)).all()
        for evaluation in evaluations:
            test=db.get(TestCaseModel,evaluation.test_id)
            detected_signature=(test.dimension,tuple(sorted(test.supporting_memory_ids)))
            evaluation.passed=detected_signature!=known_signature
        db.commit()
    review_items=client.get(f'/api/v1/audits/{fixed_run_id}/evaluation-review').json()
    for item in review_items:
        is_known=(item['test']['dimension'],tuple(sorted(item['test']['supporting_memory_ids'])))==known_signature
        for reviewer in ('Blind A','Blind B'):
            label=client.patch(f"/api/v1/audits/{fixed_run_id}/evaluations/{item['automated']['evaluation_id']}/review",json={
                'human_passed':not is_known,'human_failure_type':known_template['dimension'] if is_known else None,
                'reviewer_label':reviewer,'review_role':'independent'})
            assert label.status_code==200,label.text
    measured=client.get(f"/api/v1/audits/{audit['run_id']}/method-comparison-results?comparison_id={plan['comparison_id']}").json()
    fixed_result=next(item for item in measured['conditions'] if item['run_id']==fixed_run_id)
    assert fixed_result['valid_test_count'] == fixed_result['test_count']
    assert fixed_result['human_validity_reviewed_count'] == fixed_result['test_count']
    assert fixed_result['human_validity_pending_count'] == 0
    assert fixed_result['human_validity_acceptance_rate'] == 1.0
    assert fixed_result['category_coverage']['status'] == 'measured'
    assert fixed_result['response_level']['failure_detection_recall']==1.0
    assert fixed_result['response_level']['false_positive_rate']==0.0
    assert fixed_result['failure_discovery_rate']['status']=='awaiting_researcher_mapping'
    assert fixed_result['failure_discovery_rate']['value'] is None
    discovery_entries=fixed_result['discovery_mapping']['entries']
    known_response_ids={item['response']['response_id'] for item in review_items if
        (item['test']['dimension'],tuple(sorted(item['test']['supporting_memory_ids'])))==known_signature}
    assert next(item for item in discovery_entries if item['response_id'] in known_response_ids)['human_passed'] is False
    mapping_entries=[{"response_id":entry['response_id'],"test_id":entry['test_id'],
        "defect_ids":["D001","D002"] if entry['response_id'] in known_response_ids else []}
        for entry in discovery_entries]
    mapping_payload={"schema_version":"mha-experiment-a-discovery-map-v1",
        "comparison_id":plan['comparison_id'],
        "inventory_fingerprint_sha256":measured['inventory']['fingerprint_sha256'],
        "mapping_release_id":"fixed-review-map-v1","reviewer_pseudonym":"Researcher mapper",
        "completed_by_human":True,"entries":mapping_entries}
    unconfirmed_mapping={**mapping_payload,"completed_by_human":False}
    rejected=client.post(f"/api/v1/audits/{fixed_run_id}/method-comparison-discovery-mapping",json=unconfirmed_mapping)
    assert rejected.status_code==422
    incomplete={**mapping_payload,"entries":mapping_entries[:-1]}
    rejected=client.post(f"/api/v1/audits/{fixed_run_id}/method-comparison-discovery-mapping",json=incomplete)
    assert rejected.status_code==422
    unknown={**mapping_payload,"entries":[{**mapping_entries[0],"defect_ids":["UNKNOWN"]},*mapping_entries[1:]]}
    rejected=client.post(f"/api/v1/audits/{fixed_run_id}/method-comparison-discovery-mapping",json=unknown)
    assert rejected.status_code==422
    mismatch={**mapping_payload,"entries":[{**mapping_entries[0],"test_id":"not-the-linked-test"},*mapping_entries[1:]]}
    rejected=client.post(f"/api/v1/audits/{fixed_run_id}/method-comparison-discovery-mapping",json=mismatch)
    assert rejected.status_code==422
    saved=client.post(f"/api/v1/audits/{fixed_run_id}/method-comparison-discovery-mapping",json=mapping_payload)
    assert saved.status_code==201,saved.text
    assert saved.json()['status']=='frozen'
    repeated=client.post(f"/api/v1/audits/{fixed_run_id}/method-comparison-discovery-mapping",json=mapping_payload)
    assert repeated.status_code==201 and repeated.json()['status']=='already_frozen'
    changed={**mapping_payload,"reviewer_pseudonym":"Different researcher"}
    rejected=client.post(f"/api/v1/audits/{fixed_run_id}/method-comparison-discovery-mapping",json=changed)
    assert rejected.status_code==409
    measured=client.get(f"/api/v1/audits/{audit['run_id']}/method-comparison-results?comparison_id={plan['comparison_id']}").json()
    fixed_result=next(item for item in measured['conditions'] if item['run_id']==fixed_run_id)
    assert fixed_result['failure_discovery_rate']['value']==1.0
    assert fixed_result['failure_discovery_rate']['discovered_distinct_failures']==2
    assert fixed_result['failure_discovery_rate']['undiscovered_failure_ids']==[]
    assert fixed_result['discovery_mapping']['status']=='frozen'
    assert fixed_result['discovery_mapping']['mapped_response_count']==fixed_result['completed_answers']
    assert fixed_result['response_level']['independently_labelled_responses']==fixed_result['completed_answers']


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
    source,source_tests=run(client)
    package=client.post(f"/api/v1/audits/{source['run_id']}/method-comparison").json()
    memories=client.get(f"/api/v1/conversations/{source['conversation_id']}/memories").json()
    memories_by_id={memory['memory_id']:memory for memory in memories}
    inventory=package['inventory_template']
    inventory.update({"release_id":"attempt-fixture-release","reviewers":["Reviewer A","Reviewer B"],"defects":[],
        "fixed_template_release_id":"attempt-fixture-template","fixed_template_reviewers":["Researcher A"],
        "fixed_template_review_confirmed":True,
        "fixed_template_questions":[{"template_id":f"MFT-{index+1:03d}","dimension":test['dimension'],
            "prompt":f"Researcher reviewed attempt fixture: {test['prompt']}","expected_behavior":test['expected_behavior'],
            "supporting_memory_ids":test['supporting_memory_ids'],
            "source_message_ids":sorted({source_id for memory_id in test['supporting_memory_ids'] for source_id in memories_by_id[memory_id]['source_message_ids']}),
            "test_type":test['test_type']} for index,test in enumerate(package['inventory_template']['fixed_template_questions'])]})
    frozen=client.post(f"/api/v1/audits/{source['run_id']}/method-comparison-inventory",json=inventory)
    assert frozen.status_code==201,frozen.text
    key=package['runs'][0]['run_id']
    assert client.post(f'/api/v1/audits/{key}/generate-tests').status_code==200
    confirm_method_test_validity(client, key)
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
    assert condition['actual_target_call_attempts']==expected
    assert condition['completed_answers']==answer_count
    assert condition['unknown_attempt_records']==unknown


def test_quality_methods_do_not_promote_single_references_to_independent_validation(client):
    audit,_=run(client)
    key=audit['run_id']
    with client.sessions() as db:
        row=db.get(AuditRunModel,key)
        row.reproducibility_metadata={**row.reproducibility_metadata,'auditor_method':'hybrid'}
        db.commit()
    reviewed=client.get(f'/api/v1/audits/{key}/evaluation-review').json()[0]
    endpoint=f"/api/v1/audits/{key}/evaluations/{reviewed['automated']['evaluation_id']}/review"
    assert client.patch(endpoint,json={'human_passed':True,'reviewer_label':'reference','review_role':'reference'}).status_code==200
    one=client.get('/api/v1/auditor-quality').json()
    assert one['adjudicated_reference_count']==0
    assert one['reference_only_count']==1
    assert one['by_method'][0]['method']=='hybrid'
    assert one['by_method'][0]['resolved_reference_count']==1
    cited=[]
    cited_versions={}
    for label in ('Reviewer A','Reviewer B'):
        reply=client.patch(endpoint,json={'human_passed':False,'human_failure_type':'accuracy','reviewer_label':label,'review_role':'independent'})
        assert reply.status_code==200
        cited.append(reply.json()['review_id'])
        cited_versions[reply.json()['review_id']]=reply.json()['updated_at']
    # Double annotation alone does not invent a resolved reference.
    assert client.get('/api/v1/auditor-quality').json()['adjudicated_reference_count']==0
    assert client.patch(endpoint,json={'human_passed':False,'human_failure_type':'accuracy','reviewer_label':'Adjudicator C','review_role':'adjudication','based_on_review_ids':cited,'based_on_review_versions':cited_versions}).status_code==200
    two=client.get('/api/v1/auditor-quality').json()
    assert two['adjudicated_reference_count']==1
    assert two['reference_only_count']==0
    assert two['double_reviewed_count']==1
    assert two['by_method'][0]['adjudicated_reference_count']==1


def test_reviewer_name_variants_update_one_review_without_inventing_a_second_person(client):
    audit, _ = run(client)
    key = audit['run_id']
    reviewed = client.get(f'/api/v1/audits/{key}/evaluation-review').json()[0]
    endpoint = f"/api/v1/audits/{key}/evaluations/{reviewed['automated']['evaluation_id']}/review"
    first = client.patch(endpoint, json={'human_passed': True, 'reviewer_label': 'Reviewer A', 'review_role': 'independent'})
    second = client.patch(endpoint, json={'human_passed': False, 'reviewer_label': ' reviewer a ', 'review_role': 'independent'})
    assert first.status_code == second.status_code == 200
    assert second.json()['review_id'] == first.json()['review_id']
    assert second.json()['reviewer_label'] == 'Reviewer A'
    assert second.json()['human_passed'] is False
    item = client.get(f'/api/v1/audits/{key}/evaluation-review').json()[0]
    assert len(item['human_reviews']) == 1
    assert item['independent_reviewer_count'] == 1
    calibration = client.get(f'/api/v1/audits/{key}/evaluation-calibration').json()
    assert calibration['independent_review_count'] == 1
    assert calibration['independent_pair_count'] == 0
    quality = client.get('/api/v1/auditor-quality').json()
    assert quality['double_reviewed_count'] == 0
    queue = next(row for row in quality['review_queue'] if row['run_id'] == key)
    assert queue['adjudication_pending'] == 0
    assert client.patch(endpoint, json={'human_passed': True, 'reviewer_label': ' \t ', 'review_role': 'independent'}).status_code == 422
    # Simulate two old raw names which the prior implementation accepted.
    with client.sessions() as db:
        original = db.get(EvaluationHumanReviewModel, first.json()['review_id'])
        db.add(EvaluationHumanReviewModel(id='HRlegacyalias', run_id=key, evaluation_id=original.evaluation_id,
            reviewer_label='reviewer a', review_role='independent', human_passed=True, based_on_review_ids=[]))
        db.commit()
    item = client.get(f'/api/v1/audits/{key}/evaluation-review').json()[0]
    assert len(item['human_reviews']) == 2  # Neither original row is erased.
    assert item['independent_reviewer_count'] == 1
    reviews = item['human_reviews']
    assert client.patch(endpoint, json={'human_passed': True, 'reviewer_label': 'Final reviewer',
        'review_role': 'adjudication', 'based_on_review_ids': [row['review_id'] for row in reviews],
        'based_on_review_versions': {row['review_id']: row['updated_at'] for row in reviews}}).status_code == 422
    assert client.get(f'/api/v1/audits/{key}/evaluation-calibration').json()['independent_pair_count'] == 0
    assert client.get('/api/v1/auditor-quality').json()['double_reviewed_count'] == 0


def test_review_uses_evaluated_response_receipt_not_another_attempt(client):
    from app.models import TargetResponseModel
    audit,_=run(client)
    key=audit['run_id']
    original=client.get(f'/api/v1/audits/{key}/evaluation-review').json()[0]
    with client.sessions() as db:
        response=db.get(TargetResponseModel,original['response']['response_id'])
        unrelated=TargetResponseModel(id='another-attempt',run_id=key,test_id=response.test_id,
            response_text='Unassessed alternative answer.',model=response.model,temperature=response.temperature)
        db.add(unrelated);db.flush()
        evaluation=db.get(EvaluationResultModel,original['automated']['evaluation_id'])
        evaluation.response_id=unrelated.id
        db.commit()
    revised=client.get(f'/api/v1/audits/{key}/evaluation-review').json()
    selected=next(row for row in revised if row['test']['test_id']==original['test']['test_id'])
    assert selected['response']['response_id']=='another-attempt'
    assert selected['response']['response_text']=='Unassessed alternative answer.'
    blind=client.get(f'/api/v1/audits/{key}/blind-review').json()
    assert next(row for row in blind if row['test']['test_id']==original['test']['test_id'])['response']['response_text']=='Unassessed alternative answer.'


def test_quality_query_count_does_not_grow_per_answer_or_per_run(client):
    from sqlalchemy import event
    first,_=run(client)
    second,_=run(client)
    with client.sessions() as db:
        db.get(AuditRunModel,first['run_id']).reproducibility_metadata={}
        db.get(AuditRunModel,second['run_id']).reproducibility_metadata={}
        db.commit()
        # Audit rows are the same real ORM objects as used by the endpoint.
        from app.api.quality_routes import quality_overview
        statements=[]
        def capture(_conn,_cursor,statement,_parameters,_context,_many):
            statements.append(statement)
        event.listen(db.bind,'before_cursor_execute',capture)
        try:
            report=quality_overview(db)
        finally:
            event.remove(db.bind,'before_cursor_execute',capture)
    assert report['completed_runs']==2
    assert report['evaluated']>2
    assert len(statements)==5  # runs + tests + evaluations + responses + labels
    assert report['by_method'][0]['method']=='custom'
    assert first['run_id'] in report['by_method'][0]['run_ids']


def test_independent_revision_invalidates_old_adjudication_until_explicit_resolution(client):
    from datetime import timedelta
    from app.models import EvaluationHumanReviewModel
    audit,_=run(client)
    key=audit['run_id']
    item=client.get(f'/api/v1/audits/{key}/evaluation-review').json()[0]
    endpoint=f"/api/v1/audits/{key}/evaluations/{item['automated']['evaluation_id']}/review"
    independent=[]
    versions={}
    for name in ('A','B'):
        response=client.patch(endpoint,json={'human_passed':True,'reviewer_label':name,'review_role':'independent'})
        assert response.status_code==200
        independent.append(response.json()['review_id'])
        versions[response.json()['review_id']]=response.json()['updated_at']
    body={'human_passed':True,'reviewer_label':'C','review_role':'adjudication','based_on_review_ids':independent,'based_on_review_versions':versions}
    missing_versions=client.patch(endpoint,json={key:value for key,value in body.items() if key!='based_on_review_versions'})
    assert missing_versions.status_code==422
    assert client.get('/api/v1/auditor-quality').json()['adjudicated_reference_count']==0
    adjudication=client.patch(endpoint,json=body)
    assert adjudication.status_code==200
    assert client.get('/api/v1/auditor-quality').json()['adjudicated_reference_count']==1
    revised=client.patch(endpoint,json={'human_passed':False,'human_failure_type':'freshness','reviewer_label':'A','review_role':'independent'})
    assert revised.status_code==200
    # Explicitly order timestamps; no dependence on clock precision or sleeps.
    with client.sessions() as db:
        resolution=db.get(EvaluationHumanReviewModel,adjudication.json()['review_id'])
        resolution.updated_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        db.commit()
    rows=client.get(f'/api/v1/audits/{key}/evaluation-review').json()
    selected=next(row for row in rows if row['automated']['evaluation_id']==item['automated']['evaluation_id'])
    assert selected['human_review'] is None
    assert len(selected['human_reviews'])==3  # No evidence deleted.
    report=client.get('/api/v1/auditor-quality').json()
    assert report['adjudicated_reference_count']==0
    assert report['resolved_reference_count']==0
    assert report['review_queue'][0]['adjudication_pending']==1
    stale=client.patch(endpoint,json=body)
    assert stale.status_code==409
    assert 'Refresh the review evidence' in stale.json()['detail']
    assert client.get('/api/v1/auditor-quality').json()['adjudicated_reference_count']==0
    versions[revised.json()['review_id']]=revised.json()['updated_at']
    assert client.patch(endpoint,json=body).status_code==200
    assert client.get('/api/v1/auditor-quality').json()['adjudicated_reference_count']==1


def test_new_independent_reviewer_invalidates_partial_adjudication(client):
    audit, _ = run(client)
    key = audit['run_id']
    item = client.get(f'/api/v1/audits/{key}/evaluation-review').json()[0]
    endpoint = f"/api/v1/audits/{key}/evaluations/{item['automated']['evaluation_id']}/review"
    labels = []
    for name in ('A', 'B'):
        response = client.patch(endpoint, json={'human_passed': True, 'reviewer_label': name, 'review_role': 'independent'})
        assert response.status_code == 200
        labels.append(response.json())
    body = {'human_passed': True, 'reviewer_label': 'Coordinator', 'review_role': 'adjudication',
            'based_on_review_ids': [row['review_id'] for row in labels],
            'based_on_review_versions': {row['review_id']: row['updated_at'] for row in labels}}
    assert client.patch(endpoint, json=body).status_code == 200
    assert client.get('/api/v1/auditor-quality').json()['adjudicated_reference_count'] == 1
    new = client.patch(endpoint, json={'human_passed': False, 'human_failure_type': 'accuracy',
                                      'reviewer_label': 'D', 'review_role': 'independent'})
    assert new.status_code == 200
    report = client.get('/api/v1/auditor-quality').json()
    assert report['adjudicated_reference_count'] == 0
    assert report['review_queue'][0]['adjudication_pending'] == 1
    assert client.patch(endpoint, json=body).status_code == 409
    labels.append(new.json())
    body['based_on_review_ids'] = [row['review_id'] for row in labels]
    body['based_on_review_versions'] = {row['review_id']: row['updated_at'] for row in labels}
    assert client.patch(endpoint, json=body).status_code == 200
    assert client.get('/api/v1/auditor-quality').json()['adjudicated_reference_count'] == 1


def test_new_model_audit_freezes_output_limit_and_repair_controls_cannot_change_it(client,monkeypatch):
    source,_=run(client)
    body={'conversation_id':source['conversation_id'],'target_configuration':'strong','provider':'ollama','model':'qwen3:1.7b'}
    created=client.post('/api/v1/audits',json=body)
    assert created.status_code==201,created.text
    key=created.json()['run_id']
    assert created.json()['target_memory_profile']['output_token_limit']==512
    monkeypatch.setenv('OLLAMA_NUM_PREDICT','17')
    saved=client.get(f'/api/v1/audits/{key}').json()
    assert saved['target_memory_profile']['output_token_limit']==512
    with client.sessions() as db:
        row=db.get(AuditRunModel,key);row.status='COMPLETED';db.commit()
    rejection=client.post(f'/api/v1/audits/{key}/repair-experiment',json={
        'targeted_profile':{'output_token_limit':768},'diagnosis_note':'Check current project requirements before selecting memory.'})
    assert rejection.status_code==422
    assert 'same answer length limit' in rejection.json()['detail']


@pytest.mark.parametrize('role', ['repair_comparison', 'adaptive_follow_up', 'audit_method_comparison'])
def test_diagnostic_forks_keep_source_assessor_without_inheriting_primary_comparison(client, role):
    from app.api.quality_routes import fork_conditions
    from app.models import ExperimentModel
    audit, _ = run(client)
    with client.sessions() as db:
        source = db.get(AuditRunModel, audit['run_id'])
        parent = db.get(ExperimentModel, source.experiment_id)
        parent.test_suite_configuration = {**parent.test_suite_configuration,
            'auditor_comparison_id': 'primary-comparison-fixture', 'compare_evaluators': True,
            'evaluator_model': 'different-parent-default', 'pipeline_model': 'different-pipeline-default',
            'random_seed': 999, 'test_budget': 12, 'prompt_template_version': 'different-template-default'}
        db.commit()
        package = fork_conditions(source, db, [TargetMemoryProfile()], role=role, note='Regression fixture', same_suite=False)
        child = db.get(ExperimentModel, package['experiment_id'])
        configuration = child.test_suite_configuration
        assert configuration['auditor_comparison_id'] is None
        assert configuration['compare_evaluators'] is False
        assert configuration['evaluator_model'] == source.evaluator_model
        assert configuration['pipeline_model'] == source.pipeline_model
        assert configuration['random_seed'] == source.random_seed
        assert configuration['test_budget'] == source.test_budget
        assert configuration['prompt_template_version'] == source.prompt_template_version
        child_run = db.get(AuditRunModel, package['runs'][0]['run_id'])
        assert child_run.random_seed == source.random_seed
        assert child_run.test_budget == source.test_budget
        assert child_run.prompt_template_version == source.prompt_template_version
        assert child.test_suite_metadata['study_role'] == role
        assert parent.test_suite_configuration['auditor_comparison_id'] == 'primary-comparison-fixture'
    public = client.get("/api/v1/experiments")
    assert public.status_code == 200
    child_public = next(item for item in public.json() if item["experiment_id"] == package["experiment_id"])
    assert child_public["test_suite_metadata"]["study_role"] == role


def test_historical_diagnostic_role_is_restored_from_run_receipt_without_database_mutation(client):
    from app.api.quality_routes import fork_conditions
    from app.models import ExperimentModel
    audit, _ = run(client)
    with client.sessions() as db:
        source = db.get(AuditRunModel, audit['run_id'])
        package = fork_conditions(source, db, [TargetMemoryProfile()], role='audit_method_comparison', note='Historical fixture')
        group = db.get(ExperimentModel, package['experiment_id'])
        group.test_suite_metadata = {'test_count': 6, 'generator_version': 'historical-fixture'}
        group.test_suite_configuration = {**group.test_suite_configuration, 'auditor_comparison_id': 'historical-primary-id'}
        db.commit()
    groups = client.get('/api/v1/experiments').json()
    restored = next(item for item in groups if item['experiment_id'] == package['experiment_id'])
    assert restored['test_suite_metadata']['study_role'] == 'audit_method_comparison'
    detail = client.get(f"/api/v1/experiments/{package['experiment_id']}/results")
    assert detail.status_code == 200
    assert detail.json()['experiment']['test_suite_metadata']['study_role'] == 'audit_method_comparison'
    bundle = client.get(f"/api/v1/experiments/{package['experiment_id']}/reproducibility-bundle.json")
    assert bundle.status_code == 200
    assert bundle.json()['experiment']['test_suite_metadata'] == detail.json()['experiment']['test_suite_metadata']
    export = client.get(f"/api/v1/conversations/{audit['conversation_id']}/export")
    assert export.status_code == 200
    exported_group = next(item for item in export.json()['experiments'] if item['experiment_id'] == package['experiment_id'])
    assert exported_group['test_suite_metadata'] == detail.json()['experiment']['test_suite_metadata']
    with client.sessions() as db:
        assert 'study_role' not in db.get(ExperimentModel, package['experiment_id']).test_suite_metadata


def test_mixed_historical_study_is_not_presented_as_primary_comparison(client):
    from app.api.routes import experiment_schema
    from app.models import ExperimentModel
    audit, _ = run(client)
    with client.sessions() as db:
        source = db.get(AuditRunModel, audit['run_id'])
        group = db.get(ExperimentModel, source.experiment_id)
        public = experiment_schema(group, [{}, {'study_role': 'adaptive_follow_up', 'diagnostic_source_run_id': source.id}])
        assert public.test_suite_metadata.study_role == 'mixed_study'
        assert public.test_suite_metadata.diagnostic_source_run_id is None
        assert 'study_role' not in group.test_suite_metadata or group.test_suite_metadata['study_role'] is None


def test_unmarked_original_groups_keep_their_identity(client):
    audit, _ = run(client)
    groups = client.get('/api/v1/experiments').json()
    original = next(item for item in groups if item['experiment_id'] == audit['experiment_id'])
    assert original['test_suite_metadata']['study_role'] is None


def test_standalone_diagnostic_retains_custom_frozen_protocol(client):
    from app.api.quality_routes import fork_conditions
    from app.models import ExperimentModel
    identity = history(client, '[User] I prefer Python.')
    created = client.post('/api/v1/audits', json={'conversation_id': identity, 'provider': 'rule_based',
        'target_configuration': 'weak', 'random_seed': 17, 'test_budget': 3,
        'prompt_template_version': 'standalone-protocol-v1'})
    assert created.status_code == 201
    key = created.json()['run_id']
    for stage in ('generate-tests', 'execute', 'evaluate'):
        response = client.post(f'/api/v1/audits/{key}/{stage}')
        assert response.status_code == 200, response.text
    with client.sessions() as db:
        source = db.get(AuditRunModel, key)
        assert source.experiment_id is None
        package = fork_conditions(source, db, [TargetMemoryProfile()], role='repair_comparison', note='Standalone protocol')
        child = db.get(AuditRunModel, package['runs'][0]['run_id'])
        group = db.get(ExperimentModel, package['experiment_id'])
        assert (child.random_seed, child.test_budget, child.prompt_template_version) == (17, 3, 'standalone-protocol-v1')
        assert group.test_suite_configuration['prompt_template_version'] == 'standalone-protocol-v1'


def test_independent_category_disagreement_is_separate_from_binary_consensus(client):
    audit, _ = run(client)
    key = audit['run_id']
    evaluation = client.get(f'/api/v1/audits/{key}/evaluation-review').json()[0]['automated']['evaluation_id']
    endpoint = f'/api/v1/audits/{key}/evaluations/{evaluation}/review'
    for name, category in [('A', 'accuracy'), ('B', 'freshness')]:
        response = client.patch(endpoint, json={'human_passed': False, 'human_failure_type': category,
            'reviewer_label': name, 'review_role': 'independent'})
        assert response.status_code == 200, response.text
    summary = client.get(f'/api/v1/audits/{key}/evaluation-calibration').json()
    assert summary['independent_consensus_count'] == 1
    assert summary['independent_failure_category_compared_count'] == 1
    assert summary['independent_failure_category_agreement_count'] == 0
    assert summary['independent_failure_category_conflict_count'] == 1
    assert summary['independent_failure_category_missing_count'] == 0
    response = client.patch(endpoint, json={'human_passed': False, 'human_failure_type': 'accuracy',
        'reviewer_label': 'B', 'review_role': 'independent'})
    assert response.status_code == 200
    summary = client.get(f'/api/v1/audits/{key}/evaluation-calibration').json()
    assert summary['independent_failure_category_agreement_count'] == 1
    assert summary['independent_failure_category_conflict_count'] == 0

    with client.sessions() as db:
        review = db.scalar(select(EvaluationHumanReviewModel).where(EvaluationHumanReviewModel.evaluation_id == evaluation, EvaluationHumanReviewModel.reviewer_label == 'B'))
        review.human_failure_type = None
        db.commit()
    summary = client.get(f'/api/v1/audits/{key}/evaluation-calibration').json()
    assert summary['independent_consensus_count'] == 1
    assert summary['independent_failure_category_compared_count'] == 0
    assert summary['independent_failure_category_agreement_count'] == 0
    assert summary['independent_failure_category_missing_count'] == 1
