"""Publish compact dashboard data from preserved, source-bound study outputs."""
from pathlib import Path
import hashlib, json
from zipfile import ZipFile
R=Path(__file__).resolve().parents[1]
paths={
'a':'output/proposal-delivery/experiment-a-human-return-20261029-v1/analysis.json',
'b':'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/b-consensus-summary.json',
'b_diagnostic':'output/proposal-delivery/b-freshness-trace-diagnostic-20261029-v1/analysis.json',
'b_candidate_review':'output/ac3-generated/b-candidate-answer-development-20261029-v1/ai-review-analysis.json',
'b_candidate_verification':'output/ac3-generated/b-candidate-answer-development-20261029-v1/verification.json',
'latest_human_return':'output/proposal-delivery/ai-review-return-20261030-v1/human-confirmed-summary.json',
'latest_ac2_verification':'output/proposal-delivery/ac2-fact-slots-product-nine-development-20261029-v1/verification.json',
'c':'output/proposal-delivery/four-strategy-adjudicated-bounds-2026-10-29.json',
'ac1':'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/ac1-paired-comparison.json',
'ac2':'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/ac2-adjudicated-paired-summary.json',
'wording_comparison':'output/proposal-delivery/ac2-wording-return-20261030-v1/comparison.json',
'wording_confirmation':'output/proposal-delivery/ac2-wording-return-20261030-v1/user-confirmation.json',
'ac2_scope':'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/product-scope-retrospective-replay-v3.json',
'ac2_pilot':'output/proposal-delivery/ac2-source-supplement-review-return-20261029-v1/product-v3-pilot-reconstruction-v2.json',
'ac2_semantic':'output/ac3-generated/semantic-scope-pilot-20261029-v1/analysis.json',
'ac2_prospective':'output/proposal-delivery/ac2-v6-independent-prospective-product-20261029-v1/summary.json',
'ac2_prospective_ai':'output/proposal-delivery/ac2-v6-independent-prospective-product-20261029-v1/ai-review-summary.json',
'review_return':'research/full-project-backup-20261029/ac1-ac2-review-return/summary.json',
'final_question_reviews':'research/full-project-backup-20261029/ac2-final-review-return/reconciled.json',
'final_question_confirmation':'research/full-project-backup-20261029/ac2-final-review-return/user-human-review-confirmation.json',
'final_question_manifest':'research/full-project-backup-20261029/ac2-final-review-return/intake-manifest.json',
'ac3':'output/ac3-generated/paired-authorized-retest-20261029-v1/paired-analysis.json',
'archived':'frontend/public/reports/proposal-final-results-v1.json',
}
data={k:json.loads((R/p).read_bytes()) for k,p in paths.items()}
a=data['a']; b=data['b']; c=data['c']; c_by_id={v['strategy']:v for v in c['strategies']}
diagnostic=data['b_diagnostic']
for source_path,expected_hash in diagnostic['sources'].items():
 assert hashlib.sha256((R/source_path).read_bytes()).hexdigest()==expected_hash
