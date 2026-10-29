"""Prepare source-bound shuffled AI/human review; keep condition mapping separate."""
import hashlib,json
from pathlib import Path
from zipfile import ZIP_DEFLATED,ZipFile
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'output/ac3-generated/b-candidate-answer-development-20261029-v1'
KEY=ROOT/'output/proposal-delivery/experiment-b-four-strategy-20261029-v1/private-review-key.json'
BASE=ROOT/'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/normalized-user-confirmed/b-reviewer-1.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=json.loads((RUN/'protocol.json').read_text());l=json.loads((RUN/'ledger.json').read_text());base=json.loads(BASE.read_text());mapping=json.loads(KEY.read_text())['mapping']
 assert l['protocol_sha256']==sha(RUN/'protocol.json') and all(x['state']=='returned' for x in l['rows']) and len(l['rows'])==9
 src={x['history_id']:x['source_messages'] for x in base['histories']};answers={x['blind_id']:x for x in base['answers']};questions={x['question_id']:x for x in base['questions']}
 rows=[];private={}
 for i,(plan,item) in enumerate(zip(p['rows'],l['rows'])):
  matches=[(k,v) for k,v in mapping.items() if v['history_id']==plan['history'] and v['repetition']==plan['repeat'] and v['strategy']=='strong_rule_based' and v['dimension']=='freshness'];assert len(matches)==1
  bid,entry=matches[0];old=answers[bid];q=questions[old['question_id']];assert q['question']==plan['question']
  for arm,text in [('original',old['answer']),('candidate',item['response']['response_text'])]:
   identity=hashlib.sha256((sha(RUN/'ledger.json')+'|'+str(i)+'|'+arm).encode()).hexdigest()[:20];assert identity not in private
   private[identity]={'history':plan['history'],'repeat':plan['repeat'],'arm':arm,'original_blind_id':bid,'answer_sha256':hashlib.sha256(text.encode()).hexdigest()}
   rows.append({'review_item_id':identity,'source_messages':src[plan['history']],'question':q['question'],'reference_answer':q['expected_behavior'],'answer':text,'review':{'verdict':'','failure_dimension':'','note':''}})
 rows.sort(key=lambda x:hashlib.sha256(('review-order-v1|'+x['review_item_id']).encode()).hexdigest());assert len(rows)==18
 out=RUN/'blind-review';out.mkdir(exist_ok=False)
 packet={'format':'b-candidate-answer-review-v1','instructions':'Independently compare each answer with the entire source and question. Fill verdict pass, fail or uncertain and explain; do not infer condition from wording. AI drafts are not human review.',
  'ledger_sha256':sha(RUN/'ledger.json'),'completed_by_human':None,'independent_review':None,'items':rows}
 for i in (1,2):(out/f'reviewer-{i}.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n')
 (RUN/'private-review-mapping.json').write_text(json.dumps(private,indent=2)+'\n')
 with ZipFile(out/'双人盲审-18条回答.zip','w',ZIP_DEFLATED) as z:
  for i in (1,2):z.write(out/f'reviewer-{i}.json',f'reviewer-{i}.json')
 print('Prepared',len(rows),'shuffled answers; private mapping kept separately.')
if __name__=='__main__':main()
