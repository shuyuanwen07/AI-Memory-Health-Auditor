import copy
import pytest
from scripts.import_experiment_a_readable_review import convert


def fixture():
    items=[{'item_id':f'A{i}','source_messages':[{'message_id':'S','content':'source'}],
            'question':'question','response':'answer','frozen_defects':[{'defect_id':'D'}]}
           for i in range(36)]
    template={'format':'experiment-a-readable-answer-review-v1','reviewer_slot':1,'material_sha256':'digest',
        'reviewer_id':None,'independently_completed':None,'has_seen_automated_A_results':None,
        'used_ai_assistance':None,'instructions_zh':['instructions'],
        'items':[{**x,'review':{'verdict':None,'failure_dimension':None,'source_message_ids':[],
                                'defect_ids':None,'note':''}} for x in items]}
    return template,{'items':items}


def test_readable_review_converts_all_items_without_changing_material():
    template,material=fixture();review=copy.deepcopy(template)
    review.update(reviewer_id='Reviewer 1',independently_completed=True,
                  has_seen_automated_A_results=False,used_ai_assistance=True)
    for item in review['items']:
        item['review'].update(verdict='pass',failure_dimension=None,source_message_ids=['S'],defect_ids=[],note='')
    result=convert(review,template,material)
    assert len(result['labels'])==36 and result['labels'][0]['verdict']=='pass'
    review['items'][0]['response']='changed'
    with pytest.raises(ValueError,match='changed'):convert(review,template,material)


def test_unknown_review_is_preserved_and_requires_explanation():
    template,material=fixture();review=copy.deepcopy(template)
    review.update(reviewer_id='Reviewer 1',independently_completed=True,
                  has_seen_automated_A_results=False,used_ai_assistance=True)
    review['items'][0]['review'].update(verdict='uncertain',defect_ids=[],source_message_ids=['S'])
    with pytest.raises(ValueError,match='reason'):convert(review,template,material)