assert diagnostic['strategies']['strong_rule_based']['human_review_verdicts']==['fail','fail']
assert diagnostic['strategies']['scope_aware']['human_review_verdicts']==['pass','pass']
assert diagnostic['strategies']['strong_rule_based']['old_database_retrieved'] is False
assert diagnostic['strategies']['scope_aware']['old_database_retrieved'] is True
assert all(x['saved_automatic_verdict']=='pass' for x in diagnostic['strategies'].values())
candidate_review=data['b_candidate_review'];candidate_verification=data['b_candidate_verification']
assert candidate_review['ledger_sha256']==candidate_verification['ledger_sha256']
candidate_dir=R/'output/ac3-generated/b-candidate-answer-development-20261029-v1'
assert hashlib.sha256((candidate_dir/'ledger.json').read_bytes()).hexdigest()==candidate_review['ledger_sha256']
assert hashlib.sha256((candidate_dir/'protocol.json').read_bytes()).hexdigest()==candidate_verification['protocol_sha256']
assert hashlib.sha256((candidate_dir/'blind-review/reviewer-1.json').read_bytes()).hexdigest()==candidate_review['packet_sha256']
assert [hashlib.sha256((candidate_dir/f'blind-review/ai-review-{i}.json').read_bytes()).hexdigest() for i in (1,2)]==candidate_review['reviews_sha256']
assert candidate_verification['states']=={'returned':9,'failed':0,'not_started':0}
assert candidate_review['counts']=={'original':{'fail':9},'candidate':{'pass':9}}
assert len(candidate_review['rows'])==18
latest=data['latest_human_return']; latest_dir=R/'output/proposal-delivery/ai-review-return-20261030-v1'
assert hashlib.sha256((latest_dir/'original.zip').read_bytes()).hexdigest()==latest['original_zip_sha256']
assert hashlib.sha256((latest_dir/'analysis.json').read_bytes()).hexdigest()==latest['analysis_sha256']
assert hashlib.sha256((latest_dir/'human-confirmation.json').read_bytes()).hexdigest()==latest['human_confirmation_sha256']
assert hashlib.sha256((latest_dir/'human-independence-confirmation.json').read_bytes()).hexdigest()==latest['human_independence_confirmation_sha256']
fresh=latest['groups']['03-B新案例回答']['by_condition']
assert fresh=={'current_baseline':{'pass':4},'current_candidate':{'pass':4},'history_baseline':{'fail':4},'history_candidate':{'pass':4}}
latest_ac2=latest['groups']['01-AC2题目']; latest_ac2_verification=data['latest_ac2_verification']
assert latest_ac2['total']==24 and latest_ac2['counts']=={'valid':22,'invalid':2}
assert latest_ac2_verification['states']=={'completed':7,'failed':2} and latest_ac2_verification['saved_questions']==24
assert len(a['conditions'])==9 and len(b['strategies'])==4 and len(c_by_id)==4
labels={'weak_first_hit':'First-match retrieval','strong_rule_based':'Relationship-priority retrieval','scope_aware':'Match the task and project','temporal_importance':'Consider time and importance'}
strategies=[]
for key,label in labels.items():
 bc=b['strategies'][key]['counts'];cc=c_by_id[key];den=cc['pass']+cc['fail'];assert bc['total']==36 and cc['total_answers']==90
 dimensions=b['strategies'][key]['dimensions']
 assert set(dimensions)=={'accuracy','freshness','conflict_resolution','appropriate_use'}
 assert all(x['pass']+x['fail']==x['decided'] for x in dimensions.values())
 strategies.append({'id':key,'label':label,'b_pass':bc.get('pass',0),'b_decided':bc.get('pass',0)+bc.get('fail',0),'b_total':bc['total'],
 'b_dimensions':{name:{'passed':v['pass'],'decided':v['decided']} for name,v in dimensions.items()},
 'c_pass':cc['pass'],'c_decided':den,'c_total':cc['total_answers'],'c_uncertain':cc['uncertain']})
methods=[]
for label in ('Direct questions','Fixed templates','Contextual/indirect Auditor tests'):
 items=[x for x in a['conditions'] if x['method']==label];assert len(items)==3
 methods.append({'label':label,'detected':sum(len(x['auditor_detected_defect_ids']) for x in items),'known':sum(len(x['known_defect_ids']) for x in items)})
ac1=data['ac1']; ac2=data['ac2']; ac3=data['ac3']; archived=data['archived']['proposal_c']['archived_compatibility'];o=ac3['old']['analysis'];n=ac3['new']['analysis']
wording=data['wording_comparison']; confirmation=data['wording_confirmation']
assert confirmation['human_review_confirmed'] and confirmation['two_independent_human_reviewers_reported']
assert wording['returned_sha256']==confirmation['selected_reviews_sha256']
replayed={item['blind_id']:item for item in data['ac2_scope']['items']}
updated_arms={name:dict(arm) for name,arm in ac2['arms'].items()}
adjusted=[]
for item in wording['items']:
    previous=replayed[item['blind_id']]
    if previous['human_verdict']=='valid' and item['review_consensus']=='invalid':
        arm=updated_arms[previous['arm']]
        arm['valid']-=1; arm['invalid']+=1
        if previous['old_gate']=='accepted': arm['gate_accepted_human_invalid']+=1
        adjusted.append(previous['arm'])
