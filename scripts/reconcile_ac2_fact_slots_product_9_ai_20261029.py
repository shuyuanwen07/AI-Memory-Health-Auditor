"""Compare two AI-only reviews against the frozen 24-question packet."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'output/proposal-delivery/ac2-fact-slots-product-nine-development-20261029-v1'
PACKET=RUN/'blind-review'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ledger=RUN/'ledger.json'
    blank=json.loads((PACKET/'reviewer-1.json').read_text())
    reviews=[json.loads((PACKET/f'ai-review-{i}.json').read_text()) for i in (1,2)]
    assert blank['source_ledger_sha256']==sha(ledger)
    ids=[x['review_item_id'] for x in blank['items']]
    assert len(ids)==len(set(ids))==24
    for r in reviews:
        assert r['completed_by_human'] is False and r['completed_by_ai'] is True
        assert r['source_ledger_sha256']==blank['source_ledger_sha256']
        assert [x['review_item_id'] for x in r['items']]==ids
        for original,item in zip(blank['items'],r['items']):
            assert {k:v for k,v in item.items() if k!='review'}=={k:v for k,v in original.items() if k!='review'}
            for field in ('source_support','question_clarity','reference_answer_correctness','overall'):
                assert item['review'][field] in ('valid','invalid','uncertain')
            assert item['review']['notes'].strip()
    rows=[];counts=Counter()
    for original,a,b in zip(blank['items'],reviews[0]['items'],reviews[1]['items']):
        x=a['review']['overall']; y=b['review']['overall']
        consensus=x if x==y and x in ('valid','invalid') else 'unresolved'
        counts[consensus]+=1
        rows.append({'review_item_id':original['review_item_id'],'history_id':original['source_history_id'],
                     'reviewer_1':x,'reviewer_2':y,'consensus':consensus})
    out={'ledger_sha256':sha(ledger),'packet_sha256':sha(PACKET/'reviewer-1.json'),
         'review_sha256':[sha(PACKET/f'ai-review-{i}.json') for i in (1,2)],
         'questions':len(rows),'counts':dict(counts),'items':rows,
         'scope':'Two separate AI-only reviews, not human review or independent population validation; uncertain and disagreements remain unresolved.'}
    (PACKET/'ai-review-summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'questions':len(rows),'counts':dict(counts)},ensure_ascii=False))

if __name__=='__main__':main()
