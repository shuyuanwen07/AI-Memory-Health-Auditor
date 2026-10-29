"""In-memory tests for blindness, provenance and missing denominator handling."""
import copy
import pytest
from scripts.analyze_ac2_scope_holdout import analyze,canonical,sha


def fixture():
    material={'format':'ac2-scope-v2-blind-material-v1','histories':[{'history_id':'H','source_messages':[]}],
              'questions':[{'blind_id':'a','history_id':'H','prompt':'question'}, {'blind_id':'b','history_id':'H','prompt':'other'}]}
    digest=sha(canonical(material));key={'material_sha256':digest,'identity':{'a':{'flag':'review'},'b':{'flag':None}},'ledger':[{'missing':38}]}
    confirmation={'format':'ac2-scope-v2-human-confirmation-v1','confirmed_by':'user','completed_by_humans':True}
    reviews=[]
    for i in (1,2):
        reviews.append({'format':'ac2-scope-v2-human-review-v1','reviewer_slot':i,'material_sha256':digest,
          'histories':copy.deepcopy(material['histories']),'questions':copy.deepcopy(material['questions']),
          'reviewer_declaration':{'reviewer_label':f'R{i}','completed_by_human':True,'completed_independently':True,'seen_other_review':False,
            'seen_guard_flags':False,'used_ai_assistance':True,'prior_exposure_to_sources':None},
          'decisions':[{'blind_id':'a','grounded':'valid','structurally_executable':'invalid','reason':'ambiguous'},
                       {'blind_id':'b','grounded':'valid','structurally_executable':'valid','reason':''}]})
    return material,key,reviews,confirmation


def test_flags_and_missing_are_reported_separately():
    material,key,reviews,confirmation=fixture();result=analyze(material,key,{},reviews,confirmation)
    assert result['invalid_flag_rate']=={'numerator':1,'denominator':1,'value':1.0}
    assert result['valid_flag_rate']=={'numerator':0,'denominator':1,'value':0.0}
    assert result['unused_budget_slots']==38


def test_disagreement_does_not_enter_decided_denominator():
    material,key,reviews,confirmation=fixture();reviews[1]['decisions'][0]['structurally_executable']='uncertain';reviews[1]['decisions'][0]['reason']='unclear'
    result=analyze(material,key,{},reviews,confirmation)
    assert result['invalid_flag_rate']['denominator']==0
    assert result['counts']['structural_disagreement_or_uncertain']==1


def test_unblinding_or_source_modification_rejected():
    material,key,reviews,confirmation=fixture();reviews[0]['reviewer_declaration']['seen_guard_flags']=True
    with pytest.raises(ValueError):analyze(material,key,{},reviews,confirmation)
    material,key,reviews,confirmation=fixture();reviews[0]['questions'][0]['prompt']='modified'
    with pytest.raises(ValueError):analyze(material,key,{},reviews,confirmation)
