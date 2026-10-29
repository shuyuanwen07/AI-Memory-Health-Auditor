"""Apply the exploratory lexical warning to the previously reviewed 17 questions."""
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path
from ac2_reference_alignment_prototype_20261030 import warning

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'research/full-project-backup-20261029/ac1-ac2-review-return/AC1分阶段独立审核与AC2前瞻v2-完整结果-20261029.zip'
RUN = ROOT / 'output/proposal-delivery/ac2-v6-independent-prospective-product-20261029-v1'
OUT = ROOT / 'output/proposal-delivery/ac2-reference-alignment-development-20261030.json'


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    with zipfile.ZipFile(ARCHIVE) as archive:
        reviews = [json.loads(archive.read(next(n for n in archive.namelist() if n.endswith(f'questions-reviewer-{i}.json')))) for i in (1, 2)]
    mapping = json.loads((RUN / 'private-mapping.json').read_text())['items']
    by_id = [{x['blind_id']: x for x in review['items']} for review in reviews]
    assert set(by_id[0]) == set(by_id[1]) == set(mapping) and len(mapping) == 17
    histories = {h['history_id']: h for h in reviews[0]['histories']}
    rows = []
    for blind_id, first in by_id[0].items():
        second = by_id[1][blind_id]
        assert all(first[k] == second[k] for k in ('history_id', 'question', 'expected_behavior', 'supporting_provisional_memories'))
        history = histories[first['history_id']]
        source_by_id = {m['source_id']: m['text'] for m in history['messages']}
        source_ids = {s for mem in first['supporting_provisional_memories'] for s in mem['source_message_ids']}
        assert source_ids and source_ids <= source_by_id.keys()
        source = [source_by_id[s] for s in sorted(source_ids)]
        labels = [first['executability'], second['executability']]
        consensus = labels[0] if labels[0] == labels[1] and labels[0] in ('valid', 'invalid') else 'unresolved'
        rows.append({'blind_id': blind_id, 'prior_scope_status': mapping[blind_id]['after'], 'consensus': consensus, 'source_ids': sorted(source_ids), 'warning': warning(first['question'], source)})
    counts = Counter((r['consensus'], r['prior_scope_status'], bool(r['warning'])) for r in rows)
    result = {'archive_sha256': digest(ARCHIVE), 'mapping_sha256': digest(RUN / 'private-mapping.json'), 'prototype_sha256': digest(ROOT / 'scripts/ac2_reference_alignment_prototype_20261030.py'), 'counts': [{'consensus': k[0], 'prior_scope_status': k[1], 'prototype_warning': k[2], 'n': v} for k, v in sorted(counts.items())], 'rows': rows, 'limitations': 'Post-outcome heuristic informed by this same small, related synthetic sample. Advisory only; human review of AI-assisted labels was reported by the user, but independence is not established. No independent evaluation or product integration.'}
    OUT.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['counts'], indent=2))


if __name__ == '__main__':
    main()
