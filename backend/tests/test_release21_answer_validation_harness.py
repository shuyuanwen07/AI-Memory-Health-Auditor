"""Prospective synthetic role/provenance checks; never external model calls."""
import copy
import hashlib
import json
from pathlib import Path
import runpy
import sys

import pytest

sys.path.insert(0,str(Path('/scripts') if Path('/scripts').exists() else Path(__file__).resolve().parents[2]/'scripts'))
from stability_configuration import (pilot_call_counts, role_settings,
    preflight_all_roles, study_trial_memory_controls, study_trial_controls_match)
from stability_grading_budget import output_budget_ledger
from stability_request_contracts import expected_roles, expected_contract, validate_contract
from stability_answer_validation import (ROLE, OBSERVATIONS, DRAFT, digest, text_digest,
    read_observation, validate_binding, compare_observation, summarize)


def study(enabled=True):
    profile={'identity_analysis':'evidence_links','identity_analysis_output_token_limit':8192,
             'identity_analysis_reasoning_effort':'low','reasoning_effort':'medium'}
    if enabled:profile.update(answer_validation='source_grounding',answer_validation_output_token_limit=8192,
                              answer_validation_reasoning_effort='medium')
    s={'request_contract_required':True,'target':{'output_token_limit':8192,'memory_capacity':500,
       'max_retrieved_records':100,'context_character_budget':32000,'final_target_profile_flags':profile},
       'grading':{'output_token_limit':4096},'development_pilot':{'cohorts':[
          {'selected_ids':['a','b','c','d'],'repetitions':3,'arms':['weak_first_hit','strong_rule_based']},
          {'selected_ids':['e','f','g','h','i','j'],'repetitions':1,'arms':['strong_rule_based']}],
          'target_calls':30,'grader_calls_max':30,'evidence_stage_calls_max':18},
       'critical_guards':{'target_calls':36,'grader_calls_max':36,'identity_evidence_calls_max':36},
       'execution':{'planned_total_target_calls':120,'planned_maximum_grader_calls':120,'extra_model_stage_calls':60}}
    if enabled:
        for name,count in [('development_pilot',30),('critical_guards',36),('execution',120)]:
            s[name]['answer_validation_calls_max']=count
    return s


def trial(enabled=True,arm='weak_first_hit'):
    s=study(enabled)
    return {**study_trial_memory_controls(s),'model':'openai/gpt-6-luna','provider':'openrouter',
      'output_token_limit':8192,'grading_output_token_limit':4096,'request_contract_required':True,
      'maximum_extra_answer_validation_calls':int(enabled),'strategies':[arm]}


def test_enabled_common_role_counts_caps_and_legacy_off():
    s=study();p=trial()
    assert pilot_call_counts(s)['answer_validation_calls_max']==30
    assert role_settings(p,ROLE)=={'output_token_limit':8192,'reasoning_effort':'medium'}
    assert preflight_all_roles(s,study=True,environ={'PIPELINE_MAX_OUTPUT_TOKENS':'8192'})['passed']
    assert not preflight_all_roles(s,study=True,environ={'PIPELINE_MAX_OUTPUT_TOKENS':'4096'})['passed']
    assert output_budget_ledger(s)['all_roles_call_upper_bound_including_pilot_final_and_guards']==672
    assert output_budget_ledger(s)['all_answer_validation_output_tokens_max']==1523712
    assert output_budget_ledger(s)['all_output_token_upper_bound_including_pilot_final_and_guards']==4743168
    assert output_budget_ledger(study(False))['all_roles_call_upper_bound_including_pilot_final_and_guards']==486
    assert 'answer_validation_calls_max' not in pilot_call_counts(study(False))
    assert ROLE not in preflight_all_roles(study(False),study=True,environ={})['roles']
    assert study_trial_controls_match(s,p)


def test_extra_repair_cohort_counts_remain_dynamic_and_no_quality_rule_added():
    s=study()
    s['development_pilot']['cohorts'].append({'name':'repair','split':'development_repair',
      'selected_ids':['repair-a','repair-b','repair-c','repair-d'],'repetitions':1,'arms':['strong_rule_based']})
    s['development_pilot'].update(target_calls=34,grader_calls_max=34,evidence_stage_calls_max=22,answer_validation_calls_max=34)
    assert pilot_call_counts(s)=={'target_calls':34,'grader_calls_max':34,'evidence_stage_calls_max':22,'answer_validation_calls_max':34}
    assert output_budget_ledger(s)['all_roles_call_upper_bound_including_pilot_final_and_guards']==688