assert sorted(adjusted)==['baseline','candidate']
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
prospective=data['ac2_prospective']; prospective_ai=data['ac2_prospective_ai']
study=R/'output/proposal-delivery/ac2-v6-independent-prospective-product-20261029-v1'
digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
assert digest(study/'protocol.json')==prospective['protocol_sha256']
assert digest(study/'ledger.json')==prospective['ledger_sha256']
assert digest(R/'output/proposal-delivery/ac2-independent-source-proposal-20261029/histories.json')==prospective['source_sha256']
ledger=json.loads((study/'ledger.json').read_bytes())
assert ledger['protocol_sha256']==prospective['protocol_sha256'] and len(ledger['histories'])==prospective['planned_histories']
assert sum(h['status']=='completed' for h in ledger['histories'])==prospective['complete_histories']
assert sum(h['status']=='failed' for h in ledger['histories'])==prospective['whole_suite_failed_histories']
assert sum(len(h.get('after',{}).get('tests',[])) for h in ledger['histories'])==prospective['saved_questions']
assert digest(study/'private-mapping.json')==prospective_ai['mapping_sha256']
assert [digest(study/f'ai-review-{i}.json') for i in (1,2)]==prospective_ai['review_sha256']
reviews=[json.loads((study/f'ai-review-{i}.json').read_bytes()) for i in (1,2)]
mapping=json.loads((study/'private-mapping.json').read_bytes())
assert all(r['material_sha256']==prospective_ai['material_sha256'] for r in reviews)
assert mapping['material_sha256']==prospective_ai['material_sha256']
indexed=[{item['blind_id']:item for item in review['items']} for review in reviews]
assert all(len(items)==prospective['saved_questions'] for items in indexed)
assert set(indexed[0])==set(indexed[1])==set(mapping['items'])
recomputed={}
for item_id in indexed[0]:
 first,second=(items[item_id]['executability'] for items in indexed)
 assert first in ('valid','invalid','uncertain') and second in ('valid','invalid','uncertain')
 category=first if first==second and first in ('valid','invalid') else 'unresolved'
 key=f"{category}_{mapping['items'][item_id]['after']}"
 recomputed[key]=recomputed.get(key,0)+1
assert recomputed==prospective_ai['executability_vs_scope']
assert prospective['planned_histories']==prospective['complete_histories']+prospective['whole_suite_failed_histories']
assert prospective['saved_questions']==prospective_ai['count']==sum(prospective['after'].values())
assert prospective['dimensions']=={'accuracy':prospective['saved_questions']}
exec_counts=prospective_ai['consensus']['executability'];cross=prospective_ai['executability_vs_scope']
assert sum(exec_counts.values())==prospective['saved_questions']
assert all(cross.get(f'{kind}_accepted',0)+cross.get(f'{kind}_pending',0)==exec_counts[kind] for kind in ('valid','invalid','unresolved'))
assert sum(cross.get(f'{kind}_accepted',0) for kind in ('valid','invalid','unresolved'))==prospective['after']['accepted']
assert sum(cross.get(f'{kind}_pending',0) for kind in ('valid','invalid','unresolved'))==prospective['after']['pending']
returned=data['review_return']
assert returned['ac2']['questions']==prospective['saved_questions']
assert returned['ac2']['metrics']['executability']==exec_counts
return_dir=R/'research/full-project-backup-20261029/ac1-ac2-review-return'
return_archive=return_dir/'AC1分阶段独立审核与AC2前瞻v2-完整结果-20261029.zip'
assert digest(return_archive)==returned['source_archive_sha256']
assert digest(return_dir/'ac1-seven-human-adjudications.json')==returned['adjudication_sha256']
with ZipFile(return_archive) as archive:
 returned_reviews=[json.loads(archive.read(f'AC2前瞻v2已有审核/审核者{i}/questions-reviewer-{i}.json')) for i in (1,2)]
returned_index=[{item['blind_id']:item for item in review['items']} for review in returned_reviews]
assert all(set(idx)==set(mapping['items']) for idx in returned_index)
returned_cross={}
for item_id in returned_index[0]:
 first,second=(idx[item_id]['executability'] for idx in returned_index)
 kind=first if first==second and first in ('valid','invalid') else 'unresolved'
 key=f"{kind}_{mapping['items'][item_id]['after']}"
 returned_cross[key]=returned_cross.get(key,0)+1
