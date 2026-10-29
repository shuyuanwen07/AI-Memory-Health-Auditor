"""Reconcile two AI reviews with the fixed, anonymised fresh-pilot packet."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'output/ac3-generated/b-candidate-fresh-history-pilot-20261030-v1'
PACKET = RUN / 'blind-review'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    blank = read(PACKET / 'reviewer-1.json')
    reviews = [read(PACKET / f'ai-review-{i}.json') for i in (1, 2)]
    mapping = read(RUN / 'private-review-mapping.json')
    ledger = read(RUN / 'ledger.json')
    assert ledger['protocol_sha256'] == digest(RUN / 'protocol.json')
    assert blank['ledger_sha256'] == digest(RUN / 'ledger.json')
    ids = [item['review_item_id'] for item in blank['items']]
    assert len(ids) == len(set(ids)) == len(mapping) == 16 and set(ids) == set(mapping)
    for review in reviews:
        assert review['completed_by_human'] is False and review['completed_by_ai'] is True
        assert review['ledger_sha256'] == blank['ledger_sha256']
        assert [item['review_item_id'] for item in review['items']] == ids
        for origin, item in zip(blank['items'], review['items']):
            assert {k: v for k, v in origin.items() if k != 'review'} == {k: v for k, v in item.items() if k != 'review'}
            assert item['review']['verdict'] in ('pass', 'fail', 'uncertain') and item['review']['note'].strip()
    rows = []
    for item, a, b in zip(blank['items'], *[r['items'] for r in reviews]):
        m = mapping[item['review_item_id']]
        assert hashlib.sha256(item['answer'].encode()).hexdigest() == m['answer_sha256']
        verdicts = [a['review']['verdict'], b['review']['verdict']]
        consensus = verdicts[0] if verdicts[0] == verdicts[1] and verdicts[0] != 'uncertain' else 'unresolved'
        rows.append({'case_id': m['case_id'], 'type': m['type'], 'arm': m['arm'], 'review_item_id': item['review_item_id'], 'reviewer_verdicts': verdicts, 'consensus': consensus})
    counts = {f'{kind}_{arm}': dict(Counter(row['consensus'] for row in rows if row['type'] == kind and row['arm'] == arm)) for kind in ('history', 'current') for arm in ('baseline', 'candidate')}
    assert all(sum(counts[f'{kind}_{arm}'].values()) == 4 for kind in ('history', 'current') for arm in ('baseline', 'candidate'))
    result = {'ledger_sha256': digest(RUN / 'ledger.json'), 'packet_sha256': digest(PACKET / 'reviewer-1.json'), 'reviews_sha256': [digest(PACKET / f'ai-review-{i}.json') for i in (1, 2)], 'counts': counts, 'rows': rows, 'limitations': 'Two AI-only reviews, human review pending. Four authored similar synthetic histories, isolated candidate injection, fixed sequential calls; not independent population validation.'}
    (RUN / 'ai-review-analysis.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(counts, indent=2))


if __name__ == '__main__':
    main()
