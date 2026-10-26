"""Freeze, then materialize and execute a predeclared reliability study.

No new question/answer/source is decoded until final code is frozen. Existing
attempts cannot be overwritten. Run each case/arm/repetition independently.
"""
from stability_grading_budget import study_grader_cap, preflight_grader_budget, validate_budget_ledger, study_trial_grader_budget_matches
from stability_configuration import pilot_cohorts, pilot_cells, role_settings, preflight_all_roles, pilot_quality_gates, selection_binding, study_trial_controls_match, study_trial_memory_controls

import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


def read(p):return json.loads(p.read_text())
def dump(p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def file_path(name,workspace):
    if Path('/app/app').exists():return Path('/scripts')/Path(name).name if name.startswith('scripts/') else Path('/app')/Path(name).relative_to('backend')
    return workspace/name

def require_development_source_reviews(root, protocol):
    """Enforce the approved review prerequisite against saved terminal replies."""
    requirement=protocol.get('extra_manual_development_source_review')
    if requirement is None:return
    from export_stability_package import validate_source_reviews
    fields=('split','case_id','round','arm')
    def key(row):
        assert isinstance(row,dict) and all(field in row for field in fields), 'Source-review trial key is incomplete.'
        return tuple(row[field] for field in fields)
    required=requirement.get('required_trials',[])
    keys=[key(row) for row in required]
    assert keys and len(keys)==len(set(keys))==requirement.get('required_unique_terminal_reviews'), 'Required source-review denominator differs.'
    assert requirement.get('critical_errors_max')==0, 'This prerequisite requires zero critical source errors.'
    stage=root/'development-pilot'
    review=read(stage/'case-source-reviews.json')
    gate,verified=validate_source_reviews(review,stage,[],None)
    assert gate['status']=='pass', 'Development source reviews are incomplete, unbound or contain critical errors.'
    matrix=read(stage/'trial-matrix.json')['trials']
    planned={key(row) for row in matrix}
    actual={key(row) for row in verified.values()}
    assert set(keys)<=actual<=planned, 'Required development source-review keys are missing or use another split.'
    if requirement.get('automatic_input_wire_file_bindings') is True:
        by_key={key(row):row for row in matrix}
        for row in verified.values():
            directory=stage/by_key[key(row)]['directory']
            bindings=row.get('reviewed_file_sha256',{})
            for name in ('pilot-report.json','actual-input-receipt.json',
                         'actual-wire-attempt-receipts.json','actual-wire-validation.json'):
                path=directory/name
                assert path.is_file() and bindings.get(name)==sha(path), 'Source review input/wire snapshot is missing or changed.'
    return gate

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--stage',choices=['development-pilot','final','safety-guards'],required=True);ap.add_argument('--phase',choices=['freeze','materialize','run'],required=True);args=ap.parse_args()
    root=args.root.resolve();workspace=Path(__file__).resolve().parents[1];protocol=read(root/'study-protocol.json');commit=read(root/'selection-commitment.json');selected=read(root/'selected-metadata.json');stage=root/args.stage
    assert canon(protocol['acceptance'])==commit['quantitative_acceptance_sha256']
    assert sha(root/'selected-metadata.json')==commit['selected_metadata_sha256'] and selected['status']=='selection_complete'
    assert selected['selected_ids']==commit['selected_ids']
    actual_selection=selection_binding(protocol,selected,root,workspace)
    profile=protocol['target']['final_target_profile_flags'];assert isinstance(profile,dict),'Final interface/profile flags must be explicit before any code freeze.'
    assert profile.get('identity_analysis','off') in {'off','evidence_links'}
    memory_controls=study_trial_memory_controls(protocol)
    target_cap=role_settings(protocol,'target_answer',study=True)['output_token_limit']
    role_settings(protocol,'target_identity_evidence',study=True)
    all_role_preflight=preflight_all_roles(protocol,study=True)
    assert all_role_preflight['passed'],'Configured pipeline cap would lower a frozen role budget.'
    if profile.get('identity_analysis')=='evidence_links':assert protocol['execution']['extra_model_stage_calls']>0,'Separate evidence calls must be budgeted.'
    grader_cap=study_grader_cap(protocol)
    if 'grading' in protocol and 'budget' in protocol:validate_budget_ledger(protocol)
    budget_preflight=preflight_grader_budget(grader_cap)
    if args.phase=='run':
        dump(stage/'grading-budget-preflight.json',budget_preflight)
        dump(stage/'all-role-budget-preflight.json',all_role_preflight)
    assert budget_preflight['passed'],'Configured pipeline cap would silently lower preregistered grader budget.'
    frozen_path=stage/'FROZEN.json'
    if args.phase=='freeze':
        assert protocol['target'].get('profile_is_provisional_pending_parent_final_interface') is False,'Await explicit parent final-interface/code-freeze notice.'
        if frozen_path.exists():raise ValueError('A release freeze is immutable; use a new preregistered release.')
        if args.stage in {'final','safety-guards'}:
            require_development_source_reviews(root,protocol)
            pilotproof=root/'development-pilot/replay-proof.json';assert pilotproof.exists() and read(pilotproof)['status']=='passed','Development pilot must first have a terminal passing replay proof.'
            pilotmatrix=read(root/'development-pilot/trial-matrix.json')
            expected_cells={(row['split'],row['case_id'],row['round'],row['arm']) for row in pilot_cells(protocol)}
            actual_cells={(row['split'],row['case_id'],row['round'],row['arm']) for row in pilotmatrix['trials']}
            assert actual_cells==expected_cells and len(pilotmatrix['trials'])==len(expected_cells),'Pilot matrix omits or adds preregistered cells.'
            pilot_quality_rows=[]
            for item in pilotmatrix['trials']:
                report=read(root/'development-pilot'/item['directory']/'pilot-report.json');target=report['target_call_receipts'][0];grades=report.get('semantic_assessments',[]);meta=target.get('response',{}).get('execution_metadata',{})
                assert target['status']=='completed' and meta.get('finish_reason')=='stop' and meta.get('completion_status')=='complete' and meta.get('reported_model')=='openai/gpt-6-luna','Known4 pilot must first meet100%usable/Luna identity.'
                assert len(grades)==1 and grades[0].get('status')=='completed' and type(grades[0].get('verdict',{}).get('correct')) is bool,'Known4 pilot must first have100%validgradecoverage.'
                pilot_quality_rows.append({**item,'semantic_grade':{'status':grades[0]['status'],'correct':grades[0]['verdict']['correct']}})
            assert all(gate['status']=='pass' for gate in pilot_quality_gates(protocol,pilot_quality_rows).values()),'Prospective development quality requirements failed.'
            if protocol.get('request_contract_required') is True:
                package_path=root/protocol.get('development_pilot',{}).get('result_package_path','development-pilot/result-package.json')
                envelope=read(package_path);assert hashlib.sha256(envelope['payload_json'].encode()).hexdigest()==envelope['payload_sha256'],'Pilot package integrity differs.'
                package=json.loads(envelope['payload_json']);assert package['protocol']==protocol,'Pilot package uses another protocol.'
                gates=package['acceptance_results']['gates']
                required_gates=['actual_Luna_identity','usable_targets','grade_coverage','input_replay','actual_wire_request_contracts','frozen_protocol_binding']
                if protocol.get('memory_preparation_receipt_required') is True:required_gates.append('actual_memory_preparation')
                if profile.get('answer_validation','off')=='source_grounding':required_gates.append('answer_validation_contracts')
                if 'development-pilot' in protocol.get('additional_acceptance_requirements',{}).get('applies_to_stages',[]):required_gates.append('auxiliary_validation_coverage')
                assert all(gates.get(key,{}).get('status')=='pass' for key in required_gates),'Pilot technical/auxiliary/source gates are not complete.'

        paths=sorted(list((workspace/'backend/app').rglob('*.py'))+list((workspace/'scripts').glob('*.py')))
        manifest={str(p.relative_to(workspace)):sha(p) for p in paths}
        if args.stage in {'safety-guards','final'} and protocol.get('request_contract_required') is True:
            assert manifest==read(root/'development-pilot/tested-source-manifest.json'),'Measurement code changed after pilot; use a new release.'
        stage.mkdir(parents=True,exist_ok=True)
        dump(stage/'tested-source-manifest.json',manifest)
        with zipfile.ZipFile(stage/'tested-source.zip','w',zipfile.ZIP_DEFLATED) as z:
            for p in paths:z.write(p,str(p.relative_to(workspace)))
        dump(frozen_path,{'stage':args.stage,'created_at':now(),'protocol_sha256':sha(root/'study-protocol.json'),'selection_commitment_sha256':sha(root/'selection-commitment.json'),'source_manifest_sha256':sha(stage/'tested-source-manifest.json'),'source_archive_sha256':sha(stage/'tested-source.zip'),'selection_script_sha256':actual_selection['helper_sha256'],'selection_helper_path':actual_selection['helper_path'],'selection_fixture_manifest':actual_selection['fixture_manifest'],'new_question_content_opened':False,'fixture_manifest':{str(p.relative_to(root)):sha(p) for p in (root/'guards').glob('*.json')}})
        print(json.dumps({'status':'frozen','stage':args.stage,'files':len(manifest)}));return
    freeze=read(frozen_path);manifest=read(stage/'tested-source-manifest.json')
    def check():
        if Path('/app/app').exists():
            current={str(Path('backend/app')/p.relative_to('/app/app')) for p in Path('/app/app').rglob('*.py')}|{str(Path('scripts')/p.name) for p in Path('/scripts').glob('*.py')}
        else:current={str(p.relative_to(workspace)) for p in list((workspace/'backend/app').rglob('*.py'))+list((workspace/'scripts').glob('*.py'))}
        assert current==set(manifest),'Frozen app/scripts membership changed.'
        for name,expected in freeze.get('fixture_manifest',{}).items():assert sha(root/name)==expected,'Frozen guard fixture changed:'+name
        assert sha(root/'study-protocol.json')==freeze['protocol_sha256'],'Protocol changed after freeze.'
        current_selection=selection_binding(protocol,selected,root,workspace)
        if 'selection_fixture_manifest' in freeze:
            assert current_selection=={'helper_path':freeze['selection_helper_path'],'helper_sha256':freeze['selection_script_sha256'],'fixture_manifest':freeze['selection_fixture_manifest']},'Frozen selector binding changed.'
        assert sha(root/'selection-commitment.json')==freeze['selection_commitment_sha256']
        for name,expected in manifest.items():assert sha(file_path(name,workspace))==expected,'Frozen code changed:'+name
    check()
    if args.phase=='materialize':
        if (stage/'trial-matrix.json').exists():raise ValueError('Never rematerialize a committed/evaluated set.')
        if args.stage=='safety-guards':
            from prepare_stability_guards import materialize
            materialize(root,stage,protocol);check();print(json.dumps({'status':'materialized_synthetic_guards','trials':36}));return
        reference=root.parent/'longmemeval-identity-conservative-final-20261021';suite=read(reference/'regression-4096/run-01/suite-manifest.json');cases=[]
        cohorts=pilot_cohorts(protocol) if args.stage=='development-pilot' else []
        planned_pilot=pilot_cells(protocol) if cohorts else []
        if cohorts:
            for cohort in cohorts:
                for qid in cohort['selected_ids']:
                    if cohort.get('source_root'):
                        source_root=Path(cohort['source_root'])
                        if not source_root.is_absolute():source_root=(root/source_root).resolve()
                        data=(source_root/'inputs'/cohort.get('source_split','evaluation')/(qid+'.json')).read_bytes()
                        historical_matrix=read(source_root/'trial-matrix.json')
                        historical_rows=[row for row in historical_matrix['trials'] if row['case_id']==qid and row['split']==cohort.get('source_split','evaluation')]
                        assert historical_rows and all(row['source_sha256']==hashlib.sha256(data).hexdigest() for row in historical_rows),'Historical regression source differs from saved used cohort.'
                    else:
                        member=next(m for m in suite['cases'] if m['case_id']==qid)
                        data=(reference/'regression-4096/run-01'/member['directory']/'pilot-subset.json').read_bytes()
                        assert hashlib.sha256(data).hexdigest()==member['subset_sha256']
                    payload=json.loads(data);assert len(payload)==1 and payload[0]['question_id']==qid
                    cases.append({'split':cohort['split'],'case_id':qid,'type':payload[0]['question_type'],'payload':payload,
                                  'pilot_arms':cohort['arms'],'pilot_rounds':list(range(1,cohort['repetitions']+1)),
                                  'cohort':cohort.get('name','known-development')})
        else:
            for member in suite['cases']:
                data=(reference/'regression-4096/run-01'/member['directory']/'pilot-subset.json').read_bytes()
                assert hashlib.sha256(data).hexdigest()==member['subset_sha256']
                payload=json.loads(data);cases.append({'split':'development','case_id':member['case_id'],'type':payload[0]['question_type'],'payload':payload,'source_sha256':member['subset_sha256']})
        if args.stage=='final':
            # This marker is written BEFORE decoding any selected new record.
            dump(root/'EVALUATED_SET_DO_NOT_RETUNE.json',{'created_at':now(),'ids':selected['selected_ids'],'selection_commitment_sha256':sha(root/'selection-commitment.json'),'rule':'AlltheseIDs now permanently used; no fresh/heldout renaming after tuning.'})
            dataset=Path(selected['dataset_path']);assert sha(dataset)==selected['dataset_sha256']
            with dataset.open('rb') as source:
                for metadata in selected['selected_metadata']:
                    start,end=metadata['raw_record_byte_offsets'];source.seek(start);row=json.loads(source.read(end-start));assert row['question_id']==metadata['question_id'] and row['question_type']==metadata['question_type']
                    cases.append({'split':'evaluation','case_id':row['question_id'],'type':row['question_type'],'payload':[row]})
        provenance=read(reference/'confirmation-protocol.json')['source_provenance'];evaluator=(root.parent/'longmemeval-expanded-20261019/upstream-evaluator').resolve();trials=[]
        for case in cases:
            source=stage/'inputs'/case['split']/(case['case_id']+'.json');dump(source,case['payload']);sourcehash=sha(source)
            for repetition in case.get('pilot_rounds',[1,2,3]):
                arms=list(case.get('pilot_arms',['weak_first_hit','strong_rule_based']));digest=hashlib.sha256((selected['seed']+case['case_id']+str(repetition)).encode()).digest()
                if digest[0]%2:arms.reverse()
                for arm in arms:
                    directory=stage/'trials'/case['split']/('round-'+str(repetition))/case['case_id']/arm;directory.mkdir(parents=True,exist_ok=False)
                    try:os.link(source,directory/'pilot-subset.json')
                    except OSError:shutil.copy2(source,directory/'pilot-subset.json')
                    memory=dict(memory_controls['target_memory_profile'])
                    item={'scope':'exploratory_pilot_not_formal_experiment_c','source_authorised':True,'selected_ids':[case['case_id']],'subset_sha256':sourcehash,'source_provenance':provenance,'provider':'openrouter','model':'openai/gpt-6-luna','strategies':[arm],'target_memory_capacity':memory_controls['target_memory_capacity'],'target_memory_profile':memory,'context_character_budget':memory_controls['context_character_budget'],'output_token_limit':target_cap,'grading_output_token_limit':grader_cap,'request_contract_required':protocol.get('request_contract_required',False),'memory_preparation_receipt_required':protocol.get('memory_preparation_receipt_required',False),'grading_reasoning_effort':protocol.get('grading',{}).get('reasoning_effort'),'upstream_evaluator_directory':os.path.relpath(evaluator,directory),'maximum_extra_answer_validation_calls':int(memory.get('answer_validation','off')=='source_grounding'),'maximum_extra_identity_evidence_calls':int(arm=='strong_rule_based' and profile.get('identity_analysis')=='evidence_links'),'no_quality_retries':True,'user_authorisation':'Fixedpreregisteredengineeringreliabilitystudy; allfirstattemptsretained.'}
                    if case.get('cohort'):item['development_cohort']=case['cohort']
                    dump(directory/'pilot-protocol.json',item);trials.append({'split':case['split'],'case_id':case['case_id'],'type':case['type'],'round':repetition,'arm':arm,'directory':str(directory.relative_to(stage)),'source_sha256':sourcehash,'protocol_sha256':sha(directory/'pilot-protocol.json')})
        expected=len(planned_pilot) if args.stage=='development-pilot' else protocol['execution']['planned_total_target_calls'];assert len(trials)==expected
        dump(stage/'trial-matrix.json',{'created_at':now(),'stage':args.stage,'scope':'known-development' if args.stage=='development-pilot' else 'development_and_first_evaluation_strictly_separate','planned_trials':expected,'trials':trials});check();print(json.dumps({'status':'materialized_and_used','trials':len(trials),'new_sources_opened':args.stage=='final'}));return
    matrix_path=stage/'trial-matrix.json';matrix=read(matrix_path);execution_path=stage/'study-execution.json'
    if execution_path.exists():raise ValueError('Existing attempts must be preserved; no automatic rerun/resume.')
    for trial in matrix['trials']:
        directory=stage/trial['directory'];
        if trial.get('private_criteria_sha256'):assert sha(directory/'guard-private-criteria.json')==trial['private_criteria_sha256'] and sha(directory/'guard-case.json')==trial['guard_case_sha256']
        assert not (directory/'pilot-report.json').exists();assert sha(directory/'pilot-protocol.json')==trial['protocol_sha256'] and sha(directory/'pilot-subset.json')==trial['source_sha256']
        trial_protocol=read(directory/'pilot-protocol.json')
        assert study_trial_grader_budget_matches(protocol,read(directory/'pilot-protocol.json')),'Trial grader cap differs from frozen study grader cap.'
        assert study_trial_controls_match(protocol,trial_protocol),'Trial request controls differ from frozen study.'
    execution={'status':'running','started_at':now(),'trial_matrix_sha256':sha(matrix_path),'source_manifest_sha256':sha(stage/'tested-source-manifest.json'),'trials':[{**t,'status':'not_attempted'} for t in matrix['trials']]};dump(execution_path,execution)
    for index,trial in enumerate(execution['trials']):
        check();directory=stage/trial['directory'];assert sha(directory/'pilot-protocol.json')==trial['protocol_sha256'] and sha(directory/'pilot-subset.json')==trial['source_sha256']
        if trial.get('private_criteria_sha256'):assert sha(directory/'guard-private-criteria.json')==trial['private_criteria_sha256'] and sha(directory/'guard-case.json')==trial['guard_case_sha256']
        trial['status']='running';dump(execution_path,execution)
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('run_stability_trial.py')),'--directory',str(directory)],capture_output=True,text=True)
        (directory/'process-stdout.txt').write_text(result.stdout);(directory/'process-stderr.txt').write_text(result.stderr)
        trial.update(status='completed' if result.returncode==0 else 'error',exit_code=result.returncode);dump(execution_path,execution);print(json.dumps({'event':'trial_finished','completed':index+1,'planned':len(matrix['trials']),'case_id':trial['case_id'],'arm':trial['arm'],'round':trial['round'],'status':trial['status']}),flush=True)
        if (directory/'identity-mismatch-receipt.json').exists():execution['halt_reason']='actual_model_or_unbudgeted_stage_mismatch';break
    check();execution['status']='completed' if all(t['status']=='completed' for t in execution['trials']) else 'partial_failure';execution['finished_at']=now();dump(execution_path,execution)
    if execution['status']!='completed':raise SystemExit(1)

if __name__=='__main__':main()
