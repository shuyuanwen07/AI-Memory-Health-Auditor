"""Prospective all-final source review gate; synthetic saved files, no provider calls."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path('/scripts') if Path('/scripts').exists() else Path(__file__).resolve().parents[2]/'scripts'))
from export_stability_package import final_case_source_review_gate, validate_source_reviews

FIELDS=['run_id','case_id','target_status','target_response_path','target_response_sha256',
    'automatic_grade_path','automatic_grade_unchanged','source_message_ids','write_receipt_path',
    'retention_receipt_path','retrieval_receipt_path','final_input_path','identity_observation_path',
    'claims','critical_errors','omissions','usefulness','pipeline_losses','review_limitations']
FILES=['pilot-report.json','actual-input-receipt.json','actual-wire-attempt-receipts.json','actual-wire-validation.json']


def write(path,data):path.write_text(json.dumps(data))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def saved(tmp_path):
    stage=tmp_path/'final';stage.mkdir();trials=[];reviews=[]
    for i in range(120):
        cid=f'case-{i//6:02}';roundno=(i%6)//2+1;arm=['weak_first_hit','strong_rule_based'][i%2]
        split='development' if i//6<8 else 'evaluation'
        relative=f'trials/{split}/round-{roundno}/{cid}/{arm}';p=stage/relative;p.mkdir(parents=True)
        trial={'case_id':cid,'round':roundno,'arm':arm,'split':split,'directory':relative};trials.append(trial)
        report={'status':'completed','benchmark_result':{'run_id':f'run-{i}'},
            'target_call_receipts':[{'status':'completed','response':{'response_text':'Alpha is blue.',
                'execution_metadata':{'completion_status':'complete','finish_reason':'stop'}}}],
            'semantic_assessments':[{'status':'completed','verdict':{'correct':False}}]}
        write(p/'pilot-report.json',report)
        write(p/'pilot-subset.json',[{'haystack_sessions':[[{'role':'user','content':'Alpha is blue.'}]]}])
        for name in FILES[1:]:write(p/name,{'synthetic':True,'case':i})
        row={field:[] for field in FIELDS}
        row.update(run_id=f'run-{i}',case_id=cid,round=roundno,arm=arm,split=split,
            target_status='completed',target_response_sha256=hashlib.sha256(b'Alpha is blue.').hexdigest(),
            automatic_grade_unchanged=True,claims=[{'claim':'Alpha is blue.','source_support':'supported',
                'source_quote':'Alpha is blue.','source_message_id':'MSG-001','supplied_quote_verified':True,
                'explanation':'Exact original user source.'}],critical_errors=[],
            reviewed_file_sha256={name:sha(p/name) for name in FILES})
        reviews.append(row)
    write(stage/'trial-matrix.json',{'stage':'final','trials':trials})
    write(stage/'study-execution.json',{'status':'completed','trials':[{**t,'status':'completed'} for t in trials]})
    protocol={'execution':{'planned_total_target_calls':120},'additional_acceptance_requirements':{'final_source_review_required':True}}
    return protocol,stage,{'status':'completed','trials':reviews},trials


def test_all_120_bound_rows_pass_with_zero_critical_without_changing_false_grades(saved):
    protocol,stage,review,trials=saved
    before={str(p):sha(p) for p in stage.rglob('*.json')}
    gate,verified=final_case_source_review_gate(protocol,stage,review,FIELDS)
    assert gate['status']=='pass' and len(verified)==120
    assert gate['observed']['reviewed_trials']==120 and gate['observed']['critical_error_count']==0
    assert before=={str(p):sha(p) for p in stage.rglob('*.json')}


def test_missing_and_in_progress_are_pending_not_safe(saved):
    protocol,stage,review,_=saved
    gate,verified=final_case_source_review_gate(protocol,stage,None,FIELDS)
    assert gate['status']=='pending' and gate['observed']['review_state']=='missing' and verified=={}
    review['status']='in_progress';review['trials']=review['trials'][:24]
    gate,_=final_case_source_review_gate(protocol,stage,review,FIELDS)
    assert gate['status']=='pending' and gate['observed']['reviewed_trials']==24


def test_completed_partial_final_reviews_fail_not_guard_36_or_legacy_partial_pass(saved):
    protocol,stage,review,_=saved;review['trials']=review['trials'][:24]
    legacy,_=validate_source_reviews(review,stage,[],None)
    assert legacy['status']=='pass'
    gate,_=final_case_source_review_gate(protocol,stage,review,FIELDS)
    assert gate['status']=='fail' and gate['observed']['planned_trials']==120


@pytest.mark.parametrize('category',['unsupported_event_year','unsupported_initial_state'])
def test_any_explicit_critical_list_fails_without_whitelist_or_grade_rewrite(saved,category):
    protocol,stage,review,_=saved;review['trials'][0]['critical_errors']=[{'category':category}]
    gate,_=final_case_source_review_gate(protocol,stage,review,FIELDS)
    assert gate['status']=='fail' and gate['observed']['critical_error_count']==1


@pytest.mark.parametrize('name',FILES)
def test_each_of_four_original_snapshots_required_and_tamper_detected(saved,name):
    protocol,stage,review,trials=saved
    review['trials'][0]['reviewed_file_sha256'].pop(name)
    gate,verified=final_case_source_review_gate(protocol,stage,review,FIELDS)
    assert gate['status']=='fail' and len(verified)==119
    path=stage/trials[0]['directory']/name
    review['trials'][0]['reviewed_file_sha256'][name]=sha(path)
    path.write_text(path.read_text()+'\n')
    gate,_=final_case_source_review_gate(protocol,stage,review,FIELDS)
    assert gate['status']=='fail'


def test_schema_and_source_quote_are_required(saved):
    protocol,stage,review,_=saved
    gate,_=final_case_source_review_gate(protocol,stage,review,[])
    assert gate['status']=='fail'
    review['trials'][0]['claims'][0]['source_quote']='not original source'
    gate,_=final_case_source_review_gate(protocol,stage,review,FIELDS)
    assert gate['status']=='fail'


@pytest.mark.parametrize('declaration',[None,False])
def test_old13_and_explicit_disabled_protocol_leave_gate_absent(saved,declaration):
    protocol,stage,review,_=saved
    if declaration is None:protocol.pop('additional_acceptance_requirements')
    else:protocol['additional_acceptance_requirements']['final_source_review_required']=False
    review['trials']=review['trials'][:24]
    assert final_case_source_review_gate(protocol,stage,review,FIELDS) is None
    assert validate_source_reviews(review,stage,[],None)[0]['status']=='pass'


@pytest.mark.parametrize('flag',['true',1,None])
def test_invalid_explicit_requirement_not_silently_dropped(saved,flag):
    protocol,stage,review,_=saved
    protocol['additional_acceptance_requirements']['final_source_review_required']=flag
    assert final_case_source_review_gate(protocol,stage,review,FIELDS)[0]['status']=='fail'


def test_final_matrix_cannot_be_replaced_by_safety_guard_denominator(saved):
    protocol,stage,review,trials=saved
    write(stage/'trial-matrix.json',{'stage':'safety-guards','trials':trials[:36]})
    assert final_case_source_review_gate(protocol,stage,review,FIELDS)[0]['status']=='fail'
    write(stage/'trial-matrix.json',{'stage':'final','trials':[dict(t,split='safety_guards') for t in trials]})
    assert final_case_source_review_gate(protocol,stage,review,FIELDS)[0]['status']=='fail'


def test_split_mismatch_and_nonterminal_stage_cannot_pass(saved):
    protocol,stage,review,trials=saved
    review['trials'][0]['split']='safety_guards'
    assert final_case_source_review_gate(protocol,stage,review,FIELDS)[0]['status']=='fail'
    review['trials'][0]['split']=trials[0]['split']
    execution=json.loads((stage/'study-execution.json').read_text());execution['status']='running'
    write(stage/'study-execution.json',execution)
    assert final_case_source_review_gate(protocol,stage,review,FIELDS)[0]['status']=='pending'


@pytest.mark.parametrize('enabled',[True,False])
def test_export_main_records_optional_final_gate_without_relabeling_grades(saved,monkeypatch,enabled):
    import export_stability_package as exporter
    protocol,stage,review,trials=saved;root=stage.parent
    protocol['additional_acceptance_requirements']['final_source_review_required']=enabled
    write(root/'study-protocol.json',protocol)
    members=[{'question_id':f'case-{i:02}','question_type':'synthetic'} for i in range(20)]
    write(root/'selected-metadata.json',{'dataset_sha256':'synthetic','selected_metadata':members[8:]})
    write(root/'selection-commitment.json',{})
    guarddir=root/'guards';guarddir.mkdir();write(guarddir/'source-review-schema.json',{'required_trial_fields':FIELDS})
    reference=root.parent/'longmemeval-identity-conservative-final-20261021/regression-4096/run-01'
    reference.mkdir(parents=True,exist_ok=True)
    write(reference/'suite-manifest.json',{'cases':[{'case_id':m['question_id'],'category':'synthetic'} for m in members[:8]]})
    write(stage/'case-source-reviews.json',review)
    for i,member in enumerate(members):
        split='development' if i<8 else 'evaluation';directory=stage/'inputs'/split;directory.mkdir(parents=True,exist_ok=True)
        write(directory/(member['question_id']+'.json'),[{'question':'What is Alpha?','answer':'Blue'}])
    before={str(p):sha(p) for p in stage.rglob('pilot-report.json')}
    output=root/'package.json'
    monkeypatch.setattr(sys,'argv',['export_stability_package.py','--root',str(root),'--stage','final','--output',str(output)])
    exporter.main()
    payload=json.loads(json.loads(output.read_text())['payload_json'])
    gates=payload['acceptance_results']['gates']
    if enabled:
        assert gates['final_case_source_safety']['status']=='pass'
        assert gates['final_case_source_safety']['observed']['reviewed_trials']==120
    else:assert 'final_case_source_safety' not in gates
    assert before=={str(p):sha(p) for p in stage.rglob('pilot-report.json')}
    assert all(run['grading_attempt']['verdict']['correct'] is False for split in payload['splits'] for case in split['cases'] for run in case['runs'])


def test_bad_protocol_count_and_matrix_path_fail_closed(saved):
    protocol,stage,review,trials=saved
    for invalid in [None,{}, {'planned_total_target_calls':36}, {'planned_total_target_calls':True}]:
        bad=copy.deepcopy(protocol);bad['execution']=invalid
        assert final_case_source_review_gate(bad,stage,review,FIELDS)[0]['status']=='fail'
    trials[0]['directory']='../../outside'
    write(stage/'trial-matrix.json',{'stage':'final','trials':trials})
    assert final_case_source_review_gate(protocol,stage,review,FIELDS)[0]['status']=='fail'


def scoped(protocol):
    protocol['additional_acceptance_requirements']['final_source_critical_error_arms']=['strong_rule_based']


def test_weak_critical_is_reported_but_strong_scoped_gate_passes(saved):
    protocol,stage,review,_=saved;scoped(protocol)
    review['trials'][0]['critical_errors']=[{'category':'unsupported_initial_state'}]
    gate,verified=final_case_source_review_gate(protocol,stage,review,FIELDS)
    observed=gate['observed']
    assert gate['status']=='pass' and len(verified)==120
    assert observed['critical_error_count']==1
    assert observed['critical_error_count_by_arm']=={'weak_first_hit':1,'strong_rule_based':0}
    assert observed['critical_error_required_arms']==['strong_rule_based']
    assert observed['critical_error_required_arm_trial_count']==60
    assert observed['required_arm_critical_error_count']==0
    assert 'strong_rule_based' in gate['threshold'] and 'descriptive' in gate['threshold']


def test_strong_scoped_critical_always_fails(saved):
    protocol,stage,review,_=saved;scoped(protocol)
    review['trials'][1]['critical_errors']=[{'category':'unsupported_identity_merge'}]
    gate,_=final_case_source_review_gate(protocol,stage,review,FIELDS)
    assert gate['status']=='fail' and gate['observed']['required_arm_critical_error_count']==1


@pytest.mark.parametrize('kind',['missing','binding','schema','source','nonterminal','failed','error'])
def test_out_of_scope_weak_critical_cannot_hide_other_failures(saved,kind):
    protocol,stage,review,trials=saved;scoped(protocol)
    review['trials'][0]['critical_errors']=[{'category':'unsupported_initial_state'}]
    if kind=='missing':review['trials'].pop(2)
    elif kind=='binding':review['trials'][2]['reviewed_file_sha256'].pop(FILES[0])
    elif kind=='schema':review['trials'][2].pop('claims')
    elif kind=='source':review['trials'][2]['claims'][0]['source_quote']='not a real quote'
    elif kind=='nonterminal':
        execution=json.loads((stage/'study-execution.json').read_text());execution['status']='running'
        write(stage/'study-execution.json',execution)
    else:review['status']=kind
    gate,_=final_case_source_review_gate(protocol,stage,review,FIELDS)
    assert gate['status']!='pass'
    assert gate['observed']['critical_error_count']>=1


@pytest.mark.parametrize('scope',[[],['unknown'],['strong_rule_based','strong_rule_based'],'strong_rule_based',None,True,[1]])
def test_invalid_critical_scope_fails_closed(saved,scope):
    protocol,stage,review,_=saved
    protocol['additional_acceptance_requirements']['final_source_critical_error_arms']=scope
    gate,_=final_case_source_review_gate(protocol,stage,review,FIELDS)
    assert gate['status']=='fail' and gate['observed']['review_state']=='invalid_configuration'


def criteria(protocol,stage,review):
    path=stage.parent/'guards'/'final-source-review-criteria.json';path.parent.mkdir(exist_ok=True)
    write(path,{'critical_categories':['unsupported_initial_state']})
    digest=sha(path)
    protocol['additional_acceptance_requirements'].update(
        final_source_review_criteria_file='guards/final-source-review-criteria.json',
        final_source_review_criteria_sha256=digest)
    for row in review['trials']:row['source_review_criteria_sha256']=digest
    return path


def test_prospective_criteria_binds_every_arm_not_only_strong(saved):
    protocol,stage,review,_=saved;scoped(protocol)
    path=criteria(protocol,stage,review)
    assert final_case_source_review_gate(protocol,stage,review,FIELDS)[0]['status']=='pass'
    review['trials'][0].pop('source_review_criteria_sha256')
    assert final_case_source_review_gate(protocol,stage,review,FIELDS)[0]['status']=='fail'
    review['trials'][0]['source_review_criteria_sha256']=sha(path)
    path.write_text(path.read_text()+'\n')
    assert final_case_source_review_gate(protocol,stage,review,FIELDS)[0]['status']=='fail'


@pytest.mark.parametrize('kind',['nohash','nofile','missing','escape','absolute','invalidhash'])
def test_invalid_or_partial_criteria_declaration_fails_closed(saved,kind):
    protocol,stage,review,_=saved;path=criteria(protocol,stage,review)
    requirements=protocol['additional_acceptance_requirements']
    if kind=='nohash':requirements.pop('final_source_review_criteria_sha256')
    elif kind=='nofile':requirements.pop('final_source_review_criteria_file')
    elif kind=='missing':path.unlink()
    elif kind=='escape':requirements['final_source_review_criteria_file']='../outside.json'
    elif kind=='absolute':requirements['final_source_review_criteria_file']=str(path.resolve())
    elif kind=='invalidhash':requirements['final_source_review_criteria_sha256']='g'*64
    assert final_case_source_review_gate(protocol,stage,review,FIELDS)[0]['status']=='fail'


def declare_grid(protocol,trials):
    protocol['additional_acceptance_requirements']['final_source_review_required_cells']=[
        {field:row[field] for field in ('split','case_id','round','arm')} for row in trials]


def test_complete_declared_grid_preserves_scoped_strong_sixty(saved):
    protocol,stage,review,trials=saved;scoped(protocol);declare_grid(protocol,trials)
    review['trials'][0]['critical_errors']=[{'category':'unsupported_initial_state'}]
    gate,_=final_case_source_review_gate(protocol,stage,review,FIELDS)
    assert gate['status']=='pass'
    assert gate['observed']['critical_error_required_arm_trial_count']==60
    assert gate['observed']['reviewed_trials']==120


@pytest.mark.parametrize('kind',['one_strong','omitted','round','split','arm','boolround','strround'])
def test_actual_final_grid_must_equal_predeclared_metadata_grid(saved,kind):
    protocol,stage,review,trials=saved;scoped(protocol);declare_grid(protocol,trials)
    altered=copy.deepcopy(trials)
    if kind=='one_strong':
        # Even 120 unique cells with valid reply reviews cannot substitute 119 Weak cells.
        for i,row in enumerate(altered):
            row['case_id']=f'new-case-{i}'
            row['arm']='strong_rule_based' if i==1 else 'weak_first_hit'
    elif kind=='omitted':altered.pop()
    elif kind=='round':altered[0]['round']=4
    elif kind=='split':altered[0]['split']='evaluation'
    elif kind=='arm':altered[0]['arm']='unknown'
    elif kind=='boolround':altered[0]['round']=True
    elif kind=='strround':altered[0]['round']='1'
    write(stage/'trial-matrix.json',{'stage':'final','trials':altered})
    gate,_=final_case_source_review_gate(protocol,stage,review,FIELDS)
    assert gate['status']=='fail' and gate['observed']['review_state']=='invalid_matrix'


@pytest.mark.parametrize('kind',['empty','none','duplicate','omitted','extra','split','arm','case','boolround','zeroround','strround','extra_field','missing_field'])
def test_declared_final_grid_schema_is_strict_and_unique(saved,kind):
    protocol,stage,review,trials=saved;declare_grid(protocol,trials)
    req=protocol['additional_acceptance_requirements'];cells=req['final_source_review_required_cells']
    if kind=='empty':req['final_source_review_required_cells']=[]
    elif kind=='none':req['final_source_review_required_cells']=None
    elif kind=='duplicate':cells[1]=copy.deepcopy(cells[0])
    elif kind=='omitted':cells.pop()
    elif kind=='extra':cells.append(copy.deepcopy(cells[0]))
    elif kind=='split':cells[0]['split']='safety_guards'
    elif kind=='arm':cells[0]['arm']='unknown'
    elif kind=='case':cells[0]['case_id']=' '
    elif kind=='boolround':cells[0]['round']=True
    elif kind=='zeroround':cells[0]['round']=0
    elif kind=='strround':cells[0]['round']='1'
    elif kind=='extra_field':cells[0]['question']='forbidden extra declaration'
    elif kind=='missing_field':cells[0].pop('arm')
    gate,_=final_case_source_review_gate(protocol,stage,review,FIELDS)
    assert gate['status']=='fail' and gate['observed']['review_state']=='invalid_configuration'
