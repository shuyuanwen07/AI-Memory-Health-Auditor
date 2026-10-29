"""Verify study provenance and totals; this does not verify question validity."""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'output/proposal-delivery/ac2-four-dimension-new-source-20261029-v1'
REVIEW=ROOT/'backend/.engineering-smoke/fact-slot-prototype/four-dimension-ai-review-v1'

def sha(data):return hashlib.sha256(data).hexdigest()
def time(value):return datetime.fromisoformat(value.replace('Z','+00:00'))

def main():
    protocol_bytes=(RUN/'protocol.json').read_bytes();protocol=json.loads(protocol_bytes)
    source_bytes=(RUN/'sources.json').read_bytes();source=json.loads(source_bytes)
    ledger_bytes=(RUN/'ledger.json').read_bytes();ledger=json.loads(ledger_bytes)
    summary=json.loads((RUN/'summary.json').read_text())
    packet_bytes=(RUN/'blind-review/reviewer-1.json').read_bytes();packet=json.loads(packet_bytes)
    ai_protocol=json.loads((REVIEW/'protocol.json').read_text())
    ai_bytes=(REVIEW/'ledger.json').read_bytes();ai=json.loads(ai_bytes)
    ai_summary=json.loads((RUN/'ai-review-summary.json').read_text())
    assert protocol['source_sha256']==sha(source_bytes)
    assert protocol['runner_sha256']==sha((ROOT/'scripts/run_ac2_four_dimension_prospective_20261029.py').read_bytes())
    assert ledger['protocol_sha256']==sha(protocol_bytes)==summary['protocol_sha256']
    assert summary['ledger_sha256']==sha(ledger_bytes)==packet['source_ledger_sha256']
    assert ai_protocol['packet_sha256']==sha(packet_bytes)==ai_summary['packet_sha256']
    assert ai_summary['ledger_sha256']==sha(ai_bytes)
    assert time(protocol['created_at_utc']) <= time(ledger['started_at_utc'])
    frozen={h['id']:h for h in source['histories']}
    assert len(frozen)==protocol['histories']==len(ledger['histories'])==8
    assert {h['id'] for h in ledger['histories']}==set(frozen)
    counts=Counter(); saved_ids=set();complete=0
    for history in ledger['histories']:
        requests=history['requests'];assert all('/execute' not in r['path'] for r in requests)
        if history['state']!='completed':continue
        complete+=1
        created=next(r['body']['messages'] for r in requests if r['path']=='/conversations' and r['state']=='returned')
        assert [m['content'] for m in created]==frozen[history['id']]['texts']
        memory_calls=[r for r in requests if r['path']=='/memories' and r['state']=='returned']
        assert len(memory_calls)==len(created)==6
        ids=[r['response']['memory_id'] for r in memory_calls]
        for index,record in enumerate(memory_calls):
            assert record['body']['canonical_value']==created[index]['content']
            assert record['body']['source_message_ids']==[created[index]['message_id']]
            expected=[e for e in frozen[history['id']]['edges'] if e['source']==index]
            relations=record['body']['relationships'];assert len(relations)==len(expected)
            for relation,edge in zip(relations,expected):
                assert relation['type']==edge['type'] and relation['target_memory_id']==ids[edge['target']]
        confirmed=next(r['body']['confirmed_memory_ids'] for r in requests if r['path'].endswith('/confirm-ground-truth') and r['state']=='returned')
        assert set(confirmed)==set(ids)
        review=next(r['response'] for r in requests if r['path'].endswith('/test-review') and r['state']=='returned')
        assert len(review['tests'])==protocol['budget']
        for test in review['tests']:
            assert test['test_id'] not in saved_ids and set(test['supporting_memory_ids']).issubset(ids)
            saved_ids.add(test['test_id']);counts[test['dimension']]+=1
    mapping=json.loads((RUN/'blind-review/private-mapping.json').read_text())
    assert mapping['ledger_sha256']==sha(ledger_bytes)
    assert {x['test_id'] for x in mapping['items'].values()}==saved_ids
    assert set(mapping['items'])=={x['review_item_id'] for x in packet['items']}
    assert counts==Counter(summary['dimensions']) and sum(counts.values())==summary['saved_questions']==len(packet['items'])
    assert ai.get('finished') and all(x['state']=='completed' for x in ai['jobs'])
    assert len(ai['jobs'])==16 and ai_summary['questions']==len(packet['items'])
    result={'protocol_sha256':sha(protocol_bytes),'source_sha256':sha(source_bytes),'ledger_sha256':sha(ledger_bytes),
            'ai_ledger_sha256':sha(ai_bytes),'complete_histories':complete,'question_dimensions':dict(counts),
            'target_execution_requests':0,'verification':'Provenance, recorded inputs and counts only. This does not establish source or question validity, human review, model independence or generalisation.'}
    (RUN/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
