"""Reconcile the returned reviews without changing their original judgments."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'research/full-project-backup-20261029/ac1-ac2-review-return'
ARCHIVE = FOLDER / 'AC1分阶段独立审核与AC2前瞻v2-完整结果-20261029.zip'
ADJUDICATION = FOLDER / 'ac1-seven-human-adjudications.json'
OUTPUT = FOLDER / 'summary.json'

def main():
    digest = sha256(ARCHIVE.read_bytes()).hexdigest()
    decision = json.loads(ADJUDICATION.read_text())
    assert decision['source_archive_sha256'] == digest
    rulings = {item['id']: item['decision'] for item in decision['items']}
    assert len(rulings) == 7 and set(rulings.values()) == {'partial'}
    with ZipFile(ARCHIVE) as archive:
        def read(name):
            return json.loads(archive.read(name))
        mappings = [read(f'AC1分阶段审核/审核者{i}/02-extraction-mapping.json') for i in (1, 2)]
        qs = [read(f'AC2前瞻v2已有审核/审核者{i}/questions-reviewer-{i}.json') for i in (1, 2)]
    indexed = []
    for mapping in mappings:
        facts = {f['fact_id']: f['coverage'] for h in mapping['histories'] for f in h['reference_facts']}
        edges = {e['pair_id']: e['output_status'] for h in mapping['histories'] for e in h['source_relation_pairs']}
        assert len(mapping['histories']) == 27 and len(facts) == 216 and len(edges) == 54
        indexed.append((facts, edges))
    result = []
    for kind in range(2):
        left, right = indexed[0][kind], indexed[1][kind]
        assert left.keys() == right.keys()
        disagreements = {k for k in left if left[k] != right[k]}
        expected = {i['id'] for i in decision['items'] if i['kind'] == ('fact_coverage' if kind == 0 else 'selected_relation')}
        assert disagreements == expected
        result.append(dict(Counter(rulings[k] if k in disagreements else left[k] for k in left)))
    qindex = [{item['blind_id']: item for item in review['items']} for review in qs]
    assert len(qindex[0]) == 17 and qindex[0].keys() == qindex[1].keys()
    metrics = {}
    for field in ('grounding', 'executability', 'reference_answer_validity'):
        counts = Counter()
        for key in qindex[0]:
            a, b = (item[key][field] for item in qindex)
            assert a in ('valid', 'invalid', 'uncertain') and b in ('valid', 'invalid', 'uncertain')
            counts[a if a == b and a != 'uncertain' else 'unresolved'] += 1
        metrics[field] = dict(counts)
    summary = {'source_archive_sha256': digest, 'adjudication_sha256': sha256(ADJUDICATION.read_bytes()).hexdigest(),
               'ac1': {'histories': 27, 'facts': result[0], 'relationships': result[1]},
               'ac2': {'questions': 17, 'metrics': metrics},
               'provenance': 'AI-assisted review judgments individually checked by humans per user; independence of human review not established.'}
    OUTPUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
