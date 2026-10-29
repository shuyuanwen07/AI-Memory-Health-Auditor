"""Post-hoc scope review on regenerated copies; original research runs are read-only.

The generation and evaluation samples were observed before this diagnostic.
It compares with AI suggestions, not human labels; no target is executed.
"""
import collections, hashlib, json, pathlib, urllib.request, urllib.error
from datetime import datetime, timezone

ROOT=pathlib.Path(__file__).resolve().parents[1]
STUDY=ROOT/'output/proposal-delivery/ac2-v40-same-source-development-20261029-v1'
OUT=ROOT/'output/proposal-delivery/ac2-v40-scope-v6-copy-diagnostic-20261029-v1'
LEDGER=STUDY/'ledger.json'; MAPPING=STUDY/'blind-review-v2/private-mapping.json'
AI=STUDY/'blind-review-v2/ai-review-summary.json'; PRIOR=STUDY/'protocol.json'
PACKET=STUDY/'blind-review-v2/reviewer-1.json'; SRC=ROOT/'backend/app/test_generator/scope_review.py'
PREVIOUS=ROOT/'output/proposal-delivery/ac2-v40-scope-v5-copy-diagnostic-20261029-v1'
API='http://127.0.0.1:8000/api/v1'
KEYS=('dimension','prompt','expected_behavior','test_type','supporting_memory_ids','generator_version')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def sig(t):return canonical({k:t.get(k) for k in KEYS})
def check_inputs():
 p=json.loads(PRIOR.read_bytes()); l=json.loads(LEDGER.read_bytes()); m=json.loads(MAPPING.read_bytes()); ai=json.loads(AI.read_bytes()); packet=json.loads(PACKET.read_bytes())
 assert l['protocol_sha256']==digest(PRIOR) and m['ledger_sha256']==digest(LEDGER)
 assert m['material_sha256']==ai['material_sha256']==packet['material_sha256']
 for slot in (1,2):
  if digest(STUDY/f'blind-review-v2/ai-review-{slot}.json')!=ai['reviewer_sha256'][slot-1]:raise RuntimeError('AI review hash differs')
 success=[h for h in l['histories'] if h['status']=='completed'];assert len(success)==11
 tests={(h['history_id'],h['run_id'],t['test_id']):t for h in success for t in h['tests']}
 items={x['item_id']:x for x in packet['items']}; judgments={x['item_id']:x for x in ai['rows']}
 assert len(tests)==len(items)==len(judgments)==len(m['mapping'])==12
 for bid,info in m['mapping'].items():
  t=tests[(info['history_id'],info['run_id'],info['test_id'])];q=items[bid]
  assert (q['history_id'],q['ability'],q['question'],q['proposed_reference_answer'])==(info['history_id'],t['dimension'],t['prompt'],t['expected_behavior'])
  assert info['supporting_memory_ids']==t['supporting_memory_ids']
  assert {x['memory_id'] for x in q['cited_provisional_memories']}==set(t['supporting_memory_ids'])
 assert set(m['mapping'])==set(judgments)==set(items)
 return p,l,m,ai,success

def request(method,path,body=None):
 req=urllib.request.Request(API+path,data=None if body is None else json.dumps(body).encode(),method=method,headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=120) as r:return {'status':r.status,'body':json.load(r)}
 except urllib.error.HTTPError as e:return {'status':e.code,'body':e.read().decode(errors='replace')}
 except Exception as e:return {'status':'transport_error','error_type':type(e).__name__,'message':str(e)}

