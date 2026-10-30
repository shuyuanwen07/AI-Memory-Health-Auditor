"""Synthetic fixtures prove server plan boundaries, not research conclusions."""
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.session import Base, get_db
from app.main import app
from app.models import AuditRunModel, ConversationModel, ExperimentModel, MemoryModel, MessageModel, TestCaseModel
from app.schemas.benchmark_plan import BenchmarkPlanCreate, PlannedBenchmarkRun, PlannedRankingAnalysis
from app.schemas.benchmark import LiveBenchmarkRequest
from app.schemas.domain import Dimension
from app.services.benchmark_plan import BenchmarkPlanService
from app.services.runtime_freeze import audit_runtime_signature
from app.memory_agent.writers import RuleBasedTargetMemoryWriter
from app.target_systems.controlled import ControlledTargetSystemAdapter
from app.schemas.target_profile import TargetMemoryProfile
from app.target_ai.providers import HttpTargetAIConnector
from test_live_benchmark import PROVENANCE


@pytest.fixture
def pending(tmp_path,monkeypatch):
    # A synthetic credential passes configuration checks; transport is mocked.
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-test-key')
    monkeypatch.setattr(HttpTargetAIConnector,'_execute_provider',lambda *a:'PostgreSQL')
    engine=create_engine(f"sqlite:///{tmp_path/'plan.db'}")
    Base.metadata.create_all(engine)
    profile=TargetMemoryProfile(output_token_limit=192).model_dump(mode='json')
    now=datetime.now(timezone.utc)
    db=Session(engine)
    db.add(ConversationModel(id='C',authorised=True,source_origin='synthetic',created_at=now))
    db.flush()
    db.add(MessageModel(id='MSG',conversation_id='C',source_message_id='SRC',sequence=0,role='user',content='The backend now uses PostgreSQL.',timestamp=now))
    db.add(MemoryModel(id='M',conversation_id='C',canonical_value='The backend now uses PostgreSQL.',status='confirmed',source_message_ids=['SRC']))
    db.add(ExperimentModel(id='EXP',conversation_id='C',label='Synthetic plan fixture',status='CREATED',test_suite_configuration={},test_suite_metadata={}))
    db.flush()
    trials=[]
    for i in range(3):
        ids=[]
        for j,strategy in enumerate(['weak_first_hit','strong_rule_based']):
            rid=f'R{i}{j}'
            ids.append(rid)
            db.add(AuditRunModel(id=rid,conversation_id='C',experiment_id='EXP',status='TESTS_GENERATED',target_configuration='strong',provider='openrouter',model='openai/gpt-6-luna',temperature=0,random_seed=42,test_budget=4,prompt_template_version='fixture',pipeline_provider='rule_based',evaluator_provider='rule_based',memory_strategy=strategy,target_memory_writer='rule_based',target_memory_writer_version=RuleBasedTargetMemoryWriter.VERSION,target_system_adapter='controlled-memory',target_system_adapter_version=ControlledTargetSystemAdapter.version,reproducibility_metadata={'audit_runtime_signature':audit_runtime_signature(),'target_memory_profile':profile}))
            db.flush()
            for d in Dimension:
                canonical='TR00'+d.value
                db.add(TestCaseModel(id='T'+rid+d.value,run_id=rid,suite_test_id=None if i==j==0 else canonical,dimension=d.value,prompt={'accuracy':'What database does the backend use?','freshness':'What database should a new connection use now?','conflict_resolution':'Which database should a maintainer select for production?','appropriate_use':'What database does this project require for its backend?'}[d.value],expected_behavior='PostgreSQL',supporting_memory_ids=['M'],generator_version='fixture',quality_status='accepted',grounding_status='grounded'))
            db.flush()
        trials.append({'trial_id':f'repeat-{i+1}','reference_run_id':ids[0],'candidate_run_id':ids[1]})
    db.get(ExperimentModel,'EXP').test_suite_source_run_id='R00'
    db.commit()
    request=BenchmarkPlanCreate(benchmark=LiveBenchmarkRequest(provider='openrouter',model='openai/gpt-6-luna',payload=[dict(question_id='synthetic-case',question_type='single-session-user',question='What database does the backend use?',answer='PostgreSQL',messages=[{'role':'user','content':'The backend now uses PostgreSQL.'}])],source_authorised=True,dataset_provenance=PROVENANCE,target_memory_profile=profile),trials=trials,sampling_rule='Use this one synthetic contract fixture; it is not research data.',evaluator_model='simulated-reviewer',evaluator_revision='0'*40,metadata_storage_authorised=True)
    yield db,request
    db.close()
    app.dependency_overrides.clear()


