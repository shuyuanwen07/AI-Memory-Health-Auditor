"""Validate private paired target outcomes for later blind review.

This verifier does not query a database or contact a provider. A collector must
obtain rows under the frozen audit/ledger locks, and must not manufacture a
terminal error for a request whose billing or outcome remains unknown.
"""
import hashlib
from decimal import Decimal,InvalidOperation
from scripts.ac3_retest_paired_freeze import canonical


def build_target_export(frozen,questions,receipts,responses,*,scope,ledger_frozen_sha256,ledger_status):
    frozen_sha=hashlib.sha256(canonical(frozen)).hexdigest()
    if frozen_sha!=ledger_frozen_sha256 or ledger_status!='active' or not isinstance(scope,str) or not scope.strip():
        raise ValueError('The frozen study or ledger is unresolved')
    if not isinstance(questions,list) or len(questions)!=120 or len({q['test_id'] for q in questions})!=120:
        raise ValueError('All 120 distinct reviewed questions are required')
    if not isinstance(receipts,list) or not isinstance(responses,list):raise ValueError('Receipt and response lists required')
    by_test={};by_response={}
    for row in receipts:
        if row.get('role')!='target':continue
        if row.get('test_id') in by_test:raise ValueError('Duplicate target receipt')
        by_test[row['test_id']]=row
    for row in responses:
        if row.get('test_id') in by_response:raise ValueError('Duplicate system answer')
        by_response[row['test_id']]=row
    if set(by_test)!={q['test_id'] for q in questions} or set(by_response)!=set(by_test):
        raise ValueError('Every question needs one settled target receipt and answer')
    keys=[row.get('request_key') for row in by_test.values()]
    if len(set(keys))!=len(keys):raise ValueError('Target requests must be distinct')
    output=[]
    for question in questions:
        test_id=question['test_id'];receipt=by_test[test_id];response=by_response[test_id]
        if (receipt.get('scope_id')!=scope or receipt.get('status')!='settled'
                or not isinstance(receipt.get('request_key'),str) or not receipt['request_key'].strip()
                or not isinstance(receipt.get('response_text'),str) or not receipt['response_text'].strip()
                or receipt['response_text']!=response.get('response_text')
                or receipt.get('request_evidence_sha256')!=response.get('request_evidence_sha256')
                or not isinstance(receipt.get('request_evidence_sha256'),str)
                or len(receipt['request_evidence_sha256'])!=64
                or any(c not in '0123456789abcdef' for c in receipt['request_evidence_sha256'])):
            raise ValueError('Answer does not match its settled receipt')
        try:cost=Decimal(str(receipt.get('reported_cost_usd')))
        except InvalidOperation as exc:raise ValueError('Invalid reported cost') from exc
        if not cost.is_finite() or cost<0:raise ValueError('Invalid reported cost')
        output.append({'test_id':test_id,'history_id':question['history_id'],'status':'answered',
            'answer':receipt['response_text'],'response_sha256':hashlib.sha256(receipt['response_text'].encode()).hexdigest(),
            'request_key':receipt['request_key'],'reported_cost_usd':str(cost)})
    return {'format':'ac3-paired-target-export-v1','frozen_sha256':frozen_sha,'scope':scope,
            'answers':output,'model_called':False,'human_truth_evaluated':False,
            'limitation':'Private export; provider-reported costs are not independently reconciled billing.'}
