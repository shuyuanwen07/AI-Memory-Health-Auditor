"""Combine existing Experiment A blind materials and answer fields into JSON.

This does not create human judgments or alter the original archived packets.
"""
import hashlib
import json
from pathlib import Path


def main():
    source=Path('artifacts/local/phase4-20261027/A-blind-review')
    output=Path('output/proposal-delivery/experiment-a-answer-review-2026-10-29-v1')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    for slot in (1,2):
        folder=source/f'reviewer-{slot}'
        material=json.loads((folder/'materials.json').read_bytes())
        labels=json.loads((folder/'labels-to-complete.json').read_bytes())
        material_sha=hashlib.sha256(json.dumps(material,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if material_sha!=labels['material_sha256']:raise ValueError('Original material digest differs')
        items={row['item_id']:row for row in material['items']}
        if len(items)!=36 or {x['item_id'] for x in labels['labels']}!=set(items):
            raise ValueError('Original material and labels are not a complete match')
        doc={'format':'experiment-a-readable-answer-review-v1','reviewer_slot':slot,
             'material_sha256':material_sha,'reviewer_id':None,'independently_completed':None,
             'has_seen_automated_A_results':None,'used_ai_assistance':None,
             'instructions_zh':['请独立核对每题原文、问题与回答，不查看对方判断；已看过自动评分也请如实声明。',
                'verdict 填 pass、fail 或 uncertain；只对 fail 填 failure_dimension。',
                'source_message_ids 填支持判断的原文编号；defect_ids 仅填写该回答实际暴露的冻结缺陷编号，不凭维度名称推断。',
                '对 pass 或 uncertain，defect_ids 填空数组；无法判断时保留 uncertain 并在 note 写原因。',
                '允许 AI 辅助，但须人工逐题核对。不要修改原文、问题、回答、缺陷清单、编号或材料摘要。'],
             'items':[{**items[row['item_id']],'review':{k:v for k,v in row.items() if k!='item_id'}} for row in labels['labels']]}
        with (output/f'reviewer-{slot}.json').open('x',encoding='utf8') as f:
            json.dump(doc,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'count_per_reviewer':36,'output':str(output),'human_judgments_created':False}))


if __name__=='__main__':main()