@pytest.mark.parametrize('change',['no_permission','no_storage','already_answered','different_model','missing_dimension','different_suite','duplicate_question','duplicate_plan'])
def test_freeze_rejects_invalid_or_postexecution_inputs(pending,change):
    db,request=pending
    if change=='no_permission': request.benchmark.source_authorised=False
    elif change=='no_storage': request.metadata_storage_authorised=False
    elif change=='already_answered': db.get(AuditRunModel,'R00').status='COMPLETED';db.commit()
    elif change=='different_model': db.get(AuditRunModel,'R00').model='other';db.commit()
    elif change=='missing_dimension': db.get(TestCaseModel,'TR00accuracy').dimension='freshness';db.commit()
    elif change=='different_suite': db.get(TestCaseModel,'TR01accuracy').prompt='Different question';db.commit()
    elif change=='duplicate_question': db.get(TestCaseModel,'TR00freshness').prompt=db.get(TestCaseModel,'TR00accuracy').prompt;db.commit()
    else: BenchmarkPlanService().create(db,request)
    with pytest.raises(ValueError): BenchmarkPlanService().create(db,request)


def test_freeze_restore_metadata_and_missing_report(pending):
    db,request=pending
    service=BenchmarkPlanService()
    plan=service.create(db,request)
    assert service.view(db,plan.plan_id)==plan
    assert 'The backend now uses PostgreSQL.' not in plan.model_dump_json()
    assert plan.protocol['planned_target_calls']==6
    report=service.analyse(db,plan.plan_id,PlannedRankingAnalysis(analysis={'planned_trial_ids':[t.trial_id for t in request.trials]}))
    assert report.plan_provenance=='server_frozen_preexecution_plan'
    assert report.missing_trials==3 and report.ranking_agreement_percentage is None
    assert report.plan_fingerprint_sha256==plan.plan_fingerprint_sha256


def test_planned_dispatch_records_original_evidence_and_blocks_replay(pending):
    db,request=pending
    service=BenchmarkPlanService()
    plan=service.create(db,request)
    result=service.run(db,plan.plan_id,PlannedBenchmarkRun(trial_id='repeat-1',benchmark=request.benchmark))
    restored=service.view(db,plan.plan_id)
    assert restored.executions['repeat-1']['status']=='COMPLETED'
    assert restored.executions['repeat-1']['benchmark_run_id']==result.run_id
    assert 'PostgreSQL' not in restored.model_dump_json()
    with pytest.raises(HTTPException,match='') as error:
        service.run(db,plan.plan_id,PlannedBenchmarkRun(trial_id='repeat-1',benchmark=request.benchmark))
    assert error.value.status_code==409


def test_failed_dispatch_is_retained_and_not_silently_retried(pending,monkeypatch):
    from app.benchmarks.live import LiveBenchmarkRunner
    db,request=pending
    service=BenchmarkPlanService()
    plan=service.create(db,request)
    call=Mock(side_effect=ValueError('simulated model failure'))
    monkeypatch.setattr(LiveBenchmarkRunner,'run',call)
    with pytest.raises(ValueError): service.run(db,plan.plan_id,PlannedBenchmarkRun(trial_id='repeat-1',benchmark=request.benchmark))
    assert service.view(db,plan.plan_id).executions['repeat-1']['status']=='FAILED'
    with pytest.raises(HTTPException): service.run(db,plan.plan_id,PlannedBenchmarkRun(trial_id='repeat-1',benchmark=request.benchmark))
    assert call.call_count==1


def test_plan_blocks_changed_source_before_model_dispatch(pending,monkeypatch):
    from app.benchmarks.live import LiveBenchmarkRunner
    db,request=pending
    service=BenchmarkPlanService()
    plan=service.create(db,request)
    changed=request.benchmark.model_copy(deep=True)
    changed.payload[0]['question']='A changed source question'
    call=Mock()
    monkeypatch.setattr(LiveBenchmarkRunner,'run',call)
    with pytest.raises(ValueError): service.run(db,plan.plan_id,PlannedBenchmarkRun(trial_id='repeat-1',benchmark=changed))
    call.assert_not_called()
    assert service.view(db,plan.plan_id).executions=={}


def test_plan_blocks_audit_input_drift_at_normal_execution_boundary(pending):
    db,request=pending
    plan=BenchmarkPlanService().create(db,request)
    db.get(TestCaseModel,'TR00accuracy').prompt='Changed after freeze'
    db.commit()
    app.dependency_overrides[get_db]=lambda:db
    with TestClient(app) as client:
        result=client.post('/api/v1/audits/R00/execute')
        assert result.status_code==409,result.text
        assert 'Experiment C' in result.text
        assert client.get(f'/api/v1/research/benchmarks/longmemeval/plans/{plan.plan_id}').status_code==200