assert returned_cross==cross
final_return=data['final_question_reviews'];final_manifest=data['final_question_manifest'];final_confirmation=data['final_question_confirmation']
final_dir=R/'research/full-project-backup-20261029/ac2-final-review-return'
assert digest(final_dir/'最终新增材料-双AI复核与人工确认完成-20261029.zip')==final_manifest['original_archive_sha256']==final_confirmation['original_archive_sha256']
assert digest(final_dir/'reordered-original-json.zip')==final_manifest['reordered_archive_sha256']==final_return['input_zip_sha256']
assert digest(final_dir/'reconciled.json')==final_manifest['reconciled_sha256']
four=final_return['groups']['四维来源与题目'];four_rows=four['question_rows'];assert four['questions']==len(four_rows)==32
assert four['source_consensus']=={'valid':72}
final_dimensions=[]
for dimension,label in [('accuracy','Accuracy'),('freshness','Freshness'),('conflict_resolution','Conflict resolution'),('appropriate_use','Appropriate use')]:
 rows=[r for r in four_rows if r['dimension']==dimension]
 assert len(rows)==8
 final_dimensions.append({'dimension':dimension,'label':label,'total':len(rows),
                          'valid':sum(r['consensus']['overall']=='valid' for r in rows),
                          'invalid':sum(r['consensus']['overall']=='invalid' for r in rows),
                          'unresolved':sum(r['consensus']['overall']=='unresolved' for r in rows)})
assert all(sum(row[k] for k in ('valid','invalid','unresolved'))==row['total'] for row in final_dimensions)
prospective_summary={'histories':prospective['planned_histories'],'generated_histories':prospective['complete_histories'],
 'failed_histories':prospective['whole_suite_failed_histories'],'questions':prospective['saved_questions'],
 'accepted':prospective['after']['accepted'],'pending':prospective['after']['pending'],
 'ai_valid':exec_counts['valid'],'ai_invalid':exec_counts['invalid'],'ai_unresolved':exec_counts['unresolved'],
 'cross':cross}
out={'format':'compact-final-dashboard-v1','sources':{k:{'path':v,'sha256':hashlib.sha256((R/v).read_bytes()).hexdigest()} for k,v in paths.items()},
 'a':{'histories':3,'answers':36,'methods':methods},'strategies':strategies,
 'b_example':{'history':diagnostic['history'], 'relationship_run_id':diagnostic['strategies']['strong_rule_based']['run_id'],
              'scope_run_id':diagnostic['strategies']['scope_aware']['run_id'],
              'development_original_pass':fresh['history_baseline'].get('pass',0),
              'development_candidate_pass':fresh['history_candidate'].get('pass',0),
              'development_current_original_pass':fresh['current_baseline'].get('pass',0),
              'development_current_candidate_pass':fresh['current_candidate'].get('pass',0),
              'development_total':4},
 'c_reference':{'cases':archived['cases'],'available_cases':archived['available_cases'],'agreement':archived['b_c_ordering_agreement']},
 'ac1':{'histories':ac1['paired_complete_histories'],'old':ac1['old'],'new':ac1['new'],'partial':3,'reviewed':returned['ac1']},
 'ac2':{'histories':ac2['histories'],'baseline':updated_arms['baseline'],'candidate':updated_arms['candidate'],'slots':ac2['scheduled_per_arm'],
        'scope_replay':scope,'scope_pilot':pilot_summary,'semantic_pilot':semantic_summary,'prospective':prospective_summary,
        'four_dimension_review':{'histories':8,'dimensions':final_dimensions},
        'latest_development':{'histories':9,'saved_histories':7,'valid':latest_ac2['counts']['valid'],'invalid':latest_ac2['counts']['invalid'],'total':latest_ac2['total']}},
 'ac3':{'answers':120,'histories':30,'human_consensus':118,'human_unresolved':2,'old':o['metrics'],'new':n['metrics'],
        'detection_difference_interval':ac3['paired_history_bootstrap']['intervals']['failure_recall_conservative']}}
p=R/'frontend/src/data/compactFinalDashboard.json';p.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n');print('Generated',p)
