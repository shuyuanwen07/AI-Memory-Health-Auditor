#!/usr/bin/env python3
"""Recompute reviewed AC1 fullness and publish aggregate counts only."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'output/proposal-delivery/review-package-intake-2026-10-28/user-confirmed'
SUMMARY = ROOT / 'output/proposal-delivery/ac1-reference-fullness-reviewed-summary-2026-10-28.json'
OUTPUT = ROOT / 'frontend/public/reports/ac1-reference-fullness-summary-v1.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    record = json.loads((BASE / 'confirmation.json').read_bytes())
    if record.get('format') != 'review-package-user-confirmation-v1' or record.get('user_responses', {}).get('ac1') != '是，两人已独立核对':
        raise ValueError('The user confirmation for this review is missing')
    items = {x['slot']: x for x in record['items'] if x.get('kind') == 'ac1-fullness'}
    reviews = [BASE / f'ac1-fullness-reviewer-{i}.json' for i in (1, 2)]
    if set(items) != {1, 2} or any(digest(path) != items[i]['confirmed_sha256'] for i, path in enumerate(reviews, 1)):
        raise ValueError('Confirmed review hashes changed')
    with tempfile.TemporaryDirectory(prefix='ac1-fullness-verify-') as temporary:
        recomputed = Path(temporary) / 'result.json'
        subprocess.run([sys.executable, str(ROOT / 'scripts/import_ac1_reference_fullness_review.py'),
                        '--reviewer-1', str(reviews[0]), '--reviewer-2', str(reviews[1]), '--output', str(recomputed)],
                       check=True, capture_output=True, text=True)
        result = json.loads(recomputed.read_bytes())
    saved = json.loads(SUMMARY.read_bytes())
    if result != saved:
        raise ValueError('Saved summary differs from the independently recomputed evidence')
    return {'format': 'ac1-fullness-public-summary-v1',
            'complete_29_histories': result['complete_29_histories'],
            'including_partial_observed_output': result['including_partial_observed_output'],
            'limitations': result['limitations'],
            'review_provenance': 'User reports two independent human reviews; AI assisted; identities and independence not independently authenticated.',
            'source_sha256': digest(SUMMARY), 'confirmation_sha256': digest(BASE / 'confirmation.json')}


def main():
    result = build()
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Published {OUTPUT}')


if __name__ == '__main__':
    main()