def test_frozen_plan_binds_scoring_to_original_server_evidence(pending):
    from app.schemas.ranking_agreement import RepeatedRankingRequest
    db,request=pending
    service=BenchmarkPlanService()
    plan=service.create(db,request)
    evidence=service.run(db,plan.plan_id,PlannedBenchmarkRun(trial_id='repeat-1',benchmark=request.benchmark))
    assessment={'source':request.benchmark.payload,'source_authorised':True,'evidence':evidence.model_dump(mode='json'),
        'strategy':'weak_first_hit','evaluator_revision':'0'*40,
        'rows':[{'question_id':'synthetic-case','hypothesis':'PostgreSQL','autoeval_label':{'model':'simulated-reviewer','label':True}}]}
    candidate={**assessment,'strategy':'strong_rule_based'}
    comparison={'reference_run_id':'R00','candidate_run_id':'R01','reference_benchmark':assessment,'candidate_benchmark':candidate}
    body={'planned_trial_ids':[t.trial_id for t in request.trials],'trials':[{'trial_id':'repeat-1','comparison':comparison}]}
    # A changed response cannot qualify as evidence from the recorded call.
    changed=deepcopy(body)
    changed['trials'][0]['comparison']['reference_benchmark']['evidence']['conditions'][0]['cases'][0]['response_text']='altered'
    with pytest.raises(ValueError,match='Evidence or the evaluation standard'):
        service.analyse(db,plan.plan_id,PlannedRankingAnalysis(analysis=RepeatedRankingRequest(**changed)))
    # A changed analysis plan cannot omit planned missing repeats.
    changed=deepcopy(body)
    changed['planned_trial_ids']=['repeat-3','repeat-2','repeat-1']
    with pytest.raises(ValueError,match='original order'):
        service.analyse(db,plan.plan_id,PlannedRankingAnalysis(analysis=changed))
    changed=deepcopy(body)
    changed['trials'][0]['comparison']['reference_benchmark']['evaluator_revision']='1'*40
    with pytest.raises(ValueError,match='evaluation standard'):
        service.analyse(db,plan.plan_id,PlannedRankingAnalysis(analysis=changed))


def test_complete_frozen_execution_and_analysis_path(pending):
    db,request=pending
    service=BenchmarkPlanService()
    plan=service.create(db,request)
    app.dependency_overrides[get_db]=lambda:db
    trials=[]
    with TestClient(app) as client:
        for trial in request.trials:
            for rid in (trial.reference_run_id,trial.candidate_run_id):
                executed=client.post(f'/api/v1/audits/{rid}/execute')
                assert executed.status_code==200,executed.text
                evaluated=client.post(f'/api/v1/audits/{rid}/evaluate')
                assert evaluated.status_code==200,evaluated.text
            result=client.post(f'/api/v1/research/benchmarks/longmemeval/plans/{plan.plan_id}/execute',json={'trial_id':trial.trial_id,'benchmark':request.benchmark.model_dump(mode='json')})
            assert result.status_code==200,result.text
            evidence=result.json()
            assessments=[]
            for strategy in ('weak_first_hit','strong_rule_based'):
                assessments.append({'source':request.benchmark.payload,'source_authorised':True,'evidence':evidence,
                    'strategy':strategy,'evaluator_revision':'0'*40,'rows':[{'question_id':'synthetic-case','hypothesis':'PostgreSQL','autoeval_label':{'model':'simulated-reviewer','label':True}}]})
            trials.append({'trial_id':trial.trial_id,'comparison':{'reference_run_id':trial.reference_run_id,'candidate_run_id':trial.candidate_run_id,'reference_benchmark':assessments[0],'candidate_benchmark':assessments[1]}})
        analysed=client.post(f'/api/v1/research/benchmarks/longmemeval/plans/{plan.plan_id}/analyse',json={'analysis':{'planned_trial_ids':[t.trial_id for t in request.trials],'trials':trials}})
        assert analysed.status_code==200,analysed.text
        report=analysed.json()
        assert report['status']=='complete',report
        assert report['measured_trials']==3
        assert report['plan_provenance']=='server_frozen_preexecution_plan'
        assert report['plan_fingerprint_sha256']==plan.plan_fingerprint_sha256
        restored=client.get(f'/api/v1/research/benchmarks/longmemeval/plans/{plan.plan_id}').json()
        summary=restored['executions']['repeat-1']['dashboard_summary']
        assert summary['metric']=='lexical_match'
        assert len(summary['conditions'])==2
        assert all(row['total']==1 for row in summary['conditions'])
        assert 'PostgreSQL' not in str(summary)
        analyses=client.get('/api/v1/research/benchmarks/longmemeval/analyses').json()
        assert analyses[0]['plan_id']==plan.plan_id
        assert analyses[0]['report']['measured_trials']==3
        assert 'PostgreSQL' not in str(analyses)


def test_plan_listing_recovers_metadata_without_dispatching_or_returning_sources(pending):
    db,request=pending
    plan=BenchmarkPlanService().create(db,request)
    app.dependency_overrides[get_db]=lambda:db
    with TestClient(app) as client:
        response=client.get('/api/v1/research/benchmarks/longmemeval/plans')
        assert response.status_code==200,response.text
        assert response.json()[0]['plan_id']==plan.plan_id
        assert response.json()[0]['executions']=={}
        assert 'The backend now uses PostgreSQL.' not in response.text
