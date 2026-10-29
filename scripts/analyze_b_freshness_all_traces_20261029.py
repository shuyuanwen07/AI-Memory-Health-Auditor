"""Read saved B traces for the paired freshness questions; no target calls."""
import hashlib,json
from collections import Counter
from pathlib import Path
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1]
KEY=ROOT/'output/proposal-delivery/experiment-b-four-strategy-20261029-v1/private-review-key.json'
REV=ROOT/'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/normalized-user-confirmed'
OUT=ROOT/'output/proposal-delivery/b-freshness-all-traces-20261029-v1'
API='http://127.0.0.1:8000/api/v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def main():
 OUT.mkdir(parents=True,exist_ok=False)
 mapping=load(KEY)['mapping'];reviews=[load(REV/f'b-reviewer-{i}.json') for i in (1,2)]
 items=[(bid,x) for bid,x in mapping.items() if x['dimension']=='freshness' and x['strategy'] in ('strong_rule_based','scope_aware')]
 assert len(items)==18
 rows=[]
 for bid,x in sorted(items,key=lambda y:(y[1]['history_id'],y[1]['repetition'],y[1]['strategy'])):
  url=f"{API}/audits/{x['run_id']}/target-memory-trace"
  with urlopen(url,timeout=30) as response:trace=json.load(response)
  assert trace['run_id']==x['run_id'] and trace['memory_strategy']==x['strategy']
  file=OUT/f"{x['run_id']}.json";file.write_text(json.dumps(trace,ensure_ascii=False,indent=2)+'\n')
  retrieval=next(r for r in trace['retrievals'] if r['test_id']==x['test_id'])
  records={r['memory_id']:r for r in trace['records']};selected=set(retrieval['selected_memory_ids'])
  pairs=[(r['memory_id'],e['target_memory_id']) for r in records.values() for e in r['relationships'] if e['type']=='UPDATE' and e['target_memory_id'] in records]
  related=[pair for pair in pairs if pair[0] in selected or pair[1] in selected]
  verdict=[next(a['verdict'] for a in r['answer_reviews'] if a['blind_id']==bid) for r in reviews]
  rows.append({'history':x['history_id'],'repeat':x['repetition'],'strategy':x['strategy'],'run_id':x['run_id'],'test_id':x['test_id'],
      'question':retrieval['question'],'update_pairs_selected_current':sum(current in selected for current,prior in related),
      'update_pairs_selected_both':sum(current in selected and prior in selected for current,prior in related),
      'related_update_pairs':len(related),'human_verdicts':verdict,'trace_sha256':sha(file)})
 for h in {r['history'] for r in rows}:
  for n in (1,2,3):
   paired=[r for r in rows if r['history']==h and r['repeat']==n]
   assert len(paired)==2 and paired[0]['question']==paired[1]['question']
 summary={}
 for strategy in ('strong_rule_based','scope_aware'):
  cases=[r for r in rows if r['strategy']==strategy];v=Counter('/'.join(r['human_verdicts']) for r in cases)
  summary[strategy]={'answers':len(cases),'with_current_update_endpoint':sum(r['update_pairs_selected_current']>0 for r in cases),
   'with_both_update_endpoints':sum(r['update_pairs_selected_both']>0 for r in cases),'human_verdict_pairs':dict(v)}
 out={'mapping_sha256':sha(KEY),'review_sha256':[sha(REV/f'b-reviewer-{i}.json') for i in (1,2)],'rows':rows,'summary':summary,
      'limits':'Post-outcome analysis of three related synthetic histories repeated three times. It checks recorded retrieval membership and user-reported AI-assisted human verdicts; repetitions are correlated. Selected relationship pairs need not prove exhaustive evidence or causality.'}
 (OUT/'analysis.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
