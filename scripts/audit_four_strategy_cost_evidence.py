"""Describe stored provider costs and estimates; does not call a provider."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path


def audit(path):
    raw=path.read_bytes();run=json.loads(raw)
    targets,grades=run['target_receipts'],run['grades']
    if len(targets)!=360 or len(grades)!=360:
        raise ValueError('Expected the completed 360-answer study')
    costs=[]
    for grade in grades:
        value=(grade.get('usage') or {}).get('cost')
        if value is not None:
            amount=Decimal(str(value))
            if not amount.is_finite() or amount<0:raise ValueError('Invalid provider-reported cost')
            costs.append(amount)
    target_costs=[]
    for target in targets:
        value=(target.get('response') or {}).get('execution_metadata',{}).get('reported_cost_usd')
        if value is not None:
            amount=Decimal(str(value))
            if not amount.is_finite() or amount<0:raise ValueError('Invalid target-reported cost')
            target_costs.append(amount)
    rates={k:Decimal(str(v)) for k,v in run['cost_rate_assumptions_usd_per_token'].items()}
    target_estimate=sum((Decimal(x['input_tokens'])*rates['target_input']+Decimal(x['output_tokens'])*rates['target_output'] for x in targets),Decimal(0))
    grader_estimate=sum((Decimal(x['usage']['prompt_tokens'])*rates['grader_input']+Decimal(x['usage']['completion_tokens'])*rates['grader_output'] for x in grades),Decimal(0))
    if target_estimate+grader_estimate!=Decimal(str(run['usage_based_cost_estimate_usd'])):
        raise ValueError('Token estimate does not reconcile with the saved total')
    return {'format':'four-strategy-cost-evidence-v2','run_sha256':hashlib.sha256(raw).hexdigest(),
            'target_receipts':len(targets),'target_cost_fields_present':len(target_costs),
            'target_provider_cost_sum_usd':str(sum(target_costs,Decimal(0))) if target_costs else None,
            'grader_receipts':len(grades),'grader_cost_fields_present':len(costs),
            'grader_provider_reported_sum_usd':str(sum(costs,Decimal(0))) if costs else None,
            'run_estimated_total_usd':str(run['usage_based_cost_estimate_usd']),
            'target_token_estimate_usd':str(target_estimate), 'grader_token_estimate_usd':str(grader_estimate),
            'mixed_target_estimate_plus_grader_report_usd':str(target_estimate+sum(costs,Decimal(0))) if len(costs)==len(grades) else None,
            'target_attempts':sum(x['provider_attempt_count'] for x in targets),
            'grader_attempts':sum(len(x.get('attempts',[])) for x in grades),
            'billing_reconciled':False,'model_called':False,
            'limitations':['Saved grader response cost is provider-reported and has not been reconciled to the bill.',
                'Target receipts do not include provider cost amounts; a mixed estimate plus reported grader cost is not an actual bill.',
                'The historical token estimate used different rate assumptions for target and grader; original values remain preserved.',
                'This study alone does not establish all spending against the shared experiment cap.']}


if __name__=='__main__':
    result=audit(Path('artifacts/local/phase4-c-openrouter-20261028-v7-four-arm/C-live.json'))
    path=Path('output/proposal-delivery/four-strategy-cost-evidence-2026-10-29-v2.json')
    with path.open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.write('\n')
