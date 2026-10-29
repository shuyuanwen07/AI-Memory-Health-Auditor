"""Compare paired scorer records against two reviews, without creating labels.

The caller must independently verify source, freeze and human-review provenance.
This arithmetic never claims acceptance or authorises an experiment.
"""
from collections import Counter
import random
from scripts.ac3_retest_paired_integrity import validate_paired_records
from app.services.ac3_metrics import calculate, history_bootstrap


def compare(test_ids, histories, answers, old_records, new_records, old_version, new_version, reviews):
    integrity = validate_paired_records(test_ids, answers, old_records, new_records, old_version, new_version)
    if not isinstance(histories, dict) or set(histories) != set(test_ids) or any(
            not isinstance(x, str) or not x for x in histories.values()):
        raise ValueError('Every test must bind to its history.')
    if not isinstance(reviews, list) or len(reviews) != 2 or any(
            not isinstance(r, dict) or set(r) != set(test_ids) for r in reviews):
        raise ValueError('Two complete review mappings are required.')
    old = {r['test_id']: r for r in old_records}
    new = {r['test_id']: r for r in new_records}
    answer_map = {r['test_id']: r for r in answers}
    views = {}
    for label, records in [('old', old), ('new', new)]:
        rows, scorer_errors = [], 0
        for ident in test_ids:
            if answer_map[ident]['status'] == 'target_error':
                continue
            entry = records[ident]
            if entry['verdict'] == 'error':
                scorer_errors += 1
            # Errors contribute to conservative missed-failure/abstention
            # denominators while remaining separately visible as errors.
            verdict = 'uncertain' if entry['verdict'] == 'error' else entry['verdict']
            rows.append({'test_id': ident, 'history_id': histories[ident], 'grounding': 'valid',
                         'human_1': reviews[0][ident], 'human_2': reviews[1][ident],
                         'automatic': {'verdict': verdict, 'failure_dimension': entry['failure_type']}})
        if rows:
            analysis = calculate(rows)
            reference = analysis['human_reference']
            coverage = analysis['metrics']['decided_coverage']['value']
            # Conditional coverage can look perfect when target answers are
            # missing. Keep it, but also measure against every frozen slot.
            decided = analysis['metrics']['decided_coverage']['numerator']
            scheduled_coverage = decided / len(test_ids)
            agreed_histories = {r['history_id'] for r in rows
                                if r['human_1'] == r['human_2'] and r['human_1']['verdict'] != 'uncertain'}
            checks = {'human_passes_at_least_30': reference['pass'] >= 30,
                      'human_failures_at_least_30': reference['fail'] >= 30,
                      'decided_coverage_at_least_80_percent': coverage is not None and coverage >= .8,
                      'scheduled_coverage_at_least_80_percent': scheduled_coverage >= .8,
                      'all_frozen_histories_have_agreed_reference': agreed_histories == set(histories.values())}
            views[label] = {'scoring_errors': scorer_errors, 'analysis': analysis,
                            'scheduled_decided_coverage': {'numerator':decided,'denominator':len(test_ids),'value':scheduled_coverage},
                            'histories_with_agreed_reference':len(agreed_histories),
                            'sample_checks': checks,
                            'evidence_sufficiency': 'minimums_met_descriptively' if all(checks.values()) else 'insufficient',
                            'history_bootstrap': history_bootstrap(rows)}
        else:
            views[label] = {'scoring_errors': scorer_errors, 'analysis': None,
                            'sample_checks': {}, 'evidence_sufficiency': 'insufficient',
                            'history_bootstrap': None}
    transitions = Counter((old[i]['verdict'], new[i]['verdict']) for i in test_ids
                          if answer_map[i]['status'] == 'answered')
    # Paired correctness compares only answers for which both human reviewers
    # agree on the complete verdict and failure category. Never turn an
    # uncertain human judgment or a scorer abstention into a correct outcome.
    paired = Counter()
    for ident in test_ids:
        if answer_map[ident]['status'] == 'target_error':
            paired['target_error'] += 1
            continue
        first, second = reviews[0][ident], reviews[1][ident]
        if first != second or first['verdict'] == 'uncertain':
            paired['human_unresolved'] += 1
            continue
        a, b = old[ident]['verdict'], new[ident]['verdict']
        if a not in ('pass', 'fail') or b not in ('pass', 'fail'):
            paired['one_or_both_scorers_undecided'] += 1
            continue
        correct_a, correct_b = a == first['verdict'], b == first['verdict']
        key = ('both_correct' if correct_a and correct_b else
               'new_only_correct' if correct_b else
               'old_only_correct' if correct_a else 'neither_correct')
        paired[key] += 1
    return {'format': 'ac3-paired-metrics-descriptive-v1', 'integrity': integrity,
            'old': views['old'], 'new': views['new'],
            'verdict_transitions': [{'old': a, 'new': b, 'count': n}
                                    for (a, b), n in sorted(transitions.items())],
            'paired_verdict_correctness': {key: paired[key] for key in
                ('both_correct','new_only_correct','old_only_correct','neither_correct',
                 'one_or_both_scorers_undecided','human_unresolved','target_error')},
            'limitations': 'Descriptive arithmetic only; verify independent human review and freeze separately. '
                           'Target errors are excluded from answer-level rates and reported in integrity; '
                           'scorer errors count as abstentions and are separately reported. Scheduled coverage '
                           'is an additional conservative completeness check, not a retroactive change to the original metric.'}


