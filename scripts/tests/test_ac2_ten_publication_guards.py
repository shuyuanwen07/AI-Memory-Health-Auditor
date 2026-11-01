"""Prevent unrelated or incomplete execution evidence from certifying AC2."""
import json

import pytest

from scripts.analyze_ac2_ten_retest_review_20261101 import execution_check, sha


def fixture(tmp_path):
    summary=tmp_path/'review.json'
    confirmation=tmp_path/'confirmation.json'
    summary.write_text('{}')
    confirmation.write_text('{"explicit":true}')
    protocol=tmp_path/'protocol.json'
    protocol.write_text(json.dumps({'review_summary_sha256':sha(summary),
                                   'human_confirmation_sha256':sha(confirmation)}))
    observed={'protocol_sha256':sha(protocol),'planned_answers':40,'returned_answers':40,
              'histories':[{'history_id':f'prospective-{i:02d}','status':'completed_automatic',
                            'answers_returned':4,'evaluations_returned':4,
                            'target_max_receipts_verified':4,'judge_max_receipts_verified':4,
                            'writer_max_receipt_verified':True} for i in range(1,30,3)]}
    execution=tmp_path/'collection-summary.json'
    execution.write_text(json.dumps(observed))
    return summary,confirmation,execution,observed


def test_complete_execution_is_automatic_availability_not_human_accuracy(tmp_path):
    review,confirmation,execution,_=fixture(tmp_path)
    result=execution_check(review,execution,confirmation)
    assert result['status']=='complete'
    assert result['answers']==result['assessments']==40
    assert result['basis']=='automatic'
    assert 'not human answer accuracy' in result['interpretation']


def test_approval_from_another_cohort_cannot_publish_execution(tmp_path):
    review,confirmation,execution,_=fixture(tmp_path)
    review.write_text('{"different_cohort":true}')
    with pytest.raises(ValueError,match='exact confirmed'):
        execution_check(review,execution,confirmation)


def test_complete_answer_counts_without_model_receipts_remain_partial(tmp_path):
    review,confirmation,execution,observation=fixture(tmp_path)
    observation['histories'][0]['judge_max_receipts_verified']=3
    execution.write_text(json.dumps(observation))
    assert execution_check(review,execution,confirmation)['status']=='partial'


def test_duplicate_history_cannot_replace_a_missing_scenario(tmp_path):
    review,confirmation,execution,observation=fixture(tmp_path)
    observation['histories'][-1]['history_id']='prospective-01'
    execution.write_text(json.dumps(observation))
    with pytest.raises(ValueError,match='ten planned histories'):
        execution_check(review,execution,confirmation)


def test_summary_total_cannot_hide_missing_answer_rows(tmp_path):
    review,confirmation,execution,observation=fixture(tmp_path)
    observation['histories'][0]['answers_returned']=3
    execution.write_text(json.dumps(observation))
    with pytest.raises(ValueError,match='total differs'):
        execution_check(review,execution,confirmation)
