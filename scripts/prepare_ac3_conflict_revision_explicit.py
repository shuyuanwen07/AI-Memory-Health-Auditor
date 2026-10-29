"""Prepare a source-bound AC3 candidate that resolves venue ambiguity.

Drafts only; this never modifies the earlier suite, creates approvals, freezes a
protocol or calls a model. All reviews are blank because the source changed.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.prepare_ac3_fact_review import build, canonical_sha

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'output/proposal-delivery/ac3-prospective-inputs-2026-10-28-v3/candidate-inputs.json'
DEST = ROOT / 'output/proposal-delivery/ac3-conflict-revision-draft-2026-10-28-v3'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(raw):
    original = json.loads(raw)
    if original.get('format') != 'ac3-prospective-synthetic-inputs-v1' or len(original.get('cases', [])) != 8:
        raise ValueError('Expected the eight-history AC3 candidate')
    suite = json.loads(raw)
    suite['status'] = 'revised candidate; no human grounding or fact review, no protocol freeze or target results'
    for case in suite['cases']:
        message = case['source_messages'][3]
        old = message['text']
        marker = ' event, an active site plan reserves the '
        tail = '. A separate still-active signed booking reserves a different venue, the courtyard, for that same event. Neither record has priority and no replacement decision has been made.'
        if message['message_id'] != case['history_id'] + '-M4' or not old.startswith('For the ') or old.count(marker) != 1 or not old.endswith(tail):
            raise ValueError('Unexpected conflict source; refusing to change a different message')
        project, venue = old[len('For the '):].split(marker, 1)
        venue = venue[:-len(tail)]
        if not project or not venue: raise ValueError('Missing project or venue')
        message['text'] = (f'For the {project} event, an active site plan states that the {venue} is the only final confirmed venue. '
            'A separate still-active signed booking states that the courtyard is the only final confirmed venue for that same event. '
            'Neither record has priority and no replacement decision has been made.')
    encoded = (json.dumps(suite, ensure_ascii=False, indent=2) + '\n').encode()
    plan, facts = build(suite, sha(encoded))
    for case, packet_pair_index in zip(suite['cases'], range(len(suite['cases']))):
        hid = case['history_id']
        project = case['source_messages'][3]['text'][len('For the '):].split(' event, ', 1)[0]
        plan['histories'][hid]['facts'][4]['canonical_value'] = f'For the {project} event, a separate still-active signed booking states that the courtyard is the only final confirmed venue.'
    new_sha = canonical_sha(plan)
    for packet in facts:
        packet['fact_plan_sha256'] = new_sha
        for history in packet['histories']:
            history['proposed_facts'] = plan['histories'][history['history_id']]['facts']

    grounding = []
    for slot in (1, 2):
        grounding.append({'format': 'ac3-prospective-grounding-review-v1', 'reviewer_slot': slot,
            'input_sha256': sha(encoded),
            '说明': '新版仅修改每段 M4，两份仍有效记录分别声称自己的场地是唯一最终确认场地。请核对新版全部题目与原文的对应，尤其每段 Q3；本文件尚无任何人工判断。question_validity 填 valid、invalid 或 uncertain，并填写理由。',
            'reviewer_declaration': {'reviewer_label': None, 'completed_by_human': None,
                'completed_independently': None, 'used_ai_assistance': None, 'note': None},
            'cases': [{'history_id': case['history_id'], 'source_messages': case['source_messages'],
                'questions': [{**question, 'review': {'question_validity': None, 'rationale': ''}}
                              for question in case['tests']]} for case in suite['cases']]})
    for packet in facts:
        packet['instructions'].insert(1, '新版在每段 M4 明确两份记录各自声称唯一最终确认场地；请特别核对该前提及 F4/F5 冲突关系。先前版本的判断不自动转移。')
    return suite, encoded, plan, grounding, facts


def write_new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    original = SOURCE.read_bytes()
    suite, encoded, plan, grounding, facts = prepare(original)
    if SOURCE.read_bytes() != original:
        raise ValueError('Original input changed while preparing revision')
    DEST.mkdir(parents=True, mode=0o700, exist_ok=False)
    fd = os.open(DEST / 'candidate-inputs.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(encoded)
    write_new(DEST / 'proposed-fact-plan.json', plan)
    for slot in (1, 2):
        write_new(DEST / f'grounding-reviewer-{slot}.json', grounding[slot - 1])
        write_new(DEST / f'fact-reviewer-{slot}.json', facts[slot - 1])
        previous = json.loads(original)
        delta_cases = []
        for old_case, new_case in zip(previous['cases'], suite['cases']):
            hid = new_case['history_id']
            if old_case['history_id'] != hid or old_case['tests'] != new_case['tests']:
                raise ValueError('Unexpected change outside the conflict source')
            if any(a != b for index, (a, b) in enumerate(zip(old_case['source_messages'], new_case['source_messages'])) if index != 3):
                raise ValueError('Unexpected change outside M4')
            section = plan['histories'][hid]
            delta_cases.append({'history_id': hid,
                'previous_M4': old_case['source_messages'][3]['text'],
                'revised_M4': new_case['source_messages'][3]['text'],
                'question': new_case['tests'][2],
                'affected_facts': [f for f in section['facts'] if f['source_message_id'] == hid + '-M4'],
                'affected_conflict_relation': [r for r in section['relationships'] if r['relationship_type'] == 'CONFLICT'][0],
                'review': {'question_validity': None, 'fact_and_relation': None, 'comment': ''}})
        delta = {'format': 'ac3-conflict-revision-delta-review-v1', 'reviewer_slot': slot,
            'previous_source_sha256': sha(original), 'revised_source_sha256': sha(encoded),
            'fact_plan_sha256': canonical_sha(plan),
            '说明': '只复核修订受影响的 8 段场地来源、第 3 题和相关事实及冲突关系。逐段 question_validity 填 valid、invalid 或 uncertain；fact_and_relation 填 accept、revise 或 uncertain。请填写声明，独立审核并保持源内容不变；若需修改请在 comment 注明。原版其他题目的判断保留在原版审核记录，不能视为新版整包已完成。',
            'reviewer_declaration': {'reviewer_label': None, 'completed_by_human': None,
                'completed_independently': None, 'used_ai_assistance': None, 'note': ''}, 'cases': delta_cases}
        write_new(DEST / f'changed-items-reviewer-{slot}.json', delta)
    manifest = {'format': 'ac3-conflict-revision-draft-v1', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'original_source_sha256': sha(original), 'revised_source_sha256': sha(encoded),
        'fact_plan_sha256': canonical_sha(plan), 'histories': 8, 'questions': 32,
        'change': 'Each M4 now states that each active record claims a different venue as the only final confirmed venue; all other messages and all questions are unchanged.',
        'human_review_complete': False, 'protocol_frozen': False, 'model_called': False,
        'warning': 'Draft only. Existing reviews belong to the previous source hash. Neither source/grounding nor fact semantics are human-approved for this revision.'}
    write_new(DEST / 'manifest.json', manifest)
    (DEST / '审核说明.md').write_text('# AC3 冲突来源修订草稿\n\n旧资料中同一活动有两个场地，但没有明确只能选一个，因此未必构成互斥。新版只修改每段第 4 条来源，明确两份有效记录分别声称不同场地是唯一最终确认场地，其他来源与题目均未改动。原版和原审核保留。\n\n新版是未运行、未冻结、未经人工审核的草稿。两位审核者可分别独立填写 `changed-items-reviewer-1.json` / `changed-items-reviewer-2.json`，只复核受影响的 8 段来源、第 3 题、场地事实和冲突关系。如需审核完整新版，也提供四份完整来源题目和事实关系表。请如实填写声明。增量审核结果还需与可验证的原版审核记录衔接；当前完整审核表为空，旧来源的确认不能自动转为新版确认。\n', encoding='utf-8')
    print(json.dumps({'directory': str(DEST), 'revised_source_sha256': sha(encoded),
                      'fact_plan_sha256': canonical_sha(plan), 'human_review_complete': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
