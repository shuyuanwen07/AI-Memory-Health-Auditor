"""Generate blank paired human review packets for an AI-drafted fact plan.

Draft IDs are local planning identifiers, not database IDs. No model calls,
application writes, human judgments or confirmations are performed.
"""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'output/proposal-delivery/ac3-prospective-inputs-2026-10-28-v3/candidate-inputs.json'
OUT = ROOT / 'output/proposal-delivery/ac3-fact-review-draft-2026-10-28-v2'


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def build(suite, source_sha):
    cases = suite['cases']
    if suite.get('format') != 'ac3-prospective-synthetic-inputs-v1' or len(cases) != 8:
        raise ValueError('Expected the eight-history AC3 source')
    histories, presentation = {}, []
    for case in cases:
        hid = case['history_id']
        messages = case['source_messages']
        if len(messages) != 5 or [m['message_id'] for m in messages] != [f'{hid}-M{i}' for i in range(1, 6)]:
            raise ValueError('Unexpected message identity or order')
        texts = [m['text'] for m in messages]
        pieces4, pieces5 = texts[3].split('. '), texts[4].split('. ')
        if len(pieces4) != 3 or len(pieces5) != 2:
            raise ValueError('Unexpected compound source structure')
        # Source spans remain exact quotations; canonical_value explicitly
        # resolves pronouns with context from the same source message.
        fragments = [texts[0], texts[1], texts[2], pieces4[0] + '.',
                     pieces4[1] + '.', pieces4[2], pieces5[0] + '.', pieces5[1]]
        source_indices = [1, 2, 3, 4, 4, 4, 5, 5]
        prefix = 'For the '
        if not pieces4[0].startswith(prefix) or ' event, ' not in pieces4[0] or not pieces5[0].startswith('I generally use ') or not pieces5[0].endswith(' for coordinating projects'):
            raise ValueError('Unexpected source wording for context resolution')
        project = pieces4[0][len(prefix):].split(' event, ', 1)[0]
        general = pieces5[0][len('I generally use '):-len(' for coordinating projects')]
        canonical = list(fragments)
        canonical[4] = f'For the {project} event, a separate still-active signed booking reserves the courtyard.'
        canonical[5] = f'For the {project} event, neither the active site plan nor the signed booking has priority, and no replacement decision has been made.'
        canonical[7] = pieces5[1].replace('this does not change the general preference elsewhere',
                                           f'this does not change the general preference for {general} elsewhere')
        if canonical[7] == pieces5[1]: raise ValueError('Expected scoped-preference clause')
        facts = [{'memory_id': f'{hid}-F{i}', 'source_message_id': f'{hid}-M{source_no}',
                  'source_span': span, 'canonical_value': value}
                 for i, (span, source_no, value) in enumerate(zip(fragments, source_indices, canonical), 1)]
        if any(f['source_span'] not in texts[int(f['source_message_id'][-1]) - 1] for f in facts):
            raise ValueError('Draft fact not present in source')
        relations = [
            {'memory_id': f'{hid}-F3', 'target_memory_id': f'{hid}-F2', 'relationship_type': 'UPDATE', 'evidence_message_ids': [f'{hid}-M3']},
            {'memory_id': f'{hid}-F4', 'target_memory_id': f'{hid}-F5', 'relationship_type': 'CONFLICT', 'evidence_message_ids': [f'{hid}-M4']},
            {'memory_id': f'{hid}-F8', 'target_memory_id': f'{hid}-F7', 'relationship_type': 'CONTEXTUAL_OVERRIDE', 'evidence_message_ids': [f'{hid}-M5']},
        ]
        histories[hid] = {'facts': facts, 'relationships': relations}
        presentation.append({'history_id': hid, 'source_messages': messages,
            'questions': [{'test_id': q['test_id'], 'question': q['question'], 'expected_behavior': q['expected_behavior'], 'supporting_source_message_ids': q['supporting_source_message_ids']} for q in case['tests']],
            'proposed_facts': facts, 'proposed_relationships': relations,
            'review': {'decision': None, 'comment': ''}})
    plan = {'histories': histories}
    plan_sha = canonical_sha(plan)
    instruction = ['AI 拟稿，尚未经人工审核；请独立审阅，不参考另一份审核文件。',
        '对每段历史核对原文、各事实的 source_span 与 canonical_value，以及三条关系的方向、语义、范围和证据；全部正确填 decision=accept；有错误填 revise；不确定填 uncertain。',
        '如 revise 或 uncertain，请在 comment 指明事实或关系编号及具体问题；无问题 comment 可留空。',
        'F4 与 F5 分别是两条场地记录；F5、F6 和 F8 的 canonical_value 参照同一来源中的上下文补足指代。请核对补足后的名称、事实及范围没有超出原文，若不正确填 revise。',
        '所有 F 编号是拟议计划标识，不是系统中已经存在或确认的记忆 ID。任何修改必须生成新计划摘要，并由两位审核者重新核对。']
    packets = []
    for slot in (1, 2):
        packets.append({'format': 'ac3-fact-human-review-packet-v1', 'status': 'AI DRAFT; HUMAN REVIEW NOT YET COMPLETED',
            'reviewer_slot': slot, 'source_input_sha256': source_sha, 'fact_plan_sha256': plan_sha,
            'instructions': instruction,
            'reviewer_declaration': {'reviewer_label': None, 'completed_by_human': None,
                'completed_independently': None, 'used_ai_assistance': None, 'note': ''},
            'histories': json.loads(json.dumps(presentation, ensure_ascii=False))})
    return plan, packets


def main():
    raw = SOURCE.read_bytes(); suite = json.loads(raw)
    plan, packets = build(suite, hashlib.sha256(raw).hexdigest())
    OUT.mkdir(parents=True, mode=0o700, exist_ok=False)
    for name, data in [('proposed-fact-plan.json', plan), ('reviewer-1.json', packets[0]), ('reviewer-2.json', packets[1])]:
        fd = os.open(OUT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps({'directory': str(OUT), 'plan_sha256': canonical_sha(plan), 'histories': len(plan['histories']),
                      'facts': sum(len(x['facts']) for x in plan['histories'].values()),
                      'relationships': sum(len(x['relationships']) for x in plan['histories'].values()),
                      'human_review_completed': False}))


if __name__ == '__main__': main()
