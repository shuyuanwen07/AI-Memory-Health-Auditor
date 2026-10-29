"""Verify frozen inputs and saved target receipts, without asserting correctness."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'output/ac3-generated/b-candidate-answer-development-20261029-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=json.loads((RUN/'protocol.json').read_text());l=json.loads((RUN/'ledger.json').read_text())
 assert l['protocol_sha256']==sha(RUN/'protocol.json') and sha(ROOT/'scripts/run_b_candidate_answer_development_20261029.py')==p['runner_sha256']
 assert sha(ROOT/'output/proposal-delivery/b-freshness-all-traces-20261029-v1/candidate-profile-context.json')==p['context_sha256']
 assert len(l['rows'])==len(p['rows'])==9
 counts={'returned':0,'failed':0,'not_started':0};input_tokens=output_tokens=attempts=0; costs=[];missing_cost=0; receipts=[]
 for row,answer in zip(p['rows'],l['rows']):
  assert (row['history'],row['repeat'])==(answer['history'],answer['repeat'])
  assert answer['state'] in counts;counts[answer['state']]+=1
  if answer['state']!='returned':continue
  response=answer['response'];meta=response['execution_metadata'];context=list(dict.fromkeys(x.strip() for x in row['selected_context'] if x and x.strip()))
  digest=hashlib.sha256(json.dumps(context,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
  assert meta['memory_input']['context_sha256']==digest and response['model']==p['target']['model']
  assert meta['memory_input']['record_count']==len(context)
  input_tokens+=meta.get('input_tokens') or 0;output_tokens+=meta.get('output_tokens') or 0;attempts+=meta.get('request_attempts') or 0
  if meta.get('reported_cost_usd') is None:missing_cost+=1
  else:costs.append(meta['reported_cost_usd'])
  receipts.append({'history':row['history'],'repeat':row['repeat'],'context_sha256':digest,'response_sha256':hashlib.sha256(response['response_text'].encode()).hexdigest(),'request_attempts':meta['request_attempts']})
 out={'protocol_sha256':sha(RUN/'protocol.json'),'ledger_sha256':sha(RUN/'ledger.json'),'states':counts,'receipts':receipts,
 'reported_input_tokens':input_tokens,'reported_output_tokens':output_tokens,'recorded_attempts':attempts,'reported_cost_usd_values':costs,'missing_cost_receipts':missing_cost,
 'limits':'Receipt evidence validates the selected context hash, not the semantic correctness of answers or a complete provider bill. Expected answers are omitted in runner inputs; provider/model provenance depends on the recorded connector.'}
 (RUN/'verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('receipts','reported_cost_usd_values')},indent=2))
if __name__=='__main__':main()
