"""Post-execution labels in isolated fixtures, never claimed as human evidence."""
from datetime import datetime, timedelta
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base, get_db
from app.main import app
from app.models import AuditRunModel, TargetResponseModel, EvaluationResultModel, EvaluationHumanReviewModel
from app.services.formal_matrix import _stable_id
from test_formal_synthetic_matrix import DATASET, PILOT


@pytest.fixture
def study(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path / 'reviewed.db'}")
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,autoflush=False)
    def test_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db]=test_db
    try:
        with TestClient(app) as client:
            development=deepcopy(DATASET)
            for history in development['conversations']:
                for message in history['messages']:
                    message['content'] += ' Distinct development inventory only.'
            created=client.post('/api/v1/research/formal/synthetic-matrix',json={'dataset':DATASET,'pilot':PILOT,'development_dataset':development,'study_design':{'sampling_rule':'Select the complete fixed source inventory before inspecting any formal results; exclude none.','primary_outcome':'overall_memory_health'},'repetitions':3,'synthetic_data_confirmation':True,'success_criteria':{'failure_detection_recall_min_percent':50,'failure_classification_accuracy_min_percent':50,'test_validity_min_percent':90,'false_positive_rate_max_percent':10},'conditions':[{'label':'Weak','memory_strategy':'weak_first_hit','provider':'rule_based','model':'rule-based-target-ai'},{'label':'Strong','memory_strategy':'strong_rule_based','provider':'rule_based','model':'rule-based-target-ai'}]})
            assert created.status_code==201,created.text
            run=created.json()['scenarios'][0]['run_ids'][0]
            with factory() as db:
                for index,test in enumerate(DATASET['conversations'][0]['gold_tests']):
                    test_id=_stable_id('T',run,test['test_id'])
                    db.add(TargetResponseModel(id=f'NEW-R{index}',test_id=test_id,run_id=run,response_text=f'Actual new answer {index}, unlike the frozen example.',model='fixture',temperature=0))
                    db.flush()
                    db.add(EvaluationResultModel(id=f'NEW-E{index}',test_id=test_id,response_id=f'NEW-R{index}',passed=index!=0,failure_type='accuracy' if index==0 else None,reason='Engineering fixture',evaluator='rule_based',failure_classification={'status':'classified','method':'fixture','reason':'Engineering observed category'} if index==0 else None))
                db.get(AuditRunModel,run).status='COMPLETED';db.commit()
            yield client,factory,run,created.json()['acceptance_protocol']
    finally:
        app.dependency_overrides.clear()


def label_all(factory,run):
    with factory() as db:
        for index in range(4):
            db.add(EvaluationHumanReviewModel(id=f'REF-{index}',run_id=run,evaluation_id=f'NEW-E{index}',human_passed=index>=2,human_failure_type='accuracy' if index<2 else None,reviewer_label='Synthetic reference fixture',review_role='reference'))
        db.commit()


def report(client,run):
    response=client.get(f'/api/v1/research/formal/{run}/reviewed-acceptance')
    assert response.status_code==200,response.text
    return response.json()


def test_new_actual_answers_use_post_execution_labels_and_keep_frozen_thresholds(study):
    client,factory,run,protocol=study
    empty=report(client,run)
    assert empty['review_coverage']['missing_labels']==4
    assert empty['measures'][0]['status']=='insufficient_evidence'
    label_all(factory,run)
    result=report(client,run)
    assert result['protocol']==protocol
    assert [m['observed_percent'] for m in result['measures']]==[50,50,100,0]
    assert result['all_thresholds_met'] and result['saved_result_thresholds_met']
    assert result['review_coverage']['independently_adjudicated']==0
    assert 'not verified human identity' in result['notice']
    assert len(result['receipt_sha256'])==64
    assert result['receipt_sha256']!=empty['receipt_sha256']


def test_missing_labels_categories_and_duplicate_answers_prevent_complete_results(study):
    client,factory,run,_=study
    label_all(factory,run)
    with factory() as db:
        db.get(EvaluationHumanReviewModel,'REF-0').human_failure_type=None;db.commit()
    assert report(client,run)['measures'][1]['status']=='insufficient_evidence'
    with factory() as db:
        db.delete(db.get(EvaluationHumanReviewModel,'REF-1'))
        reply=db.get(TargetResponseModel,'NEW-R3')
        db.add(TargetResponseModel(id='DUPLICATE-R',test_id=reply.test_id,run_id=run,response_text='Duplicate fixture',model='fixture',temperature=0));db.commit()
    result=report(client,run)
    assert result['review_coverage']['ambiguous_tests']==1
    assert result['review_coverage']['missing_labels']==2
    assert not result['saved_result_thresholds_met']


def test_changed_independent_label_invalidates_old_adjudication(study):
    client,factory,run,_=study
    label_all(factory,run)
    with factory() as db:
        stamp=datetime(2026,10,12,12)
        for name in ('A','B'):
            db.add(EvaluationHumanReviewModel(id=name,run_id=run,evaluation_id='NEW-E0',human_passed=False,human_failure_type='accuracy',reviewer_label=name,review_role='independent',created_at=stamp,updated_at=stamp))
        db.add(EvaluationHumanReviewModel(id='FINAL',run_id=run,evaluation_id='NEW-E0',human_passed=False,human_failure_type='accuracy',reviewer_label='C',review_role='adjudication',based_on_review_ids=['A','B'],created_at=stamp+timedelta(hours=1),updated_at=stamp+timedelta(hours=1)));db.commit()
    assert report(client,run)['review_coverage']['independently_adjudicated']==1
    with factory() as db:
        db.get(EvaluationHumanReviewModel,'A').updated_at=stamp+timedelta(hours=2);db.commit()
    result=report(client,run)
    assert result['review_coverage']['missing_labels']==1
    assert result['measures'][0]['status']=='insufficient_evidence'


