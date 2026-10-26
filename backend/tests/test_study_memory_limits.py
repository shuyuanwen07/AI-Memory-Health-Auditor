"""Synthetic configuration/materialization only; no benchmark bodies or APIs."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path('/scripts') if Path('/scripts').exists() else Path(__file__).resolve().parents[2]/'scripts'))
from stability_configuration import study_memory_limits, study_trial_memory_controls, study_trial_controls_match
import prepare_stability_guards as guards
import run_stability_study as study_script


def study(enlarged=True):
    target={'output_token_limit':8192,'final_target_profile_flags':{
        'identity_analysis':'evidence_links','identity_analysis_failure_policy':'continue_without_advisory',
        'retention_policy':'source_coverage','reasoning_effort':'medium',
        'identity_analysis_reasoning_effort':'low','identity_analysis_output_token_limit':8192}}
    if enlarged:target.update(memory_capacity=500,max_retrieved_records=100,context_character_budget=32000)
    return {'target':target,'grading':{'output_token_limit':4096},'execution':{'extra_model_stage_calls':1}}


def trial(protocol):
    return {**study_trial_memory_controls(protocol),'output_token_limit':8192,'grading_output_token_limit':4096,
        'request_contract_required':True,'memory_preparation_receipt_required':True}


def test_legacy_omission_retains_exact_original_materialized_control_order():
    protocol=study(False);profile=protocol['target']['final_target_profile_flags']
    expected={'target_memory_capacity':500,'target_memory_profile':{'retain_assistant_history':True,
        'retrieve_message_context':True,'max_retrieved_records':50,'context_character_budget':16000,
        'output_token_limit':8192,**profile},'context_character_budget':16000}
    assert json.dumps(study_trial_memory_controls(protocol))==json.dumps(expected)
    assert study_memory_limits({})=={'memory_capacity':500,'max_retrieved_records':50,'context_character_budget':16000}
    assert study_trial_controls_match({}, {})


def test_new_shared_limits_match_nested_and_top_controls_without_mutating_study():
    protocol=study();before=copy.deepcopy(protocol);actual=trial(protocol)
    assert protocol==before
    assert actual['target_memory_profile']['max_retrieved_records']==100
    assert actual['target_memory_profile']['context_character_budget']==actual['context_character_budget']==32000
    assert actual['target_memory_capacity']==500
    protocol.update(request_contract_required=True,memory_preparation_receipt_required=True)
    assert study_trial_controls_match(protocol,actual)


@pytest.mark.parametrize('key,bad',[('memory_capacity',0),('memory_capacity',501),('memory_capacity',True),
    ('max_retrieved_records',0),('max_retrieved_records',501),('max_retrieved_records','100'),
    ('max_retrieved_records',100.0),('context_character_budget',99),('context_character_budget',100001),
    ('context_character_budget',True),('context_character_budget',None)])
def test_declared_memory_bounds_are_strict_and_fail_closed(key,bad):
    protocol=study();protocol['target'][key]=bad
    with pytest.raises(ValueError):study_memory_limits(protocol)
    assert not study_trial_controls_match(protocol,trial(study()))


@pytest.mark.parametrize('key',['max_retrieved_records','context_character_budget'])
def test_explicit_nested_study_contradictions_fail_before_materialization(key):
    protocol=study();protocol['target']['final_target_profile_flags'][key]=50
    with pytest.raises(ValueError,match='contradicts'):study_trial_memory_controls(protocol)
    assert not study_trial_controls_match(protocol,trial(study()))
    legacy=study(False);legacy['target']['final_target_profile_flags'][key]=100 if key=='max_retrieved_records' else 32000
    with pytest.raises(ValueError):study_memory_limits(legacy)


@pytest.mark.parametrize('path,value',[('capacity',499),('capacity',True),('max',50),('max',100.0),
    ('nested_context',16000),('top_context',16000),('top_context',True)])
def test_trial_tampering_fails_even_without_wire_requirement(path,value):
    protocol=study();actual=trial(protocol)
    if path=='capacity':actual['target_memory_capacity']=value
    elif path=='max':actual['target_memory_profile']['max_retrieved_records']=value
    elif path=='nested_context':actual['target_memory_profile']['context_character_budget']=value
    else:actual['context_character_budget']=value
    assert not study_trial_controls_match(protocol,actual)


def test_new_study_cannot_silently_downgrade_to_missing_legacy_limits():
    assert not study_trial_controls_match(study(),{})
    legacy=trial(study(False))
    assert study_trial_controls_match(study(False),legacy)
    legacy.pop('context_character_budget');legacy.pop('target_memory_capacity')
    legacy['target_memory_profile'].pop('max_retrieved_records');legacy['target_memory_profile'].pop('context_character_budget')
    assert study_trial_controls_match(study(False),legacy)


@pytest.mark.parametrize('enlarged',[False,True])
def test_guard_materializer_uses_shared_declared_controls_for_all36(tmp_path,enlarged):
    root=tmp_path/'synthetic';stage=root/'safety-guards';protocol=study(enlarged)
    cases=[{'case_id':f'control-{i}','question':'What did I note?','question_date':'2026/01/02',
        'conversation':{'messages':[{'message_id':'SYN1','role':'user','content':'I noted blue.',
                                    'timestamp':'2026-01-01T00:00:00Z'}]}}for i in range(12)]
    study_script.dump(root/'guards/conversation-cases.json',{'cases':cases})
    study_script.dump(root/'guards/evaluator-private-criteria.json',{'cases':[{'case_id':c['case_id']}for c in cases]})
    guards.materialize(root,stage,protocol)
    rows=study_script.read(stage/'trial-matrix.json')['trials'];assert len(rows)==36
    expected=study_trial_memory_controls(protocol)
    for row in rows:
        actual=study_script.read(stage/row['directory']/'pilot-protocol.json')
        assert all(actual[key]==value for key,value in expected.items())
        assert study_trial_controls_match(protocol,actual)


@pytest.mark.parametrize('enlarged',[False,True])
def test_real_development_materializer_both_arms_share_limits(tmp_path,monkeypatch,enlarged):
    monkeypatch.setenv('PIPELINE_MAX_OUTPUT_TOKENS','8192')
    root=tmp_path/'synthetic';stage=root/'development-pilot';protocol=study(enlarged)
    protocol.update(acceptance={},development_pilot={'selected_ids':['synthetic-q'],'repetitions':1})
    selected={'status':'selection_complete','selected_ids':['synthetic-q'],'seed':'synthetic'}
    study_script.dump(root/'study-protocol.json',protocol);study_script.dump(root/'selected-metadata.json',selected)
    study_script.dump(root/'selection-commitment.json',{'quantitative_acceptance_sha256':study_script.canon({}),
        'selected_metadata_sha256':study_script.sha(root/'selected-metadata.json'),'selected_ids':['synthetic-q']})
    reference=root.parent/'longmemeval-identity-conservative-final-20261021'
    data=[{'question_id':'synthetic-q','question_type':'synthetic','question':'What color did I note?',
        'answer':'Blue','haystack_sessions':[[{'role':'user','content':'I noted blue.'}]],
        'haystack_dates':['2026/01/01'],'haystack_session_ids':['synthetic-session']}]
    source=reference/'regression-4096/run-01/synthetic-case/pilot-subset.json';study_script.dump(source,data)
    study_script.dump(reference/'regression-4096/run-01/suite-manifest.json',{'cases':[{
        'case_id':'synthetic-q','directory':'synthetic-case','subset_sha256':study_script.sha(source)}]})
    study_script.dump(reference/'confirmation-protocol.json',{'source_provenance':{'revision':'synthetic'}})
    workspace=Path(study_script.__file__).resolve().parents[1]
    if Path('/app/app').exists():
        sources={str(Path('backend/app')/p.relative_to('/app/app')):p for p in Path('/app/app').rglob('*.py')}
        sources.update({str(Path('scripts')/p.name):p for p in Path('/scripts').glob('*.py')})
    else:
        sources={str(p.relative_to(workspace)):p for p in [*list((workspace/'backend/app').rglob('*.py')),*list((workspace/'scripts').glob('*.py'))]}
    manifest={name:hashlib.sha256(p.read_bytes()).hexdigest()for name,p in sources.items()}
    study_script.dump(stage/'tested-source-manifest.json',manifest)
    study_script.dump(stage/'FROZEN.json',{'protocol_sha256':study_script.sha(root/'study-protocol.json'),
        'selection_commitment_sha256':study_script.sha(root/'selection-commitment.json')})
    monkeypatch.setattr(sys,'argv',['run_stability_study.py','--root',str(root),'--stage','development-pilot','--phase','materialize'])
    study_script.main()
    rows=study_script.read(stage/'trial-matrix.json')['trials'];assert len(rows)==2
    assert {row['arm']for row in rows}=={'weak_first_hit','strong_rule_based'}
    expected=study_trial_memory_controls(protocol)
    for row in rows:
        actual=study_script.read(stage/row['directory']/'pilot-protocol.json')
        assert all(actual[key]==value for key,value in expected.items())
        assert study_trial_controls_match(protocol,actual)


@pytest.mark.parametrize('flag',['request_contract_required','memory_preparation_receipt_required'])
@pytest.mark.parametrize('missing',['capacity','max','nested_context','top_context','top_output'])
def test_required_study_needs_explicit_actual_memory_controls_even_at_legacy_limits(flag,missing):
    protocol=study(False);protocol[flag]=True;actual=trial(protocol)
    if missing=='capacity':actual.pop('target_memory_capacity')
    elif missing=='max':actual['target_memory_profile'].pop('max_retrieved_records')
    elif missing=='nested_context':actual['target_memory_profile'].pop('context_character_budget')
    elif missing=='top_context':actual.pop('context_character_budget')
    else:actual.pop('output_token_limit')
    assert not study_trial_controls_match(protocol,actual)


def test_contradictory_memory_limits_are_rejected_before_freeze_file(tmp_path,monkeypatch):
    root=tmp_path/'synthetic';protocol=study(False)
    protocol['target']['final_target_profile_flags']['max_retrieved_records']=100
    protocol['target']['profile_is_provisional_pending_parent_final_interface']=False
    protocol['acceptance']={}
    selected={'status':'selection_complete','selected_ids':['synthetic-q'],'seed':'synthetic'}
    study_script.dump(root/'study-protocol.json',protocol);study_script.dump(root/'selected-metadata.json',selected)
    study_script.dump(root/'selection-commitment.json',{'quantitative_acceptance_sha256':study_script.canon({}),
        'selected_metadata_sha256':study_script.sha(root/'selected-metadata.json'),'selected_ids':['synthetic-q']})
    monkeypatch.setattr(study_script,'selection_binding',lambda *args:{})
    monkeypatch.setattr(sys,'argv',['run_stability_study.py','--root',str(root),'--stage','development-pilot','--phase','freeze'])
    with pytest.raises(ValueError,match='contradicts'):study_script.main()
    assert not (root/'development-pilot/FROZEN.json').exists()


@pytest.mark.parametrize('value',[4096,True,None,'8192',8192.0])
def test_nested_output_cannot_override_or_coerce_declared_target_cap(value):
    protocol=study();protocol['target']['final_target_profile_flags']['output_token_limit']=value
    with pytest.raises(ValueError,match='output limit'):study_trial_memory_controls(protocol)


def test_matching_strict_nested_output_preserves_original_controls():
    protocol=study();before=study_trial_memory_controls(protocol)
    protocol['target']['final_target_profile_flags']['output_token_limit']=8192
    assert study_trial_memory_controls(protocol)==before


@pytest.mark.parametrize('value',[4096,True,None,'8192',8192.0])
def test_nested_output_conflicts_are_rejected_before_freeze_file(tmp_path,monkeypatch,value):
    root=tmp_path/'synthetic';protocol=study()
    protocol['target']['final_target_profile_flags']['output_token_limit']=value
    protocol['target']['profile_is_provisional_pending_parent_final_interface']=False
    protocol['acceptance']={}
    selected={'status':'selection_complete','selected_ids':['synthetic-q'],'seed':'synthetic'}
    study_script.dump(root/'study-protocol.json',protocol);study_script.dump(root/'selected-metadata.json',selected)
    study_script.dump(root/'selection-commitment.json',{'quantitative_acceptance_sha256':study_script.canon({}),
        'selected_metadata_sha256':study_script.sha(root/'selected-metadata.json'),'selected_ids':['synthetic-q']})
    monkeypatch.setattr(study_script,'selection_binding',lambda *args:{})
    monkeypatch.setattr(sys,'argv',['run_stability_study.py','--root',str(root),'--stage','development-pilot','--phase','freeze'])
    with pytest.raises(ValueError,match='output limit'):study_script.main()
    assert not (root/'development-pilot/FROZEN.json').exists()
