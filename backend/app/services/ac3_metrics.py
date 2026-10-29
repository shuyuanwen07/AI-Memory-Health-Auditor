"""AC3 held-out metric arithmetic, independent of storage and model transport.

This module does not authenticate input provenance, freeze a protocol, or
claim human independence. Callers must verify those separately. In particular,
the output is descriptive and cannot by itself establish AC3 acceptance.
"""
from collections import Counter
import random

DIMENSIONS = frozenset({'accuracy', 'freshness', 'conflict_resolution', 'appropriate_use'})
VERDICTS = frozenset({'pass', 'fail', 'uncertain'})


def _rate(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None}


def _review(value, *, automatic=False):
    if not isinstance(value, dict) or set(value) != {'verdict', 'failure_dimension'}:
        raise ValueError('A review must include exactly verdict and failure_dimension')
    verdict, dimension = value['verdict'], value['failure_dimension']
    if verdict not in VERDICTS or (verdict != 'fail' and dimension is not None):
        raise ValueError('Invalid verdict or failure dimension')
    if verdict == 'fail' and dimension not in DIMENSIONS and not (automatic and dimension is None):
        raise ValueError('A human failure must have a known dimension')
    return verdict, dimension


def calculate(rows):
    """Compare paired blind human decisions with saved automatic decisions.

    Each row has a unique test_id, source history, agreed grounding outcome,
    two independent human review objects and one automatic review object.
    An unresolved human judgment never becomes a pass or fail. Automatic
    abstentions on reference failures count as unclassified/missed in the
    conservative denominators and are separately visible.
    """
    if not isinstance(rows, list) or not rows:
        raise ValueError('A nonempty list of rows is required')
    seen, histories, reference_histories, counts = set(), set(), set(), Counter()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'test_id', 'history_id', 'grounding', 'human_1', 'human_2', 'automatic'}:
            raise ValueError('Invalid evaluation row')
        test_id, history_id, grounding = row['test_id'], row['history_id'], row['grounding']
        if not isinstance(test_id, str) or not test_id.strip() or test_id in seen or not isinstance(history_id, str) or not history_id.strip():
            raise ValueError('Duplicate or missing test or history ID')
        if grounding not in {'valid', 'invalid', 'uncertain'}:
            raise ValueError('Invalid grounding judgment')
        seen.add(test_id)
        h1, h2, auto = _review(row['human_1']), _review(row['human_2']), _review(row['automatic'], automatic=True)
        counts['grounding_' + grounding] += 1
        if grounding != 'valid':
            continue
        histories.add(history_id)
        if h1 != h2 or h1[0] == 'uncertain':
            counts['human_unresolved'] += 1
            counts['human_disagreement' if h1 != h2 else 'human_uncertain'] += 1
            continue
        reference, reference_dim = h1
        reference_histories.add(history_id)
        verdict, auto_dim = auto
        counts['human_' + reference] += 1
        counts['auto_' + verdict] += 1
        if verdict == 'uncertain':
            counts['abstain_reference_' + reference] += 1
        elif reference == 'fail' and verdict == 'fail':
            counts['tp'] += 1
            if auto_dim is None:
                counts['category_missing'] += 1
            elif auto_dim == reference_dim:
                counts['category_correct'] += 1
            else:
                counts['category_incorrect'] += 1
        elif reference == 'fail':
            counts['fn_decided'] += 1
        elif verdict == 'fail':
            counts['fp'] += 1
        else:
            counts['tn'] += 1
    reference_fail, reference_pass = counts['human_fail'], counts['human_pass']
    human_decided = reference_fail + reference_pass
    auto_decided = counts['tp'] + counts['fn_decided'] + counts['fp'] + counts['tn']
    attempted = sum(counts['grounding_' + x] for x in ('valid', 'invalid', 'uncertain'))
    return {
        'status': 'descriptive_not_acceptance', 'cases': attempted,
        'source_histories_with_valid_tests': len(histories),
        'source_histories_with_agreed_reference': len(reference_histories),
        'grounding': {'valid': counts['grounding_valid'], 'invalid': counts['grounding_invalid'], 'uncertain': counts['grounding_uncertain'],
                      'validity_conservative': _rate(counts['grounding_valid'], attempted)},
        'human_reference': {'pass': reference_pass, 'fail': reference_fail, 'unresolved': counts['human_unresolved'],
                            'disagreement': counts['human_disagreement'], 'uncertain': counts['human_uncertain']},
        'automatic': {'tp': counts['tp'], 'fp': counts['fp'], 'tn': counts['tn'], 'fn_decided': counts['fn_decided'],
                      'abstain_reference_fail': counts['abstain_reference_fail'], 'abstain_reference_pass': counts['abstain_reference_pass'],
                      'category_correct': counts['category_correct'], 'category_incorrect': counts['category_incorrect'],
                      'category_missing': counts['category_missing']},
        'metrics': {'decided_coverage': _rate(auto_decided, human_decided),
                    'failure_recall_conservative': _rate(counts['tp'], reference_fail),
                    'failure_recall_decided': _rate(counts['tp'], counts['tp'] + counts['fn_decided']),
                    'false_positive_rate_decided': _rate(counts['fp'], counts['fp'] + counts['tn']),
                    'false_positive_rate_lower_bound': _rate(counts['fp'], reference_pass),
                    'false_positive_rate_upper_bound': _rate(counts['fp'] + counts['abstain_reference_pass'], reference_pass),
                    'classification_accuracy_conservative': _rate(counts['category_correct'], counts['tp']),
                    'classification_accuracy_decided': _rate(counts['category_correct'], counts['category_correct'] + counts['category_incorrect'])},
        'notice': 'Human disagreements and uncertain judgments are unresolved. Lower-bound FPR excludes false-positive risk in abstentions. Conditional metrics exclude abstentions. Provenance, freeze timing and reviewer independence require separate verification.',
    }