def test_legacy_test_dimension_is_not_observed_failure_classification(study):
    client,factory,run,_=study
    label_all(factory,run)
    first=report(client,run)
    with factory() as db:
        db.get(EvaluationResultModel,'NEW-E0').failure_classification=None;db.commit()
    result=report(client,run)
    assert result['measures'][1]['observed_percent']==0
    assert not result['all_thresholds_met']
    assert result['receipt_sha256']!=first['receipt_sha256']


@pytest.mark.parametrize('corruption',['duplicate_verdict','duplicate_answer','wrong_run_answer','wrong_run_review'])
def test_bulk_review_cannot_use_ambiguous_or_cross_run_evidence(study,corruption):
    from app.api.routes import evaluation_review_batches_for
    client,factory,run,_=study
    label_all(factory,run)
    with factory() as db:
        original=db.get(AuditRunModel,run)
        peer_id=original.reproducibility_metadata['formal_matrix_manifest']['scenarios'][0]['run_ids'][1]
        peer=db.get(AuditRunModel,peer_id);peer.status='COMPLETED'
        answer=db.get(TargetResponseModel,'NEW-R0')
        verdict=db.get(EvaluationResultModel,'NEW-E0')
        if corruption=='duplicate_verdict':
            db.add(EvaluationResultModel(id='AMBIGUOUS-E',test_id=verdict.test_id,response_id=answer.id,passed=True,reason='Conflicting duplicate fixture',evaluator='rule_based'))
        elif corruption=='duplicate_answer':
            db.add(TargetResponseModel(id='AMBIGUOUS-R',test_id=answer.test_id,run_id=run,response_text='A second saved answer',model='fixture',temperature=0))
        elif corruption=='wrong_run_answer':
            answer.run_id=peer_id
        else:
            db.get(EvaluationHumanReviewModel,'REF-0').run_id=peer_id
        db.commit()
        integrity={}
        rows=evaluation_review_batches_for([run,peer_id],db,integrity)[run]
        assert integrity[run]['expected_questions']==4
        assert integrity[run]['excluded_questions']==(0 if corruption in ('wrong_run_review','duplicate_answer') else 1)
        affected=[item for item in rows if item.automated.evaluation_id=='NEW-E0' or item.test.test_id==verdict.test_id]
        if corruption=='duplicate_answer':
            assert len(affected)==1
            assert affected[0].response.response_id=='NEW-R0'
        elif corruption=='wrong_run_review':
            assert len(affected)==1
            assert affected[0].human_review is None
            assert affected[0].human_reviews==[]
        else:
            assert affected==[]


def test_quality_coverage_keeps_all_saved_questions_in_denominator(study):
    client,factory,run,_=study
    label_all(factory,run)
    with factory() as db:
        verdict=db.get(EvaluationResultModel,'NEW-E0')
        db.add(EvaluationResultModel(id='SECOND-E',test_id=verdict.test_id,response_id=verdict.response_id,passed=True,reason='Duplicate fixture',evaluator='rule_based'));db.commit()
    result=client.get('/api/v1/auditor-quality')
    assert result.status_code==200,result.text
    data=result.json()
    assert data['evidence_integrity']['expected_questions']==4
    assert data['evidence_integrity']['eligible_questions']==3
    assert data['evidence_integrity']['excluded_questions']==1
    assert data['review_coverage']['numerator']==3
    assert data['review_coverage']['denominator']==4
    assert data['review_coverage']['percentage']==75
    assert data['by_method'][0]['evidence_integrity']['excluded_questions']==1


def test_invalidated_duplicate_labels_still_change_the_evidence_receipt(study):
    client,factory,run,_=study
    label_all(factory,run)
    with factory() as db:
        verdict=db.get(EvaluationResultModel,'NEW-E0')
        db.add(EvaluationResultModel(id='SECOND-E',test_id=verdict.test_id,response_id=verdict.response_id,passed=True,reason='Duplicate fixture',evaluator='rule_based'));db.commit()
    before=report(client,run)
    with factory() as db:
        db.get(EvaluationHumanReviewModel,'REF-0').note='Changed excluded label version';db.commit()
    after=report(client,run)
    assert before['receipt_sha256']!=after['receipt_sha256']
    assert not after['saved_result_thresholds_met']


@pytest.mark.parametrize('corruption',['duplicate_verdict','wrong_run_answer','wrong_question_answer'])
def test_review_write_refuses_inconsistent_assessment_without_overwriting_labels(study,corruption):
    client,factory,run,_=study
    label_all(factory,run)
    with factory() as db:
        row=db.get(EvaluationResultModel,'NEW-E0')
        if corruption=='duplicate_verdict':
            db.add(EvaluationResultModel(id='SECOND-E',test_id=row.test_id,response_id=row.response_id,passed=True,reason='Duplicate fixture',evaluator='rule_based'))
        elif corruption=='wrong_question_answer':
            row.response_id='NEW-R1'
        else:
            audit=db.get(AuditRunModel,run)
            peer=audit.reproducibility_metadata['formal_matrix_manifest']['scenarios'][0]['run_ids'][1]
            db.get(TargetResponseModel,'NEW-R0').run_id=peer
        db.commit()
    result=client.patch(f'/api/v1/audits/{run}/evaluations/NEW-E0/review',json={'human_passed':True,'reviewer_label':'Synthetic reference fixture','review_role':'reference'})
    assert result.status_code==409,result.text
    with factory() as db:
        assert db.get(EvaluationHumanReviewModel,'REF-0').human_passed is False