def paired_history_bootstrap(test_ids, histories, answers, old_records, new_records,
                             old_version, new_version, reviews, *, iterations=2000, seed=5623):
    """Resample whole histories once for both scorers and report new-minus-old.

    The output is descriptive of the observed synthetic histories, not a
    population confidence guarantee. Missing denominators are never zeroed.
    """
    compare(test_ids, histories, answers, old_records, new_records, old_version, new_version, reviews)
    if type(iterations) is not int or iterations < 100:
        raise ValueError('At least 100 bootstrap iterations are required.')
    groups = {}
    for ident in test_ids:
        groups.setdefault(histories[ident], []).append(ident)
    result = {'format': 'ac3-paired-history-bootstrap-v1', 'histories': len(groups),
              'iterations': iterations, 'seed': seed, 'intervals': {},
              'limitation': 'Whole observed synthetic histories are resampled jointly for both scorers; '
                            'this does not establish population generalisation.'}
    if len(groups) < 5:
        result['status'] = 'insufficient_histories'
        return result
    old = {r['test_id']: r for r in old_records}; new = {r['test_id']: r for r in new_records}
    target = {r['test_id']: r for r in answers}; names = sorted(groups); rng = random.Random(seed)
    metric_names = ('failure_recall_conservative', 'classification_accuracy_conservative',
                    'false_positive_rate_decided', 'decided_coverage')
    values = {name: [] for name in metric_names}
    for _ in range(iterations):
        paired_rows = [[], []]
        for draw in range(len(names)):
            history = rng.choice(names)
            for ident in groups[history]:
                if target[ident]['status'] != 'answered':
                    continue
                for index, record in enumerate((old[ident], new[ident])):
                    verdict = 'uncertain' if record['verdict'] == 'error' else record['verdict']
                    paired_rows[index].append({'test_id': f'{draw}:{ident}', 'history_id': f'{draw}:{history}',
                        'grounding': 'valid', 'human_1': reviews[0][ident], 'human_2': reviews[1][ident],
                        'automatic': {'verdict': verdict, 'failure_dimension': record['failure_type']}})
        if not paired_rows[0]:
            continue
        first, second = (calculate(rows)['metrics'] for rows in paired_rows)
        for name in metric_names:
            a, b = first[name]['value'], second[name]['value']
            if a is not None and b is not None:
                values[name].append(b-a)
    for name, sample in values.items():
        sample.sort(); count = len(sample)
        result['intervals'][name] = {'valid_iterations': count,
            'lower': sample[int((count-1)*.025)] if count >= iterations*.9 else None,
            'upper': sample[int((count-1)*.975)] if count >= iterations*.9 else None}
    result['status'] = 'descriptive'
    return result
