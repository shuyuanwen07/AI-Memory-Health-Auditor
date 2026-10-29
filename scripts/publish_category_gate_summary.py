"""Publish aggregate-only category pilot results without exposing answer text."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
paths = [root / 'output/proposal-delivery/tutor-category-gate-development-replay-2026-10-28.json',
         root / 'output/proposal-delivery/tutor-category-gate-earlier-source-evaluation-2026-10-28.json']
dev, check = (json.loads(path.read_text()) for path in paths)
assert dev['format'] == 'tutor-category-gate-development-replay-v1'
assert check['format'] == 'category-gate-earlier-source-evaluation-v1'
assert dev['original']['total'] == dev['candidate']['total']
assert dev['original']['correct'] + dev['original']['incorrect'] == dev['original']['total']
assert dev['candidate']['correct'] + dev['candidate']['incorrect'] + dev['candidate']['unclassified'] == dev['candidate']['total']
assert sum(check['original'].values()) == sum(check['candidate'].values())
result = {'format': 'category-gate-summary-v1', 'development': {'original': dev['original'], 'candidate': dev['candidate']},
          'historical_check': {'original': check['original'], 'candidate': check['candidate']},
          'deployed': False, 'prospective_held_out': False,
          'source_sha256': [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]}
(root / 'frontend/public/reports/category-gate-summary-v1.json').write_text(json.dumps(result, indent=2) + '\n')
print('Published category pilot aggregate')
