"""Post-hoc cross-sample stress test of the advisory lexical prototype."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from ac2_reference_alignment_prototype_20261030 import warning

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'output/proposal-delivery/ac1-ac2-b-return-20261029-v1'
REVIEW = RUN / 'normalized-user-confirmed/ac2-reviewer-1.json'
REPLAY = RUN / 'product-scope-retrospective-replay-v3.json'
PROTOTYPE = ROOT / 'scripts/ac2_reference_alignment_prototype_20261030.py'
OUT = ROOT / 'output/proposal-delivery/ac2-reference-alignment-cross-sample-20261030.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    reviews = json.loads(REVIEW.read_text())['decisions']
    replay = json.loads(REPLAY.read_text())['items']
    verdicts = {item['blind_id']: item for item in replay}
    assert len(reviews) == len(verdicts) == 228
    assert {item['blind_id'] for item in reviews} == set(verdicts)
    rows = []
    for item in reviews:
        evidence = verdicts[item['blind_id']]
        texts = [message['text'] for message in item['source_messages']]
        assert texts and evidence['human_verdict'] in ('valid', 'invalid')
        rows.append({'blind_id': item['blind_id'], 'history_id': item['history_id'], 'arm': evidence['arm'], 'previous_review_label': evidence['human_verdict'], 'warning': warning(item['prompt'], texts)})
    counts = Counter((row['previous_review_label'], bool(row['warning'])) for row in rows)
    result = {'review_sha256': sha(REVIEW), 'replay_sha256': sha(REPLAY), 'prototype_sha256': sha(PROTOTYPE), 'counts': [{'label': k[0], 'warned': k[1], 'n': n} for k, n in sorted(counts.items())], 'rows': rows, 'limitations': 'Post-hoc stress test on earlier related synthetic histories, not a prospectively frozen validation. Full history text is supplied rather than only cited source spans; therefore this does not simulate the product check. The existing replay labels and user-reported human review are preserved. Repeated and paired questions are correlated. A warning requests review, not a correctness verdict.'}
    OUT.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['counts'], indent=2))


if __name__ == '__main__':
    main()
