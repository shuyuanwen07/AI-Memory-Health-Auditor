"""Bound selected AC2 yield if the flagged prior valid labels are reconsidered.

This changes no labels and does not estimate the chance any decision changes.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'output/proposal-delivery'
CONCERN = ROOT / 'ac2-prior-valid-scope-concern-20261030.json'
RESULT = ROOT / 'ac1-ac2-b-return-20261029-v1/ac2-adjudicated-paired-summary.json'
ADJUDICATION = ROOT / 'ac1-ac2-b-return-20261029-v1/17_AC1_AC2_B修复后审核/最终裁定.json'
DEST = ROOT / 'ac2-scope-concern-sensitivity-20261030.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    concerns = json.loads(CONCERN.read_text())['items']
    original = json.loads(RESULT.read_text())
    decisions = {x['blind_id']: x for x in json.loads(ADJUDICATION.read_text())['AC2']['decisions']}
    assert len(concerns) == 10 and len({x['blind_id'] for x in concerns}) == 10
    assert all(decisions[x['blind_id']]['grounded'] == decisions[x['blind_id']]['structurally_executable'] == 'valid' for x in concerns)
    counts = Counter(x['arm'] for x in concerns)
    assert set(counts) == {'baseline', 'candidate'}
    arms = original['arms']
    assert arms['baseline']['scheduled_slots'] == arms['candidate']['scheduled_slots'] == 120
    b, c = arms['baseline']['valid'], arms['candidate']['valid']
    low_b, low_c = b-counts['baseline'], c-counts['candidate']
    output = {'inputs_sha256': {'concerns': digest(CONCERN), 'summary': digest(RESULT), 'adjudication': digest(ADJUDICATION)}, 'original_valid': {'baseline': b, 'candidate': c}, 'flagged_per_arm': dict(counts), 'scheduled_per_arm': 120, 'if_all_flagged_reclassified_invalid': {'baseline_valid': low_b, 'candidate_valid': low_c, 'candidate_minus_baseline_pp': (low_c-low_b)/120*100}, 'bounds_if_any_flagged_may_be_reclassified_invalid': {'baseline_valid_min': low_b, 'baseline_valid_max': b, 'candidate_valid_min': low_c, 'candidate_valid_max': c, 'candidate_minus_baseline_min_pp': (low_c-b)/120*100, 'candidate_minus_baseline_max_pp': (c-low_b)/120*100}, 'limitations': 'Hypothetical bounds only, not a revised adjudication or confidence interval. Counts hold every other question fixed and assume flagged questions can only change from valid to invalid. The 10 items share three synthetic histories and may not change independently. Prior labels remain authoritative until a source-based review is completed.'}
    DEST.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
