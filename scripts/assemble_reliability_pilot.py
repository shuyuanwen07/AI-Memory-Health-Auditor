"""Bind two returned human review drafts to the original unlabelled release.

Writes a local identifier-only pilot file, never a database label. The human
attestation is a declaration, not independently verified identity evidence.
Incomplete cases remain absent and therefore blocked by the readiness service.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def assemble(original, returned):
    if returned.get('dataset_id') != original['dataset_id'] or returned.get('dataset_version') != original['dataset_version']:
        raise ValueError('Returned review belongs to a different evidence release.')
    if returned.get('completed_independently_by_human') is not True:
        raise ValueError('Independent human completion has not been declared. AI drafts cannot be assembled as human labels.')
    reviewer = returned.get('reviewer', '').strip()
    if not reviewer or reviewer.startswith('Reviewer ') or 'replace' in reviewer.lower():
        raise ValueError('Provide the actual reviewer pseudonym rather than a placeholder.')
    expected_contexts = original['contexts']
    contexts = returned.get('contexts', {})
    if set(contexts) != set(expected_contexts):
        raise ValueError('Source history inventory changed.')
    for key in contexts:
        if contexts[key]['messages'] != expected_contexts[key]['messages']:
            raise ValueError('Source messages changed; labels must bind to the original evidence.')
    expected = {item['item_id']: item for item in original['items']}
    values = returned.get('items', [])
    if len(values) != len(expected) or {item['item_id'] for item in values} != set(expected):
        raise ValueError('Returned review has missing, duplicated or unknown item identities.')
    labels = []
    for item in values:
        reference = expected[item['item_id']]
        for field in ('task', 'scenario', 'allowed_labels'):
            if item.get(field) != reference[field]:
                raise ValueError(f'Changed item evidence: {item["item_id"]}.')
        evidence = dict(item.get('evidence', {}))
        evidence.pop('corrected_reference_behavior', None)
        baseline = dict(reference['evidence'])
        baseline.pop('corrected_reference_behavior', None)
        if evidence != baseline:
            raise ValueError(f'Changed item question, fact or response: {item["item_id"]}.')
        label = item.get('label')
        if label is None:
            continue
        if label not in reference['allowed_labels']:
            raise ValueError(f'Invalid label: {item["item_id"]}.')
        if not (item.get('decision_note') or '').strip():
            raise ValueError(f'A source-based decision note is required: {item["item_id"]}.')
        labels.append({'item_id': item['item_id'], 'task': item['task'], 'label': label})
    return {'annotator_id': reviewer, 'labels': labels}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('release_directory', type=Path)
    parser.add_argument('reviewer_a', type=Path)
    parser.add_argument('reviewer_b', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    original = json.loads((args.release_directory / 'reviewer-A.json').read_text())
    package = json.loads((args.release_directory / 'pilot-package-blank.json').read_text())
    annotations = [assemble(original, json.loads(path.read_text())) for path in (args.reviewer_a, args.reviewer_b)]
    if annotations[0]['annotator_id'] == annotations[1]['annotator_id']:
        raise ValueError('Two distinct independent reviewer pseudonyms are required.')
    package['annotators'] = annotations
    # Do not automatically turn agreement into adjudication. Preserve both originals.
    args.destination.write_text(json.dumps(package, ensure_ascii=False, indent=2) + '\n')
    print('Identifier-only labels assembled. Adjudication and readiness checks still required.')