def history_bootstrap(rows, *, iterations=2000, seed=5623):
    """Descriptive cluster bootstrap; histories are not assumed population-random.

    Resamples complete histories, not individual correlated answers. A metric
    is suppressed when too many samples have no denominator.
    """
    calculate(rows)  # validate identifiers and decisions before sampling
    if not isinstance(iterations, int) or iterations < 100:
        raise ValueError('At least 100 bootstrap iterations are required')
    groups = {}
    for row in rows:
        groups.setdefault(row['history_id'], []).append(row)
    names = ('failure_recall_conservative', 'classification_accuracy_conservative', 'false_positive_rate_decided')
    result = {'method': 'history_cluster_percentile_bootstrap', 'iterations': iterations, 'seed': seed,
              'histories': len(groups), 'intervals': {},
              'limitations': 'Resamples observed synthetic histories; intervals describe resampling variability, not generalisation to a population. Repeated questions within a history remain clustered.'}
    if len(groups) < 5:
        result['status'] = 'insufficient_histories'
        return result
    rng = random.Random(seed)
    histories = sorted(groups)
    samples = {name: [] for name in names}
    for _ in range(iterations):
        draw = []
        for draw_index in range(len(histories)):
            history = rng.choice(histories)
            for row in groups[history]:
                draw.append({**row, 'test_id': f"{draw_index}:{row['test_id']}", 'history_id': f'{draw_index}:{history}'})
        metrics = calculate(draw)['metrics']
        for name in names:
            value = metrics[name]['value']
            if value is not None:
                samples[name].append(value)
    for name, values in samples.items():
        values.sort()
        count = len(values)
        if count < iterations * .9:
            result['intervals'][name] = {'lower': None, 'upper': None, 'valid_iterations': count,
                                         'status': 'insufficient_nonzero_denominators'}
        else:
            result['intervals'][name] = {'lower': values[int((count - 1) * .025)],
                                         'upper': values[int((count - 1) * .975)],
                                         'valid_iterations': count, 'status': 'descriptive'}
    result['status'] = 'descriptive'
    return result
