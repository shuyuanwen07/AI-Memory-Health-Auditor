"""Prepare source-bound blind review for the completed partial-generation probe."""
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'output/proposal-delivery/ac2-fact-slots-product-nine-development-20261029-v1'
SOURCE = ROOT / 'output/proposal-delivery/ac2-independent-source-proposal-20261029/histories.json'
OUT = RUN / 'blind-review'

def main():
    ledger_bytes = (RUN / 'ledger.json').read_bytes()
    ledger = json.loads(ledger_bytes)
    protocol_bytes = (RUN / 'protocol.json').read_bytes()
    protocol = json.loads(protocol_bytes)
    assert ledger['protocol_sha256'] == hashlib.sha256(protocol_bytes).hexdigest()
    assert protocol['source_sha256'] == hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    histories = {h['conversation_id']: h for h in json.loads(SOURCE.read_text())['conversations']}
    assert len(ledger['histories']) == 9 and all(h['state'] in ('failed', 'completed') for h in ledger['histories'])
    items, omissions = [], []
    for history in ledger['histories']:
        if history['state'] == 'failed':
            omissions.append({'history_id': history['history_id'], 'state': 'no_saved_suite', 'error': history.get('error')})
            continue
        def response(suffix):
            matches = [r['response'] for r in history['requests'] if r['path'].endswith(suffix) and r['state'] == 'returned']
            assert len(matches) == 1
            return matches[0]
        extracted = {m['memory_id']: m for m in response('/extract')}
        for test in response('/test-review')['tests']:
            assert all(mid in extracted for mid in test['supporting_memory_ids'])
            items.append({'review_item_id': f'Q{len(items)+1:03}', 'source_history_id': history['history_id'],
                          'source_messages': histories[history['history_id']]['messages'],
                          'cited_facts': [{'fact': extracted[mid]['canonical_value'], 'source_message_ids': extracted[mid]['source_message_ids']} for mid in test['supporting_memory_ids']],
                          'question': test['prompt'], 'reference_answer': test['expected_behavior'],
                          'review': {'source_support': '', 'question_clarity': '', 'reference_answer_correctness': '', 'overall': '', 'notes': ''}})
    summary = json.loads((RUN / 'summary.json').read_text())
    assert summary['ledger_sha256'] == hashlib.sha256(ledger_bytes).hexdigest()
    assert len(items) == summary['saved_questions'] and len(omissions) + summary['histories_with_saved_suite'] == 9
    OUT.mkdir(exist_ok=False)
    for slot in (1, 2):
        review = {'reviewer_id': f'reviewer-{slot}', 'completed_by_human': None, 'independent_review': None,
                  'reviewed_without_other_review': None, 'reviewed_without_system_quality_feedback': None,
                  'source_ledger_sha256': hashlib.sha256(ledger_bytes).hexdigest(),
                  'instructions': 'For each field use valid, invalid or uncertain and explain your reasoning. Assess the full source; cited extracted facts may be wrong. This is a development sample, not an independent evaluation.',
                  'items': items}
        (OUT / f'reviewer-{slot}.json').write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'no-saved-suites.json').write_text(json.dumps(omissions, ensure_ascii=False, indent=2) + '\n')
    (OUT / '填写说明.md').write_text('''# 九段复测题目审核说明

两份 reviewer JSON 使用相同的题目和完整来源，便于分别审核。对每道题核对原对话中的时间、更新与冲突，再在 `review` 中填写：

- `source_support`：引用事实是否得到原文支持。
- `question_clarity`：题目是否明确、可以根据来源作答。
- `reference_answer_correctness`：参考答案是否与完整来源一致。
- `overall`：该题整体是否适合用于审计。
- `notes`：写明依据，尤其是无效或无法判断的原因。

前四项填写 `valid`、`invalid` 或 `uncertain`，不要将证据不足的题目强行判为有效。`no-saved-suites.json` 记录未保存题目的历史，它们不计入题目有效率。只有确实完成相应人工审核后，才填写人工完成和独立性字段；AI 初审应明确标为 AI，不能代填为人工。
''', encoding='utf8')
    with ZipFile(OUT / '双人审核-九段复测.zip', 'w', ZIP_DEFLATED) as z:
        for name in ('reviewer-1.json', 'reviewer-2.json', 'no-saved-suites.json', '填写说明.md'):
            z.write(OUT / name, name)
    print(f'Prepared {len(items)} questions and {len(omissions)} no-suite histories.')

if __name__ == '__main__':
    main()
