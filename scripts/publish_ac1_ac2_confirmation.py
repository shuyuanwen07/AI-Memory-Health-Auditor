"""Publish aggregate AC1/AC2 counts from hash-bound human-confirmed AI suggestions."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTAKE = ROOT / 'output/proposal-delivery/ac1-ac2-ai-review-intake-2026-10-28'
PACKET = ROOT / 'output/proposal-delivery/AC1-AC2-待裁定-2026-10-28.json'
OUTPUT = ROOT / 'frontend/public/reports/ac1-ac2-confirmation-v1.json'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(intake: Path, packet: Path) -> dict:
    ai_path = intake / 'received-ai-suggestions.json'
    confirmation_path = intake / 'human-confirmation-record.json'
    summary_path = intake / 'intake-summary.json'
    document, confirmation, summary, original = (json.loads(p.read_text()) for p in (ai_path, confirmation_path, summary_path, packet))
    if (confirmation.get('format') != 'ac1-ac2-human-confirmation-v1'
            or confirmation.get('user_statement') != '已逐项人工核对并认可'
            or confirmation.get('applies_to_file_sha256') != sha(ai_path)
            or confirmation.get('prior_intake_summary_sha256') != sha(summary_path)
            or confirmation.get('source_packet_sha256') != sha(packet)
            or summary.get('source_hashes', {}).get('received_file') != sha(ai_path)
            or summary.get('source_hashes', {}).get('original_packet') != sha(packet)):
        raise ValueError('Human confirmation, AI file, intake summary and original packet are not hash-bound.')
    declaration = document.get('ai_adjudication_declaration', {})
    if (declaration.get('source_sha256') != sha(packet) or declaration.get('completed_by_human') is not False
            or declaration.get('human_confirmation_completed') is not False or declaration.get('used_ai_assistance') is not True
            or declaration.get('has_seen_both_reviewer_judgments') is not True):
        raise ValueError('Original preparation/exposure declaration does not match.')
    if document.get('format') != original.get('format') or len(document['待裁定项目']) != len(original['待裁定项目']) or len(document['遗漏事实差异']) != len(original['遗漏事实差异']):
        raise ValueError('Original adjudication item coverage changed.')
    for prior, current in zip(original['待裁定项目'], document['待裁定项目']):
        if {k: v for k, v in prior.items() if k != 'human_final_decision'} != {k: v for k, v in current.items() if k != 'human_final_decision'}:
            raise ValueError('Original item or reviewer judgments changed.')
    for prior, current in zip(original['遗漏事实差异'], document['遗漏事实差异']):
        ignored = {'human_final_decision', 'adjudicated_value'}
        if {k: v for k, v in prior.items() if k not in ignored} != {k: v for k, v in current.items() if k not in ignored}:
            raise ValueError('Original additional-fact comparison changed.')
    counts: Counter = Counter()
    for item in document['待裁定项目']:
        kind = item['source']['task']['kind']; decision = item['human_final_decision']
        if item['criterion'] == 'AC1' and kind == 'candidate' and decision.get('valid') is True:
            counts['ac1_valid'] += 1
        elif item['criterion'] == 'AC1' and kind == 'reference' and decision.get('coverage') == 'partial':
            counts['ac1_partial'] += 1
        elif item['criterion'] == 'AC2' and kind == 'question' and decision.get('valid') == 'uncertain':
            counts['ac2_uncertain'] += 1
        else:
            raise ValueError('Unexpected item kind or decision; refuse to publish stale counts.')
    counts['additional_fact_empty'] = sum(item['human_final_decision'].get('additional_missing_facts') == '' for item in document['遗漏事实差异'])
    if counts != {'ac1_valid': 6, 'ac1_partial': 3, 'ac2_uncertain': 13, 'additional_fact_empty': 3}:
        raise ValueError('The confirmed decision counts differ from the prepared intake.')
    expected = {'items': 22, 'candidate_valid_true': 6, 'reference_partial': 3, 'original_question_uncertain': 13, 'additional_missing_fact_empty': 3}
    if confirmation.get('counts') != expected:
        raise ValueError('Human confirmation counts differ from the item data.')
    return {
        'format': 'ac1-ac2-confirmation-v1',
        'scope': 'User-confirmed AI-assisted adjudication of previously reviewed items',
        'human_confirmation_user_reported': True,
        'ai_assisted': True, 'prior_reviewer_judgments_exposed': True,
        'independent_blind_adjudication': False,
        'items': 22, 'ac1_candidate_valid': counts['ac1_valid'],
        'ac1_reference_partial': counts['ac1_partial'], 'ac2_question_uncertain': counts['ac2_uncertain'],
        'additional_fact_empty_suggestions': counts['additional_fact_empty'],
        'confirmation_sha256': sha(confirmation_path), 'suggestion_sha256': sha(ai_path),
        'original_packet_sha256': sha(packet),
        'limitations': ['13 original questions remain uncertain and are not counted as passed.',
                        'An empty additional-facts judgment does not establish complete candidate coverage.',
                        'The AI-assisted review was exposed to prior judgments and is not an independent blind adjudication.'],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--intake', type=Path, default=INTAKE)
    parser.add_argument('--packet', type=Path, default=PACKET)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = build(args.intake, args.packet)
    tmp = args.output.with_suffix('.json.tmp')
    with tmp.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False); stream.write('\n')
    os.replace(tmp, args.output)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
