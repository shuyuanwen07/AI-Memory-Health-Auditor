"""Synthetic metadata and fake HTTP contracts; no model endpoints."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path('/scripts') if Path('/scripts').exists() else Path(__file__).resolve().parents[2]/'scripts'))
from stability_configuration import (pilot_cells,pilot_call_counts,pilot_quality_gates,
    role_settings,preflight_all_roles,source_reuse_scope)
from stability_request_contracts import WireObserver,expected_contract,validate_events,validate_contract,read_wire_events
from stability_grading_budget import output_budget_ledger
from app.target_ai.request_contracts import observe_request_contracts,send_with_request_contract,request_contract_sha256
from app.target_ai.openrouter import build_openrouter_target_payload,CHAT_COMPLETIONS_URL


def study():
    profile={'identity_analysis':'evidence_links','identity_analysis_output_token_limit':8192,
             'reasoning_effort':'low','identity_analysis_reasoning_effort':'low'}
    return {'request_contract_required':True,'target':{'output_token_limit':8192,'final_target_profile_flags':profile},
      'grading':{'output_token_limit':4096},'development_pilot':{'cohorts':[
       {'selected_ids':['a','b','c','d'],'repetitions':3,'arms':['weak_first_hit','strong_rule_based']},
       {'selected_ids':['e','f','g','h','i','j'],'repetitions':1,'arms':['strong_rule_based']}],
       'target_calls':30,'grader_calls_max':30,'evidence_stage_calls_max':18,
       'quality_requirements':[{'split':'development','arm':'strong_rule_based','minimum_correct':9},
          {'split':'development_regression','arm':'strong_rule_based','minimum_correct':5}]},
      'critical_guards':{'target_calls':36,'grader_calls_max':36,'identity_evidence_calls_max':36},
      'execution':{'planned_total_target_calls':120,'planned_maximum_grader_calls':120,'extra_model_stage_calls':60}}


def trial():
    from stability_configuration import study_trial_memory_controls
    s=study()
    return {**study_trial_memory_controls(s),
      'model':'openai/gpt-6-luna','provider':'openrouter','request_contract_required':True,
      'output_token_limit':8192,'grading_output_token_limit':4096,
      'target_memory_profile':study_trial_memory_controls(s)['target_memory_profile']}


def test_pilot_two_complete_grids_and_budget():
    s=study();cells=pilot_cells(s)
    assert len(cells)==30
    assert sum(c['split']=='development' for c in cells)==24
    assert sum(c['split']=='development_regression' for c in cells)==6
    assert pilot_call_counts(s)=={'target_calls':30,'grader_calls_max':30,'evidence_stage_calls_max':18}
    ledger=output_budget_ledger(s)
    assert ledger['all_roles_call_upper_bound_including_pilot_final_and_guards']==486
    assert ledger['all_output_token_upper_bound_including_pilot_final_and_guards']==3219456


def test_historical_pilot_remains_single_round():
    s=study();s['development_pilot']={'selected_ids':['a','b','c','d']}
    assert len(pilot_cells(s))==8


def test_pilot_overlap_and_budget_mismatch_rejected():
    s=study();s['development_pilot']['cohorts'][1]['selected_ids']=['a']
    with pytest.raises(ValueError):pilot_cells(s)
    s=study();s['development_pilot']['target_calls']=24
    with pytest.raises(ValueError):output_budget_ledger(s)


def test_all_roles_preflight_prevents_aux_clip_without_raising_grader():
    s=study()
    assert not preflight_all_roles(s,study=True,environ={'PIPELINE_MAX_OUTPUT_TOKENS':'4096'})['passed']
    p=preflight_all_roles(s,study=True,environ={'PIPELINE_MAX_OUTPUT_TOKENS':'8192'})
    assert p['passed']
    assert p['roles']['target_identity_evidence']['effective_output_token_limit']==8192
    assert p['roles']['benchmark_pilot_assessment']['effective_output_token_limit']==4096
    assert p['roles']['benchmark_pilot_assessment']['reasoning_effort'] is None


def test_unknown_effort_cannot_silently_drop():
    p=trial();p['target_memory_profile']['reasoning_effort']='unavailable'
    with pytest.raises(ValueError):role_settings(p,'target_answer')


def test_extra_development_quality_gates_do_not_pool_splits():
    s=study();rows=[]
    for cell in pilot_cells(s):rows.append({**cell,'semantic_grade':{'status':'completed','correct':True}})
    assert all(g['status']=='pass' for g in pilot_quality_gates(s,rows).values())
    for row in rows:
        if row['split']=='development_regression':row['semantic_grade']['correct']=False
    gates=pilot_quality_gates(s,rows)
    assert gates['development_quality_1']['status']=='pass'
    assert gates['development_quality_2']['status']=='fail'


def test_scope_explicitly_not_full_source_disjoint():
    scope=source_reuse_scope({'version':'catalog09b-evidence-disjoint-metadata-v1','scope_disclosure':'filler may repeat'})
    assert scope['full_source_disjoint'] is False
    assert scope['answer_evidence_disjoint'] is True
    assert scope['public_distractor_conversations_may_repeat'] is True
    assert source_reuse_scope({})['metadata_checks_status']=='legacy_declared'


def test_wire_observer_actual_boundary_and_pure_reconstruction(tmp_path):
    protocol=trial();observer=WireObserver(tmp_path,protocol)
    routing={'require_parameters':True,'allow_fallbacks':False}
    expected=observer.prepare('target_answer',instructions='private data',prompt='question',provider_options=routing)
    payload=build_openrouter_target_payload(model=protocol['model'],instructions='private data',prompt='question',temperature=0,
      max_output_tokens=8192,reasoning_effort='low',provider_options=routing)
    attempts=[]
    with observe_request_contracts(observer):
        send_with_request_contract(url=CHAT_COMPLETIONS_URL,payload=payload,role='target_answer',attempt_index=1,
          collector=attempts,send=lambda:SimpleNamespace(status_code=200))
    events=read_wire_events(tmp_path,protocol)
    assert validate_events(protocol,events,'target_answer',expected,{'request_attempts':1,'request_contract_attempts':attempts})==1
    text=(tmp_path/'actual-wire-attempt-receipts.json').read_text()
    assert 'private data' not in text and 'question' not in text
    assert expected['reasoning']=={'present':True,'value':{'effort':'low'}}


def test_wire_missing_or_changed_controls_fail_before_send(tmp_path):
    p=trial();observer=WireObserver(tmp_path,p)
    expected=observer.prepare('target_answer',instructions='i',prompt='q')
    changed=copy.deepcopy(expected);changed['reasoning']={'present':False}
    with pytest.raises(ValueError):validate_contract(p,'target_answer',changed)
    payload=build_openrouter_target_payload(model=p['model'],instructions='i',prompt='q',temperature=0,
      max_output_tokens=8192,reasoning_effort=None,provider_options={'require_parameters':True,'allow_fallbacks':False})
    sent=[]
    with observe_request_contracts(observer),pytest.raises(ValueError):
        send_with_request_contract(url=CHAT_COMPLETIONS_URL,payload=payload,role='target_answer',attempt_index=1,
         collector=[],send=lambda:sent.append(True))
    assert sent==[]


def test_grader_reasoning_omitted_and_cap_remains_4096():
    p=trial();contract=expected_contract(p,'benchmark_pilot_assessment',instructions='grade',prompt='private response',
      schema_name='grade',schema={'type':'object'})
    assert contract['reasoning']=={'present':False}
    assert contract['max_tokens']=={'present':True,'value':4096}
    validate_contract(p,'benchmark_pilot_assessment',contract)


def test_wire_validation_requires_meter_and_sidecar_agreement(tmp_path):
    p=trial();contract=expected_contract(p,'target_answer',instructions='i',prompt='q')
    event={'role':'target_answer','attempt_index':1,'status':'response','request_contract':contract,
      'request_contract_sha256':request_contract_sha256(contract)}
    with pytest.raises(ValueError):validate_events(p,[event],'target_answer',contract,{'request_attempts':1,'request_contract_attempts':[]})


@pytest.mark.parametrize('auxiliary_mode',['valid','contract','length','skip','early_failure'])
def test_real_trial_wrapper_captures_target_aux_and_grader_fake_http(monkeypatch,tmp_path,auxiliary_mode):
    import hashlib
    import httpx
    import runpy
    from app.target_ai.providers import HttpTargetAIConnector
    from app.extraction.llm import PipelineLLMClient
    from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer
    # Register original class methods so all runpy monkeypatches are restored.
    for cls,name in [(HttpTargetAIConnector,'execute'),(HttpTargetAIConnector,'_execute_provider'),
                     (PipelineLLMClient,'complete_json'),(TargetIdentityEvidenceAnalyzer,'analyze')]:
        monkeypatch.setattr(cls,name,getattr(cls,name))
    monkeypatch.setenv('OPENROUTER_API_KEY','synthetic-key')
    monkeypatch.setenv('PIPELINE_MAX_OUTPUT_TOKENS','8192')
    monkeypatch.delenv('OPENROUTER_PROVIDER',raising=False)
    calls=[]
    def post(url,headers,json,timeout):
        calls.append(copy.deepcopy(json))
        name=(json.get('response_format',{}).get('json_schema') or {}).get('name')
        if name=='target_identity_evidence' and auxiliary_mode=='early_failure':
            return httpx.Response(400,json={'error':{'message':'Synthetic unsupported parameter.'}})
        if name=='target_identity_evidence' and auxiliary_mode=='length':
            return httpx.Response(200,json={'model':'openai/gpt-6-luna','choices':[{'finish_reason':'length','message':{'content':None}}],
              'usage':{'prompt_tokens':50,'completion_tokens':8192,'total_tokens':8242,'completion_tokens_details':{'reasoning_tokens':8192}}})
        if name=='target_identity_evidence' and auxiliary_mode=='contract':
            content=__import__('json').dumps({'quotes':[{'quote_id':'Q1','record_index':1,'quote':'fabricated quote','occurrence':0}],'mentions':[],'relations':[],'limitations':'Synthetic invalid exact quote.'})
        elif name=='target_identity_evidence':
            content=__import__('json').dumps({'quotes':[],'mentions':[],'relations':[],'limitations':'Synthetic no proposed links.'})
        elif name=='longmemeval_pilot_assessment':content='{"correct":true,"reason":"Synthetic only."}'
        else:content='Two projects.'
        return httpx.Response(200,json={'model':'openai/gpt-6-luna','choices':[{'finish_reason':'stop','message':{'content':content}}],
          'usage':{'prompt_tokens':50,'completion_tokens':30,'total_tokens':80,'completion_tokens_details':{'reasoning_tokens':10}}})
    monkeypatch.setattr(httpx,'post',post)
    payload=[{'question_id':'SYN-CONTRACT','question_type':'multi-session','question':('Which project have I worked on?' if auxiliary_mode=='skip' else 'How many projects have I worked on?'),
      'question_date':'2026/01/03 (Sat) 10:00','answer':'2','answer_session_ids':['s1','s2'],
      'haystack_sessions':[[{'role':'user','content':'I worked on Orion.'}],[{'role':'user','content':'I worked on Cedar.'}]],
      'haystack_dates':['2026/01/01 (Thu) 10:00','2026/01/02 (Fri) 10:00'],'haystack_session_ids':['s1','s2']}]
    data=__import__('json').dumps(payload).encode();(tmp_path/'pilot-subset.json').write_bytes(data)
    protocol={**trial(),'scope':'exploratory_pilot_not_formal_experiment_c','source_authorised':True,
      'selected_ids':['SYN-CONTRACT'],'subset_sha256':hashlib.sha256(data).hexdigest(),
      'strategies':['strong_rule_based'],'target_memory_capacity':500,'maximum_extra_identity_evidence_calls':1,
      'source_provenance':{'revision':'synthetic','license':'synthetic','citation':'Synthetic test only.'}}
    protocol['target_memory_profile'].update(retain_assistant_history=True,retrieve_message_context=True,
       context_character_budget=16000,identity_analysis_failure_policy='continue_without_advisory')
    (tmp_path/'pilot-protocol.json').write_text(__import__('json').dumps(protocol))
    monkeypatch.setattr(sys,'argv',['run_stability_trial.py','--directory',str(tmp_path)])
    with pytest.raises(SystemExit) as completed:
        runpy.run_path(str(Path('/scripts/run_stability_trial.py') if Path('/scripts').exists() else Path(__file__).resolve().parents[2]/'scripts/run_stability_trial.py'),run_name='__main__')
    assert completed.value.code==(1 if auxiliary_mode=='early_failure' else 0)
    report=__import__('json').loads((tmp_path/'pilot-report.json').read_text())
    if auxiliary_mode=='early_failure':
        proof=__import__('json').loads((tmp_path/'actual-wire-validation.json').read_text())
        assert proof['status']=='failed' and set(proof['actual_roles'])=={'target_identity_evidence'}
        assert {'target_answer','benchmark_pilot_assessment'}<=set(proof['required_roles'])
        assert report['status']=='failed' and report['semantic_assessments']==[]
        return
    assert report['status']=='completed'
    proof=__import__('json').loads((tmp_path/'actual-wire-validation.json').read_text())
    assert proof['status']=='passed',proof
    roles=['target_answer','benchmark_pilot_assessment'] if auxiliary_mode=='skip' else ['target_identity_evidence','target_answer','benchmark_pilot_assessment']
    assert proof['roles']=={role:1 for role in roles}
    assert [call['max_tokens'] for call in calls]==([8192,4096] if auxiliary_mode=='skip' else [8192,8192,4096])
    assert all(call['reasoning']=={'effort':'low'} for call in calls[:-1])
    assert 'reasoning' not in calls[-1]
    metadata=report['benchmark_result']['conditions'][0]['cases'][0]['execution_metadata']
    identity=metadata['identity_analysis']
    assert identity['status']==('skipped_not_applicable' if auxiliary_mode=='skip' else 'analyzed' if auxiliary_mode=='valid' else 'degraded_without_advisory')
    if auxiliary_mode in {'contract','length'}:
        assert identity['failure_receipt']['version']=='target-identity-failure-receipt-v2'
        assert metadata['memory_input']['identity_advisory_sha256'] is None
    from stability_request_contracts import validate_events
    events=read_wire_events(tmp_path,protocol)
    extra=__import__('json').loads((tmp_path/'agent-execution-receipts.json').read_text())
    for payload_sent,role in zip(calls,roles):
        fmt=payload_sent.get('response_format',{}).get('json_schema') or {}
        kwargs={'instructions':payload_sent['messages'][0]['content'],'prompt':payload_sent['messages'][1]['content']}
        if role!='target_answer':kwargs.update(schema_name=fmt['name'],schema=fmt['schema'])
        contract=expected_contract(protocol,role,provider_options=payload_sent['provider'],**kwargs)
        execution=report['target_call_receipts'][0]['response']['execution_metadata'] if role=='target_answer' else next(item['execution'] for item in extra if item['agent_role']==role)
        assert validate_events(protocol,events,role,contract,execution)==1


def test_export_actual_two_cohort_grid_keeps_all30_missing_cells(tmp_path):
    import subprocess
    root=tmp_path/'synthetic-study';root.mkdir()
    protocol=study();(root/'study-protocol.json').write_text(json.dumps(protocol))
    selected={'version':'catalog09b-evidence-disjoint-metadata-v1','dataset_sha256':'synthetic-only',
      'selected_metadata':[],'scope_disclosure':'Synthetic metadata rule: mutual fillers may repeat.'}
    (root/'selected-metadata.json').write_text(json.dumps(selected));(root/'selection-commitment.json').write_text('{}')
    suite=tmp_path/'longmemeval-identity-conservative-final-20261021/regression-4096/run-01'
    suite.mkdir(parents=True);(suite/'suite-manifest.json').write_text('{"cases":[]}')
    for cell in pilot_cells(protocol):
        path=root/'development-pilot/inputs'/cell['split']/(cell['case_id']+'.json')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps([{'question':'Synthetic question','question_type':'multi-session','answer':0}]))
    out=root/'package.json'
    scripts=Path('/scripts') if Path('/scripts').exists() else Path(__file__).resolve().parents[2]/'scripts'
    result=subprocess.run([sys.executable,str(scripts/'export_stability_package.py'),'--root',str(root),
       '--stage','development-pilot','--output',str(out)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    package=json.loads(json.loads(out.read_text())['payload_json'])
    assert [(split['name'],split['rounds'],split['arms'],len(split['cases'])) for split in package['splits']]==[
      ('development',[1,2,3],['weak_first_hit','strong_rule_based'],4),
      ('development_regression',[1],['strong_rule_based'],6)]
    assert package['acceptance_results']['planned_denominator']==30
    assert sum(len(case['runs']) for split in package['splits'] for case in split['cases'])==30
    assert package['provenance']['source_disjoint_metadata_only_selection'] is False
    assert package['provenance']['source_reuse_scope']['public_distractor_conversations_may_repeat'] is True


def test_required_roles_follow_same_applicability_and_missing_aux_stops_final(tmp_path):
    from stability_request_contracts import expected_roles
    p={**trial(),'strategies':['strong_rule_based']}
    assert expected_roles(p,question='How many events did I attend?',selected_record_count=2)=={
      'target_answer','benchmark_pilot_assessment','target_identity_evidence'}
    assert expected_roles(p,question='Which database do I use?',selected_record_count=2)=={
      'target_answer','benchmark_pilot_assessment'}
    p['strategies']=['weak_first_hit']
    assert expected_roles(p,question='How many events did I attend?',selected_record_count=2)=={
      'target_answer','benchmark_pilot_assessment'}
    p['strategies']=['strong_rule_based'];observer=WireObserver(tmp_path,p)
    with pytest.raises(ValueError,match='Applicable auxiliary'):
        observer.set_target_plan(question='How many events did I attend?',selected_record_count=2)
    assert {'target_answer','benchmark_pilot_assessment'}<=observer.required_roles


@pytest.mark.parametrize('mutation',['required','targetcap','auxcap','targeteffort','auxeffort','grader'])
def test_required_study_cannot_downgrade_trial_controls(mutation):
    from stability_configuration import study_trial_controls_match
    s=study();p=trial();assert study_trial_controls_match(s,p)
    if mutation=='required':p['request_contract_required']=False
    elif mutation=='targetcap':p['output_token_limit']=4096
    elif mutation=='auxcap':p['target_memory_profile']['identity_analysis_output_token_limit']=4096
    elif mutation=='targeteffort':p['target_memory_profile'].pop('reasoning_effort')
    elif mutation=='auxeffort':p['target_memory_profile'].pop('identity_analysis_reasoning_effort')
    else:p['grading_output_token_limit']=1024
    assert not study_trial_controls_match(s,p)


def test_selection_helper_fixture_binding_and_tamper(tmp_path):
    import hashlib
    from stability_configuration import selection_binding
    root=tmp_path/'study';folder=root/'selection-evidence';folder.mkdir(parents=True)
    names=['select_metadata09b.py','prospective-rule-authorization.json','selected-metadata.json',
       'provenance-proof.json','postselection-invariants.json','exclusion-audit.json','shared-filler-ledger.json']
    selected={'version':'catalog09b-evidence-disjoint-metadata-v1'}
    for name in names:(folder/name).write_text(json.dumps(selected) if name=='selected-metadata.json' else 'Synthetic metadata fixture')
    (root/'selected-metadata.json').write_bytes((folder/'selected-metadata.json').read_bytes())
    h=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    config={'helper_path':'selection-evidence/select_metadata09b.py','helper_sha256':h(folder/'select_metadata09b.py'),
       'fixture_manifest':{str(file.relative_to(root)):h(file) for file in folder.iterdir()}}
    p={'selection':config}
    assert selection_binding(p,selected,root,tmp_path)['helper_sha256']==config['helper_sha256']
    (folder/'shared-filler-ledger.json').write_text('changed')
    with pytest.raises(ValueError):selection_binding(p,selected,root,tmp_path)
    with pytest.raises(ValueError):selection_binding({},selected,root,tmp_path)


def test_legacy_selection_description_keeps_old_selector(tmp_path):
    from stability_configuration import selection_binding
    scripts=tmp_path/'scripts';scripts.mkdir();helper=scripts/'prepare_stability_study.py';helper.write_text('# synthetic old selector')
    bound=selection_binding({'selection':{'new_unique_questions':12,'metadata_only':True}},{},tmp_path/'old-study',tmp_path)
    assert bound['helper_path']=='scripts/prepare_stability_study.py' and bound['fixture_manifest']=={}
