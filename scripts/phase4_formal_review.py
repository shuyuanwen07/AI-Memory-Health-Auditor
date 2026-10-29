"""Validate actual independent worksheets; compute only supported consensus metrics.

No AI labels, reviewer signatures or resolved disagreements are generated here.
"""
import argparse,collections,hashlib,json
from pathlib import Path
DIMS={'accuracy','freshness','conflict_resolution','appropriate_use'}
RELATIONS={'UPDATE','CONFLICT','CONTEXTUAL_OVERRIDE','NONE','uncertain'}
def fraction(n,d):return n/d if d else None
def validate(material,key,review):
 if review.get('schema_version')!='phase4-complete-review-v1':raise ValueError('Unsupported return schema')
 if review.get('material_sha256') not in key['material_sha256']:raise ValueError('Frozen material fingerprint mismatch')
 name=str(review.get('reviewer_id') or '').strip()
 if not name or len(name)>80:raise ValueError('Actual reviewer pseudonym of1-80 characters required')
 if review.get('completed_by_human') is not True or review.get('completed_independently') is not True:raise ValueError('Actual human independent completion declarations required')
 for field in ['has_seen_automated_results','used_ai_assistance']:
  if type(review.get(field)) is not bool:raise ValueError('Declare '+field)
 labels=review.get('labels')
 if not isinstance(labels,dict) or set(labels)!=set(material['items']):raise ValueError('Complete exact item IDs required')
 for ident,item in material['items'].items():
  row=labels[ident];kind=item['kind']
  if kind=='response':
   if row.get('verdict') not in {'pass','fail','uncertain'}:raise ValueError('Response verdict missing')
   if row['verdict']=='fail' and row.get('failure_dimension') not in DIMS|{'unclassified'}:raise ValueError('Observed failure category required')
   if row['verdict']!='fail' and row.get('failure_dimension') is not None:raise ValueError('Nonfailure must not have a failure dimension')
   if row.get('critical_error') not in {'yes','no','uncertain'}:raise ValueError('Critical-error decision required')
   if row['verdict']=='pass' and row['critical_error']=='yes':raise ValueError('Passing answer cannot also be a critical failure')
   allowed={m['message_id'] for m in material['histories'][item['history']]}
   if not row.get('source_message_ids') or not set(row['source_message_ids']).issubset(allowed):raise ValueError('Valid source citations required')
   if item['study']=='A':
    ids=row.get('defect_ids');valid={d['defect_id'] for d in item['defects']}
    if not isinstance(ids,list) or len(set(ids))!=len(ids) or not set(ids).issubset(valid):raise ValueError('Explicit frozen-defect list or explicit empty list required')
    if row['verdict']!='fail' and ids:raise ValueError('Only a failed response can discover a frozen defect')
  elif kind in {'question','candidate'}:
   if type(row.get('valid')) is not bool and row.get('valid')!='uncertain':raise ValueError('Validity decision required')
  elif kind=='reference':
   if type(row.get('valid')) is not bool and row.get('valid')!='uncertain':raise ValueError('Reference-unit decision required')
   if row.get('coverage') not in {'full','partial','none','uncertain'}:raise ValueError('Reference coverage decision required')
   ids=row.get('candidate_ids')
   if not isinstance(ids,list) or len(set(ids))!=len(ids) or not set(ids).issubset(item['candidate_ids']):raise ValueError('Invalid reference-to-candidate links')
  elif kind=='relationship':
   if row.get('relationship_type') not in RELATIONS:raise ValueError('Relationship classification required')
  else:raise ValueError('Unknown item kind')
  if not isinstance(row.get('note',''),str):raise ValueError('Note must be text')
 extras=review.get('additional_missing_facts')
 if not isinstance(extras,dict) or set(extras)!=set(material['histories']) or any(not isinstance(v,str) for v in extras.values()):raise ValueError('Review complete source inventories and record missing-fact notes')
 return labels

