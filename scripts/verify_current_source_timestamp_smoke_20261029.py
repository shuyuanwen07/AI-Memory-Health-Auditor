"""Verify the saved synthetic, simulated-operator demonstration."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'output/proposal-delivery/current-source-timestamp-smoke-20261029-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=json.loads((RUN/'protocol.json').read_text()); ledger=json.loads((RUN/'ledger.json').read_text())
 assert ledger['status']=='completed' and ledger['protocol_sha256']==sha(RUN/'protocol.json')
 calls=ledger['requests'];assert all(x['state']=='returned' for x in calls)
 def one(method,suffix):
  a=[x for x in calls if x['method']==method and x['path'].endswith(suffix)];assert len(a)==1;return a[0]
 created=one('POST','/conversations')['response'];message=created['messages'][0]
 assert message['content']==p['source'] and message['original_timestamp'] is None
 export=one('GET','/export')['response']['conversation'];assert export['messages']==created['messages']
 suite=one('GET','/test-review')['response'];test=suite['tests'][0]
 assert len(suite['tests'])==1 and test['quality_status']=='pending'
 review=one('PATCH','/review');assert review['request']['quality_status']=='accepted' and 'Simulated' in review['request']['note']
 answers=one('POST','/execute')['response'];assert len(answers)==1 and answers[0]['model']==p['target_model']
 result=one('GET','/results')['response'];assert result['run_id']==ledger['run_id'] and result['tests_total']==1 and len(result['answers'])==1
 final=one('GET','/'+ledger['run_id'])['response'];assert final['status']=='COMPLETED'
 out={'protocol_sha256':sha(RUN/'protocol.json'),'ledger_sha256':sha(RUN/'ledger.json'),'run_id':ledger['run_id'],
      'source_date':'unknown','questions':1,'target_model':answers[0]['model'],'tests_passed':result['tests_passed'],
      'uncertain_count':result['uncertain_count'],'formal_overall_score':result.get('formal_overall_score'),
      'scope':'One synthetic case; operator confirmation was simulated, and assessment was automatic. Not a human-reviewed experiment or a general accuracy estimate.'}
 (RUN/'verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
