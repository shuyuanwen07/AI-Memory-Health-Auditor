"""Post-outcome source-order development replay; AI labels are provisional."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from ac2_explicit_time_update_guard_20261030 import explicit_later_update

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'output/proposal-delivery/ac2-fact-slots-product-nine-development-20261029-v1/blind-review'
OUT = ROOT / 'output/proposal-delivery/ac2-time-update-warning-development-20261030.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    paths = [PACKET / f'ai-review-{i}.json' for i in (1, 2)]
    a, b = (json.loads(path.read_text()) for path in paths)
    assert a['completed_by_human'] is False and b['completed_by_human'] is False
    assert len(a['items']) == len(b['items']) == 24
    rows = []
    for x, y in zip(a['items'], b['items']):
        assert {k: v for k, v in x.items() if k != 'review'} == {k: v for k, v in y.items() if k != 'review'}
        messages = x['source_messages']
        timestamps = [m['timestamp'] for m in messages]
        assert all(timestamps) and timestamps == sorted(timestamps)
        ids = sorted({source for fact in x['cited_facts'] for source in fact['source_message_ids']})
        reason = explicit_later_update(messages, ids, chronology_trusted=True)
        left, right = x['review']['overall'], y['review']['overall']
        label = left if left == right and left in ('valid', 'invalid') else 'unresolved'
        rows.append({'review_item_id': x['review_item_id'], 'history_id': x['source_history_id'], 'ai_consensus': label, 'warning': reason})
    counts = Counter((row['ai_consensus'], bool(row['warning'])) for row in rows)
    result = {'ai_review_sha256': [sha(path) for path in paths], 'prototype_sha256': sha(ROOT / 'scripts/ac2_explicit_time_update_guard_20261030.py'), 'counts': [{'ai_consensus': k[0], 'warned': k[1], 'n': n} for k, n in sorted(counts.items())], 'rows': rows, 'limitations': 'Post-outcome heuristic designed using these examples. Two AI-only reviews, human review pending. Timestamp ordering is assumed from authored synthetic messages, not a general provenance guarantee. Matching times and replacement words cannot establish that they describe the same event. This is advisory only; lack of warning does not imply validity.'}
    OUT.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['counts'], indent=2))


if __name__ == '__main__':
    main()
