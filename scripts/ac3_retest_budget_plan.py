"""Read-only budget projection for the paired AC3 target questions.

This is not a dispatch ledger, price guarantee, or authorization. Candidate
scorer charges need their own frozen budget and durable accounting.
"""
import hashlib
import json
from decimal import Decimal, InvalidOperation
from scripts.ac3_retest_paired_freeze import compile_isolated


def combined_budget_preflight(*, prior_upper_bound_usd, target_reserved_usd, scorer_reserved_usd,
                              max_usd='0.40'):
    """Conservative arithmetic only; caller must independently verify all inputs."""
    if any(value is None for value in (prior_upper_bound_usd,target_reserved_usd,scorer_reserved_usd,max_usd)):
        return {'status':'unresolved','may_dispatch':False,
                'reason':'Prior costs, target reservations, scorer reservations and total cap must all be known.'}
    try:
        values=[]
        for value in (prior_upper_bound_usd,target_reserved_usd,scorer_reserved_usd,max_usd):
            if isinstance(value,bool): raise ValueError
            number=Decimal(str(value))
            if not number.is_finite() or number<0: raise ValueError
            values.append(number)
    except (InvalidOperation,ValueError) as exc:
        raise ValueError('Combined budget values must be finite non-negative amounts') from exc
    prior,target,scorer,cap=values
    if cap<=0 or cap>Decimal('0.40'):
        raise ValueError('Combined cap must be positive and at most US$0.40')
    total=prior+target+scorer
    return {'status':'within_planning_cap' if total<=cap else 'over_planning_cap',
            'prior_upper_bound_usd':str(prior),'target_reserved_usd':str(target),
            'scorer_reserved_usd':str(scorer),'max_usd':str(cap),'projected_total_usd':str(total),
            # Arithmetic alone never authorizes live requests.
            'may_dispatch':False,'limitation':'Amounts are supplied assumptions; provider billing is not guaranteed.'}


def budget_plan(frozen_raw, expected_sha256, source_raw, plan_raw, reviews, components, reservation):
    if hashlib.sha256(frozen_raw).hexdigest()!=expected_sha256:
        raise ValueError('Frozen paired study digest changed')
    frozen=json.loads(frozen_raw)
    stage=compile_isolated(frozen,source_raw,plan_raw,reviews,components)
    config=frozen['protocol']['budget']
    tracking_only=frozen['protocol'].get('budget_mode') == 'tracking_only'
    try:
        if isinstance(reservation,bool): raise ValueError
        per=Decimal(str(reservation));expected=Decimal(str(config['per_request_reservation_usd']))
        maximum=Decimal(str(config['max_usd']))
    except (ValueError,InvalidOperation) as exc:
        raise ValueError('Invalid budget') from exc
    if (not per.is_finite() or not maximum.is_finite() or per<=0 or maximum<=0
            or per!=expected or (not tracking_only and maximum>Decimal('0.40'))):
        raise ValueError('Reservation must match the frozen plan and the $0.40 cap')
    count=len(stage['test_ids'])
    if not tracking_only and per*count>maximum:
        raise ValueError('Planned target reservations exceed the study cap')
    return {'format':'ac3-paired-target-budget-plan-v1','frozen_sha256':expected_sha256,
            'eligible_test_ids':stage['test_ids'],'question_count':count,
            'max_usd':str(maximum),'reservation_per_target_usd':str(per),
            'planned_target_reservations_usd':str(per*count),'budget_mode':'tracking_only' if tracking_only else 'capped', 'model_called':False,
            'database_written':False,'execution_supported':False,
            'limitations':['Reservations are estimates, not a provider billing cap.',
                           'Scorer and prior-study costs are not included in this projection.',
                           'A combined budget, durable ledger and settlement are required before dispatch.']}
