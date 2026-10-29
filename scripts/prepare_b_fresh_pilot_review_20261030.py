"""Create blinded review packets from a completed fresh-history pilot."""
import hashlib,json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'output/ac3-generated/b-candidate-fresh-history-pilot-20261030-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=json.loads((RUN/'protocol.json').read_text());l=json.loads((RUN/'ledger.json').read_text());assert l['protocol_sha256']==sha(RUN/'protocol.json') and 'finished_at_utc' in l and len(l['rows'])==p['planned_calls']
 cases={c['id']:c for c in p['cases']};items=[];mapping={};omissions=[]
 for i,row in enumerate(l['rows']):
  if row['state']!='returned':omissions.append({'case_id':row['case_id'],'type':row['type'],'arm':row['arm'],'state':row['state']});continue
  c=cases[row['case_id']];answer=row['response']['response_text'];identity=hashlib.sha256((sha(RUN/'ledger.json')+'|'+str(i)).encode()).hexdigest()[:20]
  mapping[identity]={'case_id':c['id'],'type':row['type'],'arm':row['arm'],'answer_sha256':hashlib.sha256(answer.encode()).hexdigest()}
  items.append({'review_item_id':identity,'source_messages':[c['old'],c['new']],'question':c[row['type']+'_question'],'expected_behavior':('State '+c['new_value']+' as current'+(' and explain that it replaced '+c['old_value'] if row['type']=='history' else '')+'.'),'answer':answer,'review':{'verdict':'','note':''}})
 items.sort(key=lambda x:hashlib.sha256(('review-order-v1|'+x['review_item_id']).encode()).hexdigest())
 out=RUN/'blind-review';out.mkdir(exist_ok=False)
 packet={'format':'fresh-b-pilot-answer-review-v1','ledger_sha256':sha(RUN/'ledger.json'),'completed_by_human':None,'independent_review':None,
 'instructions':'Assess each answer against both source statements and the question. Use pass, fail or uncertain and explain. These are synthetic development cases; AI review is not human review.', 'items':items}
 for i in (1,2):(out/f'reviewer-{i}.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n')
 (RUN/'private-review-mapping.json').write_text(json.dumps(mapping,indent=2)+'\n');(out/'omissions.json').write_text(json.dumps(omissions,indent=2)+'\n')
 with ZipFile(out/'双人复核-新样本.zip','w',ZIP_DEFLATED) as z:
  for name in ('reviewer-1.json','reviewer-2.json','omissions.json'):z.write(out/name,name)
 print('Prepared',len(items),'answers and',len(omissions),'omissions.')
if __name__=='__main__':main()
