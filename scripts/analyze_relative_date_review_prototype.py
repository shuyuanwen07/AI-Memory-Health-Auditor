"""Post-outcome diagnostic on the nine-history AI review, not validation."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from scripts.relative_date_review_prototype import relative_date_advice

ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'output/proposal-delivery/ac2-fact-slots-product-nine-development-20261029-v1/blind-review'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    source=PACKET/'reviewer-1.json';review=PACKET/'ai-review-summary.json'
    packet=json.loads(source.read_text());summary=json.loads(review.read_text())
    assert summary['packet_sha256']==sha(source)
    opinions={x['review_item_id']:x['consensus'] for x in summary['items']}
    assert len(opinions)==len(packet['items'])==24
    counts=Counter(); cited_counts=Counter()
    for item in packet['items']:
        flag=bool(relative_date_advice(item['question'],item['reference_answer'],[m['text'] for m in item['source_messages']]))
        counts[f"{opinions[item['review_item_id']]}_{'flagged' if flag else 'unflagged'}"]+=1
        cited_ids={message_id for fact in item['cited_facts'] for message_id in fact['source_message_ids']}
        cited=[message['text'] for message in item['source_messages'] if message['source_id'] in cited_ids]
        assert len(cited)==len(cited_ids)
        cited_flag=bool(relative_date_advice(item['question'],item['reference_answer'],cited))
        cited_counts[f"{opinions[item['review_item_id']]}_{'flagged' if cited_flag else 'unflagged'}"]+=1
    result={'packet_sha256':sha(source),'ai_summary_sha256':sha(review),
            'prototype_sha256':sha(ROOT/'scripts/relative_date_review_prototype.py'),
            'questions':24,'counts':dict(counts),'cited_source_only_counts':dict(cited_counts),
            'scope':'Post-outcome exploratory replay on related synthetic histories with AI-only opinions. Cited-source-only ignores later unreferenced updates. A warning does not mean invalidity; the data do not establish warning accuracy or independent generalisation.'}
    out=PACKET/'relative-date-prototype-diagnostic.json';out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
