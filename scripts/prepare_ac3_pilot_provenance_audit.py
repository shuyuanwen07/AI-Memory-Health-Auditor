"""Recompute a pilot and document its provenance, without creating human attestation.

The review is an automated Codex source check. It does not verify reviewer
identity, independent completion, or unobserved exposure to automated scores.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / 'output/proposal-delivery/ac3-pilot-threshold-draft-2026-10-28-v2.json'
INDEPENDENCE = ROOT / 'output/proposal-delivery/human-review-independence-user-confirmation-2026-10-28.json'
SELECTION = ROOT / 'output/proposal-delivery/ac3-threshold-selection-user-delegated-2026-10-28.json'
BUNDLE = ROOT / 'output/proposal-delivery/live-current-source-repair-2026-10-28/experiment.bundle.json'
KEY = ROOT / 'output/proposal-delivery/live-current-source-repair-2026-10-28/human-review/review-key-private.json'
RECONCILIATION = ROOT / 'output/proposal-delivery/reconciliation-user-2026-10-28.json'
RECALCULATOR = ROOT / 'scripts/prepare_ac3_pilot_threshold_draft.py'


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_audit():
    files = {'pilot': PILOT, 'bundle': BUNDLE, 'key': KEY, 'reconciliation': RECONCILIATION,
             'independence_confirmation': INDEPENDENCE, 'user_threshold_selection': SELECTION,
             'recalculator': RECALCULATOR}
    if any(not p.is_file() or p.is_symlink() for p in files.values()):
        raise ValueError('Every pilot evidence source must be a regular, non-symlink file.')
    before = {name: _sha(path) for name, path in files.items()}
    pilot = json.loads(PILOT.read_text()); selection = json.loads(SELECTION.read_text())
    confirmation = json.loads(INDEPENDENCE.read_text()); reconciliation = json.loads(RECONCILIATION.read_text())
    if pilot.get('sources_sha256') != {name: before[name] for name in ('bundle', 'key', 'reconciliation')}:
        raise ValueError('Pilot sources do not match their recorded hashes.')
    if (selection.get('format') != 'ac3-user-selected-thresholds-v1' or
            selection.get('pilot_draft_sha256') != before['pilot'] or
            selection.get('held_out_results_seen') is not False or
            not selection.get('user_response') or not selection.get('provenance_limitations')):
        raise ValueError('Threshold selection does not bind the pilot and its limitations.')
    integrity = reconciliation.get('source_integrity', {})
    return_hashes = [integrity.get('reviewer_a_return_source_sha256'), integrity.get('reviewer_b_return_source_sha256')]
    if (confirmation.get('format') != 'human-review-independence-confirmation-v1' or
            confirmation.get('applies_to_return_sha256') != return_hashes or
            confirmation.get('user_statement') != '彼此独立，且审核前未看自动评分'):
        raise ValueError('Later independence confirmation does not bind the same reviewer returns.')
    declarations = reconciliation.get('reviewer_declarations', {})
    first = declarations.get('reviewer_slot_1', {}).get('values', {})
    second = declarations.get('reviewer_slot_2', {}).get('values', {})
    if (first.get('completed_by_human') is not False or first.get('completed_independently') is not False or
            second.get('completed_by_human') is not False or second.get('completed_independently') is not False or
            second.get('has_seen_automated_or_aggregate_results') is not True or
            first.get('used_ai_assistance') is not True or second.get('used_ai_assistance') is not True):
        raise ValueError('Original review declarations differ from the recorded provenance conflict.')
    # Rebuild the pilot in an isolated temporary directory using the original
    # evidence and original arithmetic, without replacing the source document.
    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory) / 'recomputed.json'
        code = ('from pathlib import Path; import sys; '
                'from scripts import prepare_ac3_pilot_threshold_draft as m; '
                'm.DEST = Path(sys.argv[1]); m.main()')
        proc = subprocess.run([sys.executable, '-c', code, str(out)], cwd=ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            raise ValueError('Pilot recomputation failed: ' + proc.stderr[-1000:])
        recalculated = json.loads(out.read_text())
    for key in ('pilot', 'metrics', 'proposed_thresholds', 'sources_sha256'):
        if recalculated.get(key) != pilot.get(key):
            raise ValueError(f'Pilot {key} differs from recomputed source evidence.')
    if any(_sha(path) != before[name] for name, path in files.items()):
        raise ValueError('Pilot sources changed during audit.')
    return {
        'format': 'ac3-pilot-provenance-audit-v1',
        'review_method': 'automated_source_check',
        'assessor': 'Codex (AI); no human provenance signature asserted',
        'human_attestation_created': False,
        'identity_or_independence_authenticated': False,
        'pilot_draft_sha256': before['pilot'],
        'user_threshold_selection_sha256': before['user_threshold_selection'],
        'sources': {name: {'path': str(path), 'sha256': before[name]} for name, path in files.items()},
        'source_check': 'Pilot counts, metrics, proposed thresholds and source digests independently recomputed from saved development data.',
        'pilot_limitations': 'One synthetic history and eight distinct questions; observations are correlated. Original returns say AI assistance, no independent human completion, and one says result exposure. User later reported distinct independent people and no prior automatic-score exposure. Both records remain; conflict and identities are not independently resolved.',
        'user_independence_statement': confirmation['user_statement'],
        'user_threshold_statement': selection['user_response'],
        'selection_basis': selection['selection_basis'],
        'selected_thresholds': selection['thresholds'],
        'held_out_results_seen_in_user_selection_record': selection['held_out_results_seen'],
        'acceptance_claim': 'None. Exploratory threshold provenance only; no evidence of held-out Auditor validity.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    value = build_audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps({'output': str(args.output), 'human_attestation_created': False,
                      'identity_or_independence_authenticated': False, 'model_called': False}))


if __name__ == '__main__':
    main()
