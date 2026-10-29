"""Prepare source-bound blind review for the completed partial-generation probe."""
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'output/proposal-delivery/ac2-partial-twenty-five-history-development-20261029-v1'
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
    assert len(ledger['histories']) == 25 and all(h['state'] in ('failed', 'completed') for h in ledger['histories'])
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
    assert len(items) == 15 and len(omissions) == 12
    OUT.mkdir(exist_ok=False)
    for slot in (1, 2):
        review = {'reviewer_id': f'reviewer-{slot}', 'completed_by_human': None, 'independent_review': None,
                  'reviewed_without_other_review': None, 'reviewed_without_system_quality_feedback': None,
                  'source_ledger_sha256': hashlib.sha256(ledger_bytes).hexdigest(),
                  'instructions': 'For each field use valid, invalid or uncertain and explain your reasoning. Assess the full source; cited extracted facts may be wrong. This is a development sample, not an independent evaluation.',
                  'items': items}
        (OUT / f'reviewer-{slot}.json').write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'no-saved-suites.json').write_text(json.dumps(omissions, ensure_ascii=False, indent=2) + '\n')
    with ZipFile(OUT / '双人审核-15题.zip', 'w', ZIP_DEFLATED) as z:
        for name in ('reviewer-1.json', 'reviewer-2.json', 'no-saved-suites.json'):
            z.write(OUT / name, name)
    print(f'Prepared {len(items)} questions and {len(omissions)} no-suite histories.')

if __name__ == '__main__':
    main()
