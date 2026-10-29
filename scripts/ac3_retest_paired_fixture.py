"""Offline paired-run harness; only explicit synthetic fixtures are accepted.

This module cannot contact a model, import application memories, evaluate real
responses, or write experiment results. It exercises exhaustive pairing before
any future live integration.
"""
import hashlib
from scripts.ac3_retest_paired_integrity import validate_paired_records


def run_fixture(stage, old_version, new_version):
    if stage.get('format') != 'ac3-retest-paired-offline-stage-v1' or stage.get('product_execution_supported') is not False:
        raise ValueError('Only an offline staged fixture is permitted.')
    tests=stage['test_ids'];answers=[];old=[];new=[]
    for i, ident in enumerate(tests):
        answer=None if i % 41 == 0 else f'SYNTHETIC-ONLY:{ident}'
        answer_digest=hashlib.sha256(answer.encode()).hexdigest() if answer else None
        answers.append({'test_id':ident,'status':'answered' if answer else 'target_error','answer':answer})
        for rows,version in ((old,old_version),(new,new_version)):
            rows.append({'test_id':ident,'target_answer_sha256':answer_digest,'evaluator_version_sha256':version,
                         'verdict':'uncertain' if answer else 'error','failure_type':None})
    verification=validate_paired_records(tests,answers,old,new,old_version,new_version)
    return {'format':'ac3-retest-paired-fixture-result-v1','synthetic_only':True,'model_called':False,
            'database_written':False,'human_evidence':False,'integrity':verification}
