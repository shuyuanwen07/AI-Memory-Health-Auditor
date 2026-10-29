"""Summarize two AI review passes without converting them to human labels."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'output/proposal-delivery/ac2-four-dimension-new-source-20261029-v1'
AI=ROOT/'backend/.engineering-smoke/fact-slot-prototype/four-dimension-ai-review-v1'

def main():
    packet_bytes=(RUN/'blind-review/reviewer-1.json').read_bytes();packet=json.loads(packet_bytes)
    ledger_bytes=(AI/'ledger.json').read_bytes();ledger=json.loads(ledger_bytes)
    protocol_bytes=(AI/'protocol.json').read_bytes();protocol=json.loads(protocol_bytes)
    assert ledger.get('finished') and ledger['protocol_sha256']==hashlib.sha256(protocol_bytes).hexdigest()
    assert protocol['packet_sha256']==hashlib.sha256(packet_bytes).hexdigest()
    items={x['review_item_id']:x for x in packet['items']}
    assert len(items)==len(packet['items'])
    reviews={1:{},2:{}}
    for job in ledger['jobs']:
        if job['state']!='completed':continue
        for row in job['items']:
            assert row['review_item_id'] in items and row['review_item_id'] not in reviews[job['reviewer']]
            reviews[job['reviewer']][row['review_item_id']]=row
    def overall(row):
        labels=[row[k] for k in ('source_support','question_clarity','reference_answer_correctness')]
        return 'invalid' if 'invalid' in labels else 'valid' if all(v=='valid' for v in labels) else 'uncertain'
    rows=[]
    for item_id,item in items.items():
        labels=[overall(review[item_id]) if item_id in review else 'missing' for review in reviews.values()]
        consensus=labels[0] if labels[0]==labels[1] and labels[0] in ('valid','invalid') else 'unresolved'
        rows.append({'id':item_id,'history_id':item['history_id'],'dimension':item['dimension'],'reviewer_1':labels[0],'reviewer_2':labels[1],'consensus':consensus})
    counts=Counter(r['consensus'] for r in rows)
    dimension_counts={dim:dict(Counter(r['consensus'] for r in rows if r['dimension']==dim)) for dim in sorted({r['dimension'] for r in rows})}
    result={'packet_sha256':hashlib.sha256(packet_bytes).hexdigest(),'ledger_sha256':hashlib.sha256(ledger_bytes).hexdigest(),
            'questions':len(rows),'history_count':len({r['history_id'] for r in rows}), 'consensus':dict(counts),
            'by_dimension':dimension_counts,'rows':rows,
            'limitations':['Two separate AI passes using the same model are not independent human judgments.',
                           'Related synthetic sources and questions within the same history are not independent population samples.',
                           'Failed or uncertain jobs are unresolved, not valid.',
                           'Human reference review and an independent evaluation are still required.']}
    (RUN/'ai-review-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('questions','history_count','consensus','by_dimension')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
