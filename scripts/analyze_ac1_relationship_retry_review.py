"""Verify source-bound returned reviews without resolving their disagreements."""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def analyze(templates, reviews):
    if len(templates) != 2 or len(reviews) != 2:
        raise ValueError('Two reviewer packets are required')
    labels, decisions = set(), []
    for template, review in zip(templates, reviews):
        declaration = review.get('reviewer_declaration', {})
        label = declaration.get('reviewer_label')
        if (not isinstance(label, str) or not label.strip() or label.strip().casefold() in labels
                or declaration.get('completed_by_human') is not True
                or declaration.get('completed_independently') is not True
                or type(declaration.get('used_ai_assistance')) is not bool):
            raise ValueError('Each reviewer must declare distinct independent human review')
        labels.add(label.strip().casefold())
        clean = copy.deepcopy(review)
        clean['reviewer_declaration'] = template['reviewer_declaration']
        for case in clean.get('cases', []):
            case['review'] = {'correct': None, 'reason': ''}
        if clean != template:
            raise ValueError('Frozen source, relationship or review identity changed')
        for case in review['cases']:
            value = case['review']
            if (set(value) != {'correct', 'reason'} or value['correct'] not in ('valid', 'invalid', 'uncertain')
                    or not isinstance(value['reason'], str) or not value['reason'].strip()):
                raise ValueError('Every decision needs an allowed value and a reason')
        decisions.append({case['case_id']: case['review'] for case in review['cases']})
    if set(decisions[0]) != set(decisions[1]) or len(decisions[0]) != 6:
        raise ValueError('Case identity is incomplete')
    cases = []
    for case_id in decisions[0]:
        a, b = decisions[0][case_id], decisions[1][case_id]
        verdict = a['correct'] if a['correct'] == b['correct'] and a['correct'] != 'uncertain' else 'unresolved'
        cases.append({'case_id': case_id, 'consensus': verdict, 'reviewer_1': a, 'reviewer_2': b})
    return {'format': 'ac1-retry-human-review-summary-v1', 'cases': cases,
            'limitations': ['Previously observed synthetic histories; not independent model validation.',
                'H04 is a gate question, not a successfully produced edge.',
                'Human reviewer identity and independence are user-reported, not authenticated.']}


def main():
    p = argparse.ArgumentParser()
    for name in ('review-1', 'review-2', 'confirmation', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    paths = [a.review_1, a.review_2]
    confirmation = json.loads(a.confirmation.read_bytes())
    expected = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    if (confirmation.get('format') != 'ac1-retry-human-confirmation-v1'
            or confirmation.get('confirmed_by') != 'user'
            or confirmation.get('completed_by_humans') is not True
            or confirmation.get('review_sha256') != expected):
        raise ValueError('User confirmation must bind the two exact returned reviews')
    root = Path('output/ac3-generated/ac1-relationship-retry-diagnostic-20261029-v1/human-review')
    templates = [json.loads((root / f'reviewer-{i}.json').read_bytes()) for i in (1, 2)]
    reviews = [json.loads(path.read_bytes()) for path in paths]
    result = analyze(templates, reviews)
    result['user_confirmation_sha256'] = hashlib.sha256(a.confirmation.read_bytes()).hexdigest()
    with a.output.open('x', encoding='utf8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
