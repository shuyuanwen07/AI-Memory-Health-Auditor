"""Publish only aggregate counts from the verified, saved human-confirmation receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / 'output/proposal-delivery/ac4-human-confirmed-intake-2026-10-28'
RETURNS = ROOT / 'output/proposal-delivery/multi-review-complete-2026-10-28'
OUTPUT = ROOT / 'frontend/public/reports/ac4-intake-confirmation-v1.json'
INDEPENDENCE = ROOT / 'output/proposal-delivery/human-review-independence-user-confirmation-2026-10-28.json'
RECONCILIATION = ROOT / 'output/proposal-delivery/reconciliation-user-2026-10-28.json'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(receipt: Path, returns: Path, independence: Path, reconciliation: Path) -> dict:
    manifest_path = receipt / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('format') != 'ac4-human-confirmation-application-v1' or manifest.get('response_status') != 200 or manifest.get('model_calls') != 0:
        raise ValueError('Confirmation receipt format or execution does not match.')
    if sha(reconciliation) != manifest['reconciliation_sha256']:
        raise ValueError('Original reconciliation no longer matches confirmation receipt.')
    rec = json.loads(reconciliation.read_text())
    declaration = json.loads(independence.read_text())
    originals = [rec['source_integrity']['reviewer_a_return_source_sha256'], rec['source_integrity']['reviewer_b_return_source_sha256']]
    if declaration.get('format') != 'human-review-independence-confirmation-v1' or declaration.get('applies_to_return_sha256') != originals or declaration.get('user_statement') != '彼此独立，且审核前未看自动评分':
        raise ValueError('User independence confirmation does not bind the original returns.')
    for name in ('current-conversation.json', 'current-memories.json', 'confirmed-ground-truth-response.json'):
        if sha(receipt / name) != manifest['files'][name]:
            raise ValueError(f'Confirmation evidence changed: {name}')
    before = json.loads((receipt / 'current-memories.json').read_text())
    after = json.loads((receipt / 'confirmed-ground-truth-response.json').read_text())
    indexed = lambda values: {row['memory_id']: row for row in values}
    old, new = indexed(before), indexed(after)
    if len(before) != len(old) or len(after) != len(new) or set(old) != set(new) or len(old) != 14:
        raise ValueError('Candidate identity/coverage mismatch.')
    for key, prior in old.items():
        expected = dict(prior, status='confirmed')
        if prior['status'] != 'candidate' or new[key] != expected:
            raise ValueError('The confirmation changed more than the memory status.')
    relationships = sum(len(row['relationships']) for row in before)
    if relationships != 4 or manifest['confirmed_count'] != len(old):
        raise ValueError('Confirmed candidate or relationship count mismatch.')
    for number in (1, 2):
        path = returns / f'reviewer-{number}-with-previous-progress.json'
        if sha(path) != manifest['returns_sha256'][f'reviewer-{number}']:
            raise ValueError('Human-review return changed after confirmation.')
        doc = json.loads(path.read_text())
        queue = next(q for q in doc['queues'] if q['queue_id'] == 'current_source_intake_candidates_14')
        items = {item['candidate_id']: item for item in queue['items']}
        if set(items) != set(old) or len(queue['items']) != len(old):
            raise ValueError('Human-review candidate identities differ.')
        for key, item in items.items():
            review = item['review']
            if review['decision'] != 'accept' or item['proposed_memory'] != old[key]['canonical_value'] or set(item['source_message_ids']) != set(old[key]['source_message_ids']):
                raise ValueError('Human-review decision, value, or source differs.')
            rels = {rel['relationship_id']: rel for rel in review['relationship_review']}
            expected = {rel['relationship_id']: rel for rel in old[key]['relationships']}
            if set(rels) != set(expected) or any(rels[k]['decision'] != 'accept' or set(rels[k]['supporting_source_message_ids']) != set(expected[k]['evidence_message_ids']) for k in expected):
                raise ValueError('Human relationship review differs.')
    return {
        'format': 'ac4-intake-confirmation-v1',
        'scope': 'Saved synthetic intake; status at confirmation time',
        'candidate_count': len(old), 'human_confirmed_count': len(new),
        'reviewer_count_reported': 2, 'independence_user_reported': True,
        'original_declaration_conflict': True,
        'relationships_reviewed': relationships, 'target_audit_at_confirmation': False,
        'model_calls_for_confirmation': 0,
        'source_manifest_sha256': sha(manifest_path),
        'independence_confirmation_sha256': sha(independence),
        'limitations': ['User reports two independent reviewers with no prior automatic-score exposure; original file declarations contain conflicting statements.',
                        'Confirmation does not establish extraction accuracy or held-out Auditor validity.',
                        'No target audit existed for this intake at the time of confirmation.'],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, default=RECEIPT)
    parser.add_argument('--returns', type=Path, default=RETURNS)
    parser.add_argument('--independence', type=Path, default=INDEPENDENCE)
    parser.add_argument('--reconciliation', type=Path, default=RECONCILIATION)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = build(args.receipt, args.returns, args.independence, args.reconciliation)
    tmp = args.output.with_suffix('.json.tmp')
    with tmp.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    os.replace(tmp, args.output)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
