"""Synthetic in-memory tests; no actual reviewer decisions are created."""
import copy
import pytest
from scripts.analyze_ac2_source_supplement_paired import analyze,canonical,sha


def fixture():
    material={'format':'ac2-source-supplement-blind-material-v1','histories':[{'history_id':'H','source_messages':[]}],
              'questions':[{'blind_id':'b','history_id':'H','prompt':'before'}, {'blind_id':'s','history_id':'H','prompt':'after'}]}
    digest=sha(canonical(material));key={'material_sha256':digest,'identity':{'b':{'arm':'baseline','history_id':'H','guard_warning':None},
        's':{'arm':'supplement','history_id':'H','guard_warning':'review'}},'ledger':[]}
    for i in range(10):
        for arm in ('baseline','supplement'):
            key['ledger'].append({'history_id':'H' if i==0 else f'H{i}','arm':arm,'generated':1 if i==0 else 0,'missing_slots':3 if i==0 else 4})
    reviewers=[]
    for i in (1,2):
        reviewers.append({'format':'ac2-source-supplement-human-review-v1','reviewer_slot':i,'material_sha256':digest,
         'histories':copy.deepcopy(material['histories']),'questions':copy.deepcopy(material['questions']),
         'reviewer_declaration':{'reviewer_label':f'R{i}','completed_by_human':True,'completed_independently':True,'seen_other_review':False,
           'seen_automatic_flags_or_arm':False,'used_ai_assistance':True,'prior_source_exposure':None},
         'decisions':[{'blind_id':'b','grounded':'valid','structurally_executable':'invalid','reason':'ambiguous'},
                      {'blind_id':'s','grounded':'valid','structurally_executable':'valid','reason':''}]})
    return material,key,reviewers


def test_valid_yield_includes_missing_slots_and_keeps_guard_flags_separate():
    material,key,reviews=fixture();result=analyze(material,key,reviews)
    assert result['arms']['baseline']['generated']==1 and result['arms']['baseline']['unfilled_budget_slots']==39
    assert result['arms']['supplement']['consensus_valid_per_budget_capacity']==1/40
    assert result['arms']['supplement']['consensus_valid_per_generated']['value']==1
    assert result['arms']['supplement']['valid_flagged']==1
    assert result['mean_paired_valid_per_budget_difference']==0.025


def test_disagreement_is_unresolved_not_assumed_valid_or_invalid():
    material,key,reviews=fixture();reviews[1]['decisions'][1]['structurally_executable']='uncertain';reviews[1]['decisions'][1]['reason']='unclear'
    result=analyze(material,key,reviews)
    assert result['arms']['supplement']['unresolved']==1
    assert result['arms']['supplement']['consensus_valid_per_budget_capacity']==0


def test_modified_sources_or_false_independence_are_rejected():
    material,key,reviews=fixture();reviews[0]['questions'][0]['prompt']='changed'
    with pytest.raises(ValueError):analyze(material,key,reviews)
    material,key,reviews=fixture();reviews[0]['reviewer_declaration']['seen_other_review']=True
    with pytest.raises(ValueError):analyze(material,key,reviews)
