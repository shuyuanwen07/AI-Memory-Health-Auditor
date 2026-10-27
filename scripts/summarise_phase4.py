"""Descriptive frozen-candidate analysis. Human validity stays unmeasured."""
import collections,hashlib,json,math,random,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'artifacts/local/phase4-20261027';STRATEGIES=['weak_first_hit','strong_rule_based'];DIMS=['accuracy','freshness','conflict_resolution','appropriate_use']
def signature(run):return sorted((t['dimension'],t['prompt'],t['expected_behavior'],tuple(sorted(t['supporting_memory_ids']))) for t in run['tests'])
def direction(w,s):return 'tie' if w==s else 'strong_higher' if s>w else 'weak_higher'
def main():
 b=json.loads((D/'B-live.json').read_text());c=json.loads((D/'C-live.json').read_text());protocol=json.loads((D/'protocol.json').read_text());rows=[];missing=[];mismatch=[]
 for h in b['scenarios']:
  for run in h['runs']:
   if signature(run)!=signature(h['runs'][0]):mismatch.append(run['run_id'])
   tests={t['test_id']:t for t in run['tests']};ev={e['test_id']:e for e in run.get('evaluations',[])}
   for tid,t in tests.items():
    if tid not in ev:missing.append(tid);continue
    e=ev[tid];rows.append({'history':h['scenario_id'],'strategy':run['strategy'],'repetition':run['repetition'],'dimension':t['dimension'],'passed':e['passed'],'run_id':run['run_id']})
 def score(items):
  decided=[r for r in items if r['passed'] is not None];dims={d:{'pass':sum(r['passed'] is True for r in decided if r['dimension']==d),'total':sum(r['dimension']==d for r in decided)} for d in DIMS}
  return {'dimensions':dims,'macro_percentage':statistics.mean(v['pass']/v['total']*100 for v in dims.values() if v['total']) if decided else None,'pass':sum(r['passed'] is True for r in items),'fail':sum(r['passed'] is False for r in items),'uncertain':sum(r['passed'] is None for r in items)}
 bs={s:score([r for r in rows if r['strategy']==s]) for s in STRATEGIES};reps={str(rep):{s:score([r for r in rows if r['strategy']==s and r['repetition']==rep]) for s in STRATEGIES} for rep in range(1,4)}
 for s in STRATEGIES:bs[s]['macro_population_stddev_across_repetitions']=statistics.pstdev(reps[str(rep)][s]['macro_percentage'] for rep in range(1,4))
 paired=[]
 for h in b['scenarios']:
  scores=[score([r for r in rows if r['history']==h['scenario_id'] and r['strategy']==s])['macro_percentage'] for s in STRATEGIES];paired.append(scores[1]-scores[0])
 rng=random.Random(42);samples=sorted(statistics.mean(rng.choices(paired,k=len(paired))) for _ in range(10000));nonzero=[x for x in paired if x];k=min(sum(x>0 for x in nonzero),sum(x<0 for x in nonzero));sign=min(1,2*sum(math.comb(len(nonzero),i) for i in range(k+1))/2**len(nonzero)) if nonzero else 1
 grades=[g for g in c['grades'] if g.get('verdict_usable')];ids=set(protocol['C']['selected_ids']);cstats={};agreement=[]
 for rep in range(1,4):
  cstats[str(rep)]={}
  for s in STRATEGIES:
   gs=[g for g in grades if g['repetition']==rep and g['strategy']==s];assert len({g['question_id'] for g in gs})==len(gs),'Duplicate semantic grades'
   cstats[str(rep)][s]={'pass':sum(g['autoeval_label'] for g in gs),'total':len(gs),'percentage':100*sum(g['autoeval_label'] for g in gs)/len(gs) if gs else None,'complete':{g['question_id'] for g in gs}==ids}
  x=cstats[str(rep)];br=reps[str(rep)];complete=all(x[s]['complete'] for s in STRATEGIES) and not missing and not mismatch
  bd=direction(*(br[s]['macro_percentage'] for s in STRATEGIES));cd=direction(*(x[s]['percentage'] for s in STRATEGIES)) if all(x[s]['percentage'] is not None for s in STRATEGIES) else None
  agreement.append({'repetition':rep,'B_order':bd,'C_order':cd,'comparable_complete':complete,'agreement':(bd==cd) if complete and 'tie' not in [bd,cd] else None,'tie':complete and 'tie' in [bd,cd]})
 overall_C={s:{'pass':sum(g['autoeval_label'] for g in grades if g['strategy']==s),'total':sum(g['strategy']==s for g in grades),'strata':{kind:{'pass':sum(g['autoeval_label'] for g in grades if g['strategy']==s and ('abstention' if g['question_id'].endswith('_abs') else g['question_type'])==kind),'total':sum(g['strategy']==s and ('abstention' if g['question_id'].endswith('_abs') else g['question_type'])==kind for g in grades)} for kind in protocol['C']['strata']}} for s in STRATEGIES}
 # All benchmark reader controls must match the frozen target; payloads contain no gold fields.
 for run in c['reader_runs']:
  r=run['result'];assert r['model']==protocol['target']['model'];assert r['random_seed']==42
  for history in b['scenarios']:
   for condition in history['runs']:
    config=condition['configuration'];assert r['target_memory_profile']==config['target_memory_profile'];assert r['target_memory_capacity']==config['target_memory_capacity'];assert r['reader_configuration']==config['target_configuration']=='strong'
    ingested=next(e for e in condition['trace']['events'] if e['event_type']=='INGESTED');assert ingested['details']['writer_version']==r['writer_version'];assert ingested['details']['maintenance_policy']==protocol['target']['memory_maintenance_policy']
 for receipt in c['target_receipts']:
  assert receipt['expected_behavior_empty'] and receipt['supporting_gold_ids_empty']
 result={'scope':'automated candidate collection; not formal human-validated study','B':{'complete':len(rows)==72 and not missing and not mismatch,'answers':len(rows),'missing_test_ids':missing,'noncanonical_runs':mismatch,'policies':bs,'repetitions':reps,'paired_history_macro_deltas_pp':paired,'paired_mean_delta_pp':statistics.mean(paired),'descriptive_history_bootstrap_95_interval_pp':[samples[249],samples[9749]],'exact_two_sided_history_sign_p':sign,'distinct_synthetic_histories':3,'sampling_limitation':'Three histories share an authored scenario structure; repetitions and template variants are not independent population samples','critical_errors':None,'critical_error_status':'Requires real independent actual-answer review; absent human labels do not mean zero errors'},'C':{'status':c['status'],'responses':len(c['target_receipts']),'usable_grades':len(grades),'overall_policies':overall_C,'repetitions':cstats,'ranking_comparison':agreement,'limitations':c['compatibility_deviations']},'cost_estimate_usd':{'B_completed_usage':b.get('estimated_target_cost_usd'),'C_recorded_usage_and_failed_grader_reserves':c['estimated_cost_usd'],'failed_target_usage':'Unknown; not a billing receipt'},'human_metrics_status':'unmeasured until independent labels and source reconciliation arrive','A_status':'awaiting real inventory and fixed-template review; no formal target execution'}
 for run in c['reader_runs']:
  target=D/'hypotheses'/('rep-'+str(run['repetition'])+'-'+run['strategy']+'.jsonl');target.parent.mkdir(exist_ok=True)
  target.write_text(''.join(json.dumps({'question_id':case['case_id'],'hypothesis':case['response_text']})+'\n' for case in run['result']['conditions'][0]['cases']))
 (D/'analysis.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
