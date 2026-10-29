"""Summarise AC1 adjudication without altering the original retrospective results.

The reference list is not known to be exhaustive and the later user-confirmed
adjudication was prepared with AI assistance after prior judgments were seen.
This cannot establish independent AC1 validity or population-level recall.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.publish_ac1_ac2_confirmation import build as validate_confirmation

INTAKE = ROOT / 'output/proposal-delivery/ac1-ac2-ai-review-intake-2026-10-28'
PACKET = ROOT / 'output/proposal-delivery/AC1-AC2-待裁定-2026-10-28.json'
RECON = ROOT / 'output/proposal-delivery/reconciliation-user-2026-10-28.json'
OUTPUT = ROOT / 'output/proposal-delivery/ac1-retrospective-adjudicated-2026-10-28.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(intake=INTAKE, packet=PACKET, recon=RECON):
    validate_confirmation(intake, packet)
    suggestion = json.loads((intake / 'received-ai-suggestions.json').read_text())
    reconciliation = json.loads(recon.read_text())
    if suggestion.get('来源汇总_sha256') != sha(recon) or reconciliation.get('format') != 'multi-reviewer-private-reconciliation-v1':
        raise ValueError('Adjudication must bind to the exact reviewed reconciliation')
    items = [x for x in reconciliation['items'] if x.get('queue_id') == 'proposal_ab_formal_review_216']
    if len({x['item_id'] for x in items}) != len(items):
        raise ValueError('Duplicate source item identity')
    kinds = {k: [x for x in items if x['identity_fields']['task']['kind'] == k] for k in ('candidate', 'reference')}
    if len(kinds['candidate']) != 27 or len(kinds['reference']) != 24:
        raise ValueError('Unexpected source item inventory')
    reviewed = {x['item_id']: x for x in suggestion['待裁定项目'] if x['criterion'] == 'AC1'}
    if len(reviewed) != 9:
        raise ValueError('Unexpected AC1 adjudication count')
    valid_ids, source_bound_ids = set(), set()
    for item in kinds['candidate']:
        judgments = item['primary_judgments']
        if len(judgments) != 1 or judgments[0]['field'] != 'valid':
            raise ValueError('Candidate judgments malformed')
        judge = judgments[0]
        if judge['comparison'] == 'agreed' and all(judge[f'reviewer_slot_{i}']['value'] is True for i in (1, 2)):
            valid_ids.add(item['item_id'])
        elif item['item_id'] in reviewed and reviewed[item['item_id']]['source']['task']['kind'] == 'candidate' and reviewed[item['item_id']]['human_final_decision'].get('valid') is True:
            valid_ids.add(item['item_id']); source_bound_ids.add(item['item_id'])
        else:
            raise ValueError('Unexpected unresolved candidate')
    if len(valid_ids) != 27 or len(source_bound_ids) != 6:
        raise ValueError('Unexpected candidate adjudication')
    full = partial = 0
    for item in kinds['reference']:
        slot1, slot2 = [item['actual_review_fields'][f'reviewer_slot_{i}'] for i in (1, 2)]
        if slot1.get('valid') is not True or slot2.get('valid') is not True:
            raise ValueError('Reference validity is not agreed')
        if slot1.get('coverage') == slot2.get('coverage') and slot1.get('coverage') in ('full', 'partial'):
            coverage = slot1['coverage']
            ids1, ids2 = slot1.get('candidate_ids'), slot2.get('candidate_ids')
            if not isinstance(ids1, list) or not isinstance(ids2, list) or set(ids1) != set(ids2):
                raise ValueError('Reference mapping is not agreed')
            ids = ids1
        elif item['item_id'] in reviewed and reviewed[item['item_id']]['source']['task']['kind'] == 'reference':
            final = reviewed[item['item_id']]['human_final_decision']
            coverage, ids = final.get('coverage'), final.get('candidate_ids')
        else:
            raise ValueError('Unexpected unresolved reference')
        if coverage not in ('full', 'partial') or not isinstance(ids, list) or not ids or not set(ids).issubset(valid_ids):
            raise ValueError('Reference mapping requires confirmed valid candidates')
        full += coverage == 'full'; partial += coverage == 'partial'
    if (full, partial) != (18, 6):
        raise ValueError('Unexpected confirmed reference coverage')
    return {'format': 'ac1-retrospective-adjudicated-v1',
      'scope': 'Three related synthetic histories; retrospective user-confirmed, AI-assisted adjudication',
      'candidate_valid': {'numerator': len(valid_ids), 'denominator': len(kinds['candidate']),
                          'agreed_original': 21, 'later_adjudicated': len(source_bound_ids)},
      'reference_coverage': {'full': full, 'partial': partial, 'total': len(kinds['reference'])},
      'limitations': ['Six candidate approvals require the original source context; they are not all standalone memories.',
        'The reference catalogue is not known to be exhaustive; full coverage among listed units is not population recall.',
        'Later adjudication was AI-assisted and exposed to previous judgments; independence and reviewer identity are not authenticated.',
        'These counts do not establish AC1 acceptance and do not replace the earlier preserved result.'],
      'source_sha256': {'reconciliation': sha(recon), 'suggestion': sha(intake / 'received-ai-suggestions.json'),
                        'user_confirmation': sha(intake / 'human-confirmation-record.json'), 'packet': sha(packet)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2); f.write('\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()