def analyse(material,key,reviews,known_exposed_reviewers=()):
 if len(reviews)!=2:raise ValueError('Exactly two actual independent returns required')
 names=[str(r.get('reviewer_id') or '').strip().casefold() for r in reviews]
 if len(set(names))!=2:raise ValueError('Two different reviewers required')
 tables=[validate(material,key,r) for r in reviews]
 exposed=any(r['has_seen_automated_results'] or r['used_ai_assistance'] for r in reviews)
 known_exposed_names={str(name).strip().casefold() for name in [*key.get('known_result_exposed_reviewer_ids',[]),*known_exposed_reviewers]}
 known_exposed=any(name in known_exposed_names for name in names)
 unresolved=[];reference_disagreements=[];counts=collections.defaultdict(collections.Counter);groups={};class_counts=collections.Counter();crit=collections.Counter()
 for ident,item in material['items'].items():
  left,right=(t[ident] for t in tables);kind=item['kind']
  if kind=='response':
   private=key['items'][ident];study=item['study'];g=groups.setdefault(private['condition'],{'study':study,'items':0,'resolved':0,'mapping_resolved':0,'discovered':set(),'known':set(private.get('known_defect_ids',[])),'counts':collections.Counter()});g['items']+=1
   if left['verdict']!=right['verdict'] or left['verdict']=='uncertain':unresolved.append(ident);continue
   verdict=left['verdict'];g['resolved']+=1;pred=private['automated']['passed'];counts[study]['resolved']+=1;counts[study]['human_failure' if verdict=='fail' else 'human_pass']+=1
   if pred is None:bucket='automated_uncertain'
   else:bucket={('fail',False):'tp',('fail',True):'fn',('pass',False):'fp',('pass',True):'tn'}[(verdict,pred)]
   counts[study][bucket]+=1;g['counts'][bucket]+=1
   if verdict=='fail':
    if left['failure_dimension']==right['failure_dimension'] and left['failure_dimension'] in DIMS:
     class_counts['typed_reference']+=1;auto=private['automated'];classified=(auto.get('failure_classification') or {}).get('status')=='classified';class_counts['classified']+=int(classified);class_counts['correct']+=int(classified and auto.get('failure_type')==left['failure_dimension'])
    else:reference_disagreements.append(ident+':failure_category')
   if left['critical_error']==right['critical_error'] and left['critical_error']!='uncertain':crit['resolved']+=1;crit['critical']+=int(left['critical_error']=='yes')
   else:reference_disagreements.append(ident+':critical')
   if study=='A':
    if set(left['defect_ids'])==set(right['defect_ids']):
     g['mapping_resolved']+=1
     if verdict=='fail':g['discovered'].update(left['defect_ids'])
    else:reference_disagreements.append(ident+':defect_mapping')
  else:
   field={'question':'valid','candidate':'valid','reference':'valid','relationship':'relationship_type'}[kind]
   if left[field]!=right[field] or left[field]=='uncertain':unresolved.append(ident);continue
   if kind in {'question','candidate'}:counts[kind]['resolved']+=1;counts[kind]['valid']+=int(left['valid'])
   elif kind=='relationship':counts[kind]['resolved']+=1;counts[kind]['correct']+=int(left[field]==key['items'][ident]['predicted_type'])
   elif left['valid']:
    counts[kind]['gold_units']+=1
    # A reviewer may call a reference unit fully covered while citing a
    # candidate they or the other reviewer did not confirm as valid. Preserve
    # both source labels and leave only this coverage decision unresolved.
    cited=set(left['candidate_ids'])|set(right['candidate_ids'])
    full_has_confirmed_candidates=(left['coverage']!='full' or all(
     table[candidate].get('valid') is True for table in tables for candidate in cited
    ))
    if left['coverage']==right['coverage'] and left['coverage']!='uncertain' and full_has_confirmed_candidates:counts[kind]['coverage_resolved']+=1;counts[kind]['covered']+=int(left['coverage']=='full')
    else:unresolved.append(ident+':coverage')
 missing_notes=any(v.strip() for r in reviews for v in r['additional_missing_facts'].values())
 detection={}
 for study in ['A','B']:
  c=counts[study];p=fraction(c['tp'],c['tp']+c['fp']);r=fraction(c['tp'],c['tp']+c['fn']);detection[study]={'counts':dict(c),'precision_decided':p,'recall_decided':r,'recall_all_agreed_failures':fraction(c['tp'],c['human_failure']),'f1_decided':(2*p*r/(p+r) if p+r else 0) if p is not None and r is not None else None,'false_positive_rate_decided':fraction(c['fp'],c['fp']+c['tn'])}
 conditions=[]
 for name,g in groups.items():
  ready=(g['resolved']==g['items'] and g['mapping_resolved']==g['items'])
  qs=[qid for qid,conditions in key.get('question_conditions',{}).items() if name in conditions]
  validity_resolved=bool(qs) and all(type(tables[0][qid]['valid']) is bool and tables[0][qid]['valid']==tables[1][qid]['valid'] for qid in qs)
  dimensions={key['items'][qid]['dimension'] for qid in qs if tables[0][qid]['valid'] is True and tables[1][qid]['valid'] is True}
  conditions.append({'condition':name,'study':g['study'],'responses':g['items'],'resolved':g['resolved'],'mapping_resolved':g['mapping_resolved'],'category_coverage':len(dimensions)/4 if validity_resolved else None,'known_defect_ids':sorted(g['known']),'discovered_defect_ids':sorted(g['discovered']),'failure_discovery_rate':fraction(len(g['discovered']),len(g['known'])) if g['study']=='A' and ready else None})
 question_issues=any(item['kind']=='question' and any(t[ident]['valid'] is not True for t in tables) for ident,item in material['items'].items())
 formal_ready=not(exposed or known_exposed or unresolved or reference_disagreements or missing_notes)
 return {'scope':'Two-return retrospective reference calibration; not proof of identities, preregistration, representativeness or generalisation','reviewer_ids':[r['reviewer_id'] for r in reviews],'independent_blind_declarations_eligible':not(exposed or known_exposed),'formal_ready':formal_ready,'unresolved_item_ids':unresolved,'reference_or_mapping_disagreements':reference_disagreements,'additional_fact_reconciliation_required':missing_notes,'invalid_or_uncertain_question_review':question_issues,'failure_detection':detection,'failure_classification':{'counts':dict(class_counts),'accuracy_on_classified':fraction(class_counts['correct'],class_counts['classified']),'joint_detection_classification_recall':fraction(class_counts['correct'],class_counts['typed_reference'])},'test_validity':fraction(counts['question']['valid'],counts['question']['resolved']),'memory_extraction_precision':fraction(counts['candidate']['valid'],counts['candidate']['resolved']),'memory_reference_unit_recall':fraction(counts['reference']['covered'],counts['reference']['gold_units']) if not missing_notes and counts['reference']['coverage_resolved']==counts['reference']['gold_units'] else None,'relationship_accuracy_on_declared_pairs':fraction(counts['relationship']['correct'],counts['relationship']['resolved']),'critical_errors':dict(crit),'conditions':conditions,'formal_failure_discovery_rates':[{**x,'failure_discovery_rate':x['failure_discovery_rate'] if not(exposed or known_exposed) else None} for x in conditions if x['study']=='A'],'server_import_performed':False}

def main():
 p=argparse.ArgumentParser();p.add_argument('bundle',type=Path);p.add_argument('reviewer1',type=Path);p.add_argument('reviewer2',type=Path);p.add_argument('output',type=Path);p.add_argument('--known-exposed-reviewer',action='append',default=[],help='Reviewer known to have seen outcomes or earlier labels in this review phase; repeat for each person.');a=p.parse_args()
 key=json.loads((a.bundle/'private/key.json').read_text());material=json.loads((a.bundle/'private/material.json').read_text());reviews=[json.loads(x.read_text()) for x in [a.reviewer1,a.reviewer2]];result=analyse(material,key,reviews,a.known_exposed_reviewer)
 if a.output.exists():raise SystemExit('Refuse to overwrite existing analysis')
 a.output.write_text(json.dumps(result,indent=2));print('Analysis saved; formal_ready='+str(result['formal_ready']))
if __name__=='__main__':main()
