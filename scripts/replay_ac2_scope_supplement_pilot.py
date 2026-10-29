"""Reconstruct and review the 33-question supplement pilot, offline only.

The original pilot saved generated questions, but did not execute or save
the product quality gate.  Consequently both gate results below are newly
reconstructed, not results from the historical collection or a live UI.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.schemas import AuditRun, Conversation, MemoryStatus
from app.test_generator.quality import RuleBasedTestQualityValidator
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.test_generator.scope_review import VERSION, scope_warning
from scripts.analyze_ac2_source_supplement_paired import analyze, canonical
from scripts.replay_ac2_product_scope_gate import apply_gate

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / 'output/proposal-delivery/ac2-source-supplement-paired-20261029-v1'
RETURNS = ROOT / 'output/proposal-delivery/ac2-source-supplement-review-return-20261029-v1'
SUPPLEMENT = ROOT / 'output/proposal-delivery/ac2-scope-guard-development-20261029/source_candidate_v1.py'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def signature(prompt, expected, evidence):
    """Preserve every support fact and exact source ID, not just question text."""
    return canonical({'prompt': prompt, 'expected_behavior': expected,
                      'provisional_evidence': sorted(evidence, key=lambda x: canonical(x))})


def replay(protocol, material, key, reviews, confirmation):
    if VERSION != 'source-scope-review-v3' or RuleBasedTestGenerator.VERSION != 'rule-based-v36':
        raise ValueError('Unexpected current product scope or frozen generator version')
    if sha((STUDY / 'protocol.json').read_bytes()) != key['protocol_sha256']:
        raise ValueError('Protocol differs from generated key')
    if sha(SUPPLEMENT.read_bytes()) != protocol['supplement_sha256']:
        raise ValueError('Frozen source supplement changed')
    # The experiment was frozen before the new opt-in API route existed.
    # That unrelated route intentionally differs; all other frozen app files
    # are required to match the recorded study before reconstructing tests.
    for name, digest in protocol['application_sha256'].items():
        if name == 'backend/app/api/routes.py':
            continue
        path = ROOT / name
        if not path.is_file() or sha(path.read_bytes()) != digest:
            raise ValueError(f'Frozen application source changed: {name}')
    for name, digest in protocol['source_sha256'].items():
        if sha((ROOT / name).read_bytes()) != digest:
            raise ValueError(f'Frozen pilot source changed: {name}')
    if (confirmation.get('format') != 'ac2-source-supplement-human-confirmation-v1'
            or confirmation.get('confirmed_by') != 'user'
            or confirmation.get('completed_by_humans') is not True):
        raise ValueError('Missing user-confirmed reviews')
    # Original analyzer checks both human declarations and immutable material.
    established = analyze(material, key, reviews)
    questions = {x['blind_id']: x for x in material['questions']}
    if len(questions) != 33 or set(questions) != set(key['identity']):
        raise ValueError('Pilot questions and allocations do not match')
    spec = importlib.util.spec_from_file_location('frozen_source_supplement', SUPPLEMENT)
    supplement = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(supplement)
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    tables = [{x['blind_id']: x for x in review['decisions']} for review in reviews]
    rows, unmatched = [], []
    counters = {'baseline': Counter(), 'supplement': Counter()}
    for history in material['histories']:
        hid = history['history_id']
        source_file = ROOT / f'datasets/assessment-candidates-v1/pilot/{hid}.json'
        source = json.loads(source_file.read_bytes())
        if history['source_messages'] != source['messages']:
            raise ValueError(f'Original source differs for {hid}')
        conversation = Conversation(conversation_id=hid, created_at=now, authorised=True,
                                    source_origin='synthetic', messages=source['messages'])
        source_by_id = {m['message_id']: m['content'] for m in source['messages'] if m['role'] == 'user'}
        for arm in ('baseline', 'supplement'):
            memories = RuleBasedMemoryExtractor().extract(conversation) if arm == 'baseline' else supplement.extract(conversation)
            # This reproduces the original simulation fixture; it is not a
            # claim that these provisional memories were human-confirmed.
            for memory in memories:
                memory.status = MemoryStatus.CONFIRMED
            by_id = {m.memory_id: m for m in memories}
            if len(by_id) != len(memories):
                raise ValueError('Duplicate generated memory ID')
            run = AuditRun(run_id=f'{hid}-{arm}', conversation_id=hid, status='CREATED',
                           target_configuration='weak', provider='rule_based', model='local', temperature=0,
                           random_seed=42, test_budget=4, prompt_template_version='rule-based-v36', created_at=now)
            generated = RuleBasedTestGenerator().generate(memories, run)
            queues = defaultdict(deque)
            for test in generated:
                evidence = [{'canonical_value': by_id[mid].canonical_value,
                             'source_message_ids': by_id[mid].source_message_ids} for mid in test.supporting_memory_ids]
                queues[signature(test.prompt, test.expected_behavior, evidence)].append(test)
            original = [q for q in material['questions'] if q['history_id'] == hid and key['identity'][q['blind_id']]['arm'] == arm]
            for question in original:
                bid = question['blind_id']
                queue = queues[signature(question['prompt'], question['expected_behavior'], question['provisional_evidence'])]
                if not queue:
                    unmatched.append({'blind_id': bid, 'reason': 'No exact reconstructed prompt, answer and support match'})
                    continue
                test = queue.popleft()
                if test.dimension.value != key['identity'][bid]['dimension']:
                    unmatched.append({'blind_id': bid, 'reason': 'Reconstructed dimension differs'})
                    continue
                old_assessment = RuleBasedTestQualityValidator().validate(test, memories)
                old_status = old_assessment.quality_status.value
                support = [by_id.get(mid) for mid in test.supporting_memory_ids]
                source_complete = bool(support) and all(m is not None and m.source_message_ids
                    and all(mid in source_by_id for mid in m.source_message_ids) for m in support)
                topics = {m.memory_id: RuleBasedTestGenerator._topic(m) for m in memories}
                support_topics = {topics[m.memory_id] for m in support if m is not None}
                related_count = max((sum(topic == other for other in topics.values()) for topic in support_topics), default=1)
                warning = scope_warning(test.prompt, test.dimension.value, list(source_by_id.values()),
                                        source_complete=source_complete, related_topic_count=related_count)
                after = apply_gate(old_status, warning)
                a, b = (table[bid] for table in tables)
                values = (a['grounded'], a['structurally_executable'], b['grounded'], b['structurally_executable'])
                human = ('unresolved' if a['grounded'] != b['grounded'] or a['structurally_executable'] != b['structurally_executable']
                         or 'uncertain' in values else 'valid' if a['grounded'] == a['structurally_executable'] == 'valid' else 'invalid')
                counters[arm]['matched'] += 1
                counters[arm][f'{human}_old_{old_status}'] += 1
                counters[arm][f'{human}_after_{after}'] += 1
                rows.append({'blind_id': bid, 'history_id': hid, 'arm': arm, 'human_consensus': human,
                             'reconstructed_old_gate': old_status, 'old_gate_reason': old_assessment.reason,
                             'v3_after_scope_review': after, 'v3_warning': warning,
                             'related_topic_count': related_count, 'source_complete': source_complete})
            remaining = sum(len(q) for q in queues.values())
            if remaining:
                unmatched.append({'history_id': hid, 'arm': arm, 'reason': f'{remaining} reconstructed questions not in frozen packet'})
    return {'format': 'ac2-source-supplement-product-v3-reconstruction-v1',
            'matched': len(rows), 'unmatched': unmatched, 'arms': {k: dict(v) for k,v in counters.items()},
            'items': rows, 'original_human_consensus_summary': established['arms'],
            'limitations': ['The original study did not save any product quality-gate decision; old and new gate results here are reconstructed after the study, not historic or live decisions.',
                'The old gate is the per-question rule validator only. Suite-level validation, semantic review, human review actions, and the product API were not replayed; this is not a full production-gate simulation.',
                'Candidate memories and relationships were provisional; fixture status was set to confirmed to reproduce the original test generation. It does not attest that a user confirmed these memories.',
                'Ten selected pilot histories are synthetic, non-random and prior exposure is unknown. Rules were adapted on different observed cases, but independence and generalisability are not established.',
                'Five disputed or uncertain human judgments are retained as unresolved; they are not counted as valid or invalid.',
                'A pending warning is not a pass, and lack of a warning does not certify a question as valid.',
                'Four per history is a budget ceiling, not a required question count.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = RETURNS / 'user-confirmed'
    paths = [root / f'reviewer-{i}.json' for i in (1, 2)]
    confirmation_path = root / 'confirmation.json'
    confirmation = json.loads(confirmation_path.read_bytes())
    if confirmation.get('review_sha256') != [sha(x.read_bytes()) for x in paths]:
        raise ValueError('Review confirmation does not bind the exact files')
    in_paths = {'protocol': STUDY/'protocol.json', 'material': STUDY/'private/material.json',
                'key': STUDY/'private/key.json', 'review_1': paths[0], 'review_2': paths[1],
                'confirmation': confirmation_path}
    values = {k: json.loads(p.read_bytes()) for k,p in in_paths.items()}
    result = replay(values['protocol'], values['material'], values['key'],
                    [values['review_1'], values['review_2']], values['confirmation'])
    result['source_sha256'] = {k: sha(p.read_bytes()) for k,p in in_paths.items()}
    result['scope_source_sha256'] = sha((ROOT/'backend/app/test_generator/scope_review.py').read_bytes())
    result['quality_source_sha256'] = sha((ROOT/'backend/app/test_generator/quality.py').read_bytes())
    result['replay_source_sha256'] = sha(Path(__file__).read_bytes())
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'matched': result['matched'], 'unmatched': len(result['unmatched']),
                      'arms': result['arms']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
