"""Convert two completed fact-review packets into freeze-compatible declarations.

Never fills in human decisions. All source, plan and presented review content
must match exactly; every history must explicitly be accepted independently.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical_hash(value):
    return _hash(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def convert(suite_raw, plan_raw, packet_raws):
    suite, plan = json.loads(suite_raw), json.loads(plan_raw)
    if suite.get('format') != 'ac3-prospective-synthetic-inputs-v1' or len(suite.get('cases', [])) != 8:
        raise ValueError('Expected exactly eight frozen source histories')
    cases = {case['history_id']: case for case in suite['cases']}
    if len(cases) != 8 or set(plan.get('histories', {})) != set(cases):
        raise ValueError('The plan must contain the same eight distinct histories')
    if len(packet_raws) != 2:
        raise ValueError('Two separate independent reviews are required')
    plan_sha, source_sha = _canonical_hash(plan), _hash(suite_raw)
    results, labels, slots = [], set(), set()
    for raw in packet_raws:
        packet = json.loads(raw)
        if packet.get('format') != 'ac3-fact-human-review-packet-v1' or packet.get('fact_plan_sha256') != plan_sha or packet.get('source_input_sha256') != source_sha:
            raise ValueError('Review packet does not bind the exact source and fact plan')
        slot = packet.get('reviewer_slot')
        if type(slot) is not int or slot not in (1, 2) or slot in slots:
            raise ValueError('Review packets must use two distinct reviewer slots')
        slots.add(slot)
        declaration = packet.get('reviewer_declaration')
        if not isinstance(declaration, dict): raise ValueError('Reviewer declaration is required')
        label = declaration.get('reviewer_label')
        if not isinstance(label, str) or not label.strip(): raise ValueError('Reviewer identity is required')
        normal = label.strip().casefold()
        if normal in labels: raise ValueError('Reviewer identities must be different')
        labels.add(normal)
        if declaration.get('completed_by_human') is not True or declaration.get('completed_independently') is not True or type(declaration.get('used_ai_assistance')) is not bool:
            raise ValueError('Explicit human, independence and AI-assistance declarations are required')
        histories = packet.get('histories')
        if not isinstance(histories, list) or len(histories) != 8:
            raise ValueError('Review must cover all eight histories')
        ids = [h.get('history_id') for h in histories]
        if len(set(ids)) != 8 or set(ids) != set(cases):
            raise ValueError('Review history identities do not match the frozen source')
        for history in histories:
            hid = history['history_id']; source = cases[hid]; section = plan['histories'][hid]
            expected_questions = [{'test_id': q['test_id'], 'question': q['question'], 'expected_behavior': q['expected_behavior'], 'supporting_source_message_ids': q['supporting_source_message_ids']} for q in source['tests']]
            if history.get('source_messages') != source['source_messages'] or history.get('questions') != expected_questions or history.get('proposed_facts') != section['facts'] or history.get('proposed_relationships') != section['relationships']:
                raise ValueError('Reviewer was shown content different from the exact source or plan')
            review = history.get('review')
            if not isinstance(review, dict) or review.get('decision') != 'accept':
                raise ValueError('Every history must be accepted; revise and uncertain require a new reviewed plan')
        results.append({'reviewer_label': label.strip(), 'completed_by_human': declaration['completed_by_human'],
            'completed_independently': declaration['completed_independently'],
            'used_ai_assistance': declaration['used_ai_assistance'],
            'reviewed_fact_and_relation_semantics': True, 'fact_plan_sha256': plan_sha,
            'source_packet_sha256': _hash(raw), 'reviewer_slot': slot,
            'note': declaration.get('note', '')})
    return sorted(results, key=lambda x: x['reviewer_slot'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--review-1', type=Path, required=True)
    parser.add_argument('--review-2', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    inputs = [args.suite, args.plan, args.review_1, args.review_2]
    if any(p.is_symlink() or not p.is_file() for p in inputs):
        raise ValueError('Inputs must be regular non-symlink files')
    raw = [p.read_bytes() for p in inputs]
    converted = convert(raw[0], raw[1], raw[2:])
    # Confirm source files did not change during validation.
    if any(p.read_bytes() != data for p, data in zip(inputs, raw)):
        raise ValueError('A review source changed during conversion')
    args.output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    for i, review in enumerate(converted, 1):
        fd = os.open(args.output_dir / f'fact-review-{i}.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(review, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps({'review_count': len(converted), 'fact_plan_sha256': converted[0]['fact_plan_sha256'],
                      'review_sources_preserved': True, 'execution_authorized': False}))


if __name__ == '__main__': main()
