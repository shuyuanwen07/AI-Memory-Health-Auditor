"""Create a compact, source-linked AC1/AC2 human adjudication packet.

Does not resolve or alter the two reviewer returns; a human must supply decisions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source_bytes = args.source.read_bytes()
    data = json.loads(source_bytes)
    if data.get('source_reconciliation_sha256') is None:
        raise ValueError('Expected the source-bound review-difference packet.')
    selected = [item for item in data['items']
                if item.get('queue_id') == 'proposal_ab_formal_review_216'
                and item.get('item_id', '').startswith(('C-', 'G-', 'Q-'))]
    counts = {kind: sum(item['item_id'].startswith(kind + '-') for item in selected)
              for kind in ('C', 'G', 'Q')}
    if counts != {'C': 6, 'G': 3, 'Q': 13}:
        raise ValueError(f'Unexpected unresolved AC1/AC2 case count: {counts}')
    results = []
    for item in selected:
        prefix = item['item_id'][0]
        decision = ({'valid': None} if prefix in ('C', 'Q') else
                    {'coverage': None, 'candidate_ids': None})
        results.append({
            'criterion': 'AC2' if prefix == 'Q' else 'AC1',
            'item_id': item['item_id'],
            'source': item['source'],
            'reviewer_judgments': item['reviewer_judgments'],
            'human_final_decision': {**decision, 'source_message_ids': None,
                                     'reason': None, 'adjudicator': None, 'date': None},
        })
    additional = data['additional_missing_fact_differences']['proposal_ab_formal_review_216']
    if len(additional) != 3:
        raise ValueError('Expected one additional-facts difference for each of the three histories.')
    packet = {
        'format': 'ac1-ac2-human-adjudication-v1',
        '说明': [
            '此前两位不同审核者已填写，以下只摘录仍有不确定判断或分歧的 AC1/AC2 项；原始文件保持不变。',
            '请由知情的人工裁定者逐项检查 source 中的对话、候选或问题与两个判断。可以选择 uncertain，不要猜测。',
            '这份材料展示两位审核者的判断，属于分歧裁定，不是新的盲审；不能把裁定冒充独立盲审。',
            '请填 human_final_decision、source_message_ids、理由、裁定者和日期；完成后另存回传。',
        ],
        '来源差异包_sha256': hashlib.sha256(source_bytes).hexdigest(),
        '来源汇总_sha256': data['source_reconciliation_sha256'],
        '字段说明': {
            'valid': '候选或问题有来源支持且表述成立填 true；不成立填 false；无法判断填 "uncertain"。',
            'coverage': '参考事实覆盖情况填 "full"、"partial"、"none" 或 "uncertain"。',
            'candidate_ids': '支撑 coverage 判断的现有候选 ID 数组；确无匹配填 []；不确定保留 null 并说明。',
            'source_message_ids': '支持最终判断的对话消息 ID 数组，例如 ["P4H1S8"]。',
        },
        '统计': {'AC1_candidate_uncertain': 6, 'AC1_reference_mapping_disagreement': 3,
               'AC2_question_validity_uncertain': 13, 'additional_fact_disagreements': 3},
        '待裁定项目': results,
        '遗漏事实差异': [
            {**row, 'human_final_decision': {'additional_missing_facts': None,
                                            'source_message_ids': None, 'reason': None,
                                            'adjudicator': None, 'date': None}}
            for row in additional
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(packet, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps({'output': str(args.output), 'items': len(results), 'counts': counts}, ensure_ascii=False))


if __name__ == '__main__':
    main()
