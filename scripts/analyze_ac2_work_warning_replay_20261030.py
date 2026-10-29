"""Post-outcome diagnostic, not a product-path or independent validation."""
import hashlib
import json
from collections import Counter
from pathlib import Path

from app.test_generator.scope_review import scope_warning

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'output/proposal-delivery/ac1-ac2-b-return-20261029-v1'
REVIEW = RUN / 'normalized-user-confirmed/ac2-reviewer-1.json'
REPLAY = RUN / 'product-scope-retrospective-replay-v3.json'
SOURCE = ROOT / 'backend/app/test_generator/scope_review.py'
OUT = ROOT / 'output/proposal-delivery/ac2-work-warning-replay-20261030.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    items = json.loads(REVIEW.read_text())['decisions']
    previous = {item['blind_id']: item for item in json.loads(REPLAY.read_text())['items']}
    assert len(items) == len(previous) == 228
    assert {item['blind_id'] for item in items} == set(previous)
    rows = []
    for item in items:
        texts = [message['text'] for message in item['source_messages']]
        assert texts
        # The full history is used because the frozen study does not provide
        # question-level cited spans in this review file.
        reason = scope_warning(item['prompt'], 'accuracy', texts, source_complete=True)
        rows.append({'blind_id': item['blind_id'], 'history_id': item['history_id'],
                     'label': previous[item['blind_id']]['human_verdict'],
                     'working_arrangement_warning': bool(reason and 'does not explicitly describe a working arrangement' in reason)})
    counts = Counter((row['label'], row['working_arrangement_warning']) for row in rows)
    output = {'review_sha256': sha(REVIEW), 'replay_sha256': sha(REPLAY), 'implementation_sha256': sha(SOURCE),
              'counts': [{'label': key[0], 'warned': key[1], 'n': n} for key, n in sorted(counts.items())], 'rows': rows,
              'limitations': 'Post-outcome diagnostic on related synthetic histories. Full history replaces cited spans and accuracy is supplied as a probe, so this is not the product flow. Review warnings do not decide validity and do not establish population performance.'}
    OUT.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output['counts'], indent=2))


if __name__ == '__main__':
    main()
