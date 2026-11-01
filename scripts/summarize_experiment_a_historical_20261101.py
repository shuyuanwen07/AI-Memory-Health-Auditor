"""Bind proposal Experiment A recall and discovery figures to the reviewed source."""
import collections
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'research/astra-ac2-20261101/experiment-a-historical-review.zip'
with zipfile.ZipFile(SOURCE) as archive:
    raw = archive.read('analysis.json')
analysis = json.loads(raw)
by_method = collections.defaultdict(list)
for row in analysis['conditions']:
    by_method[row['method']].append(row)
if len(by_method) != 3 or any(len(rows) != 3 for rows in by_method.values()):
    raise SystemExit('Expected three methods across three scenarios')
results = []
for method, rows in sorted(by_method.items()):
    if any(not row['complete_resolved_labels'] for row in rows):
        raise SystemExit('A response label is unresolved')
    tp = sum(row['tp'] for row in rows)
    fn = sum(row['fn'] for row in rows)
    fp = sum(row['fp'] for row in rows)
    tn = sum(row['tn'] for row in rows)
    known = set().union(*(set(row['known_defect_ids']) for row in rows))
    found = set().union(*(set(row['auditor_detected_defect_ids']) for row in rows))
    if not found <= known:
        raise SystemExit('Detected defect is not in the frozen inventory')
    results.append({'method': method, 'true_positive': tp, 'false_negative': fn,
                    'false_positive': fp, 'true_negative': tn,
                    'failure_recall': {'numerator': tp, 'denominator': tp + fn},
                    'inventoried_defects_detected': {'numerator': len(found), 'denominator': len(known)}})
out = ROOT / 'research/astra-ac2-20261101/experiment-a-historical-metrics.json'
payload = json.dumps({'source_sha256': hashlib.sha256(raw).hexdigest(),
    'scope': 'Three related synthetic histories, four questions per method per history; reported human checks of AI-assisted reviews.',
    'limitations': ['The inventory does not cover all observed failures.',
                    'Few human-pass cases and correlated scenarios limit generalisation.',
                    'These historical metrics do not establish performance on new scenarios.',
                    'Category coverage is not derived here: question validity needs separate evidence.'],
    'methods': results}, indent=2, ensure_ascii=False) + '\n'
out.write_text(payload)
(ROOT / 'frontend/src/data/experimentAHistoricalMetrics.json').write_text(payload)
print(out)
