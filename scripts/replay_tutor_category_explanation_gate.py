"""Offline exploratory category-only replay; no provider calls or frozen edits.

Human labels are used solely after predictions for evaluation. The same 13
reviewed failures informed development; results are not held-out validation.
"""
import collections
import importlib.util
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'output/proposal-delivery/live-current-source-repair-2026-10-28/experiment.bundle.json'
KEY = BUNDLE.parent / 'human-review/review-key-private.json'
HUMAN = ROOT / 'output/proposal-delivery/reconciliation-user-2026-10-28.json'
GATE = ROOT / 'backend/app/evaluator/category_explanation_gate.py'
OUTPUT = ROOT / 'output/proposal-delivery/tutor-category-gate-development-replay-2026-10-28.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    spec = importlib.util.spec_from_file_location('category_explanation_gate', GATE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    bundle, key, review = (json.loads(path.read_text()) for path in (BUNDLE, KEY, HUMAN))
    manifest = json.loads((KEY.parent / 'packet-manifest.json').read_text())
    if sha(BUNDLE) != key['bundle_sha256'] or sha(KEY) != manifest['files']['review-key-private.json']:
        raise ValueError('Saved bundle or blinded key has changed.')
    mapping = {row['response_id']: row['review_id'] for row in key['rows']}
    human = {row['item_id']: row for row in review['items'] if row['queue_id'] == 'current_source_repair_24'}
    if len(mapping) != 24 or set(mapping.values()) != set(human):
        raise ValueError('Unmatched or duplicate review identities.')
    predictions = []
    for run in bundle['runs']:
        for answer in run['answers']:
            if answer['outcome'] != 'fail':
                continue
            proposal = answer['observed_category']
            explanation = answer['failure_classification']['reason']
            # The prediction sees only the saved automatic category/reason.
            predicted = gate.supported_category(proposal, explanation)
            predictions.append((mapping[answer['response_id']], proposal, predicted))
    if len(predictions) != 13 or len({r[0] for r in predictions}) != 13:
        raise ValueError('Unexpected automatically decided failure count.')
    scores = collections.Counter()
    for item_id, original, candidate in predictions:
        fields = human[item_id]['actual_review_fields']
        left, right = (fields[f'reviewer_slot_{slot}']['failure_type'] for slot in (1, 2))
        if not left or left != right:
            raise ValueError('Do not treat a missing or disputed category as a reference.')
        scores['original_correct'] += original == left
        scores['original_incorrect'] += original != left
        scores['candidate_correct'] += candidate == left
        scores['candidate_incorrect'] += candidate is not None and candidate != left
        scores['candidate_unclassified'] += candidate is None
    result = {
        'format': 'tutor-category-gate-development-replay-v1',
        'scope': 'Development replay on the same 13 failures that motivated the gate; not independent held-out validation. No model requests; original results unchanged.',
        'original': {'correct': scores['original_correct'], 'incorrect': scores['original_incorrect'], 'total': len(predictions)},
        'candidate': {'correct': scores['candidate_correct'], 'incorrect': scores['candidate_incorrect'], 'unclassified': scores['candidate_unclassified'], 'total': len(predictions)},
        'interpretation': 'The gate only withholds unsupported or ambiguous category assignments. It does not repair them, change pass/fail, or prove better recall on unseen data.',
        'sha256': {'bundle': sha(BUNDLE), 'key': sha(KEY), 'review': sha(HUMAN), 'gate': sha(GATE)},
    }
    if OUTPUT.exists():
        raise FileExistsError('Refusing to overwrite previous development replay.')
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