@pytest.mark.parametrize('arm',['weak_first_hit','strong_rule_based'])
def test_wire_role_common_both_arms_and_strict_json_contract(arm):
    p=trial(arm=arm)
    roles=expected_roles(p,question='What is the recorded color?',selected_record_count=1)
    assert ROLE in roles and 'target_identity_evidence' not in roles
    contract=expected_contract(p,ROLE,instructions='Synthetic review.',prompt='Synthetic payload.',
      schema_name='target_answer_source_validation',schema={'type':'object','properties':{},'additionalProperties':False})
    validate_contract(p,ROLE,contract)
    assert contract['max_tokens']=={'present':True,'value':8192}
    assert contract['reasoning']=={'present':True,'value':{'effort':'medium'}}
    changed=copy.deepcopy(contract);changed['reasoning']={'present':False}
    with pytest.raises(ValueError):validate_contract(p,ROLE,changed)


@pytest.mark.parametrize('mutation',['mode','cap','effort','calls','disable'])
def test_study_trial_cannot_downgrade_validation(mutation):
    s=study();p=trial()
    if mutation=='mode':p['target_memory_profile']['answer_validation']='off'
    if mutation=='disable':s=study(False)
    if mutation=='cap':p['target_memory_profile']['answer_validation_output_token_limit']=4096
    if mutation=='effort':p['target_memory_profile']['answer_validation_reasoning_effort']='low'
    if mutation=='calls':p['maximum_extra_answer_validation_calls']=0
    assert not study_trial_controls_match(s,p)


@pytest.mark.parametrize('value',[0,511,8193,True,'8192'])
def test_invalid_declared_validation_cap_fails(value):
    p=trial();p['target_memory_profile']['answer_validation_output_token_limit']=value
    with pytest.raises(ValueError):role_settings(p,ROLE)


def test_missing_validation_logical_ledger_does_not_borrow_identity_budget():
    s=study();del s['execution']['answer_validation_calls_max']
    with pytest.raises(ValueError):output_budget_ledger(s)


def bound_fixture():
    from app.target_systems.controlled import ControlledTargetSystemAdapter
    context=['The synthetic object is blue.'];question='What color is the synthetic object?';draft_text='It is blue.'
    execution={'provider':'openrouter','model':'openai/gpt-6-luna','reported_model':'openai/gpt-6-luna',
      'agent_role':ROLE,'requested_output_token_limit':8192,'declared_output_token_limit':8192,
      'requested_reasoning_effort':'medium','request_attempts':1,'reported_output_tokens':20,
      'private_unexported_extra':'not part of public meter'}
    hashes={'question_sha256':text_digest(question),'source_context_sha256':digest(context),'source_roles_sha256':digest(['user']),
      'draft_answer_sha256':text_digest(draft_text),'final_answer_sha256':text_digest(draft_text)}
    result={'version':'target-answer-source-validation-v1','validation_scope':'local_byte_bindings_and_recorded_model_review_not_semantic_proof',
            'decision':'supported','final_answer':draft_text,**hashes}
    observation={'status':'completed','raw_input_payload':{'question':question,'selected_context':context,'source_roles':['user'],'draft_answer':draft_text},
      'execution':execution,'output_data':result,'raw_model_review':{'synthetic':'separate raw review'},'elapsed_ms':1}
    draft={'response_text':draft_text,'execution_metadata':{'memory_input':{'context_sha256':digest(context),'prompt_sha256':text_digest(question)}}}
    final=copy.deepcopy(draft);final['execution_metadata']['answer_validation']={k:v for k,v in result.items() if k!='final_answer'}
    final['execution_metadata']['answer_validation'].update(execution=ControlledTargetSystemAdapter._answer_validation_meter(execution),
      draft_execution_id='DRAFT-STAGE',execution_id='REVIEW-STAGE',final_text_source='original_draft')
    events=[{'agent_role':ROLE,'execution':execution}]
    return observation,draft,final,events


def test_exact_primary_final_meter_binding_and_separate_summary():
    observation,draft,final,events=bound_fixture()
    row=validate_binding(trial(),observation=observation,draft=draft,final=final,events=events)
    assert row['status']=='validated' and row['semantic_correctness_proven'] is False
    result=summarize([{'answer_validation':row,'extra_agent_executions':events}])
    assert result['validated']==1 and result['attempted_calls']==1
    assert result['separate_execution_usage']['request_attempts']['complete_total']==1
    assert result['separate_execution_usage']['reported_cost_credits']['complete_total'] is None
    from stability_auxiliary import summarize_auxiliary
    assert summarize_auxiliary([{'split':'development','arm':'weak_first_hit','round':1,
      'answer_validation':row,'extra_agent_executions':events}])['total']['attempted']==0


