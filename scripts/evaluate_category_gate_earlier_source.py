"""Evaluate frozen category gate on the preselected earlier-source archive.

Human review was performed before the candidate gate was frozen and the source
may have been viewed. This is a separate historical synthetic fixture, not a
prospective independent held-out study. The gate never receives human labels.
"""
import collections
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / 'output/proposal-delivery/tutor-category-gate-earlier-source-selection-2026-10-28.json'
OUTPUT = ROOT / 'output/proposal-delivery/tutor-category-gate-earlier-source-evaluation-2026-10-28.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    frozen = json.loads(SELECTION.read_text())
    if frozen['format'] != 'category-gate-earlier-source-selection-v1':
        raise ValueError('Unrecognised selection manifest.')
    for path, digest in frozen['files'].items():
        if sha(ROOT / path) != digest:
            raise ValueError(f'Frozen input changed: {path}')
    group = ROOT / 'output/proposal-delivery/live-repair-loop-2026-10-28'
    module_path = ROOT / 'backend/app/evaluator/category_explanation_gate.py'
    spec = importlib.util.spec_from_file_location('candidate_gate', module_path)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    ids = json.loads((group / 'review-key-private.json').read_text())['items']
    refs = {r['response_id']: r['review_item'] for r in ids}
    if len(ids) != 36 or len(refs) != 36:
        raise ValueError('Expected exactly 36 uniquely identified answers.')
    review = json.loads((ROOT / 'output/proposal-delivery/reconciliation-user-2026-10-28.json').read_text())
    reference = {r['item_id']: r for r in review['items'] if r['queue_id'] == 'earlier_repair_loop_36'}
    if set(reference) != set(refs.values()):
        raise ValueError('Review identifiers differ from the preselected archive.')
    predictions = []
    for path in sorted(group.glob('group-*.json')):
        for run in json.loads(path.read_text())['runs']:
            for answer in run['answers']:
                if answer['outcome'] == 'fail':
                    proposed = answer['observed_category']
                    predicted = gate.supported_category(proposed, answer['failure_classification']['reason'])
                    predictions.append((refs[answer['response_id']], proposed, predicted))
    counters = collections.Counter()
    for item_id, original, candidate in predictions:
        r = reference[item_id]
        left, right = (r['actual_review_fields'][f'reviewer_slot_{i}'] for i in (1, 2))
        if left['answer_correctness'] != 'Fail' or right['answer_correctness'] != 'Fail':
            counters['reference_nonfailure_or_uncertain'] += 1
            continue
        human_a, human_b = left['failure_category'], right['failure_category']
        if not human_a or human_a != human_b:
            counters['reference_missing_or_disputed_category'] += 1
            continue
        counters['eligible'] += 1
        counters['original_correct'] += original == human_a
        counters['original_incorrect'] += original != human_a
        counters['candidate_correct'] += candidate == human_a
        counters['candidate_incorrect'] += candidate is not None and candidate != human_a
        counters['candidate_unclassified'] += candidate is None
    output = {
        'format': 'category-gate-earlier-source-evaluation-v1',
        'selection_sha256': sha(SELECTION),
        'scope': frozen['scope'],
        'sample': {'answers': len(refs), 'automatically_flagged_failures': len(predictions), 'eligible_reviewed_failure_categories': counters['eligible'], 'reference_nonfailure_or_uncertain': counters['reference_nonfailure_or_uncertain'], 'reference_missing_or_disputed_category': counters['reference_missing_or_disputed_category']},
        'original': {'correct': counters['original_correct'], 'incorrect': counters['original_incorrect']},
        'candidate': {'correct': counters['candidate_correct'], 'incorrect': counters['candidate_incorrect'], 'unclassified': counters['candidate_unclassified']},
        'interpretation': 'Candidate only withholds unsupported or ambiguous labels, does not repair classification, and has not been tested prospectively on independent histories. The samples have repeated related cases.',
    }
    if OUTPUT.exists():
        raise FileExistsError('Refusing to overwrite previous evaluation.')
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
