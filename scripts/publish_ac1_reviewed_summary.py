#!/usr/bin/env python3
"""Publish source-bound aggregate AC1 review, without private review details."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'output/proposal-delivery/ac1-extraction-reviewed-summary-2026-10-28-v2.json'
raw = source.read_bytes()
review = json.loads(raw)
keys = ('supported_candidate_precision_decided', 'reference_fact_id_matched_coverage', 'relationship_precision_decided', 'reference_relationship_coverage_conservative')
assert review['primary_complete_histories'] == 29 and review['partial_histories'] == 1
assert review['ai_assistance'] == [True, True]
primary = {key: review[key] for key in keys}
sensitivity = {key: review['sensitivity_including_partial'][key] for key in keys}
for metrics in (primary, sensitivity):
    for value in metrics.values():
        assert 0 <= value['numerator'] <= value['denominator'] and value['denominator'] > 0
        assert abs(value['value'] - value['numerator']/value['denominator']) < 1e-9
summary = {'format':'ac1-reviewed-aggregate-v2', 'primary_histories':29, 'partial_histories':1,
           'primary':primary, 'sensitivity':sensitivity, 'source_sha256':hashlib.sha256(raw).hexdigest()}
(root / 'frontend/public/reports/ac1-reviewed-aggregate-v2.json').write_text(json.dumps(summary, indent=2)+'\n')
