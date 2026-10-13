from types import SimpleNamespace

import pytest

from app.services.generator_usage import generator_usage


def receipt(**changes):
    return {'version':'pipeline-http-meter-v1','provider':'openrouter','model':'fixed-generator',
            'status':'parsed','request_attempts':1,'failed_http_attempts':0,'elapsed_ms':100,
            'reported_total_tokens':10,'reported_cost_credits':0.01,**changes}


def run(history):
    return SimpleNamespace(pipeline_provider='openrouter',pipeline_model='fixed-generator',
                           reproducibility_metadata={'generation_observations':history})


def operation(identity, *receipts, status='completed'):
    return {'operation_id':identity,'status':status,
            'attempts':[{'http_execution':item} for item in receipts]}


def test_failed_first_operation_and_repairs_remain_in_usage_totals():
    observed=generator_usage(run([
        operation('failed',receipt(status='failed',request_attempts=2,failed_http_attempts=1,
                                   elapsed_ms=300,reported_cost_credits=0.02),status='failed'),
        operation('retry',receipt(),receipt()),
    ]))
    assert observed['recorded_invocations']==3 and observed['receipt_count']==3
    assert observed['request_attempts']==4 and observed['failed_http_attempts']==1
    assert observed['observed_elapsed_ms']==500
    assert observed['observed_cost_credits']==pytest.approx(0.04)
    assert observed['observed_total_tokens']==30
    assert not observed['complete_cost_coverage']


def test_unknown_no_dispatch_and_reported_zero_are_different():
    unknown=generator_usage(run([operation('legacy',None)]))
    assert unknown['request_attempts'] is None and unknown['observed_cost_credits'] is None
    no_dispatch=generator_usage(run([operation('no-key',receipt(status='failed',request_attempts=0,
        reported_total_tokens=None,reported_cost_credits=None),status='failed')]))
    assert no_dispatch['request_attempts']==0 and no_dispatch['observed_elapsed_ms'] is None
    measured=generator_usage(run([operation('valid',receipt(reported_cost_credits=0,reported_total_tokens=0))]))
    assert measured['observed_cost_credits']==0 and measured['observed_total_tokens']==0
    assert measured['complete_cost_coverage']
    unfinished=generator_usage(run([operation('valid',receipt()),operation('pending',status='started')]))
    assert unfinished['unfinished_operations'] and not unfinished['complete_cost_coverage']


@pytest.mark.parametrize('change',[{'model':'other'},{'provider':'openai'},
    {'reported_cost_credits':True},{'reported_cost_credits':float('inf')},
    {'request_attempts':True},{'failed_http_attempts':2},{'elapsed_ms':float('nan')}])
def test_unbound_or_invalid_receipts_are_excluded(change):
    observed=generator_usage(run([operation('bad',receipt(**change)),operation('valid',receipt())]))
    assert observed['receipt_count']==1
    assert observed['observed_cost_credits']==0.01
    assert not observed['complete_cost_coverage']


def test_duplicated_operations_and_overflow_cannot_inflate_known_totals():
    duplicated=generator_usage(run([operation('duplicate',receipt()),operation('duplicate',receipt())]))
    assert duplicated['receipt_count']==0 and duplicated['observed_cost_credits'] is None
    overflow=generator_usage(run([operation('a',receipt(reported_cost_credits=1e308)),
        operation('b',receipt(reported_cost_credits=1e308))]))
    assert overflow['observed_cost_credits'] is None and not overflow['complete_cost_coverage']
