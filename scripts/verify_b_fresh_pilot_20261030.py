"""Verify frozen paired conditions and actual retrieved-input receipts."""
import hashlib,json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'output/ac3-generated/b-candidate-fresh-history-pilot-20261030-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=json.loads((RUN/'protocol.json').read_text());l=json.loads((RUN/'ledger.json').read_text());assert l['protocol_sha256']==sha(RUN/'protocol.json') and len(l['rows'])==p['planned_calls']==16
 assert 'finished_at_utc' in l and len({(x['case_id'],x['type'],x['arm']) for x in l['rows']})==16
 counts=Counter(x['state'] for x in l['rows']);retrieval={};receipts=[]
 for row in l['rows']:
  c=next(x for x in p['cases'] if x['id']==row['case_id']);ctx=row.get('retrieved_context',[])
  key=row['type']+'_'+row['arm'];retrieval.setdefault(key,{'n':0,'both_values':0,'old_only':0})
  retrieval[key]['n']+=1;old=any(c['old_value'].lower() in t.lower() for t in ctx);new=any(c['new_value'].lower() in t.lower() for t in ctx)
  retrieval[key]['both_values']+=int(old and new);retrieval[key]['old_only']+=int(old and not new)
  if row['state']=='returned':
   meta=row['response']['execution_metadata'];dedup=list(dict.fromkeys(x.strip() for x in ctx if x and x.strip()))
   h=hashlib.sha256(json.dumps(dedup,ensure_ascii=False,separators=(',',':')).encode()).hexdigest();assert h==meta['memory_input']['context_sha256']
   receipts.append({'case_id':row['case_id'],'type':row['type'],'arm':row['arm'],'context_sha256':h,'response_sha256':hashlib.sha256(row['response']['response_text'].encode()).hexdigest()})
 out={'protocol_sha256':sha(RUN/'protocol.json'),'ledger_sha256':sha(RUN/'ledger.json'),'states':dict(counts),'retrieval':retrieval,'receipts':receipts,'limits':'Input and trace checks only; matching tokens are descriptive, not semantic truth. Four authored similar histories; simulated reference and isolated injection.'}
 (RUN/'verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='receipts'},indent=2))
if __name__=='__main__':main()
