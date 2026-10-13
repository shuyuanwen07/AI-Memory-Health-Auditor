"""Validate frozen worksheet returns without promoting AI drafts to human gold."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DIMENSIONS = {'accuracy', 'freshness', 'conflict_resolution', 'appropriate_use', 'other', 'uncertain'}


def load_reference(path: Path) -> dict:
    match = re.search(r'<script id="payload" type="application/json">(.*?)</script>', path.read_text(), re.DOTALL)
    if not match:
        raise ValueError('The original worksheet payload is missing.')
    return json.loads(match.group(1))


def analyse(reference: dict, reviews: list[dict]) -> dict:
    if not reviews:
        raise ValueError('At least one returned review is required.')
    expected = {}
    for i in range(len(reference['material']['histories'])):
        for field in ('fact', 'relation', 'factnote'):
            expected[f'{field}-{i}'] = 'text'
    for section in ('ordinary', 'official'):
        for i in range(len(reference['material'][section + '_answers'])):
            for field in ('correct', 'valid', 'reference', 'dimension', 'note'):
                expected[f'{section}-{field}-{i}'] = 'dimension' if field == 'dimension' else 'text' if field == 'note' else 'decision'
    records = []
    for review in reviews:
        if review.get('schema') != 'three-independent-review-worksheet-v1':
            raise ValueError('Unsupported worksheet schema.')
        if review.get('material_sha256') != reference['material_sha256'] or review.get('material') != reference['material']:
            raise ValueError('Returned material differs from the frozen source evidence.')
        reviewer = review.get('reviewer')
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError('A reviewer identifier is required.')
        if any(row['reviewer'].strip().casefold() == reviewer.strip().casefold() for row in records):
            raise ValueError('Duplicate reviewer identifiers cannot represent independent reviews.')
        labels = review.get('labels')
        if not isinstance(labels, dict) or set(labels) - set(expected):
            raise ValueError('Missing label object or unknown worksheet fields.')
        missing = []
        for key, kind in expected.items():
            value = labels.get(key)
            if value is None or isinstance(value, str) and not value.strip():
                missing.append(key)
                continue
            valid = (isinstance(value, str) if kind == 'text' else
                     isinstance(value, str) and value in DIMENSIONS if kind == 'dimension' else
                     type(value) is bool or value == 'uncertain')
            if not valid:
                raise ValueError(f'Invalid label value: {key}.')
        records.append({'reviewer': reviewer, 'filled_fields': len(expected) - len(missing),
                        'expected_fields': len(expected), 'missing_fields': missing,
                        'declared_provenance': review.get('provenance', {}),
                        'provenance_notice': review.get('notice', '')})
    disagreements = []
    for key, kind in expected.items():
        if kind == 'text':
            continue
        values = {r['reviewer']: r['labels'].get(key) for r in reviews}
        decided = [v for v in values.values() if v is not None and not (isinstance(v, str) and not v.strip())]
        if len({(type(v).__name__, str(v)) for v in decided}) > 1:
            disagreements.append({'field': key, 'values': values, 'status': 'unresolved_source_review_required'})
    return {'material_sha256': reference['material_sha256'], 'reviews': records,
            'disagreements': disagreements, 'review_count': len(records),
            'formal_human_validation_ready': False,
            'notice': 'Development feedback only. Matching labels do not establish independent human validation. '
                      'Preserve provenance; do not import these returns as human gold. Missing reviewers and '
                      'disagreements require follow-up, and new held-out responses remain necessary.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('worksheet', type=Path)
    parser.add_argument('reviews', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = analyse(load_reference(args.worksheet), [json.loads(path.read_text()) for path in args.reviews])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
