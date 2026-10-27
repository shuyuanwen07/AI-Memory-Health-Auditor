"""Read-only validation of two real independent returns. No label fabrication."""
import argparse,collections,json
from pathlib import Path
DIMS={'accuracy','freshness','conflict_resolution','appropriate_use'}
def ratio(n,d):return n/d if d else None
def indexed(rows,expected):
 ids=[r['item_id'] for r in rows]
 if len(ids)!=len(set(ids)) or set(ids)!=set(expected):raise ValueError('Missing, duplicate or unexpected item IDs')
 return {r['item_id']:r for r in rows}
def analyse(manifest,key,returns):
 if len(returns)!=2:raise ValueError('Exactly two independent returns required')
 names=[str(r.get('reviewer_id') or '').strip().casefold() for r in returns]
 if not all(names) or len(set(names))!=2:raise ValueError('Two distinct nonblank reviewer pseudonyms required')
 if not all(r.get('independently_completed') is True for r in returns):raise ValueError('Actual independent review declaration is missing')
 refs=[];questions=[]
 for r in returns:
  if manifest.get('material_sha256') and r.get('material_sha256') not in manifest['material_sha256']:raise ValueError('Source material fingerprint differs from the frozen packet')
  rows=indexed(r['response_labels'],manifest['response_items']);qs=indexed(r['question_labels'],manifest['question_items']);indexed(r['extraction_labels'],manifest['extraction_items'])
  for row in rows.values():
   if row['verdict'] not in {'pass','fail','uncertain'}:raise ValueError('Incomplete or invalid response verdict')
   if row['verdict']=='fail' and row['failure_dimension'] not in DIMS:raise ValueError('Failed response needs an observed failure dimension')
   if row['verdict']!='fail' and row['failure_dimension'] is not None:raise ValueError('Non-failure must not have a failure classification')
   scenario=key[row['item_id']]['scenario_id'];valid_ids={m['message_id'] for q in manifest['question_source'] if q['item_id'].startswith(scenario+'-') for m in q['source_messages']}
   if not row['source_message_ids'] or not set(row['source_message_ids']).issubset(valid_ids):raise ValueError('Missing or invalid source citations')
  if any(type(q['valid']) is not bool for q in qs.values()):raise ValueError('Question validity requires true/false decisions')
  refs.append(rows);questions.append(qs)
 counts=collections.Counter();disagreements=[];classification_correct=classification_total=0;complete_gold=True
 for ident in manifest['response_items']:
  left,right=refs[0][ident],refs[1][ident]
  if (left['verdict'],left['failure_dimension'])!=(right['verdict'],right['failure_dimension']):
   disagreements.append(ident);complete_gold=False;continue
  actual=left['verdict'];auto=key[ident]['automated'];pred=auto['passed']
  if actual=='uncertain':counts['human_uncertain']+=1;complete_gold=False;continue
  counts['human_failure' if actual=='fail' else 'human_pass']+=1
  if pred is None:counts['automated_uncertain']+=1;continue
  counts[{('fail',False):'tp',('fail',True):'fn',('pass',False):'fp',('pass',True):'tn'}[(actual,pred)]]+=1
  if actual=='fail' and pred is False:
   classification_total+=1
   classification=auto.get('failure_classification') or {}
   classification_correct+=int(classification.get('status')=='classified' and auto.get('failure_type')==left['failure_dimension'])
 tp,fp,fn,tn=(counts[k] for k in ['tp','fp','fn','tn']);p=ratio(tp,tp+fp);recall=ratio(tp,tp+fn)
 agreement=sum(refs[0][i]['verdict']==refs[1][i]['verdict'] for i in manifest['response_items'])/len(manifest['response_items'])
 marginals=[collections.Counter(x[i]['verdict'] for i in manifest['response_items']) for x in refs];n=len(manifest['response_items']);chance=sum(marginals[0][v]*marginals[1][v] for v in ['pass','fail','uncertain'])/n**2
 q_agreed=[questions[0][i]['valid'] for i in manifest['question_items'] if questions[0][i]['valid']==questions[1][i]['valid']]
 return {'provenance':'Self-declared independent human returns; identities and independence not authenticated by software','counts':dict(counts),'unresolved_disagreements':disagreements,'complete_resolved_gold':complete_gold,'failure_precision_decided':p,'failure_recall_decided':recall,'failure_recall_all_agreed_human_failures':ratio(tp,counts['human_failure']),'failure_f1_decided':2*p*recall/(p+recall) if p is not None and recall is not None and p+recall else None,'false_positive_rate_decided':ratio(fp,fp+tn),'failure_classification_correct':classification_correct,'failure_classification_total_detected_failures':classification_total,'failure_classification_accuracy_detected_failures':ratio(classification_correct,classification_total),'question_validity_agreed':ratio(sum(q_agreed),len(q_agreed)),'question_validity_resolved_count':len(q_agreed),'response_verdict_agreement':agreement,'cohens_kappa':(agreement-chance)/(1-chance) if chance<1 else None,'memory_extraction_precision_recall':None,'relationship_classification_accuracy':None,'extraction_relationship_status':'Await source-bound fact-unit reconciliation and adjudication; free-text missing facts are not automatically equated across people','failure_discovery_rate':None,'failure_discovery_status':'Experiment A inventory and response-defect mapping require separate researcher releases'}
def main():
 p=argparse.ArgumentParser();p.add_argument('private_directory',type=Path);p.add_argument('reviewer_1',type=Path);p.add_argument('reviewer_2',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
 result=analyse(json.loads((a.private_directory/'review-manifest.json').read_text()),json.loads((a.private_directory/'identity-key.json').read_text()),[json.loads(f.read_text()) for f in [a.reviewer_1,a.reviewer_2]])
 if a.output.exists():raise SystemExit('Refusing to overwrite a prior human analysis')
 a.output.write_text(json.dumps(result,indent=2));print(a.output)
if __name__=='__main__':main()