@pytest.mark.parametrize('mutation',['draft','final','context','roles','question','meter','missing','duplicate','ids'])
def test_bound_validation_tampering_fails(mutation):
    obs,draft,final,events=bound_fixture()
    if mutation=='draft':draft['response_text']='A changed draft.'
    if mutation=='final':final['response_text']='A changed delivered answer.'
    if mutation in {'context','roles','question'}:
        key={'context':'selected_context','roles':'source_roles','question':'question'}[mutation]
        obs['raw_input_payload'][key]=['altered'] if mutation!='question' else 'altered'
    if mutation=='meter':final['execution_metadata']['answer_validation']['execution']['requested_output_token_limit']=4096
    if mutation=='missing':obs=None
    if mutation=='duplicate':events*=2
    if mutation=='ids':final['execution_metadata']['answer_validation']['execution_id']='DRAFT-STAGE'
    with pytest.raises(ValueError):validate_binding(trial(),observation=obs,draft=draft,final=final,events=events)


def test_observation_replay_is_exact_except_elapsed_and_private_schema():
    obs,*_=bound_fixture();again=copy.deepcopy(obs);again['elapsed_ms']=99
    compare_observation(obs,again)
    for key in ['raw_model_review','raw_input_payload','output_data','execution']:
        changed=copy.deepcopy(again);changed[key]={}
        with pytest.raises(ValueError):compare_observation(obs,changed)


def test_public_export_excludes_private_answer_review_bodies():
    from export_stability_package import public_metadata,actual_role_mismatches
    public=public_metadata({'raw_model_review':{'private':'source'},'draft_answer':'private draft',
      'selected_context':['private source'],'execution':{'agent_role':ROLE,'reported_output_tokens':7}})
    assert public=={'execution':{'agent_role':ROLE,'reported_output_tokens':7}}
    obs,draft,final,events=bound_fixture()
    assert actual_role_mismatches([{'case_id':'synthetic','split':'development','round':1,'arm':'weak_first_hit',
      'target_usable':False,'agent_execution_attempts':events}])==[]



def test_disabled_historical_records_not_invented_as_validation():
    assert validate_binding(trial(False),observation=None,draft=None,final={},events=[])['status']=='not_enabled'
    obs,draft,final,events=bound_fixture()
    with pytest.raises(ValueError):validate_binding(trial(False),observation=obs,draft=draft,final=final,events=events)


def test_private_observation_wrapper_retains_first_failure_and_0600(tmp_path):
    from run_stability_trial import identity_observation_wrapper
    class Validator:
        last_observation=None
        last_execution=None
        def validate(self):
            self.last_observation={'status':'failed','raw_model_review':{'private':'source'}}
            raise ValueError('original-contract-failure')
    wrapped=identity_observation_wrapper(Validator.validate,tmp_path,filename=OBSERVATIONS,
      version='private-answer-validation-observation-receipts-v1')
    with pytest.raises(ValueError,match='original-contract-failure'):wrapped(Validator())
    assert (tmp_path/OBSERVATIONS).stat().st_mode & 0o777==0o600
    assert read_observation(tmp_path)['raw_model_review']=={'private':'source'}
    value=json.loads((tmp_path/OBSERVATIONS).read_text());value['observations']*=2
    (tmp_path/OBSERVATIONS).write_text(json.dumps(value))
    with pytest.raises(ValueError):read_observation(tmp_path)


