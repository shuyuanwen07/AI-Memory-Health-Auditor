"""Rebuild every planned input offline, replaying saved target-only evidence JSON.

Sockets are blocked; no target or grader is called. Both advisory-stage input and
final instructions/advisory hash are compared. Missing/failure cells stay explicit.
"""
from stability_grading_budget import trial_grader_cap, grader_budget_matches, budget_source, study_trial_grader_budget_matches, study_grader_cap

import copy
from stability_configuration import selection_binding, study_trial_controls_match, answer_validation_enabled
from stability_answer_validation import ROLE as VALIDATION_ROLE, DRAFT as PRIMARY_DRAFT, read_observation as read_validation_observation, validate_binding as validate_answer_binding, compare_observation as compare_answer_observation
from stability_auxiliary import agent_identity_matches
from stability_request_contracts import required as wire_required, read_wire_events, expected_contract, validate_events, expected_roles

import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys


def read(p):return json.loads(p.read_text())
def sha_text(s):return hashlib.sha256(s.encode()).hexdigest()
def sha_file(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def compare_identity_observation(original, reconstructed):
    """Compare stored validation evidence, requiring every candidate-selection binding.

    Inspect both versions and both evidence objects: downgrading either version
    must not bypass the candidate protocol. Unknown candidate versions fail
    closed until their replay contract has been reviewed.
    """
    for key in ('status','error_code','error_diagnostics','raw_model_draft',
                'quote_binding_adjustments','relation_cue_adjustments'):
        if key in original:
            assert reconstructed.get(key)==original[key], 'Auxiliary validation outcome differs from the saved actual observation.'
    candidate_keys=('candidate_catalog','raw_model_selection','hydrated_quote_draft','candidate_selection_receipt')
    supported=('target-identity-evidence-v8-','target-identity-evidence-v9-',
               'target-identity-evidence-v10-')
    original_version=original.get('prompt_template_version')
    replay_version=reconstructed.get('prompt_template_version')
    def candidate_protocol(version):
        return isinstance(version,str) and version.startswith(supported)
    def candidate_family(version):
        match=re.match(r'^target-identity-evidence-v(\d+)(?:-|$)',version) if isinstance(version,str) else None
        return bool(match and int(match[1])>=8)
    candidate_version=(candidate_family(original_version) or candidate_family(replay_version)
                       or any(key in observation for observation in (original,reconstructed) for key in candidate_keys))
    if candidate_version:
        assert original_version==replay_version, 'Identity observation version differs.'
        assert candidate_protocol(original_version), 'Unsupported candidate observation version.'
        for key in candidate_keys:
            assert key in original and key in reconstructed, 'Missing candidate selection evidence.'
            assert original[key]==reconstructed[key], 'Candidate selection evidence differs from offline reconstruction.'
    return candidate_version

def compare_identity_observations(saved, reconstructed):
    assert isinstance(saved,list) and isinstance(reconstructed,list) and len(saved)==len(reconstructed), 'Missing or extra auxiliary observation sidecar entries.'
    for original,replayed in zip(saved,reconstructed):
        compare_identity_observation(original.get('last_observation') or {},replayed)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--stage',choices=['development-pilot','final','safety-guards'],required=True);ap.add_argument('--frozen-source-root',type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args();root=a.root.resolve();stage=root/a.stage;matrix=read(stage/'trial-matrix.json');frozen=read(stage/'FROZEN.json');manifest=read(stage/'tested-source-manifest.json');workspace=Path(__file__).resolve().parents[1]
    runtime_root=a.frozen_source_root.resolve() if a.frozen_source_root else workspace
    diagnostic=bool(a.frozen_source_root)
    proof_path=a.output.resolve() if a.output else stage/('replay-proof-frozen-diagnostic.json' if diagnostic else 'replay-proof.json')
    if diagnostic:assert sha_file(stage/'tested-source-manifest.json')==frozen['source_manifest_sha256'],'Frozen manifest binding changed.'
    harness_sha256=sha_file(Path(__file__))
    harness_matches=harness_sha256==manifest.get('scripts/replay_stability_study.py')
    assert sha_file(root/'study-protocol.json')==frozen['protocol_sha256']
    study_protocol=read(root/'study-protocol.json')
    def check():
        if not diagnostic and Path('/app/app').exists():
            current={str(Path('backend/app')/p.relative_to('/app/app')) for p in Path('/app/app').rglob('*.py')}|{str(Path('scripts')/p.name) for p in Path('/scripts').glob('*.py')}
        else:current={str(p.relative_to(runtime_root)) for p in list((runtime_root/'backend/app').rglob('*.py'))+list((runtime_root/'scripts').glob('*.py'))}
        assert current==set(manifest),'Frozen app/scripts membership changed.'
        if 'selection_fixture_manifest' in frozen:
            selection=selection_binding(study_protocol,read(root/'selected-metadata.json'),root,runtime_root)
            assert selection=={'helper_path':frozen['selection_helper_path'],'helper_sha256':frozen['selection_script_sha256'],'fixture_manifest':frozen['selection_fixture_manifest']},'Frozen selector evidence changed.'
        elif study_protocol.get('request_contract_required') is True:raise ValueError('Required study has no frozen selection provenance.')
        for name,expected in frozen.get('fixture_manifest',{}).items():assert sha_file(root/name)==expected
        for name,expected in manifest.items():
            p=(Path('/scripts')/Path(name).name if name.startswith('scripts/') else Path('/app')/Path(name).relative_to('backend')) if not diagnostic and Path('/app/app').exists() else runtime_root/name
            assert sha_file(p)==expected,'Frozen code changed:'+name
    check();os.environ['DATABASE_URL']='sqlite://'
    if diagnostic:sys.path.insert(0,str(runtime_root/'scripts'))
    sys.path.insert(0,str(Path('/app') if not diagnostic and Path('/app/app').exists() else runtime_root/'backend'))
    from app.benchmarks.live import LiveBenchmarkRunner
    from app.schemas.benchmark import LiveBenchmarkRequest
    from app.target_ai.providers import HttpTargetAIConnector
    from app.target_ai.rule_based import memory_input_evidence,target_question_input
    from app.extraction.llm import PipelineLLMClient, PipelineRequestError
    from run_longmemeval_pilot import protocol_memory_profile
    from longmemeval_grading import load_upstream_prompt
    original_connect=socket.socket.connect;original_provider=HttpTargetAIConnector._execute_provider;original_credential=HttpTargetAIConnector._credential_for;original_agent=PipelineLLMClient.complete_json;original_target_execute=HttpTargetAIConnector.execute;network_attempts=0;rows=[]
    def blocked(*args,**kwargs):
        nonlocal network_attempts
        network_attempts+=1;raise RuntimeError('Network forbidden during replay.')
    socket.socket.connect=blocked;HttpTargetAIConnector._credential_for=staticmethod(lambda provider:'offline-no-credential')
    try:
        for trial in matrix['trials']:
            directory=stage/trial['directory'];file=directory/'pilot-report.json';row={k:trial[k] for k in ['split','case_id','round','arm']};rows.append(row)
            if not file.exists():row.update(status='missing',inputs_equal=False);continue
            report=read(file);protocol=read(directory/'pilot-protocol.json');payload=read(directory/'pilot-subset.json')
            assert sha_file(directory/'pilot-protocol.json')==trial['protocol_sha256'];assert sha_file(directory/'pilot-subset.json')==trial['source_sha256']
            if not study_trial_grader_budget_matches(study_protocol,protocol):
                row.update(status='error',inputs_equal=False,error_type='StudyTrialGraderBudgetMismatch',grade_budget_compared=False,study_grader_cap=study_grader_cap(study_protocol),trial_grader_cap=trial_grader_cap(protocol))
                print(json.dumps({'event':'offline_trial_replayed','count':len(rows),'planned':len(matrix['trials']),'status':row['status']}),flush=True)
                continue
            if not study_trial_controls_match(study_protocol,protocol):
                row.update(status='error',inputs_equal=False,error_type='StudyTrialRequestControlsMismatch')
                print(json.dumps({'event':'offline_trial_replayed','count':len(rows),'planned':len(matrix['trials']),'status':row['status']}),flush=True)
                continue
            receipts=report.get('target_call_receipts',[])
            if len(receipts)!=1:
                row.update(status='error',inputs_equal=False,error_type='MissingTargetReceipt' if not receipts else 'MultipleTargetReceipts',target_status='not_attempted' if not receipts else 'invalid_receipt_count',grade_input_present=bool(report.get('semantic_assessments')),grade_input_compared=False)
                print(json.dumps({'event':'offline_trial_replayed','count':len(rows),'planned':len(matrix['trials']),'status':row['status']}),flush=True)
                continue
            wire_events=read_wire_events(directory,protocol)
            wire_comparisons=[];wire_required_roles=set()
            def compare_wire(role,execution,**kwargs):
                if not wire_required(protocol):return
                matching=[event for event in wire_events if event.get('role')==role]
                if not matching:raise ValueError('Missing actual wire attempts.')
                routing=matching[0]['request_contract']['provider']['value']
                contract=expected_contract(protocol,role,provider_options=routing,**kwargs)
                validate_events(protocol,wire_events,role,contract,execution)
                wire_comparisons.extend(matching)
            target=receipts[0];actual=read(directory/'actual-input-receipt.json') if (directory/'actual-input-receipt.json').exists() else None;events=read(directory/'agent-execution-receipts.json') if (directory/'agent-execution-receipts.json').exists() else [];evidence=[x for x in events if x.get('agent_role')=='target_identity_evidence'];used=[];captured=[]
            validation_enabled=answer_validation_enabled(protocol.get('target_memory_profile',{}))
            validation_events=[x for x in events if x.get('agent_role')==VALIDATION_ROLE]
            validation_used=[];validation_reconstructed=[]
            saved_validation=read_validation_observation(directory)
            draft=read(directory/PRIMARY_DRAFT) if (directory/PRIMARY_DRAFT).exists() else None
            if not validation_enabled and (validation_events or saved_validation is not None or draft is not None):raise ValueError('Unexpected disabled validation evidence.')
            def replay_agent(self,**kwargs):
                role=kwargs.get('agent_role')
                if role==VALIDATION_ROLE:
                    assert validation_enabled and not validation_used and len(validation_events)==1,'Missing/extra answer validation attempt.'
                    saved=validation_events[0]
                    compare_wire(role,saved['execution'],instructions=kwargs['instructions'],prompt=kwargs['prompt'],schema_name=kwargs['schema_name'],schema=kwargs['schema'])
                    assert sha_text(kwargs['instructions'])==saved['actual_instruction_sha256'] and sha_text(kwargs['prompt'])==saved['actual_prompt_sha256']
                    assert kwargs.get('max_output_tokens')==saved['requested_max_output_tokens']
                    assert saved_validation is not None and saved_validation.get('raw_model_review')==saved.get('result')
                    self.last_execution=copy.deepcopy(saved['execution']);validation_used.append(saved)
                    return copy.deepcopy(saved['result'])
                assert role=='target_identity_evidence','Unexpected model stage during offline replay.'
                assert len(used)<len(evidence),'An unsaved extra evidence request was reconstructed.'
                saved=evidence[len(used)]
                if protocol.get('request_contract_required') is True:compare_wire('target_identity_evidence',saved['execution'],instructions=kwargs['instructions'],prompt=kwargs['prompt'],schema_name=kwargs['schema_name'],schema=kwargs['schema'])
                assert sha_text(kwargs['instructions'])==saved['actual_instruction_sha256'];assert sha_text(kwargs['prompt'])==saved['actual_prompt_sha256'];assert kwargs.get('max_output_tokens')==saved['requested_max_output_tokens']
                self.last_execution=dict(saved['execution']);used.append(saved)
                if saved.get('evidence_payload') is None:
                    execution=saved['execution']
                    assert (saved.get('status')=='failed' and saved.get('exception_type')=='PipelineRequestError'
                            and execution.get('status')=='failed' and execution.get('reported_finish_reason')=='length'
                            and execution.get('last_http_status')==200
                            and agent_identity_matches(execution,protocol['model'],'target_identity_evidence',kwargs.get('max_output_tokens'))),'Unsaved/unknown failure cannot be reconstructed as a refused advisory.'
                    raise PipelineRequestError('The configured pipeline model reached its output limit before completing the required result.')
                return copy.deepcopy(saved['evidence_payload'])
            def capture_provider(self,audit,test,instructions,credential):
                assert not test.expected_behavior and not test.supporting_memory_ids,'Evaluator gold entered private target input.'
                ev=memory_input_evidence(test,audit.target_configuration,instructions).model_dump(mode='json');prompt=target_question_input(test.prompt)
                observed={'memory_input':ev,'instruction_sha256':sha_text(instructions),'question_sha256':sha_text(prompt),'combined_input_sha256':sha_text(json.dumps({'instructions':instructions,'question':prompt},sort_keys=True)),'requested_output_token_limit':audit.target_memory_profile.output_token_limit,'identity_advisory_sha256':ev.get('identity_advisory_sha256')}
                if 'identity_failure_receipt_sha256' in ev:observed['identity_failure_receipt_sha256']=ev.get('identity_failure_receipt_sha256')
                assert actual is not None and observed==actual,'Actual final target input differs from offline reconstruction.';captured.append(observed)
                if wire_required(protocol):wire_required_roles.update(expected_roles(protocol,question=test.prompt,selected_record_count=ev['record_count']))
                target_execution=(target.get('response') or {}).get('execution_metadata') or target.get('execution') or {}
                compare_wire('target_answer',target_execution,instructions=instructions,prompt=prompt)
                return draft['response_text'] if validation_enabled and isinstance(draft,dict) else 'Offline replay only; no model call.'
            replay_observations=[];original_analyze=None;analyzer_class=None
            if evidence:
                from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer
                analyzer_class=TargetIdentityEvidenceAnalyzer;original_analyze=analyzer_class.analyze
                def observed_analyze(self,*args,**kwargs):
                    try:return original_analyze(self,*args,**kwargs)
                    finally:replay_observations.append(copy.deepcopy(self.last_observation))
                analyzer_class.analyze=observed_analyze
            validation_class=None;original_validate=None
            if validation_enabled:
                from app.memory_agent.answer_validation import TargetAnswerValidator
                from app.schemas import TargetResponse
                validation_class=TargetAnswerValidator;original_validate=validation_class.validate
                def capture_validate(self,*args,**kwargs):
                    previous=os.environ.get('PIPELINE_MAX_OUTPUT_TOKENS')
                    configured=saved_validation.get('configured_output_token_cap') if isinstance(saved_validation,dict) else None
                    if configured is None:os.environ.pop('PIPELINE_MAX_OUTPUT_TOKENS',None)
                    else:
                        assert type(configured) is int and 256<=configured<=12000
                        os.environ['PIPELINE_MAX_OUTPUT_TOKENS']=str(configured)
                    try:return original_validate(self,*args,**kwargs)
                    finally:
                        validation_reconstructed.append(copy.deepcopy(self.last_observation))
                        if previous is None:os.environ.pop('PIPELINE_MAX_OUTPUT_TOKENS',None)
                        else:os.environ['PIPELINE_MAX_OUTPUT_TOKENS']=previous
                validation_class.validate=capture_validate
                def restore_actual_draft(self,test,audit):
                    original_target_execute(self,test,audit)  # reconstruct primary input without network
                    assert isinstance(draft,dict),'Missing actual original draft.'
                    return TargetResponse.model_validate(copy.deepcopy(draft))
                HttpTargetAIConnector.execute=restore_actual_draft
            else:HttpTargetAIConnector.execute=original_target_execute
            PipelineLLMClient.complete_json=replay_agent;HttpTargetAIConnector._execute_provider=capture_provider
            preparation_store=None;original_ingest=None;preparation_observations=[]
            try:
                if protocol.get('memory_preparation_receipt_required') is True:
                    from app.memory_agent.store import SqlTargetMemoryStore
                    from run_stability_trial import build_memory_preparation_observation
                    from stability_memory_preparation import compare_private_memory_preparation_receipts
                    preparation_store=SqlTargetMemoryStore;original_ingest=preparation_store.ingest
                    observed_runs=set()
                    def capture_ingest(self,run_id,conversation):
                        result=original_ingest(self,run_id,conversation)
                        if run_id not in observed_runs:
                            preparation_observations.append(build_memory_preparation_observation(
                                self,run_id,conversation,status='completed'))
                            observed_runs.add(run_id)
                        return result
                    preparation_store.ingest=capture_ingest
                provenance=protocol['source_provenance'];result=LiveBenchmarkRunner().run(LiveBenchmarkRequest(payload=payload,source_authorised=True,dataset_provenance={'dataset_version':provenance['revision'],'license':provenance['license'],'citation':provenance['citation']},provider=protocol['provider'],model=protocol['model'],strategies=protocol['strategies'],max_cases=1,target_memory_capacity=500,target_memory_profile=protocol_memory_profile(protocol)))
                assert len(captured)==1 and len(used)==len(evidence)
                if validation_enabled:
                    assert len(validation_used)==len(validation_reconstructed)==1
                    compare_answer_observation(saved_validation,validation_reconstructed[0])
                    final=target.get('response') or {}
                    validate_answer_binding(protocol,observation=saved_validation,draft=draft,final=final,events=events)
                    actual_cases=[case for condition in result.conditions for case in condition.cases]
                    assert len(actual_cases)==1 and actual_cases[0].response_text==final['response_text'],'Delivered final answer differs from replay.'
                    reconstructed_meta=actual_cases[0].execution_metadata.answer_validation
                    actual_meta=final['execution_metadata']['answer_validation']
                    # Execution IDs are fresh database row identifiers only; all
                    # decision/hash/execution/budget fields stay exact.
                    excluded={'execution_id','draft_execution_id'}
                    assert {k:v for k,v in reconstructed_meta.items() if k not in excluded}=={k:v for k,v in actual_meta.items() if k not in excluded}
                    row.update(answer_validation_input_compared=True,answer_validation_validated=1)
                if protocol.get('memory_preparation_receipt_required') is True:
                    preparation_path=directory/'private-memory-preparation-receipts.json'
                    comparison=compare_private_memory_preparation_receipts(read(preparation_path),preparation_observations,
                        expected_profile=protocol_memory_profile(protocol),expected_capacity=protocol['target_memory_capacity'],
                        expected_observation_count=1)
                    row.update(memory_preparation_compared=True,memory_preparation_receipt_sha256=sha_file(preparation_path))
                if target.get('status')=='completed':
                    primary_metadata=draft['execution_metadata'] if validation_enabled else target['response']['execution_metadata']
                    assert primary_metadata['memory_input']==captured[0]['memory_input']
                    if validation_enabled:
                        original_final_input=target['response']['execution_metadata']['memory_input']
                        assert {k:v for k,v in original_final_input.items() if k!='sent_memory_ids'}=={k:v for k,v in captured[0]['memory_input'].items() if k!='sent_memory_ids'}
                grades=report.get('semantic_assessments',[]);grade_equal=False
                if grades:
                    assert len(grades)==1,'Expected exactly one original grader attempt.'
                    response=target.get('response',{}).get('response_text','')
                    if protocol.get('assessment_kind')=='synthetic_source_safety':
                        from run_stability_guard_trial import grading_prompt
                        prompt=grading_prompt(read(directory/'guard-case.json'),read(directory/'guard-private-criteria.json'),response)
                        assert grades[0]['execution']['agent_role']=='stability_guard_assessment'
                        if wire_required(protocol):
                            from run_stability_guard_trial import ASSESSMENT_INSTRUCTIONS, SCHEMA
                            grade_role='stability_guard_assessment';grade_instructions=ASSESSMENT_INSTRUCTIONS;grade_schema=SCHEMA;grade_schema_name='synthetic_source_safety_guard'
                    else:
                        upstream,_=load_upstream_prompt((directory/protocol['upstream_evaluator_directory']).resolve());case=payload[0];prompt=upstream(case['question_type'],case['question'],case['answer'],response,abstention='_abs' in case['question_id'])
                    if wire_required(protocol) and protocol.get('assessment_kind')!='synthetic_source_safety':
                        from longmemeval_grading import UPSTREAM_INSTRUCTIONS
                        from run_longmemeval_pilot import ASSESSMENT_SCHEMA
                        grade_role='benchmark_pilot_assessment';grade_instructions=UPSTREAM_INSTRUCTIONS;grade_schema=ASSESSMENT_SCHEMA;grade_schema_name='longmemeval_pilot_assessment'
                    if wire_required(protocol):compare_wire(grade_role,grades[0]['execution'],instructions=grade_instructions,prompt=prompt,schema_name=grade_schema_name,schema=grade_schema)
                    grade_equal=grades[0]['execution']['input_fingerprint']==sha_text(prompt);assert grade_equal
                    grade_budget_equal=grader_budget_matches(protocol,grades[0]['execution'])
                    row['grading_budget']={'study_cap':study_grader_cap(study_protocol),'protocol_cap':trial_grader_cap(protocol),'protocol_source':budget_source(protocol),'execution_declared_cap':grades[0]['execution'].get('declared_output_token_limit'),'execution_effective_cap':grades[0]['execution'].get('requested_output_token_limit')}
                    row['grade_budget_compared']=grade_budget_equal
                    assert grade_budget_equal,'Original grader execution budget differs from its frozen trial protocol.'
                observation_path=directory/'identity-observation-receipts.json'
                saved_observations=read(observation_path).get('observations',[]) if observation_path.exists() else []
                compare_identity_observations(saved_observations,replay_observations)
                if wire_required(protocol):
                    compared_roles={event['role'] for event in wire_comparisons}
                    if len(wire_comparisons)!=len(wire_events) or compared_roles!=wire_required_roles:raise ValueError('Missing required HTTP role or unreplayed extra attempts.')
                    row['wire_required_roles']=sorted(wire_required_roles)
                    row['wire_compared_roles']=sorted(compared_roles)
                row['wire_contract_required']=wire_required(protocol)
                row['wire_http_attempt_comparisons']=len(wire_comparisons)
                row['auxiliary_http_inputs_compared']=len(used)
                row['auxiliary_validation_failed']=sum(item.get('status')=='failed' for item in replay_observations if isinstance(item,dict))
                row['auxiliary_validated']=sum(item.get('status')=='completed' for item in replay_observations if isinstance(item,dict))
                row['identity_failure_receipt_sha256']=captured[0].get('identity_failure_receipt_sha256')
                row.update(status='compared',inputs_equal=True,evidence_stage_inputs_compared=len(used),final_input_compared=True,advisory_sha256=captured[0]['identity_advisory_sha256'],grade_input_compared=grade_equal,grade_input_present=bool(grades))
            except Exception as exc:row.update(status='error',inputs_equal=False,error_type=type(exc).__name__)
            finally:
                if validation_class is not None:validation_class.validate=original_validate
                HttpTargetAIConnector.execute=original_target_execute
                if analyzer_class is not None:analyzer_class.analyze=original_analyze
                if preparation_store is not None:preparation_store.ingest=original_ingest
            print(json.dumps({'event':'offline_trial_replayed','count':len(rows),'planned':len(matrix['trials']),'status':row['status']}),flush=True)
        check();assert network_attempts==0
    finally:
        socket.socket.connect=original_connect;HttpTargetAIConnector._execute_provider=original_provider;HttpTargetAIConnector._credential_for=staticmethod(original_credential);PipelineLLMClient.complete_json=original_agent;HttpTargetAIConnector.execute=original_target_execute
    compared=sum(r.get('inputs_equal') is True for r in rows);grader_compared=sum(r.get('grade_input_compared') is True for r in rows);proof={'scope':'offline_actual_evidence_and_final_target_input_replay','status':'passed' if compared==len(matrix['trials']) and grader_compared==len(matrix['trials']) else 'failed','model_calls':0,'network_attempts':network_attempts,'source_unchanged':harness_matches,'runtime_source_unchanged':True,'replay_harness_sha256':harness_sha256,'replay_harness_support_sha256':{'stability_grading_budget.py':sha_file(Path(sys.modules['stability_grading_budget'].__file__)),'stability_auxiliary.py':sha_file(Path(sys.modules['stability_auxiliary'].__file__)),'stability_answer_validation.py':sha_file(Path(sys.modules['stability_answer_validation'].__file__)),'stability_configuration.py':sha_file(Path(sys.modules['stability_configuration'].__file__)),'stability_request_contracts.py':sha_file(Path(sys.modules['stability_request_contracts'].__file__))},'replay_harness_matches_frozen_source':harness_matches,'frozen_source_root':str(runtime_root) if diagnostic else None,'runtime_source_manifest_sha256':sha_file(stage/'tested-source-manifest.json'),'memory_preparation_receipt_required':study_protocol.get('memory_preparation_receipt_required') is True,'memory_preparation_comparisons':sum(r.get('memory_preparation_compared') is True for r in rows),'planned_trials':len(matrix['trials']),'compared_trials':compared,'grader_input_comparisons':grader_compared,'planned_grader_input_comparisons':len(matrix['trials']),'auxiliary_http_input_comparisons':sum(r.get('auxiliary_http_inputs_compared',0) for r in rows),'auxiliary_validation_failed':sum(r.get('auxiliary_validation_failed',0) for r in rows),'auxiliary_validated':sum(r.get('auxiliary_validated',0) for r in rows),'answer_validation_input_comparisons':sum(r.get('answer_validation_input_compared') is True for r in rows),'answer_validation_validated':sum(r.get('answer_validation_validated',0) for r in rows),'wire_http_attempt_comparisons':sum(r.get('wire_http_attempt_comparisons',0) for r in rows),'wire_contract_required':study_protocol.get('request_contract_required') is True,'target_input_comparisons':compared,'evidence_stage_input_comparisons':sum(r.get('evidence_stage_inputs_compared',0) for r in rows),'trial_matrix_sha256':sha_file(stage/'trial-matrix.json'),'rows':rows,'limitation':'Provenance/input equality is not proof of semantic correctness or independent human gold.'};proof_path.parent.mkdir(parents=True,exist_ok=True);proof_path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in proof.items() if k!='rows'}))
    if proof['status']!='passed':raise SystemExit(1)

if __name__=='__main__':main()
