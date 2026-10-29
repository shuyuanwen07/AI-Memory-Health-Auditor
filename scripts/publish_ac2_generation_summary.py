#!/usr/bin/env python3
"""Publish counts only from the independently generated AC2 review batch."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'output/proposal-delivery'
source = BASE / 'ac2-reference-generation-output-corrected-2026-10-28-v1.json'
raw = source.read_bytes()
data = json.loads(raw)
digest = hashlib.sha256(raw).hexdigest()
assert data['format'] == 'ac2-reference-generation-output-v1'
assert data['source_frozen_sha256'] == 'ec20077e07ead83925fa38bb67936d81773098e0762c1e4627ae3b94d8ff0f58'
histories = data['histories']
assert len(histories) == 30 and all(h['status'] in ('completed', 'rejected_by_product_gate') and len(h['tests']) == 4 for h in histories)
counts = {'accepted': 0, 'rejected': 0}
for history in histories:
    rejected = []
    for test in history['tests']:
        status = test['quality_assessment']['quality_status']
        assert status in counts
        counts[status] += 1
        if status == 'rejected': rejected.append(test['test']['test_id'])
    assert set(rejected) == set(history['rejected_test_ids'])
    assert (history['status'] == 'rejected_by_product_gate') == bool(rejected)
reviewers = []
for i in (1, 2):
    review = json.loads((BASE / f'ac2-generation-review-intake-2026-10-28/reviewer-{i}-user-confirmed.json').read_bytes())
    assert review['output_sha256'] == digest and len(review['histories']) == 30
    reviewers.append(bool(review['reviewer_declaration']['completed_by_human']))
out = {'format': 'ac2-generation-summary-v1', 'histories': len(histories), 'questions': sum(counts.values()),
       'automatic_question_gate': counts, 'automatic_suite_gate': {'accepted': sum(not h['rejected_test_ids'] for h in histories), 'rejected': sum(bool(h['rejected_test_ids']) for h in histories)},
       'reviewers_declared_complete': sum(reviewers), 'source_sha256': digest, 'corrected_offline': True}
target = ROOT / 'frontend/public/reports/ac2-generation-summary-v1.json'
target.write_text(json.dumps(out, indent=2) + '\n')