def main():
 prior,l,m,ai,success=check_inputs()
 prev=json.loads((PREVIOUS/'ledger.json').read_bytes()); prev_summary=json.loads((PREVIOUS/'summary.json').read_bytes())
 if digest(PREVIOUS/'ledger.json')!=prev_summary['ledger_sha256'] or digest(PREVIOUS/'protocol.json')!=prev_summary['protocol_sha256']:raise ValueError('Prior v5 diagnostic hash differs')
 previous={q['item_id']:q for run in prev['runs'] if run.get('status')=='completed' for q in run.get('comparisons',[])}
 if len(previous)!=12 or set(previous)!=set(m['mapping']):raise ValueError('Prior v5 questions cannot be paired')
 OUT.mkdir(parents=True,exist_ok=False)
 frozen={'format':'ac2-v40-scope-v6-copy-diagnostic-v1','created_at_utc':datetime.now(timezone.utc).isoformat(),
 'script_sha256':digest(pathlib.Path(__file__)),'original_protocol_sha256':digest(PRIOR),'original_ledger_sha256':digest(LEDGER),'blind_mapping_sha256':digest(MAPPING),'ai_summary_sha256':digest(AI),'scope_implementation_sha256':digest(SRC),'previous_v5_ledger_sha256':digest(PREVIOUS/'ledger.json'),'previous_v5_protocol_sha256':digest(PREVIOUS/'protocol.json'),'current_application_sha256':{str(path.relative_to(ROOT)):digest(path) for path in sorted((ROOT/'backend/app').rglob('*.py'))},
 'method':'Create a new separate audit on each original already-confirmed synthetic conversation; regenerate the same suite without target calls; require exact dimension, question, reference, type, generator version, and cited memory IDs before calling optional scope-review on copy only. Verify originals remain unchanged. No paid model.',
 'limitations':['Post-hoc on already reviewed, AI-authored related synthetic histories; not independent validation.','Two AI reviewers, not human judgments or reference gold.','Candidate confirmations were simulated, not human.','Scope warning means pending, not invalid; accepted does not certify validity.','Pair only exact matches; retain unpaired and errors.']}
 save(OUT/'protocol.json',frozen)
 ledger={'format':'ac2-v40-scope-v6-copy-diagnostic-ledger-v1','runs':[]};save(OUT/'ledger.json',ledger)
 mapping=m['mapping']; decisions={x['item_id']:x['judgments'] for x in ai['rows']}
 def verify_frozen():
  if ({str(path.relative_to(ROOT)):digest(path) for path in sorted((ROOT/'backend/app').rglob('*.py'))}!=frozen['current_application_sha256']
      or digest(pathlib.Path(__file__))!=frozen['script_sha256']
      or digest(LEDGER)!=frozen['original_ledger_sha256']
      or digest(PRIOR)!=frozen['original_protocol_sha256']
      or digest(MAPPING)!=frozen['blind_mapping_sha256'] or digest(AI)!=frozen['ai_summary_sha256']
      or digest(PREVIOUS/'ledger.json')!=frozen['previous_v5_ledger_sha256']
      or digest(PREVIOUS/'protocol.json')!=frozen['previous_v5_protocol_sha256']):
   raise RuntimeError('Current frozen application or input changed')
 for h in success:
  record={'history_id':h['history_id'],'original_run_id':h['run_id'],'calls':[]};ledger['runs'].append(record);save(OUT/'ledger.json',ledger)
  try:
   check_inputs()
   verify_frozen()
   def call(method,path,body=None):
    verify_frozen()
    result=request(method,path,body);record['calls'].append({'method':method,'path':path,'request':body,'result':result});save(OUT/'ledger.json',ledger)
    verify_frozen()
    if result['status'] not in (200,201):raise RuntimeError('API returned '+str(result['status'])+' on '+path)
    return result['body']
   original=call('GET',f"/audits/{h['run_id']}/test-review")
   if sorted(map(sig,original['tests']))!=sorted(map(sig,h['scope_review']['tests'])) or {t['test_id']:(t['quality_status'],t['validation_notes']) for t in original['tests']}!={t['test_id']:(t['quality_status'],t['validation_notes']) for t in h['scope_review']['tests']}:raise RuntimeError('Original run differs from frozen suite or status')
   memories=call('GET',f"/conversations/{h['product_conversation_id']}/memories")
   memory_keys=('memory_id','canonical_value','status','source_message_ids','relationships')
   memory_sig=lambda rows:sorted(canonical({key:row.get(key) for key in memory_keys}) for row in rows)
   if memory_sig(memories)!=memory_sig(h['simulated_confirmed_memories']):raise RuntimeError('Frozen conversation memories changed')
   create=next(x['request'] for x in h['requests'] if x['method']=='POST' and x['path']=='/audits')
   clone=call('POST','/audits',create);rid=clone['run_id'];record['copy_run_id']=rid
   generated=call('POST',f'/audits/{rid}/generate-tests');before=call('GET',f'/audits/{rid}/test-review')
   if sorted(map(sig,before['tests']))!=sorted(map(sig,h['tests'])):
    record['status']='unpaired';record['reason']='Regenerated question, reference or evidence differs';save(OUT/'ledger.json',ledger);continue
   if {sig(t):t['quality_status'] for t in before['tests']}!={sig(t):t['quality_status'] for t in h['review']['tests']}:raise RuntimeError('Copy before quality statuses differ')
   after=call('POST',f'/audits/{rid}/tests/scope-review')
   before_by={sig(t):t for t in before['tests']};after_by={sig(t):t for t in after['tests']}
   if before_by.keys()!=after_by.keys():raise RuntimeError('Scope review changed question contents')
   bid_by_sig={sig(t):next(bid for bid,v in mapping.items() if v['run_id']==h['run_id'] and v['test_id']==t['test_id']) for t in h['tests']}
   record['comparisons']=[{'item_id':bid_by_sig[key],'before':before_by[key]['quality_status'],'v4_after':next(t['quality_status'] for t in original['tests'] if sig(t)==key),'v5_after':previous[bid_by_sig[key]]['after'],'after':after_by[key]['quality_status'],'warning':after_by[key]['validation_notes'],'ai_judgments':decisions[bid_by_sig[key]]} for key in before_by]
   if any(x['after']=='pending' and not x['warning'].startswith('source-scope-review-v6:') for x in record['comparisons']):raise RuntimeError('Scope version mismatch')
   final_original=call('GET',f"/audits/{h['run_id']}/test-review")
   if final_original['tests']!=original['tests']:raise RuntimeError('Original run changed unexpectedly')
   record['status']='completed';save(OUT/'ledger.json',ledger)
  except Exception as e:
   record['status']='failed';record['error_type']=type(e).__name__;record['error']=str(e);save(OUT/'ledger.json',ledger);print(h['history_id'],'failed',str(e),flush=True)
   if 'Current frozen application changed' in str(e) or 'Original run changed' in str(e):break
  print(h['history_id'],record['status'],flush=True)
 rows=[q for r in ledger['runs'] if r.get('status')=='completed' for q in r['comparisons']]; counts=collections.Counter()
 for q in rows:
  for k in ('question_executability','reference_answer_validity'):
   counts[(k,q['ai_judgments'][k]['consensus'],q['after'])]+=1
 summary={'format':'ac2-v40-scope-v6-copy-diagnostic-summary-v1','protocol_sha256':digest(OUT/'protocol.json'),'ledger_sha256':digest(OUT/'ledger.json'),'original_ledger_sha256':digest(LEDGER),'planned_runs':11,'attempted_runs':len(ledger['runs']),'status_counts':dict(collections.Counter(r['status'] for r in ledger['runs'])),'paired_questions':len(rows),'scope_status_counts':dict(collections.Counter(q['after'] for q in rows)),'v5_to_v6':dict(collections.Counter(q['v5_after']+' -> '+q['after'] for q in rows)),
 'ai_consensus_and_scope':{f:{label:{status:counts[(f,label,status)] for status in ('accepted','pending','rejected')} for label in ('valid','invalid','unresolved')} for f in ('question_executability','reference_answer_validity')},'limitations':frozen['limitations']}
 save(OUT/'summary.json',summary);print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__':main()
