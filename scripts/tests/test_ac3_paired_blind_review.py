"""Anonymous review packets using synthetic source data only."""
import copy
import hashlib
import pytest
from scripts.ac3_paired_blind_review import make_packets,validate_reviews
from scripts.ac3_paired_target_export import build_target_export
from scripts.ac3_retest_paired_freeze import canonical


def fixture():
    frozen={'suite':{'cases':[{'history_id':f'h{i}','source_messages':[{'text':f'source {i}'}]} for i in range(30)]}}
    sha=hashlib.sha256(canonical(frozen)).hexdigest()
    questions=[{'test_id':f'q{i}','history_id':f'h{i//4}','question':f'question {i}',
                'expected_behavior':f'expected {i}'} for i in range(120)]
    receipts=[{'scope_id':'scope','test_id':q['test_id'],'role':'target','status':'settled',
               'request_key':'req-'+q['test_id'],'response_text':'answer '+q['test_id'],
               'request_evidence_sha256':'a'*64,'reported_cost_usd':'0.0001'} for q in questions]
    responses=[{'test_id':r['test_id'],'response_text':r['response_text'],
                'request_evidence_sha256':r['request_evidence_sha256']} for r in receipts]
    export=build_target_export(frozen,questions,receipts,responses,scope='scope',ledger_frozen_sha256=sha,ledger_status='active')
    return frozen,questions,export


def test_both_reviewers_get_same_anonymous_cases_without_scores():
    frozen,questions,export=fixture();packet,reviews,private=make_packets(frozen,questions,export)
    assert len(packet['items'])==len(private['mapping'])==120
    assert reviews[0]['decisions']==reviews[1]['decisions']
    assert all('test_id' not in row and 'history_id' not in row and 'score' not in row for row in packet['items'])
    assert all(row['verdict'] is None and row['failure_dimension'] is None for row in reviews[0]['decisions'])
    assert set(private['mapping'])=={row['blind_id'] for row in packet['items']}


def test_missing_or_tampered_answer_is_rejected():
    frozen,questions,export=fixture();export['answers'][0]['answer']='changed'
    with pytest.raises(ValueError,match='digest'):make_packets(frozen,questions,export)


def test_review_validation_preserves_independent_disagreement_and_rejects_changed_source():
    frozen,questions,export=fixture();packet,reviews,private=make_packets(frozen,questions,export)
    for i,review in enumerate(reviews,1):
        review['reviewer_declaration']={'reviewer_label':f'person-{i}','completed_by_human':True,
            'completed_independently':True,'has_seen_automatic_results':False,'has_seen_other_review':False,'used_ai_assistance':False}
        for row in review['decisions']:
            row.update(verdict='pass',failure_dimension=None,rationale='Synthetic evidence.')
    reviews[1]['decisions'][0].update(verdict='uncertain',rationale='Synthetic uncertainty.')
    checked=validate_reviews(packet,reviews,private)
    assert checked['reviews'][0]!=checked['reviews'][1] and not checked['adjudicated']
    changed=copy.deepcopy(reviews);changed[0]['decisions'][0]['answer']='changed'
    with pytest.raises(ValueError,match='changed'):validate_reviews(packet,changed,private)
