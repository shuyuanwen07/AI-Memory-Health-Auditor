"""Synthetic export checks: no real reviews or provider requests."""
import hashlib
import pytest
from scripts.ac3_paired_target_export import build_target_export
from scripts.ac3_retest_paired_freeze import canonical


def fixture():
    frozen={'suite':'synthetic'};sha=hashlib.sha256(canonical(frozen)).hexdigest()
    questions=[{'test_id':f'q{i}','history_id':f'h{i//4}'} for i in range(120)]
    receipts=[{'scope_id':'scope','test_id':q['test_id'],'role':'target','status':'settled',
               'request_key':'req-'+q['test_id'],'response_text':'answer '+q['test_id'],
               'request_evidence_sha256':'a'*64,'reported_cost_usd':'0.0001'} for q in questions]
    responses=[{'test_id':r['test_id'],'response_text':r['response_text'],
                'request_evidence_sha256':r['request_evidence_sha256']} for r in receipts]
    return frozen,questions,receipts,responses,{'scope':'scope','ledger_frozen_sha256':sha,'ledger_status':'active'}


def test_exports_all_saved_answers_without_grades():
    frozen,questions,receipts,responses,kwargs=fixture()
    result=build_target_export(frozen,questions,receipts,responses,**kwargs)
    assert len(result['answers'])==120 and not result['model_called'] and not result['human_truth_evaluated']
    assert all('grade' not in item for item in result['answers'])


def test_rejects_unsettled_missing_duplicate_or_changed_answer():
    frozen,questions,receipts,responses,kwargs=fixture()
    with pytest.raises(ValueError,match='unresolved'):
        build_target_export(frozen,questions,receipts,responses,**{**kwargs,'ledger_status':'unknown'})
    with pytest.raises(ValueError,match='Every question'):
        build_target_export(frozen,questions,receipts[:-1],responses,**kwargs)
    with pytest.raises(ValueError,match='Duplicate'):
        build_target_export(frozen,questions,receipts+[receipts[0]],responses,**kwargs)
    responses[0]['response_text']='changed'
    with pytest.raises(ValueError,match='settled receipt'):
        build_target_export(frozen,questions,receipts,responses,**kwargs)
