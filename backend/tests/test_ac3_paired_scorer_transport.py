"""Mock transport checks; no model requests or human evidence."""
from unittest.mock import MagicMock, patch
import httpx
import pytest
from app.services.ac3_paired_scorer_transport import post_once
from app.target_ai.request_contracts import build_openrouter_request_contract, request_contract_sha256


def fixture():
    payload={'model':'openai/gpt-6-luna','messages':[{'role':'user','content':'synthetic'}],'max_tokens':20}
    contract=build_openrouter_request_contract(url='https://openrouter.ai/api/v1/chat/completions',
                                               payload=payload,role='paired_scorer')
    ledger=MagicMock();ledger.settle.return_value={'status':'settled'}
    args=dict(scope='scope',test_id='test',request_key='request',target_answer_sha256='a'*64,
              expected_contract=contract,payload=payload,headers={'Authorization':'Bearer synthetic'},output_token_limit=20)
    return ledger,args


def test_reserves_exact_contract_before_one_send_and_records_output():
    ledger,args=fixture()
    response=httpx.Response(200,json={'choices':[{'message':{'content':'synthetic'}}],'usage':{'cost':0.0001}})
    def send(*a,**kw):
        ledger.begin.assert_called_once_with('scope','test','scorer','request',
            request_contract_sha256(args['expected_contract']),target_answer_sha256='a'*64)
        return response
    with patch('app.services.ac3_paired_scorer_transport.httpx.post',side_effect=send) as post:
        result=post_once(ledger,**args)
    assert post.call_count==1 and result['status']=='settled' and not result['automatic_retry_allowed']
    assert ledger.settle.call_args.args[-1]==0.0001


def test_changed_contract_never_reserves_or_sends():
    ledger,args=fixture();args['payload']={**args['payload'],'max_tokens':21}
    with patch('app.services.ac3_paired_scorer_transport.httpx.post') as post:
        with pytest.raises(ValueError,match='contract'):post_once(ledger,**args)
    ledger.begin.assert_not_called();post.assert_not_called()


def test_transport_failure_does_not_retry_or_claim_settlement():
    ledger,args=fixture()
    with patch('app.services.ac3_paired_scorer_transport.httpx.post',side_effect=httpx.ConnectError('synthetic')) as post:
        with pytest.raises(httpx.ConnectError):post_once(ledger,**args)
    assert post.call_count==1;ledger.begin.assert_called_once();ledger.settle.assert_not_called()


def test_missing_cost_preserves_result_but_keeps_unknown_status():
    ledger,args=fixture();ledger.settle.return_value={'status':'cost_unknown'}
    response=httpx.Response(200,json={'choices':[{'message':{'content':'synthetic'}}],'usage':{}})
    with patch('app.services.ac3_paired_scorer_transport.httpx.post',return_value=response):
        result=post_once(ledger,**args)
    assert result['status']=='cost_unknown' and result['scorer_output_preserved']
    assert ledger.settle.call_args.args[-1] is None
