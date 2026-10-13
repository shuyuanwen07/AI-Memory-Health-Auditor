import pytest
from sqlalchemy import select
from app.models import AuditRunModel, EvaluationResultModel, TestCaseModel, TargetResponseModel
from app.services.assessor_observations import assessor_observations
from test_reviewed_acceptance import study as reviewed_study

study = reviewed_study


def receipt(**overrides):
    return {'version':'judge-http-meter-v2','provider':'openrouter','model':'fixed-meter',
        'request_attempts':1,'failed_http_attempts':0,'elapsed_ms':100,
        'verdict_status':'valid',**overrides}


def test_partial_receipts_show_observed_amounts_and_explicit_coverage(study):
    _,factory,run_id,_ = study
    with factory() as db:
        run=db.get(AuditRunModel,run_id);run.evaluator_provider='openrouter';run.evaluator_model='fixed-meter'
        rows=db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id==run_id).order_by(EvaluationResultModel.id)).all()
        rows[0].judge_execution=receipt(reported_cost_credits=0.02,reported_total_tokens=20)
        rows[1].judge_execution=receipt(elapsed_ms=300,request_attempts=2,failed_http_attempts=1,reported_cost_credits=0.03,reported_total_tokens=30)
        rows[2].judge_execution=None
        rows[3].judge_execution=receipt(model='another-model',reported_cost_credits=99)
        db.commit()
        data=assessor_observations(db,run)
        assert data['expected_answers']==4 and data['receipt_count']==2
        assert data['mean_elapsed_ms']==200
        assert data['observed_cost_credits']==pytest.approx(0.05)
        assert data['observed_total_tokens']==50
        assert data['request_attempts']==3 and data['failed_http_attempts']==1
        assert data['cost_reported_answers']==2 and not data['complete_cost_coverage']


def test_absent_and_explicit_zero_cost_are_distinct(study):
    _,factory,run_id,_ = study
    with factory() as db:
        run=db.get(AuditRunModel,run_id)
        initial=assessor_observations(db,run)
        assert initial['observed_cost_credits'] is None
        assert initial['mean_elapsed_ms'] is None
        assert initial['request_attempts'] is None
        run.evaluator_provider='openrouter';run.evaluator_model='fixed-meter'
        rows=db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id==run_id)).all()
        for row in rows:row.judge_execution=receipt(reported_cost_credits=0)
        db.commit()
        data=assessor_observations(db,run)
        assert data['observed_cost_credits']==0
        assert data['cost_reported_answers']==4 and data['complete_cost_coverage']


@pytest.mark.parametrize('corruption',['duplicate','wrong_answer','bad_receipt'])
def test_corrupt_evidence_does_not_inflate_receipt_totals(study,corruption):
    _,factory,run_id,_ = study
    with factory() as db:
        run=db.get(AuditRunModel,run_id);run.evaluator_provider='openrouter';run.evaluator_model='fixed-meter'
        rows=db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id==run_id).order_by(EvaluationResultModel.id)).all()
        for row in rows:row.judge_execution=receipt(reported_cost_credits=0.01)
        if corruption=='duplicate':
            db.add(EvaluationResultModel(id='DUPLICATE-METER',test_id=rows[0].test_id,response_id=rows[0].response_id,
                passed=True,reason='fixture',evaluator='fixture',judge_execution=receipt(reported_cost_credits=99)))
        elif corruption=='wrong_answer':
            db.get(TargetResponseModel,rows[0].response_id).test_id=rows[1].test_id
        else:
            rows[0].judge_execution=receipt(reported_cost_credits=True)
        db.commit()
        data=assessor_observations(db,run)
        assert data['receipt_count']==3
        assert data['observed_cost_credits']==pytest.approx(0.03)
        assert not data['complete_cost_coverage']
