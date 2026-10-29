"""Predeclared repeat selection and descriptive paired automatic stability.

Repeats are a separate study, not additional independent primary cases or
human gold labels. This module makes no accuracy or population claim.
"""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone

VERDICTS = {'pass', 'fail', 'uncertain'}
DIMENSIONS = {'accuracy', 'freshness', 'conflict_resolution', 'appropriate_use'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical_sha(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def _time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None: raise ValueError('A timezone is required.')
    return result.astimezone(timezone.utc)


def validate_plan(plan, suite):
    """Enforce ten predeclared histories without consulting outcome data."""
    cases = suite.get('cases')
    if not isinstance(cases, list) or len(cases) != 30:
        raise ValueError('Stability plan requires the 30-history primary source.')
    ids = [case.get('history_id') for case in cases]
    if any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != 30:
        raise ValueError('Primary history identities must be unique.')
    expected = sorted(ids)[::3]
    if (not isinstance(plan, dict) or plan.get('format') != 'ac3-stability-plan-v1' or
            plan.get('selection_rule') != 'sorted_history_ids_every_third_from_first' or
            plan.get('selected_history_ids') != expected or len(expected) != 10 or
            plan.get('extra_repeats_per_question') != 1):
        raise ValueError('Stability history selection must be the predeclared ten-history rule.')
    if any(len(case.get('tests', [])) != 4 for case in cases if case['history_id'] in expected):
        raise ValueError('Each stability history must contribute four primary questions.')
    return expected


def _review(value):
    if not isinstance(value, dict) or set(value) != {'verdict', 'failure_dimension'}:
        raise ValueError('Automatic assessment must have verdict and failure dimension.')
    verdict, dimension = value['verdict'], value['failure_dimension']
    if verdict not in VERDICTS or (verdict != 'fail' and dimension is not None) or (verdict == 'fail' and dimension not in DIMENSIONS and dimension is not None):
        raise ValueError('Invalid automatic assessment.')
    return verdict, dimension


def _responses(run, expected, frozen_sha):
    if run.get('format') != 'ac3-heldout-run-export-v1' or run.get('frozen_sha256') != frozen_sha:
        raise ValueError('Run is not bound to its own frozen suite.')
    entries = run.get('responses')
    if not isinstance(entries, list) or len(entries) != len(expected):
        raise ValueError('Every selected question needs exactly one saved answer.')
    by_id = {}
    for row in entries:
        ident = row.get('test_id')
        if ident not in expected or ident in by_id or row.get('history_id') != expected[ident]:
            raise ValueError('Unknown, duplicated or mismatched answer identity.')
        answer = row.get('response')
        if not isinstance(answer, str) or not answer.strip() or sha(answer.encode()) != row.get('response_sha256'):
            raise ValueError('Saved answer digest is missing or inconsistent.')
        _review(row.get('automatic'))
        by_id[ident] = row
    return by_id


def summarize(primary_frozen, primary_sha, primary_run, primary_run_sha,
              child_frozen, child_sha, repeat_run, repeat_run_sha):
    """Compare automatic decisions on 120 original and 40 repeated answers."""
    plan = primary_frozen.get('protocol', {}).get('stability_plan')
    selected = validate_plan(plan, primary_frozen['suite'])
    primary_cases = primary_frozen['suite']['cases']
    expected_cases = [case for case in primary_cases if case['history_id'] in set(selected)]
    if (primary_frozen.get('study_role') != 'primary_validation' or
            child_frozen.get('study_role') != 'stability_repeat' or
            child_frozen.get('parent_frozen_sha256') != primary_sha or
            child_frozen.get('stability_plan_sha256') != canonical_sha(plan) or
            child_frozen.get('suite', {}).get('cases') != expected_cases):
        raise ValueError('Repeat suite differs from the predeclared primary source subset.')
    parent_facts = primary_frozen.get('reviewed_fact_plan', {}).get('histories', {})
    child_facts = child_frozen.get('reviewed_fact_plan', {}).get('histories', {})
    if (set(child_facts) != set(selected) or any(
            child_facts[history] != parent_facts.get(history) for history in selected)):
        raise ValueError('Repeat fact plans are not identical to the reviewed primary subset.')
    parent_cfg, child_cfg = primary_frozen['protocol'], child_frozen['protocol']
    if child_cfg.get('model_configuration') != parent_cfg.get('model_configuration'):
        raise ValueError('Repeat target configuration differs from primary.')
    if child_cfg.get('thresholds') != parent_cfg.get('thresholds'):
        raise ValueError('Repeat protocol thresholds differ from primary.')
    # Both studies must be prepared before any primary outcomes are observed.
    if (_time(child_frozen['frozen_at_utc']) < _time(primary_frozen['frozen_at_utc']) or
            _time(child_frozen['frozen_at_utc']) >= _time(primary_run['started_at_utc']) or
            _time(repeat_run['started_at_utc']) <= _time(child_frozen['frozen_at_utc'])):
        raise ValueError('Repeat plan was not frozen before the primary output or repeat began too early.')
    primary_expected = {q['test_id']:case['history_id'] for case in primary_cases for q in case['tests']}
    repeat_expected = {q['test_id']:case['history_id'] for case in expected_cases for q in case['tests']}
    if len(primary_expected) != 120 or len(repeat_expected) != 40:
        raise ValueError('Expected 120 unique primary questions and 40 repeat questions.')
    first = _responses(primary_run, primary_expected, primary_sha)
    second = _responses(repeat_run, repeat_expected, child_sha)
    transitions, per_history = Counter(), {}
    same_answer = same_verdict = both_decided = same_decided = 0
    for test_id, history_id in repeat_expected.items():
        before, after = first[test_id], second[test_id]
        a, b = before['automatic']['verdict'], after['automatic']['verdict']
        transitions[f'{a}_to_{b}'] += 1
        same_answer += before['response_sha256'] == after['response_sha256']
        same_verdict += a == b
        decided = a != 'uncertain' and b != 'uncertain'
        both_decided += decided
        same_decided += decided and a == b
        row = per_history.setdefault(history_id, {'pairs':0, 'same_verdict':0, 'both_decided':0, 'same_decided_verdict':0})
        row['pairs'] += 1; row['same_verdict'] += a == b
        row['both_decided'] += decided; row['same_decided_verdict'] += decided and a == b
    return {
        'format':'ac3-stability-descriptive-v1', 'primary_frozen_sha256':primary_sha,
        'primary_run_sha256':primary_run_sha, 'repeat_frozen_sha256':child_sha,
        'repeat_run_sha256':repeat_run_sha,
        'stability_plan_sha256':canonical_sha(plan), 'history_count':10, 'pairs':40,
        'repeat_ids':[{'repeat_id':f'R2:{ident}','original_test_id':ident,'history_id':history}
                      for ident,history in sorted(repeat_expected.items())],
        'same_exact_answer_count':same_answer, 'same_automatic_verdict_count':same_verdict,
        'both_decided_pairs':both_decided, 'same_decided_verdict_count':same_decided,
        'automatic_verdict_transitions':dict(sorted(transitions.items())), 'per_history':per_history,
        'human_reviewed_repeat_answers':False,
        'limitations':'Automatic-score stability only; repeated answers are not independent cases or human gold. Histories are authored synthetic data; provider randomness and external provenance are not independently authenticated.',
    }
