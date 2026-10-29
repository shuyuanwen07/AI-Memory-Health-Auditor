"""Bind two AI-only judgments to shuffled paired development answers."""
import hashlib,json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'output/ac3-generated/b-candidate-answer-development-20261029-v1';PACKET=RUN/'blind-review'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def main():
 blank=load(PACKET/'reviewer-1.json');review=[load(PACKET/f'ai-review-{i}.json') for i in (1,2)];mapping=load(RUN/'private-review-mapping.json');ledger=load(RUN/'ledger.json');protocol=load(RUN/'protocol.json')
 assert blank['ledger_sha256']==sha(RUN/'ledger.json') and ledger['protocol_sha256']==sha(RUN/'protocol.json')
 ids=[x['review_item_id'] for x in blank['items']];assert len(ids)==len(set(ids))==len(mapping)==18
 for a in review:
  assert a['completed_by_human'] is False and a['completed_by_ai'] is True and a['ledger_sha256']==blank['ledger_sha256']
  assert [x['review_item_id'] for x in a['items']]==ids
  for origin,item in zip(blank['items'],a['items']):
   assert {k:v for k,v in origin.items() if k!='review'}=={k:v for k,v in item.items() if k!='review'}
   assert item['review']['verdict'] in ('pass','fail','uncertain') and item['review']['note'].strip()
 rows=[]
 for i,(item,a,b) in enumerate(zip(blank['items'],review[0]['items'],review[1]['items'])):
  ident=item['review_item_id'];m=mapping[ident];assert hashlib.sha256(item['answer'].encode()).hexdigest()==m['answer_sha256']
  verdicts=[a['review']['verdict'],b['review']['verdict']];consensus=verdicts[0] if verdicts[0]==verdicts[1] and verdicts[0]!='uncertain' else 'unresolved'
  rows.append({'history':m['history'],'repeat':m['repeat'],'arm':m['arm'],'consensus':consensus,'reviewer_verdicts':verdicts})
 counts={arm:dict(Counter(x['consensus'] for x in rows if x['arm']==arm)) for arm in ('original','candidate')}
 out={'ledger_sha256':sha(RUN/'ledger.json'),'packet_sha256':sha(PACKET/'reviewer-1.json'),'reviews_sha256':[sha(PACKET/f'ai-review-{i}.json') for i in (1,2)],'counts':counts,'rows':rows,
 'scope':'Two AI-only reviews; prior results informed candidate; identical related synthetic questions repeated across three histories. No concurrent control, live retrieval or human confirmation; do not generalize.'}
 (RUN/'ai-review-analysis.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(counts,indent=2))
if __name__=='__main__':main()
