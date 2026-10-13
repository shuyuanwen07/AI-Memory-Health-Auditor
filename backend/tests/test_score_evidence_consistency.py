"""Single-run scores and paired comparisons must reject the same corrupt evidence."""
import pytest
from sqlalchemy import select

from app.models import AuditRunModel, TestCaseModel, TargetResponseModel, EvaluationResultModel
from test_reviewed_acceptance import study as reviewed_study

study = reviewed_study


def test_old_report_exposes_rule_version_difference_without_overwriting_its_score(study):
    from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
    client,factory,run,_ = study
    with factory() as db:
        rows = db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id==run)).all()
        for row in rows:
            row.evaluator = RuleBasedBehaviourEvaluator.VERSION
        db.commit()
    current = client.get(f'/api/v1/audits/{run}/results').json()
    assert not any('different version of the evidence rules' in warning for warning in current['evaluation_warnings'])
    with factory() as db:
        db.get(EvaluationResultModel,'NEW-E0').evaluator = 'rule-based-v1'
        db.commit()
    archived = client.get(f'/api/v1/audits/{run}/results').json()
    assert any('1 saved assessment used a different version' in warning for warning in archived['evaluation_warnings'])
    for key in ('overall_score','tests_passed','tests_total','dimensions','uncertain_count'):
        assert archived[key] == current[key]
    with factory() as db:
        assert db.get(EvaluationResultModel,'NEW-E0').evaluator == 'rule-based-v1'


def complete_peer(factory, peer):
    with factory() as db:
        for index, test in enumerate(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == peer))):
            response_id = f'PEER-R{index}'
            db.add(TargetResponseModel(id=response_id,test_id=test.id,run_id=peer,response_text='fixture',model='fixture',temperature=0))
            db.flush()
            db.add(EvaluationResultModel(id=f'PEER-E{index}',test_id=test.id,response_id=response_id,passed=True,reason='fixture',evaluator='rule_based'))
        db.get(AuditRunModel,peer).status='COMPLETED'
        db.commit()


@pytest.mark.parametrize('corruption', ['duplicate', 'wrong_run', 'wrong_question', 'missing_assessment'])
def test_scoring_count_details_and_pairing_share_evidence_exclusions(study, corruption):
    client,factory,run,_=study
    plan=client.get(f'/api/v1/research/formal/{run}/plan').json()
    peer=plan['scenarios'][0]['run_ids'][1]
    complete_peer(factory,peer)
    with factory() as db:
        evaluation=db.get(EvaluationResultModel,'NEW-E0')
        if corruption=='duplicate':
            db.add(EvaluationResultModel(id='DUPLICATE',test_id=evaluation.test_id,response_id=evaluation.response_id,passed=True,reason='fixture',evaluator='rule_based'))
        elif corruption=='wrong_run':
            db.get(TargetResponseModel,evaluation.response_id).run_id=peer
        elif corruption=='wrong_question':
            db.get(TargetResponseModel,evaluation.response_id).test_id=db.get(EvaluationResultModel,'NEW-E1').test_id
        else:
            db.delete(evaluation)
        db.commit()
    result=client.get(f'/api/v1/audits/{run}/results')
    assert result.status_code==200,result.text
    body=result.json()
    assert body['expected_tests']==4 and body['excluded_evidence_count']==1
    assert body['evaluated_count']==body['tests_total']==body['tests_passed']==3
    assert body['failures']==[]
    accuracy=next(dimension for dimension in body['dimensions'] if dimension['dimension']=='accuracy')
    assert accuracy['expected_tests']==1 and accuracy['excluded_evidence_count']==1
    assert accuracy['percentage'] is None
    assert body['overall_score']==100
    assert any('neither passes nor failures' in warning for warning in body['evaluation_warnings'])
    analytics=client.get(f"/api/v1/experiments/{plan['scenarios'][0]['experiment_id']}/results")
    assert analytics.status_code==200,analytics.text
    pair=analytics.json()['paired_comparisons'][0]
    assert pair['shared_question_count']==4
    assert pair['shared_tests']==3
    assert pair['excluded_assessment_count']==1
    assert pair['excluded_uncertain_count']==0
    assert pair['candidate_delta_percentage_points']==0
    comparison=client.get('/api/v1/audit-comparisons',params={'before':run,'after':peer})
    assert comparison.status_code==200,comparison.text
    assert comparison.json()['decided_shared_question_count']==3
    assert any('inconsistent assessment evidence' in warning for warning in comparison.json()['warnings'])


def test_extra_unassessed_answer_preserves_the_exact_assessed_reply(study):
    client,factory,run,_=study
    with factory() as db:
        original=db.get(TargetResponseModel,'NEW-R0')
        db.add(TargetResponseModel(id='OTHER-ATTEMPT',test_id=original.test_id,run_id=run,response_text='unassessed',model='fixture',temperature=0))
        db.commit()
    result=client.get(f'/api/v1/audits/{run}/results').json()
    assert result['excluded_evidence_count']==0
    assert result['tests_total']==4 and result['tests_passed']==3
    assert result['failures'][0]['response']['response_id']=='NEW-R0'


def test_audit_result_includes_every_saved_answer_outcome_and_original_sources(study):
    client,factory,run,_=study
    with factory() as db:
        db.get(EvaluationResultModel,'NEW-E2').passed=None
        db.delete(db.get(EvaluationResultModel,'NEW-E3'))
        db.commit()

    response=client.get(f'/api/v1/audits/{run}/results')
    assert response.status_code==200,response.text
    answers=response.json()['answers']
    assert len(answers)==4
    assert {answer['outcome'] for answer in answers}=={'pass','fail','uncertain','unassessed'}
    by_response={answer['response']['response_id']:answer for answer in answers}
    assert by_response['NEW-R0']['outcome']=='fail'
    assert by_response['NEW-R1']['outcome']=='pass'
    assert by_response['NEW-R2']['outcome']=='uncertain'
    assert by_response['NEW-R3']['outcome']=='unassessed'
    assert by_response['NEW-R3']['reason']=='No unique valid assessment is linked to this saved response.'
    for answer in answers:
        assert answer['test'].get('target_memory_context') is None
        assert answer['source_statements']
        assert answer['source_statements'][0]['content']=='Synthetic fact 1.'
