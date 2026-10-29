"""Compare v6/v7 source warnings offline on previously reviewed AI examples."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from app.test_generator.frozen_scope_review_v7 import scope_warning as v7
from app.test_generator.frozen_scope_review_v6 import scope_warning as v6

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT/'output/proposal-delivery/ac2-fact-slots-product-nine-development-20261029-v1/blind-review'
OUT = ROOT/'output/proposal-delivery/ac2-scope-v7-subject-development-20261030.json'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    paths = [PACKET/f'ai-review-{i}.json' for i in (1,2)]
    a,b = (json.loads(path.read_text()) for path in paths)
    assert a['completed_by_human'] is False and b['completed_by_human'] is False
    assert len(a['items']) == len(b['items']) == 24
    rows = []
    for x,y in zip(a['items'],b['items']):
        assert {k:v for k,v in x.items() if k!='review'} == {k:v for k,v in y.items() if k!='review'}
        messages=x['source_messages']; ids={source for fact in x['cited_facts'] for source in fact['source_message_ids']}
        cited=[m['text'] for m in messages if m['source_id'] in ids]; assert cited and ids <= {m['source_id'] for m in messages}
        full=[m['text'] for m in messages]
        args=(x['question'],'accuracy',cited)
        before=v6(*args,source_complete=True,conversation_source_texts=full)
        after=v7(*args,source_complete=True,conversation_source_texts=full)
        left,right=x['review']['overall'],y['review']['overall']
        label=left if left==right and left in ('valid','invalid') else 'unresolved'
        rows.append({'review_item_id':x['review_item_id'],'ai_consensus':label,'v6_warning':before,'v7_warning':after})
    counts=Counter((row['ai_consensus'],bool(row['v6_warning']),bool(row['v7_warning'])) for row in rows)
    output={'review_sha256':[sha(path) for path in paths],
            'v6_sha256':sha(ROOT/'backend/app/test_generator/frozen_scope_review_v6.py'),
            'v7_sha256':sha(ROOT/'backend/app/test_generator/frozen_scope_review_v7.py'),
            'counts':[{'ai_consensus':k[0],'v6_warned':k[1],'v7_warned':k[2],'n':v} for k,v in sorted(counts.items())],
            'items':rows,'limitations':'Post-outcome offline replay, not a live API comparison. Related-topic count held at its default and all questions are Accuracy. Two prior AI-only reviews; human review pending. Rule designed after observing this sample; a warning is not a validity decision.'}
    OUT.write_text(json.dumps(output,indent=2)+'\n'); print(json.dumps(output['counts'],indent=2))


if __name__=='__main__': main()
