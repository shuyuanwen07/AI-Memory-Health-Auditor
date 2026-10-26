"""Synthetic source review prerequisites block progression before any calls."""
import hashlib
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def setup_review(tmp_path, monkeypatch):
    scripts=Path('/scripts') if Path('/scripts/run_stability_study.py').exists() else Path(__file__).resolve().parents[2]/'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    module=importlib.import_module('run_stability_study')
    stage=tmp_path/'development-pilot'
    directory=stage/'trials/synthetic'
    directory.mkdir(parents=True)
    row={'split':'development_regression','case_id':'SYN-ONLY','round':1,'arm':'strong_rule_based','directory':'trials/synthetic'}
    def write(path,value):path.write_text(json.dumps(value))
    write(stage/'trial-matrix.json',{'trials':[row]})
    write(stage/'study-execution.json',{'status':'completed','trials':[{**row,'status':'completed'}]})
    write(directory/'pilot-report.json',{'status':'completed','target_call_receipts':[{'status':'completed','response':{'response_text':'Synthetic fact.','execution_metadata':{'completion_status':'complete','finish_reason':'stop'}}}],'semantic_assessments':[{'status':'completed'}]})
    write(directory/'guard-case.json',{'conversation':{'messages':[{'message_id':'SYN-SOURCE','content':'Synthetic fact.'}]},'runtime_source_id_map':[{'original_source_id':'SYN-SOURCE','runtime_source_id':'MSG-001'}]})
    review={'status':'completed','trials':[{**row,'target_status':'completed','target_response_sha256':hashlib.sha256(b'Synthetic fact.').hexdigest(),'critical_errors':[],'claims':[{'claim':'Synthetic fact.','source_support':'supported','source_quote':'Synthetic fact.','source_message_id':'MSG-001','supplied_quote_verified':True,'explanation':'Synthetic exact source.'}]}]}
    for name in ('actual-input-receipt.json','actual-wire-attempt-receipts.json','actual-wire-validation.json'):
        write(directory/name,{'synthetic_snapshot_only':True})
    review['trials'][0]['reviewed_file_sha256']={name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ('pilot-report.json','actual-input-receipt.json','actual-wire-attempt-receipts.json','actual-wire-validation.json')}
    write(stage/'case-source-reviews.json',review)
    protocol={'extra_manual_development_source_review':{'required_trials':[row],'required_unique_terminal_reviews':1,'critical_errors_max':0,'automatic_input_wire_file_bindings':True}}
    return module,tmp_path,protocol,review,write


def test_bound_required_review_passes(setup_review):
    module,root,protocol,_,_=setup_review
    assert module.require_development_source_reviews(root,protocol)['status']=='pass'


@pytest.mark.parametrize('mutation',['missing','critical','wrong_hash','wrong_split','duplicate_required','missing_wire_binding','changed_input'])
def test_invalid_review_blocks_progression(setup_review,mutation):
    module,root,protocol,review,write=setup_review
    if mutation=='missing':review['trials']=[]
    elif mutation=='critical':review['trials'][0]['critical_errors']=['unsupported identity merge']
    elif mutation=='wrong_hash':review['trials'][0]['target_response_sha256']='0'*64
    elif mutation=='wrong_split':review['trials'][0]['split']='evaluation'
    elif mutation=='duplicate_required':protocol['extra_manual_development_source_review']['required_trials']*=2
    elif mutation=='missing_wire_binding':del review['trials'][0]['reviewed_file_sha256']['actual-wire-attempt-receipts.json']
    else:write(root/'development-pilot/trials/synthetic/actual-input-receipt.json',{'changed':True})
    write(root/'development-pilot/case-source-reviews.json',review)
    with pytest.raises(AssertionError):module.require_development_source_reviews(root,protocol)


def test_legacy_protocol_does_not_invent_review_prerequisite(setup_review):
    module,root,_,_,_=setup_review
    assert module.require_development_source_reviews(root,{}) is None
