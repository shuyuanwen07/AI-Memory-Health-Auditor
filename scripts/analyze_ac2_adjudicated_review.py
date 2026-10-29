"""Validate source-bound AC2 human adjudication and summarize each frozen arm.

This analysis is descriptive: it does not change reviewer judgments, edit the
frozen study, call a model, or turn missing outputs into generated questions.
"""
import collections
import hashlib
import json
import random
from pathlib import Path


def read(path):
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def run():
    root = Path('output/proposal-delivery/ac1-ac2-b-return-20261029-v1')
    review_dir = Path('output/proposal-delivery/ac2-paired-review-2026-10-29-v1')
    protocol_path = Path('output/proposal-delivery/human-return-2026-10-29-ff607492/ac2-frozen.json')
    files = {
        'adjudication': root / '17_AC1_AC2_B修复后审核/最终裁定.json',
        'review1': root / 'normalized-user-confirmed/ac2-reviewer-1.json',
        'review2': root / 'normalized-user-confirmed/ac2-reviewer-2.json',
        'confirmation': root / 'normalized-user-confirmed/user-confirmation.json',
        'consensus': root / 'ac2-consensus-summary.json',
        'packet': review_dir / 'blind-packet.json',
        'allocation_key': review_dir / 'private/allocation-key.json',
        'protocol': protocol_path,
    }
    values, digests = {}, {}
    for name, path in files.items():
        values[name], digests[name] = read(path)
    adj = values['adjudication']['AC2']
    packet = values['packet']; allocation = values['allocation_key']; inputs = values['protocol']['inputs']
    canonical = lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    if hashlib.sha256(canonical(packet)).hexdigest() != allocation['packet_sha256']:
        raise ValueError('Blind packet differs from the source-bound allocation key')
    if values['consensus']['protocol_sha256'] != digests['protocol'] or values['consensus']['private_key_sha256'] != digests['allocation_key']:
        raise ValueError('Consensus was not calculated against this protocol and key')
    cases = {x['blind_id']: x for x in packet['cases']}
    labels = {x['blind_id']: x for x in adj['decisions']}
    mapping = allocation['items']
    reviewers = [{x['blind_id']: x for x in values[f'review{i}']['decisions']} for i in (1, 2)]
    if len(cases) != 228 or len(labels) != 228 or any(set(x) != set(cases) for x in [labels, mapping, *reviewers]):
        raise ValueError('Missing, duplicate or unexpected question IDs')
    for i, r in enumerate(reviewers, 1):
        if values[f'review{i}']['packet_sha256'] != allocation['packet_sha256']:
            raise ValueError('Reviewer packet binding changed')
        for ident, original in cases.items():
            for k in original:
                if r[ident].get(k) != original[k]:
                    raise ValueError(f'Reviewer {i} changed question source or content: {ident}')
    hids = inputs['history_ids']; scheduled = inputs['scheduled_questions_per_history']
    if len(hids) != 30 or scheduled != 4:
        raise ValueError('Unexpected frozen study schedule')
    result = {arm: collections.Counter() for arm in ('baseline', 'candidate')}
    per_history = {h: {arm: collections.Counter() for arm in result} for h in hids}
    disagreement_items = 0
    for ident, case in cases.items():
        label = labels[ident]; info = mapping[ident]; r1, r2 = (r[ident] for r in reviewers)
        arm, hid = info['condition'], info['history_id']
        if hid != case['history_id'] or label['history_id'] != hid or arm not in result:
            raise ValueError('History/arm mismatch')
        fields = ('grounded', 'structurally_executable')
        if any(label[f] not in ('valid', 'invalid', 'uncertain') for f in fields):
            raise ValueError('Invalid adjudication')
        different = any(r1[f] != r2[f] for f in fields)
        if type(label['was_disagreement']) is not bool or label['was_disagreement'] != different:
            raise ValueError('Adjudication disagreement flag does not reconcile')
        disagreement_items += different
        for field in fields:
            if r1[field] == r2[field] and label[field] != r1[field]:
                raise ValueError('Adjudication overrides an agreed judgment')
        state = ('valid' if all(label[f] == 'valid' for f in fields) else
                 'invalid' if any(label[f] == 'invalid' for f in fields) else 'uncertain')
        for c in (result[arm], per_history[hid][arm]):
            c['generated'] += 1; c[state] += 1
            c['grounded_' + label['grounded']] += 1
            c['structural_' + label['structurally_executable']] += 1
            if info['gate_status'] == 'accepted' and state == 'invalid':
                c['gate_accepted_human_invalid'] += 1
    if disagreement_items != adj['disagreements_adjudicated']:
        raise ValueError('Disagreement count mismatch')
    ledger = allocation['generation_ledger']
    for arm in result:
        for hid in hids:
            c = per_history[hid][arm]; row = ledger[arm][hid]
            if c['generated'] != row['generated_count'] or c['generated'] + row['missing_slots'] != scheduled:
                raise ValueError('Question count or missing slots mismatch')
            c['missing_slots'] = row['missing_slots']
            result[arm]['missing_slots'] += row['missing_slots']
        result[arm]['scheduled_slots'] = scheduled * len(hids)
        if result[arm]['generated'] + result[arm]['missing_slots'] != result[arm]['scheduled_slots']:
            raise ValueError('Study total mismatch')
    deltas = [(per_history[h]['candidate']['valid'] - per_history[h]['baseline']['valid']) / scheduled * 100 for h in hids]
    rng = random.Random(5623)
    samples = sorted(sum(rng.choice(deltas) for _ in hids) / len(hids) for _ in range(10000))
    out = {'format': 'ac2-adjudicated-paired-summary-v1', 'source_sha256': digests,
           'review_confirmation': values['confirmation']['user_statement'],
           'histories': len(hids), 'scheduled_per_arm': scheduled * len(hids),
           'arms': {arm: dict(v) for arm, v in result.items()},
           'mean_paired_valid_yield_delta_pp': sum(deltas) / len(deltas),
           'paired_history_bootstrap_95_percent_interval_pp': [samples[249], samples[9749]],
           'original_consensus_delta_pp': values['consensus']['mean_paired_delta_pp'],
           'reviewer_disagreement_questions_adjudicated': disagreement_items,
           'per_history': {h: {arm: dict(v) for arm, v in row.items()} for h, row in per_history.items()},
           'limitations': ['Thirty selected synthetic histories; paired-history bootstrap does not establish population generalization.',
                           'Reviewers used AI assistance; their reported independence is not independently authenticated.',
                           'The human adjudication is a separate view; original reviewer disagreements remain preserved.',
                           'The validity yield uses all scheduled slots; missing slots count as no valid output, not invalid generated questions.',
                           'Both frozen arms use the same current runtime; this is not a historical-container replay.'],
           'model_called': False}
    destination = root / 'ac2-adjudicated-paired-summary.json'
    with destination.open('x', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2); f.write('\n')
    print(json.dumps({'output': str(destination), 'arms': out['arms'], 'delta_pp': out['mean_paired_valid_yield_delta_pp'], 'interval_pp': out['paired_history_bootstrap_95_percent_interval_pp']}, ensure_ascii=False))


if __name__ == '__main__':
    run()
