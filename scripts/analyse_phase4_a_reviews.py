"""Analyse real A review returns read-only; retain disagreements and uncertain labels."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.analyse_phase4_reviews import indexed,ratio,DIMS
def analyse(manifest,key,reviews):
 if len(reviews)!=2:raise ValueError('Two independent actual-answer reviews required')
 names=[str(r.get('reviewer_id') or '').strip().casefold() for r in reviews]
 if not all(names) or len(set(names))!=2:raise ValueError('Two distinct nonblank reviewer identities required')
 items={x['item_id']:x for x in manifest['items']};tables=[]
 for review in reviews:
  if review.get('material_sha256') not in manifest['material_sha256']:raise ValueError('Frozen material fingerprint mismatch')
  if review.get('independently_completed') is not True:raise ValueError('Actual independent completion declaration required')
  if type(review.get('has_seen_automated_A_results')) is not bool:raise ValueError('Declare prior exposure to automated A results')
  table=indexed(review['labels'],manifest['item_ids'])
  for ident,row in table.items():
   if row['verdict'] not in {'pass','fail','uncertain'}:raise ValueError('Incomplete verdict')
   if row['verdict']=='fail' and row.get('failure_dimension') not in DIMS:raise ValueError('Observed failure dimension required')
   if row['verdict']!='fail' and row.get('failure_dimension') is not None:raise ValueError('Nonfailure has a failure dimension')
   valid_sources={m['message_id'] for m in items[ident]['source_messages']}
   if not row.get('source_message_ids') or not set(row['source_message_ids']).issubset(valid_sources):raise ValueError('Valid source citations required')
   defects=row.get('defect_ids');valid_defects={d['defect_id'] for d in items[ident]['frozen_defects']}
   if not isinstance(defects,list) or len(set(defects))!=len(defects) or not set(defects).issubset(valid_defects):raise ValueError('Explicit valid defect mapping required')
   if row['verdict']!='fail' and defects:raise ValueError('Only an actual failed response can discover a defect')
  tables.append(table)
 grouped={}
 for ident in manifest['item_ids']:
  provenance=key[ident];group=(provenance['scenario_id'],provenance['condition_label']);g=grouped.setdefault(group,{'response_count':0,'resolved_responses':0,'disagreements':[],'human_uncertain':[],'tp':0,'fn':0,'fp':0,'tn':0,'automated_uncertain':0,'human_failures':0,'discovered_defect_ids':set(),'auditor_detected_defect_ids':set(),'known_defect_ids':{d['defect_id'] for d in items[ident]['frozen_defects']}});g['response_count']+=1
  left,right=(t[ident] for t in tables)
  if (left['verdict'],left['failure_dimension'],set(left['defect_ids']))!=(right['verdict'],right['failure_dimension'],set(right['defect_ids'])):g['disagreements'].append(ident);continue
  if left['verdict']=='uncertain':g['human_uncertain'].append(ident);continue
  g['resolved_responses']+=1;failure=left['verdict']=='fail';pred=provenance['evaluation']['passed'];g['human_failures']+=int(failure)
  if failure:g['discovered_defect_ids'].update(left['defect_ids'])
  if failure and pred is False:g['auditor_detected_defect_ids'].update(left['defect_ids'])
  if pred is None:g['automated_uncertain']+=1
  else:g[{(True,False):'tp',(True,True):'fn',(False,False):'fp',(False,True):'tn'}[(failure,pred)]]+=1
 result=[]
 for (scenario,method),g in grouped.items():
  complete=g['resolved_responses']==g['response_count'];g.update(scenario_id=scenario,method=method,complete_resolved_labels=complete,failure_detection_recall_decided=ratio(g['tp'],g['tp']+g['fn']),failure_detection_recall_all_resolved_human_failures=ratio(g['tp'],g['human_failures']),false_positive_rate_decided=ratio(g['fp'],g['fp']+g['tn']),failure_discovery_rate=ratio(len(g['discovered_defect_ids']),len(g['known_defect_ids'])) if complete else None,auditor_detected_failure_discovery_rate=ratio(len(g['auditor_detected_defect_ids']),len(g['known_defect_ids'])) if complete else None)
  g['discovered_defect_ids']=sorted(g['discovered_defect_ids']);g['auditor_detected_defect_ids']=sorted(g['auditor_detected_defect_ids']);g['known_defect_ids']=sorted(g['known_defect_ids']);result.append(g)
 return {'scope':'Human-return analysis; self-declared identities and independence are not authenticated','blind_review_declared':all(r['has_seen_automated_A_results'] is False for r in reviews),'conditions':result,'server_import_performed':False,'notice':'Human-observed discovery includes all reviewer-confirmed failure mappings; auditor-detected discovery additionally requires an automatic failure verdict. Disagreements require actual adjudication. No automated verdict or missing label was substituted for human gold. This read-only draft does not freeze a server discovery mapping.'}
def main():
 p=argparse.ArgumentParser();p.add_argument('private_directory',type=Path);p.add_argument('reviewer1',type=Path);p.add_argument('reviewer2',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
 report=analyse(json.loads((a.private_directory/'A-review-manifest.json').read_text()),json.loads((a.private_directory/'A-identity-key.json').read_text()),[json.loads(x.read_text()) for x in [a.reviewer1,a.reviewer2]])
 if a.output.exists():raise SystemExit('Refuse to overwrite existing human analysis')
 a.output.write_text(json.dumps(report,indent=2))
if __name__=='__main__':main()
