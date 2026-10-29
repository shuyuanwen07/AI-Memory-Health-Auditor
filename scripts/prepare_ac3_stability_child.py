"""Derive a separate, predeclared repeat suite from a frozen primary suite.

No model call, database write or new human judgment is made. The child only
inherits exact primary source material and reviewed fact plans for 10 histories.
"""
import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ac3_stability import canonical_sha, validate_plan
from scripts.ac3_fixed_suite_adapter import compile_mock, sha


def _time(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None: raise ValueError('Timezone required.')
    return result.astimezone(timezone.utc)


def derive_child(parent, parent_path, parent_sha, child_frozen_at):
    if parent.get('study_role')!='primary_validation' or parent.get('format')!='ac3-prospective-frozen-suite-v1':
        raise ValueError('A frozen expanded primary validation suite is required.')
    if _time(child_frozen_at)<_time(parent['frozen_at_utc']):
        raise ValueError('Repeat suite cannot precede the primary freeze.')
    protocol=parent['protocol']; stability=protocol.get('stability_plan')
    ids=validate_plan(stability,parent['suite'])
    if parent.get('stability_plan_sha256')!=canonical_sha(stability):
        raise ValueError('Primary freeze does not bind its predeclared repeat plan.')
    parent_facts=parent.get('reviewed_fact_plan',{}).get('histories',{})
    if not set(ids)<=set(parent_facts): raise ValueError('Selected histories lack reviewed fact plans.')
    planned=stability.get('budget',{});original=protocol['budget']
    primary_max=Decimal(str(original['max_new_estimated_usd']))
    repeat_max=Decimal(str(planned.get('max_new_estimated_usd')))
    reserve=Decimal(str(planned.get('per_request_reservation_usd')))
    prior=Decimal(str(original['existing_estimated_usd']));cap=Decimal(str(original['cumulative_cap_usd']))
    if (not all(v.is_finite() for v in (primary_max,repeat_max,reserve,prior,cap)) or
            min(primary_max,repeat_max,reserve)<=0 or prior<0 or reserve*40>repeat_max or
            prior+primary_max+repeat_max>cap):
        raise ValueError('Primary and repeat reservations exceed their combined planning cap.')
    suite=copy.deepcopy(parent['suite'])
    suite['cases']=[c for c in suite['cases'] if c['history_id'] in set(ids)]
    fact_plan=copy.deepcopy(parent['reviewed_fact_plan'])
    fact_plan['histories']={history:fact_plan['histories'][history] for history in ids}
    child_protocol=copy.deepcopy(protocol)
    child_protocol['budget']={'existing_estimated_usd':float(prior+primary_max),
        'max_new_estimated_usd':float(repeat_max),'cumulative_cap_usd':float(cap),
        'per_request_reservation_usd':float(reserve),
        'allocation_note':'The existing estimate reserves the full primary planning allowance; it is not a claim of actual primary spend.'}
    return {'format':'ac3-stability-derived-suite-v1','study_role':'stability_repeat',
            'frozen_at_utc':child_frozen_at,'parent_frozen_path':str(Path(parent_path).resolve()),
            'parent_frozen_sha256':parent_sha,'stability_plan_sha256':canonical_sha(stability),
            'suite':suite,'reviewed_fact_plan':fact_plan,'protocol':child_protocol,
            'execution_supported':False,'model_called':False,'results_observed':False,
            'provenance':'Exact selected source and fact subset inherited from the primary human-reviewed suite; no additional human review is claimed.',
            'budget_notice':'Separate planning allocation; provider charges can differ. Primary and repeat caps together remain within the combined plan.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--primary-frozen',required=True,type=Path);p.add_argument('--primary-sha256',required=True)
    p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.primary_frozen.is_symlink() or not a.primary_frozen.is_file(): raise ValueError('Primary suite must be a regular file.')
    raw=a.primary_frozen.read_bytes()
    if sha(raw)!=a.primary_sha256: raise ValueError('Primary suite digest differs.')
    parent=json.loads(raw)
    reserve=parent['protocol']['budget'].get('per_request_reservation_usd')
    compile_mock(a.primary_frozen,a.primary_sha256,str(reserve))
    child=derive_child(parent,a.primary_frozen,a.primary_sha256,datetime.now(timezone.utc).isoformat())
    if sha(a.primary_frozen.read_bytes())!=a.primary_sha256: raise ValueError('Primary suite changed during derivation.')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w',encoding='utf8') as stream:json.dump(child,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'output':str(a.output),'sha256':sha(a.output.read_bytes()),'histories':10,'questions':40,
                      'model_called':False,'new_human_review_claimed':False}))


if __name__=='__main__':main()
