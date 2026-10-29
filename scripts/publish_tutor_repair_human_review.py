"""Publish only aggregate counts from the source-bound tutor human review."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'output/proposal-delivery/tutor-repair-human-review-summary-2026-10-28-v2.json'
target = ROOT / 'frontend/public/reports/tutor-repair-human-review-v2.json'
data = json.loads(source.read_text())
if data.get('format') != 'tutor-repair-human-review-summary-v1':
    raise ValueError('Unexpected tutor review summary format.')
conditions = data['conditions']
if len(conditions) != 3 or any(item['total'] != item['pass'] + item['fail'] or item['total'] != 8 for item in conditions):
    raise ValueError('Invalid paired condition counts.')
paired = data['paired_original_to_target']
if sum(paired.values()) != 8:
    raise ValueError('Paired result does not cover all eight cases.')
output = {
    'format': 'tutor-repair-human-review-public-v1',
    'experiment_id': data['experiment_id'],
    'scope': data['scope'],
    'human_confirmation': data['human_confirmation'],
    'agreement': data['agreement'],
    'conditions': conditions,
    'paired_original_to_target': paired,
    'automatic_vs_human': data['automatic_vs_human'],
    'source_summary_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'source_sha256': data['source_sha256'],
}
if target.exists():
    raise FileExistsError('Refusing to overwrite an existing public summary.')
target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
print(f'Published aggregate-only review summary: {target}')
