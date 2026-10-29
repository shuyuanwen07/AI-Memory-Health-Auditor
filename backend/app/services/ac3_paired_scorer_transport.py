"""Single-attempt scorer transport bound to a saved paired target answer.

Internal primitive only. Its caller must build `expected_contract` from the
reviewed question, evidence, answer and frozen scorer snapshot, then verify
those inputs under the experiment locks. No public route invokes this code.
"""
import json
import httpx
from app.target_ai.request_contracts import build_openrouter_request_contract, request_contract_sha256


def post_once(ledger, *, scope, test_id, request_key, target_answer_sha256,
              expected_contract, payload, headers, output_token_limit):
    """Reserve before sending; retain provider output, and halt on uncertainty."""
    url='https://openrouter.ai/api/v1/chat/completions'
    actual=build_openrouter_request_contract(url=url,payload=payload,role='paired_scorer')
    if (not isinstance(expected_contract,dict) or actual!=expected_contract
            or actual.get('model')!='openai/gpt-6-luna'
            or type(output_token_limit) is not int or output_token_limit<=0
            or actual.get('max_tokens')!={'present':True,'value':output_token_limit}):
        raise ValueError('Scorer request differs from the frozen request contract')
    contract_sha=request_contract_sha256(actual)
    ledger.begin(scope,test_id,'scorer',request_key,contract_sha,target_answer_sha256=target_answer_sha256)
    # Once reserved, any transport or parse failure leaves the scope unknown;
    # there is no retry and no inference that a failed call was free.
    response=httpx.post(url,headers={'Content-Type':'application/json',**headers},json=payload,timeout=60.0)
    try:
        data=response.json()
    except ValueError as exc:
        raise ValueError('Scorer response is not valid JSON; request remains unresolved') from exc
    if not isinstance(data,dict):raise ValueError('Scorer response is not an object; request remains unresolved')
    raw=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    usage=data.get('usage')
    cost=usage.get('cost') if response.is_success and isinstance(usage,dict) else None
    saved=ledger.settle(scope,request_key,contract_sha,raw,cost)
    if not response.is_success or saved['status']!='settled':
        return {'status':saved['status'],'scorer_output_preserved':True,'automatic_retry_allowed':False}
    return {'status':'settled','scorer_output_preserved':True,'automatic_retry_allowed':False,
            'provider_data':data,'request_contract_sha256':contract_sha}
