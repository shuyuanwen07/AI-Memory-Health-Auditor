#!/usr/bin/env python3
"""Publish aggregate AC2 reviewer outcomes without exposing question-level evidence."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'output/proposal-delivery/ac2-generation-reviewed-summary-2026-10-28-v1.json'
raw = source.read_bytes()
summary = json.loads(raw)
assert summary['format'] == 'ac2-reference-generation-reviewed-summary-v1'
assert summary['ai_assistance'] == [True, True] and summary['generated_test_count'] == 120
for filename, digest in summary['evidence_sha256'].items():
    assert hashlib.sha256((root / filename).read_bytes()).hexdigest() == digest
results = {key: {name: summary['results'][key][name] for name in ('valid','invalid','unresolved','denominator')} for key in ('grounded','structurally_executable')}
for row in results.values():
    assert row['valid'] + row['invalid'] + row['unresolved'] == row['denominator'] == 120
out = {'format':'ac2-reviewed-aggregate-v1','results':results,'source_sha256':hashlib.sha256(raw).hexdigest()}
(root / 'frontend/public/reports/ac2-reviewed-aggregate-v1.json').write_text(json.dumps(out, indent=2)+'\n')
