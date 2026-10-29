"""Paired case-cluster bootstrap for previously confirmed four-strategy reviews.

The 30 selected cases are not a random population sample. Intervals describe
resampling those cases; they do not authenticate review or prove generality.
"""
import hashlib
import itertools
import json
import random
from pathlib import Path

from scripts.check_four_strategy_adjudication import check, TEMPLATES


def analyze(review1, review2, adjudication, confirmed, key, *, iterations=10000, seed=5623):
    checked = check(review1, review2, adjudication)
    confirmation = json.loads(confirmed)
    private = json.loads(key)
    if (key != (TEMPLATES / 'PRIVATE-v7-identity-key.json').read_bytes()
            or confirmation.get('publication_status') != 'user_confirmed_human_adjudication'
            or confirmation.get('adjudication_sha256') != hashlib.sha256(adjudication).hexdigest()
            or confirmation.get('review_sha256') != checked['review_sha256']
            or confirmation.get('counts') != checked['counts']
            or confirmation.get('by_strategy') != checked['by_strategy']):
        raise ValueError('Confirmed adjudication does not match validated source evidence')
    mapping = private['mapping']
    decisions = json.loads(adjudication)['decisions']
    ids = {row['item_id']: row for row in mapping}
    if len(mapping) != 360 or len(ids) != 360 or {r['item_id'] for r in decisions} != set(ids):
        raise ValueError('Answer identity mapping is incomplete or duplicated')
    strategies = sorted(checked['by_strategy'])
    cases = sorted({item['question_id'] for item in mapping})
    expected = set(itertools.product(cases, strategies, (1, 2, 3)))
    cells = {}
    for row in decisions:
        info = ids[row['item_id']]
        cell = (info['question_id'], info['strategy'], info['repetition'])
        if cell in cells:
            raise ValueError('Duplicate case, strategy and repetition')
        cells[cell] = row['final_judgment']
    if len(cases) != 30 or set(cells) != expected:
        raise ValueError('Expected 30 cases with three answers for each strategy')
    if type(iterations) is not int or iterations < 1000:
        raise ValueError('At least 1000 resamples are required')
    def rates(sample):
        result = {}
        for strategy in strategies:
            values = [cells[(case, strategy, repetition)] for case in sample for repetition in (1, 2, 3)]
            passed, failed = values.count('Pass'), values.count('Fail')
            result[strategy] = passed / (passed + failed) if passed + failed else None
        return result
    observed = rates(cases)
    pairs = list(itertools.combinations(strategies, 2))
    samples = {pair: [] for pair in pairs}
    rng = random.Random(seed)
    for _ in range(iterations):
        current = rates([rng.choice(cases) for _ in cases])
        for a, b in pairs:
            if current[a] is not None and current[b] is not None:
                samples[(a, b)].append(current[a] - current[b])
    result = []
    for a, b in pairs:
        values = sorted(samples[(a, b)])
        result.append({'strategy_a': a, 'strategy_b': b,
                       'observed_decided_rate_difference': observed[a] - observed[b],
                       'valid_resamples': len(values),
                       'bootstrap_lower': values[int((len(values)-1)*.025)] if len(values) >= iterations*.9 else None,
                       'bootstrap_upper': values[int((len(values)-1)*.975)] if len(values) >= iterations*.9 else None})
    return {'format': 'four-strategy-clustered-adjudication-v1',
            'adjudication_sha256': hashlib.sha256(adjudication).hexdigest(),
            'identity_key_sha256': hashlib.sha256(key).hexdigest(),
            'case_count': len(cases), 'answers_per_strategy': 90, 'iterations': iterations, 'seed': seed,
            'comparisons': result, 'model_called': False,
            'limitations': ['Cases are a selected LongMemEval subset, not a random population sample.',
                'Each bootstrap draw jointly resamples cases across all strategies and keeps their three repetitions.',
                'Rates exclude uncertain judgments; the number of decided answers differs by strategy.',
                'Intervals quantify variability under resampling these cases and do not address selection or review bias.']}


def main():
    root = Path('output/proposal-delivery')
    intake = root / 'human-return-2026-10-29-ff607492'
    result = analyze((intake/'four-reviewer-1-user-confirmed.json').read_bytes(),
                     (intake/'four-reviewer-2-user-confirmed.json').read_bytes(),
                     (intake/'four-final-adjudication-original.json').read_bytes(),
                     (intake/'four-adjudication-user-confirmed.json').read_bytes(),
                     (root/'multi-review-complete-2026-10-28/PRIVATE-v7-identity-key.json').read_bytes())
    output = root/'four-strategy-clustered-adjudication-2026-10-29.json'
    with output.open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write('\n')


if __name__ == '__main__':
    main()
