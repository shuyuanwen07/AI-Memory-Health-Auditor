"""Publish compact dashboard data from preserved, source-bound study outputs."""
from pathlib import Path
import hashlib, json
R=Path(__file__).resolve().parents[1]
paths={
'a':'output/proposal-delivery/experiment-a-human-return-20261029-v1/analysis.json',
'b':'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/b-consensus-summary.json',
'c':'output/proposal-delivery/four-strategy-adjudicated-bounds-2026-10-29.json',
'ac1':'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/ac1-paired-comparison.json',
'ac2':'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/ac2-adjudicated-paired-summary.json',
'ac2_scope':'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/product-scope-retrospective-replay-v3.json',
'ac2_pilot':'output/proposal-delivery/ac2-source-supplement-review-return-20261029-v1/product-v3-pilot-reconstruction-v2.json',
'ac2_semantic':'output/ac3-generated/semantic-scope-pilot-20261029-v1/analysis.json',
'ac3':'output/ac3-generated/paired-authorized-retest-20261029-v1/paired-analysis.json',
'archived':'frontend/public/reports/proposal-final-results-v1.json',
}
data={k:json.loads((R/p).read_bytes()) for k,p in paths.items()}
a=data['a']; b=data['b']; c=data['c']; c_by_id={v['strategy']:v for v in c['strategies']}
assert len(a['conditions'])==9 and len(b['strategies'])==4 and len(c_by_id)==4
labels={'weak_first_hit':'First-match retrieval','strong_rule_based':'Relationship-priority retrieval','scope_aware':'Match the task and project','temporal_importance':'Consider time and importance'}
strategies=[]
for key,label in labels.items():
 bc=b['strategies'][key]['counts'];cc=c_by_id[key];den=cc['pass']+cc['fail'];assert bc['total']==36 and cc['total_answers']==90
 strategies.append({'id':key,'label':label,'b_pass':bc.get('pass',0),'b_decided':bc.get('pass',0)+bc.get('fail',0),'b_total':bc['total'],
 'c_pass':cc['pass'],'c_decided':den,'c_total':cc['total_answers'],'c_uncertain':cc['uncertain']})
methods=[]
for label in ('Direct questions','Fixed templates','Contextual/indirect Auditor tests'):
 items=[x for x in a['conditions'] if x['method']==label];assert len(items)==3
 methods.append({'label':label,'detected':sum(len(x['auditor_detected_defect_ids']) for x in items),'known':sum(len(x['known_defect_ids']) for x in items)})
ac1=data['ac1']; ac2=data['ac2']; ac3=data['ac3']; archived=data['archived']['proposal_c']['archived_compatibility'];o=ac3['old']['analysis'];n=ac3['new']['analysis']
scope=dict(data['ac2_scope']['arms']['candidate'])
for field in ('invalid_after_rejected','invalid_after_pending','invalid_after_accepted','valid_after_rejected','valid_after_pending','valid_after_accepted'):
 scope.setdefault(field,0)
assert sum(scope[k] for k in ('invalid_after_rejected','invalid_after_pending','invalid_after_accepted'))==scope['human_invalid']
assert sum(scope[k] for k in ('valid_after_rejected','valid_after_pending','valid_after_accepted'))==scope['human_valid']
pilot=data['ac2_pilot']; assert pilot['matched']==33 and not pilot['unmatched'] and len(pilot['items'])==33
rows=pilot['items']
assert all(r['human_consensus'] in ('valid','invalid','unresolved') for r in rows)
pilot_summary={'histories':10,'total':len(rows),'valid':sum(r['human_consensus']=='valid' for r in rows),
 'valid_pending':sum(r['human_consensus']=='valid' and r['v3_after_scope_review']=='pending' for r in rows),
 'invalid':sum(r['human_consensus']=='invalid' for r in rows),
 'invalid_rule_rejected':sum(r['human_consensus']=='invalid' and r['reconstructed_old_gate']=='rejected' for r in rows),
 'unresolved':sum(r['human_consensus']=='unresolved' for r in rows)}
assert pilot_summary=={'histories':10,'total':33,'valid':14,'valid_pending':13,'invalid':14,'invalid_rule_rejected':14,'unresolved':5}
semantic=data['ac2_semantic']; assert semantic['count']==33 and semantic['human_consensus_counts']=={'valid':14,'invalid':14,'unresolved':5}
confusion=semantic['confusion']; semantic_summary={'total':semantic['count'],'unresolved':semantic['human_consensus_counts']['unresolved'],
 'parse_errors':semantic['provider_statuses']['error'],
 'invalid_invalid':confusion.get('invalid_model_invalid',0),'invalid_uncertain':confusion.get('invalid_model_uncertain',0),'invalid_valid':confusion.get('invalid_model_valid',0),
 'valid_invalid':confusion.get('valid_model_invalid',0),'valid_uncertain':confusion.get('valid_model_uncertain',0),'valid_valid':confusion.get('valid_model_valid',0)}
assert semantic_summary=={'total':33,'unresolved':5,'parse_errors':4,'invalid_invalid':2,'invalid_uncertain':12,'invalid_valid':0,'valid_invalid':3,'valid_uncertain':1,'valid_valid':10}
out={'format':'compact-final-dashboard-v1','sources':{k:{'path':v,'sha256':hashlib.sha256((R/v).read_bytes()).hexdigest()} for k,v in paths.items()},
 'a':{'histories':3,'answers':36,'methods':methods},'strategies':strategies,
 'c_reference':{'cases':archived['cases'],'available_cases':archived['available_cases'],'agreement':archived['b_c_ordering_agreement']},
 'ac1':{'histories':ac1['paired_complete_histories'],'old':ac1['old'],'new':ac1['new'],'partial':3},
 'ac2':{'histories':ac2['histories'],'baseline':ac2['arms']['baseline'],'candidate':ac2['arms']['candidate'],'slots':ac2['scheduled_per_arm'],
        'scope_replay':scope,'scope_pilot':pilot_summary,'semantic_pilot':semantic_summary},
 'ac3':{'answers':120,'histories':30,'human_consensus':118,'human_unresolved':2,'old':o['metrics'],'new':n['metrics']}}
p=R/'frontend/src/data/compactFinalDashboard.json';p.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n');print('Generated',p)