@pytest.mark.parametrize('arm',['weak_first_hit','strong_rule_based'])
@pytest.mark.parametrize('validation_mode',['uncertain','malformed'])
def test_actual_wrapper_distinguishes_primary_draft_from_final_fake_http(monkeypatch,tmp_path,arm,validation_mode):
    import httpx
    from app.target_ai.providers import HttpTargetAIConnector
    from app.extraction.llm import PipelineLLMClient
    from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer
    from app.memory_agent.answer_validation import TargetAnswerValidator,ABSTENTION_TEXT
    from app.target_systems.controlled import ControlledTargetSystemAdapter
    for cls,name in [(HttpTargetAIConnector,'execute'),(HttpTargetAIConnector,'_execute_provider'),
      (PipelineLLMClient,'complete_json'),(TargetIdentityEvidenceAnalyzer,'analyze'),
      (TargetAnswerValidator,'validate'),(ControlledTargetSystemAdapter,'answer')]:
        monkeypatch.setattr(cls,name,getattr(cls,name))
    monkeypatch.setenv('OPENROUTER_API_KEY','synthetic-key');monkeypatch.setenv('PIPELINE_MAX_OUTPUT_TOKENS','8192')
    monkeypatch.delenv('OPENROUTER_PROVIDER',raising=False)
    calls=[]
    def post(url,headers,json,timeout):
        calls.append(copy.deepcopy(json));name=(json.get('response_format',{}).get('json_schema') or {}).get('name')
        if name=='target_answer_source_validation':
            content='{}' if validation_mode=='malformed' else __import__('json').dumps({'decision':'uncertain','final_answer':ABSTENTION_TEXT,'quotes':[],'claims':[],'flags':[],'review_note':'Synthetic contract check, no semantic scoring claim.'})
        elif name=='longmemeval_pilot_assessment':content='{"correct":true,"reason":"Synthetic harness only."}'
        else:content='The object is blue.'
        return httpx.Response(200,json={'model':'openai/gpt-6-luna','choices':[{'finish_reason':'stop','message':{'content':content}}],
          'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}})
    monkeypatch.setattr(httpx,'post',post)
    payload=[{'question_id':'SYN-VALIDATE','question_type':'single-session-user','question':'What color is the object?',
      'question_date':'2026/01/03 (Sat) 10:00','answer':'blue','answer_session_ids':['s1'],
      'haystack_sessions':[[{'role':'user','content':'The object is blue.'}]],
      'haystack_dates':['2026/01/01 (Thu) 10:00'],'haystack_session_ids':['s1']}]
    data=json.dumps(payload).encode();(tmp_path/'pilot-subset.json').write_bytes(data)
    p=trial(arm=arm);p['target_memory_profile'].update(identity_analysis='off',retain_assistant_history=True,retrieve_message_context=True)
    p.update(scope='exploratory_pilot_not_formal_experiment_c',source_authorised=True,selected_ids=['SYN-VALIDATE'],
      subset_sha256=hashlib.sha256(data).hexdigest(),maximum_extra_identity_evidence_calls=0,
      source_provenance={'revision':'synthetic','license':'synthetic','citation':'Synthetic test only.'})
    (tmp_path/'pilot-protocol.json').write_text(json.dumps(p));monkeypatch.setattr(sys,'argv',['run_stability_trial.py','--directory',str(tmp_path)])
    path=Path('/scripts/run_stability_trial.py') if Path('/scripts').exists() else Path(__file__).resolve().parents[2]/'scripts/run_stability_trial.py'
    with pytest.raises(SystemExit) as terminal:runpy.run_path(str(path),run_name='__main__')
    assert terminal.value.code==(0 if validation_mode=='uncertain' else 1)
    report=json.loads((tmp_path/'pilot-report.json').read_text());proof=json.loads((tmp_path/'actual-wire-validation.json').read_text())
    draft=json.loads((tmp_path/DRAFT).read_text())
    assert draft['response_text']=='The object is blue.'
    assert (tmp_path/DRAFT).stat().st_mode & 0o777==0o600
    if validation_mode=='uncertain':
        assert report['target_call_receipts'][0]['response']['response_text']==ABSTENTION_TEXT
        assert proof['status']=='passed'
        assert proof['required_roles']==sorted(['target_answer',ROLE,'benchmark_pilot_assessment'])
        assert len(calls)==3 and proof['answer_validation']['decision']=='uncertain'
        assert read_observation(tmp_path)['raw_input_payload']['draft_answer']==draft['response_text']
    else:
        assert proof['status']=='failed' and report['target_call_receipts'][0]['status']=='failed'
        assert len(calls)==2 and report['semantic_assessments']==[]
        assert read_observation(tmp_path)['status']=='failed'


def test_question_hash_is_utf8_text_not_canonical_json_string():
    obs,draft,final,events=bound_fixture()
    question='谁记录了蓝色物体？ 🧭'
    obs['raw_input_payload']['question']=question
    obs['output_data']['question_sha256']=text_digest(question)
    draft['execution_metadata']['memory_input']['prompt_sha256']=text_digest(question)
    final['execution_metadata']['memory_input']['prompt_sha256']=text_digest(question)
    final['execution_metadata']['answer_validation']['question_sha256']=text_digest(question)
    result=validate_binding(trial(),observation=obs,draft=draft,final=final,events=events)
    assert result['question_sha256']==text_digest(question)
    assert result['question_sha256']!=digest(question)


def test_legacy_canonical_string_question_hash_cannot_impersonate_utf8_receipt():
    obs,draft,final,events=bound_fixture()
    wrong=digest(obs['raw_input_payload']['question'])
    obs['output_data']['question_sha256']=wrong
    final['execution_metadata']['answer_validation']['question_sha256']=wrong
    with pytest.raises(ValueError,match='hash mismatch'):
        validate_binding(trial(),observation=obs,draft=draft,final=final,events=events)
