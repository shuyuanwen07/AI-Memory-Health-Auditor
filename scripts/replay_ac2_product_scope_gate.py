"""Replay the product scope advisory on the frozen, already-reviewed AC2 set.

This is observational and offline. It neither writes to the application nor
changes frozen research files. Only unanswered, generated questions with
source-bound memory mappings are evaluated; inability to match is unresolved.
The held-out status of these data is explicitly not claimed.
"""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from app.test_generator.rule_based import RuleBasedTestGenerator
from app.test_generator.frozen_scope_review_v3 import VERSION, scope_warning


ROOT = Path(__file__).resolve().parents[1]
FILES = {
    'packet': 'output/proposal-delivery/ac2-paired-review-2026-10-29-v1/blind-packet.json',
    'allocation': 'output/proposal-delivery/ac2-paired-review-2026-10-29-v1/private/allocation-key.json',
    'raw_output': 'output/proposal-delivery/human-return-2026-10-29-ff607492/ac2-output.json',
    'adjudication': 'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/17_AC1_AC2_B修复后审核/最终裁定.json',
    'confirmation': 'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/normalized-user-confirmed/user-confirmation.json',
    'adjudication_summary': 'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/ac2-adjudicated-paired-summary.json',
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def apply_gate(old_status, warning):
    """Match route behavior for an unreviewed, not-yet-executed question."""
    if old_status not in {'accepted', 'rejected', 'pending'}:
        raise ValueError('Unknown original gate state')
    if old_status == 'rejected':
        return 'rejected'
    return 'pending' if warning else old_status


def replay(values):
    packet, allocation, output, adjudication = (values[k] for k in ('packet', 'allocation', 'raw_output', 'adjudication'))
    if hashlib.sha256(canonical(packet)).hexdigest() != allocation['packet_sha256']:
        raise ValueError('Question packet differs from frozen allocation key')
    cases = {c['blind_id']: c for c in packet['cases']}
    mapping = allocation['items']
    adjudicated = adjudication['AC2']['decisions']
    labels = {r['blind_id']: r for r in adjudicated}
    if len(cases) != 228 or len(labels) != len(adjudicated) or set(cases) != set(mapping) or set(labels) != set(cases):
        raise ValueError('Missing or duplicated frozen question or adjudication')
    runs = {arm: {row['history_id']: row for row in rows} for arm, rows in output['conditions'].items()}
    groups = {arm: collections.Counter() for arm in ('baseline', 'candidate')}
    unmatched, evidence = [], []
    for blind_id, case in cases.items():
        meta, label = mapping[blind_id], labels[blind_id]
        arm, hid = meta['condition'], meta['history_id']
        if arm not in groups or case['history_id'] != hid or label['history_id'] != hid:
            raise ValueError('Frozen history or arm identity mismatch')
        try:
            record = runs[arm][hid]['tests'][meta['row_index']]
            test, assessment = record['test'], record['quality_assessment']
            if any(test[k] != case[k] for k in ('prompt', 'expected_behavior')):
                raise ValueError('Prompt or expected behavior differs from frozen raw output')
            old = assessment['quality_status']
            if old != meta['gate_status']:
                raise ValueError('Original quality gate differs from allocation')
            facts = case['reviewed_reference']['facts']
            by_id = {f['memory_id']: f for f in facts}
            if len(by_id) != len(facts):
                raise ValueError('Duplicate reference fact ID')
            source_by_id = {m['message_id']: m['text'] for m in case['source_messages'] if m['role'] == 'user'}
            if len(source_by_id) != len([m for m in case['source_messages'] if m['role'] == 'user']):
                raise ValueError('Duplicate source message ID')
            support_ids = test['supporting_memory_ids']
            if not isinstance(support_ids, list) or any(x not in by_id for x in support_ids):
                raise ValueError('No matching reviewed reference fact for support')
            source_complete = bool(support_ids) and all(by_id[x]['source_message_id'] in source_by_id for x in support_ids)
            topics = {f['memory_id']: RuleBasedTestGenerator._topic(SimpleNamespace(canonical_value=f['canonical_value'])) for f in facts}
            related_topic_count = max((sum(other == topics[x] for other in topics.values()) for x in support_ids), default=1)
            warning = scope_warning(test['prompt'], test['dimension'], list(source_by_id.values()),
                                    source_complete=source_complete, related_topic_count=related_topic_count)
            after = apply_gate(old, warning)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            unmatched.append({'blind_id': blind_id, 'reason': str(exc)})
            groups[arm]['unmatched'] += 1
            continue
        values_ = (label['grounded'], label['structurally_executable'])
        if any(x not in ('valid', 'invalid', 'uncertain') for x in values_):
            raise ValueError('Invalid adjudicated judgment')
        state = 'invalid' if 'invalid' in values_ else ('valid' if values_ == ('valid', 'valid') else 'uncertain')
        c = groups[arm]
        c['matched'] += 1
        c[f'human_{state}'] += 1
        c[f'{state}_old_{old}'] += 1
        c[f'{state}_after_{after}'] += 1
        if old == 'accepted' and after == 'pending':
            c[f'{state}_newly_pending'] += 1
        evidence.append({'blind_id': blind_id, 'history_id': hid, 'arm': arm, 'human_verdict': state,
                         'old_gate': old, 'after_scope_review': after, 'warning': warning})
    return {'format': 'ac2-product-scope-retrospective-replay-v1', 'scope_review_version': VERSION,
            'matched': len(evidence), 'unmatched': unmatched,
            'arms': {arm: dict(counts) for arm, counts in groups.items()}, 'items': evidence,
            'limitations': [
                'These 228 already-reviewed questions include cases used to develop scope rules; results are not independent validation.',
                'Replay reconstructs confirmed reference memories and their original source message IDs, not a live application run.',
                'The scope check is opt-in, flags questions for review, and does not prove unflagged questions valid.',
                'Unmatched items are excluded and explicitly retained; pending is not a pass or automatic rejection.',
                'Reviewed source references may be incomplete and human identity and independence are user reported.'
            ]}


def main():
    values, hashes = {}, {}
    for name, relative in FILES.items():
        raw = (ROOT / relative).read_bytes()
        values[name] = json.loads(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    confirmed_hashes = values['adjudication_summary']['source_sha256']
    for name, confirmed_name in (('adjudication', 'adjudication'), ('confirmation', 'confirmation'),
                                 ('packet', 'packet'), ('allocation', 'allocation_key')):
        if hashes[name] != confirmed_hashes[confirmed_name]:
            raise ValueError(f'{name} is not the source of the confirmed adjudication summary')
    result = replay(values)
    result['source_sha256'] = hashes
    result['scope_implementation_sha256'] = hashlib.sha256((ROOT / 'backend/app/test_generator/frozen_scope_review_v3.py').read_bytes()).hexdigest()
    result['topic_implementation_sha256'] = hashlib.sha256((ROOT / 'backend/app/test_generator/rule_based.py').read_bytes()).hexdigest()
    result['replay_implementation_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    out = ROOT / 'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/product-scope-retrospective-replay-v2.json'
    with out.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({'output': str(out), 'matched': result['matched'], 'unmatched': len(result['unmatched']), 'arms': result['arms']}))


if __name__ == '__main__':
    main()
