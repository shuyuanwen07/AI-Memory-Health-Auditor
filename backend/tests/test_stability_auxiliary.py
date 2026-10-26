"""Synthetic offline tests for refused-advisory bindings, replay and acceptance."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from stability_auxiliary import (canonical_sha256, agent_identity_matches, validate_final_identity_binding,
    describe_auxiliary, summarize_auxiliary, auxiliary_acceptance_gate)
from test_target_identity_failure_policy import install_failed_analysis, enable
from test_target_identity_integration import setup_target

MODEL = 'openai/gpt-6-luna'
REQUIREMENTS = {'additional_acceptance_requirements': {'auxiliary_validation_coverage_minimum': .9,
    'auxiliary_minimum_attempted_calls': 1, 'applies_to_stages': ['safety-guards', 'final'],
    'degraded_final_source_review_required':True, 'degraded_final_source_critical_errors_max':0}}


def run_counts(validated, degraded=0, blocked=0, skipped=0, unknown=0, split='safety_guards'):
    rows = []
    for status, count in [('validated', validated), ('degraded', degraded), ('blocked', blocked), ('skipped', skipped), ('unknown', unknown)]:
        for _ in range(count):
            rows.append({'split': split, 'arm': 'strong_rule_based', 'round': 1,
                         'auxiliary_analysis': {'planned_eligible': True, 'attempted_calls': int(status not in {'skipped','unknown'}),
                             **{key: key == status for key in ('validated','degraded','blocked','skipped','unknown')}, 'unexpected_calls': False}})
    return summarize_auxiliary(rows)


@pytest.mark.parametrize('kind', ['contract', 'length', 'oversize'])
def test_actual_failed_observation_binds_same_final_and_never_counts_as_auxiliary_success(monkeypatch, kind):
    seen = install_failed_analysis(monkeypatch, kind=kind)
    if kind == 'oversize':
        from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer
        monkeypatch.setattr(TargetIdentityEvidenceAnalyzer, 'MAX_ADVISORY_CHARACTERS', 1)
    db, audit, case, adapter = setup_target(); enable(audit)
    try:
        response = adapter.answer(case, audit)
        private = seen['answer'][0][0]
        observation = seen['observations'][0]
        metadata = response.execution_metadata.model_dump(mode='json')
        protocol = {'provider': 'openrouter', 'model': MODEL,
                    'target_memory_profile': audit.target_memory_profile.model_dump(mode='json')}
        assert validate_final_identity_binding(test=private, audit=audit, memory_input=metadata['memory_input'],
            protocol=protocol, evidence_calls=1, observation=observation) is None
        events = [{'agent_role': 'target_identity_evidence', 'execution': observation['execution']}]
        observations = [{'last_observation': observation, 'analyzer_call_status': 'failed'}]
        summary = describe_auxiliary(metadata=metadata, observations=observations, events=events,
            trial_protocol=protocol, arm='strong_rule_based', target_status='completed')
        assert summary['degraded'] and not summary['validated']
        assert summary['analyzer_status'] == 'failed'
        assert summary['http_execution_status'] == ('failed' if kind == 'length' else 'parsed')
        counts = summarize_auxiliary([{'split': 'safety_guards', 'round': 1, 'arm': 'strong_rule_based', 'auxiliary_analysis': summary}])
        assert counts['total']['attempted'] == 1 and counts['total']['validated'] == 0
        assert counts['total']['degraded'] == 1 and counts['total']['degraded_rate'] == 1
        assert counts['total']['eligible_accounting_complete']
        gate = auxiliary_acceptance_gate(REQUIREMENTS, 'safety-guards', {'safety-guards': counts}, True)
        assert gate['status'] == 'fail'
        for mutated in [dict(metadata['memory_input'], identity_advisory_sha256='a'*64),
                        dict(metadata['memory_input'], identity_failure_receipt_sha256=None),
                        dict(metadata['memory_input'], identity_failure_receipt_sha256='b'*64)]:
            assert validate_final_identity_binding(test=private,audit=audit,memory_input=mutated,
                protocol=protocol,evidence_calls=1,observation=observation) is not None
        closed = copy.deepcopy(protocol); closed['target_memory_profile']['identity_analysis_failure_policy']='fail_closed'
        assert validate_final_identity_binding(test=private,audit=audit,memory_input=metadata['memory_input'],
            protocol=closed,evidence_calls=1,observation=observation) == 'unregistered_identity_degradation'
        unknown = describe_auxiliary(metadata=metadata, observations=[], events=events,
            trial_protocol=protocol, arm='strong_rule_based', target_status='completed')
        assert unknown['unknown'] and not unknown['validated'] and not unknown['degraded']
        # A forged receipt cannot qualify merely because its hash is self-consistent.
        forged = copy.deepcopy(metadata)
        forged['identity_analysis']['failure_receipt']['input_fingerprint']='f'*64
        fakehash = canonical_sha256(forged['identity_analysis']['failure_receipt'])
        forged['identity_analysis']['failure_receipt_sha256']=fakehash
        forged['memory_input']['identity_failure_receipt_sha256']=fakehash
        invalid = describe_auxiliary(metadata=forged, observations=observations, events=events,
            trial_protocol=protocol, arm='strong_rule_based', target_status='completed')
        assert invalid['unknown'] and not invalid['degraded']
    finally:
        db.close()


def test_valid_advisory_or_failure_hash_xor_and_no_unobserved_binding():
    advisory={'version':'synthetic-advisory','quotes':[]}
    test=SimpleNamespace(target_identity_evidence=advisory,target_identity_failure_receipt=None)
    audit=SimpleNamespace(target_configuration='strong')
    protocol={'provider':'openrouter','model':MODEL,'target_memory_profile':{}}
    memory={'identity_advisory_sha256':canonical_sha256(advisory),'identity_failure_receipt_sha256':None}
    observation={'status':'completed','output_data':advisory}
    assert validate_final_identity_binding(test=test,audit=audit,memory_input=memory,protocol=protocol,evidence_calls=1,observation=observation) is None
    assert validate_final_identity_binding(test=test,audit=audit,memory_input={},protocol=protocol,evidence_calls=1,observation=observation)
    assert validate_final_identity_binding(test=test,audit=audit,memory_input=memory,protocol=protocol,evidence_calls=0,observation=observation)
    assert validate_final_identity_binding(test=SimpleNamespace(target_identity_evidence=None,target_identity_failure_receipt=None),audit=audit,memory_input={},protocol=protocol,evidence_calls=0,observation=None) is None


def test_failed_http_meter_still_requires_actual_identity_role_and_declared_effective_cap():
    meter={'status':'failed','provider':'openrouter','model':MODEL,'reported_model':MODEL,
           'agent_role':'target_identity_evidence','requested_output_token_limit':4096,'declared_output_token_limit':4096}
    assert agent_identity_matches(meter, MODEL, 'target_identity_evidence', 4096)
    for patch in [{'reported_model':None},{'reported_model':'another-model'},{'provider':'openai'},
                  {'agent_role':'other-role'},{'requested_output_token_limit':1024},{'declared_output_token_limit':1024}]:
        assert not agent_identity_matches({**meter,**patch},MODEL,'target_identity_evidence',4096)


def test_skipping_requires_actual_skip_metadata_and_zero_receipts():
    protocol={'model':MODEL,'target_memory_profile':{'identity_analysis':'evidence_links'}}
    args=dict(observations=[],events=[],trial_protocol=protocol,arm='strong_rule_based',target_status='completed')
    assert describe_auxiliary(metadata={'identity_analysis':{'status':'skipped_not_applicable'}},**args)['skipped']
    assert describe_auxiliary(metadata={},**args)['unknown']
    args['events']=[{'agent_role':'target_identity_evidence','execution':{}}]
    assert not describe_auxiliary(metadata={'identity_analysis':{'status':'skipped_not_applicable'}},**args)['skipped']


def test_unknown_and_unexpected_weak_calls_cannot_be_hidden_by_successful_attempts():
    summary=run_counts(95,unknown=5)
    assert summary['total']['validation_coverage']==1
    assert auxiliary_acceptance_gate(REQUIREMENTS,'safety-guards',{'safety-guards':summary},True)['status']=='fail'
    protocol={'model':MODEL,'target_memory_profile':{'identity_analysis':'evidence_links'}}
    weak=describe_auxiliary(metadata={},observations=[],events=[{'agent_role':'target_identity_evidence','execution':{}}],
        trial_protocol=protocol,arm='weak_first_hit',target_status='completed')
    assert weak['unexpected_calls'] and not weak['validated']


def test_point9_integer_boundary_and_each_stage_no_pooling():
    passing=run_counts(9,1)
    assert auxiliary_acceptance_gate(REQUIREMENTS,'safety-guards',{'safety-guards':passing},True)['status']=='pass'
    failing=run_counts(8,1)
    assert auxiliary_acceptance_gate(REQUIREMENTS,'safety-guards',{'safety-guards':failing},True)['status']=='fail'
    final=run_counts(100,split='evaluation')
    assert auxiliary_acceptance_gate(REQUIREMENTS,'final',{'final':final,'safety-guards':failing},True)['status']=='fail'
    assert auxiliary_acceptance_gate(REQUIREMENTS,'final',{'final':final,'safety-guards':passing},True)['status']=='pass'


def test_empty_attempted_denominator_fails_pilot_only_displays_and_running_stays_pending():
    skipped=run_counts(0,skipped=36)
    assert skipped['total']['validation_coverage'] is None
    assert auxiliary_acceptance_gate(REQUIREMENTS,'safety-guards',{'safety-guards':skipped},True)['status']=='fail'
    assert auxiliary_acceptance_gate(REQUIREMENTS,'development-pilot',{'development-pilot':skipped},True) is None
    assert auxiliary_acceptance_gate(REQUIREMENTS,'safety-guards',{'safety-guards':run_counts(9,1)},False)['status']=='pending'


def test_trial_profile_cannot_turn_predeclared_eligible_cells_off():
    row=describe_auxiliary(metadata={},observations=[],events=[],trial_protocol={'model':MODEL,'target_memory_profile':{'identity_analysis':'off'}},
        arm='strong_rule_based',target_status='completed',expected_profile={'identity_analysis':'evidence_links'})
    assert row['planned_eligible'] and row['unknown'] and not row['profile_matches_study']


@pytest.mark.parametrize('kind', ['contract', 'length'])
def test_actual_replay_function_reconstructs_original_refusal_and_same_final_instructions(monkeypatch, kind):
    """Execute the production replay callback, never the provider transport."""
    import ast
    import hashlib
    from app.extraction.llm import PipelineLLMClient, PipelineRequestError
    seen = install_failed_analysis(monkeypatch, kind=kind)
    db, audit, case, adapter = setup_target(); enable(audit)
    try:
        original = adapter.answer(case, audit)
        observation = copy.deepcopy(seen['observations'][0])
        request = seen['analysis'][0]
        # The outer complete_json API receives instructions/prompt hashed in the
        # real meter, while the inner fake transport receives its prepared data.
        saved = {'agent_role':'target_identity_evidence', 'execution':observation['execution'],
            'evidence_payload':observation.get('raw_model_draft'),
            'actual_instruction_sha256':hashlib.sha256(request['instructions'].encode()).hexdigest(),
            'actual_prompt_sha256':observation['execution']['input_fingerprint'],
            'requested_max_output_tokens':4096}
        if kind == 'length':saved.update(status='failed', exception_type='PipelineRequestError')
        tree = ast.parse((SCRIPTS/'replay_stability_study.py').read_text())
        node = next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='replay_agent')
        used=[]
        namespace={'evidence':[saved], 'used':used, 'protocol':{'model':MODEL}, 'copy':copy, 'VALIDATION_ROLE':'target_answer_validation',
            'PipelineRequestError':PipelineRequestError, 'agent_identity_matches':agent_identity_matches,
            'sha_text':lambda value:hashlib.sha256(value.encode()).hexdigest()}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])), '<actual-replay-agent>', 'exec'),namespace)
        monkeypatch.setattr(PipelineLLMClient,'complete_json',namespace['replay_agent'])
        replayed=adapter.answer(case,audit)
        assert len(used)==1 and len(seen['analysis'])==1 # no second transport/model call
        assert len(seen['answer'])==2
        assert seen['answer'][1][1]==seen['answer'][0][1]
        assert replayed.execution_metadata.memory_input.identity_failure_receipt_sha256 == original.execution_metadata.memory_input.identity_failure_receipt_sha256
        assert replayed.execution_metadata.identity_analysis['status']=='degraded_without_advisory'
        assert seen['observations'][1]['status']=='failed'
        assert seen['observations'][1]['execution']==observation['execution']
        assert seen['observations'][1].get('raw_model_draft')==observation.get('raw_model_draft')
    finally:db.close()


def test_frozen_protocol_binding_rejects_threshold_edit_missing_stage_and_independent_safety(tmp_path):
    import hashlib
    from stability_auxiliary import frozen_protocol_binding
    path=tmp_path/'study-protocol.json'
    path.write_text(json.dumps(REQUIREMENTS))
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    for stage in ['final','safety-guards']:
        (tmp_path/stage).mkdir();(tmp_path/stage/'FROZEN.json').write_text(json.dumps({'protocol_sha256':digest}))
    assert frozen_protocol_binding(tmp_path,['final','safety-guards'])['status']=='pass'
    changed=copy.deepcopy(REQUIREMENTS);changed['additional_acceptance_requirements']['auxiliary_validation_coverage_minimum']=.1
    path.write_text(json.dumps(changed))
    assert frozen_protocol_binding(tmp_path,['final','safety-guards'])['status']=='fail'
    (tmp_path/'final/FROZEN.json').write_text(json.dumps({'protocol_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
    assert frozen_protocol_binding(tmp_path,['final','safety-guards'])['status']=='fail'
    (tmp_path/'safety-guards/FROZEN.json').unlink()
    assert frozen_protocol_binding(tmp_path,['final','safety-guards'])['status']=='fail'


def test_export_controlled_identity_join_preserves_actual_input_and_rejects_mismatch():
    spec=importlib.util.spec_from_file_location('aux_export',SCRIPTS/'export_stability_package.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    actual={'memory_input':{'instruction_sha256':'a'*64,'identity_failure_receipt_sha256':'b'*64,'sent_memory_ids':[]},
        'reported_model':MODEL,'response_source':'openrouter','requested_output_token_limit':4096,
        'completion_status':'complete','finish_reason':'stop'}
    controlled=copy.deepcopy(actual)
    controlled['memory_input']['sent_memory_ids']=['synthetic-persisted-memory-id']
    controlled['identity_analysis']={'status':'degraded_without_advisory','advisory_applied':False}
    joined,matched=module.enrich_controlled_identity(actual,controlled)
    assert matched and joined['identity_analysis']==controlled['identity_analysis']
    assert joined['memory_input']==actual['memory_input'] # actual receipt never rewritten
    controlled['memory_input']['identity_failure_receipt_sha256']='c'*64
    assert module.enrich_controlled_identity(actual,controlled)==(actual,False)


def test_degraded_final_requires_its_own_completed_source_review_not_just_safety_pass():
    rows=[]
    for index in range(10):
        rows.append({'split':'evaluation','arm':'strong_rule_based','round':1,
            'auxiliary_analysis':{'planned_eligible':True,'attempted_calls':1,
                'validated':index<9,'degraded':index==9}})
    summary=summarize_auxiliary(rows)
    assert summary['total']['degraded_unreviewed']==1
    stages={'final':summary,'safety-guards':run_counts(9,1)}
    assert auxiliary_acceptance_gate(REQUIREMENTS,'final',stages,True)['status']=='fail'
    rows[-1].update(source_review={'critical_errors':[]},source_review_status='pending')
    assert summarize_auxiliary(rows)['total']['degraded_unreviewed']==1
    rows[-1]['source_review_status']='pass'
    stages['final']=summarize_auxiliary(rows)
    assert auxiliary_acceptance_gate(REQUIREMENTS,'final',stages,True)['status']=='pass'
    rows[-1]['source_review']['critical_errors']=['synthetic unsupported identity merge']
    assert summarize_auxiliary(rows)['total']['degraded_unreviewed']==1


def test_non_guard_review_quote_binds_to_own_original_message_not_other_question(tmp_path):
    spec=importlib.util.spec_from_file_location('source_export',SCRIPTS/'export_stability_package.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    trial={'case_id':'DEV-SYNTHETIC','round':1,'arm':'strong_rule_based','directory':'trials/one'}
    directory=tmp_path/trial['directory'];directory.mkdir(parents=True)
    def write(path,value):path.write_text(json.dumps(value))
    write(directory/'pilot-subset.json',[{'question_id':trial['case_id'], 'haystack_sessions':[[{'role':'user','content':'My friend attended a synthetic recital.'}]]}])
    text='The synthetic recital remains uncertain.'
    write(directory/'pilot-report.json',{'status':'completed','target_call_receipts':[{'status':'completed','response':{'response_text':text,'execution_metadata':{'completion_status':'complete','finish_reason':'stop'}}}], 'semantic_assessments':[{'status':'completed'}]})
    write(tmp_path/'trial-matrix.json',{'trials':[trial]})
    write(tmp_path/'study-execution.json',{'status':'completed','trials':[{**trial,'status':'completed'}]})
    import hashlib
    review={'status':'completed','trials':[{**trial,'target_response_sha256':hashlib.sha256(text.encode()).hexdigest(),'target_status':'completed','critical_errors':[],
        'claims':[{'claim':'synthetic recital','source_support':'supported','source_quote':'synthetic recital','source_message_id':'MSG-001','supplied_quote_verified':True,'explanation':'Exact original source quotation.'}]}]}
    assert module.validate_source_reviews(review,tmp_path,[],None)[0]['status']=='pass'
    review['trials'][0]['claims'][0]['source_quote']='A different question mentions a synthetic lecture.'
    assert module.validate_source_reviews(review,tmp_path,[],None)[0]['status']=='fail'
    assert module.validate_source_reviews(review,tmp_path,[],None)[1]=={}
    review['trials'][0]['claims'][0].update(source_quote='synthetic recital',source_message_id='MSG-002')
    assert module.validate_source_reviews(review,tmp_path,[],None)[0]['status']=='fail'


def test_validated_auxiliary_requires_actual_matching_observation_and_http_event(monkeypatch):
    from app.extraction.llm import PipelineLLMClient,_PIPELINE_METER
    seen=install_failed_analysis(monkeypatch)
    def complete(self,**request):
        _PIPELINE_METER.get().update(last_http_status=200,reported_model=self.model,request_attempts=1,
            failed_http_attempts=0,reported_finish_reason='stop',response_choice_count=1)
        return {'quotes':[],'mentions':[],'relations':[],'limitations':'No supported relation in this synthetic example.'}
    monkeypatch.setattr(PipelineLLMClient,'_complete_json',complete)
    db,audit,case,adapter=setup_target();enable(audit)
    try:
        response=adapter.answer(case,audit)
        metadata=response.execution_metadata.model_dump(mode='json')
        observation=seen['observations'][0]
        args={'metadata':metadata,'observations':[{'last_observation':observation,'analyzer_call_status':'completed'}],
            'events':[{'agent_role':'target_identity_evidence','execution':observation['execution']}],
            'trial_protocol':{'provider':'openrouter','model':MODEL,'target_memory_profile':audit.target_memory_profile.model_dump(mode='json')},
            'arm':'strong_rule_based','target_status':'completed'}
        summary=describe_auxiliary(**args)
        assert summary['validated'] and not summary['degraded']
        args['events']=copy.deepcopy(args['events'])
        args['events'][0]['execution']['output_fingerprint']='f'*64
        assert describe_auxiliary(**args)['unknown']
    finally:db.close()
