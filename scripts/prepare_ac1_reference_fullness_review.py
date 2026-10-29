#!/usr/bin/env python3
"""Prepare source-bound independent follow-up reviews for matched reference IDs."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'output/proposal-delivery'
summary_path=BASE/'ac1-extraction-reviewed-summary-2026-10-28-v2.json'
summary=json.loads(summary_path.read_bytes())
paths=[BASE/f'ac1-extraction-review-intake-2026-10-28/reviewer-{i}-user-confirmed.json' for i in (1,2)]
digest=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for p in paths:
    assert summary['review_and_manifest_sha256'][str(p.relative_to(ROOT))]==digest(p)
reviews=[json.loads(p.read_bytes()) for p in paths]
assert all(r['human_review_confirmation']['decision']=='accept_review_findings' for r in reviews)
assert reviews[0]['evidence_sha256']==reviews[1]['evidence_sha256']==summary['source_hashes']
by_history=[]
for a,b in zip(reviews[0]['histories'],reviews[1]['histories'],strict=True):
    assert a['history_id']==b['history_id'] and a['source_messages']==b['source_messages'] and a['reviewed_reference_facts']==b['reviewed_reference_facts'] and a['extraction_status']==b['extraction_status']
    ca={c['candidate']['candidate_id']:c for c in a['candidates']}; cb={c['candidate']['candidate_id']:c for c in b['candidates']}
    assert ca.keys()==cb.keys() and all(ca[k]['candidate']==cb[k]['candidate'] for k in ca)
    facts=[]
    for ref in a['reviewed_reference_facts']:
        if ref['reference_status']!='reviewed': continue
        fid=ref['fact']['memory_id']
        matched=[k for k in ca if ca[k]['review']['supported']=='valid' and cb[k]['review']['supported']=='valid' and fid in ca[k]['review']['matched_reference_fact_ids'] and fid in cb[k]['review']['matched_reference_fact_ids']]
        facts.append((ref,matched,ca,cb))
    by_history.append((a,facts))
matched_complete=sum(bool(m) for h,fs in by_history if h['extraction_status']=='completed' for _,m,_,_ in fs)
matched_partial=sum(bool(m) for h,fs in by_history if h['extraction_status']=='partial' for _,m,_,_ in fs)
assert (matched_complete,matched_partial)==(228,8)
out=BASE/'ac1-reference-fullness-followup-2026-10-28-v1'
out.mkdir(parents=True,exist_ok=False)
instructions=[
 '请两位审核者各自独立逐条填写 matched_reference_items 里的 fullness，不查看对方本轮判断。',
 '比较参考事实的完整内容与本条列出的所有候选合起来能否表达其全部实质信息和限定；可以参考同段 source_messages。',
 'full：候选整体覆盖完整参考事实及关键限定；partial：只覆盖一部分；none：列出的候选实际均不支持该参考事实；uncertain：无法判断。',
 '即使原审核认为同一 ID 已匹配，也可判断 partial、none 或 uncertain。请在 note 写明缺失、歧义或原因；不要为了达标修改证据。',
 '没有共同匹配的参考项列在 unmatched_reference_items 供查阅，不要求重复判定；这只是既有审核无共同映射，不预断语义遗漏。',
 'H04 为部分运行，缺失输出属于未知，不能据此断言遗漏。其已有候选可以审核完整性，统计时须与29段完整运行分开。',
 '完成后填写 reviewer_declaration。保留历史原审核、原意见以及仍存分歧，不改 source 或 candidate。'
]
for index in (0,1):
    histories=[]
    for h, facts in by_history:
        matched_items=[]; unmatched=[]
        for ref, ids, ca, cb in facts:
            if not ids: unmatched.append({'reference_fact':ref['fact'],'prior_status':'no_mutually agreed mapping; not automatically an omission'}); continue
            own=ca if index==0 else cb
            matched_items.append({'reference_fact':ref['fact'], 'previously_mapped_candidates':[{'candidate':own[k]['candidate'],'your_prior_review':own[k]['review']} for k in ids], 'review':{'fullness':None,'note':''}})
        histories.append({'history_id':h['history_id'],'extraction_status':h['extraction_status'],'source_messages':h['source_messages'],'matched_reference_items':matched_items,'unmatched_reference_items':unmatched})
    doc={'format':'ac1-reference-fullness-human-review-v1','reviewer_slot':index+1,'source_summary_sha256':digest(summary_path),'prior_review_sha256':digest(paths[index]),'instructions':instructions,'reviewer_declaration':{'reviewer_label':None,'completed_by_human':None,'completed_independently':None,'used_ai_assistance':None,'note':''},'histories':histories}
    (out/f'reviewer-{index+1}.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
manifest={'format':'ac1-reference-fullness-manifest-v1','summary_sha256':digest(summary_path),'prior_review_sha256':[digest(p) for p in paths], 'matched_complete_history_references':matched_complete,'matched_partial_history_references':matched_partial,'unmatched_complete_history_references':sum(not m for h,fs in by_history if h['extraction_status']=='completed' for _,m,_,_ in fs),'partial_history_cannot_establish_missing_output':True}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(manifest,ensure_ascii=False))
