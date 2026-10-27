"""Close AI-assisted A reference analysis without inventing formal blind gold/mappings."""
import collections,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'artifacts/local/phase4-20261027'
def analyse(a,revision,cross):
 labels={r['response_id']:r for r in revision['common_labels_adopted_by_both_reviewers']};cases={r['response_id']:r for r in cross['cases']}
 assert len(labels)==len(cases)==36 and set(labels)==set(cases)
 groups=[];mapping=[]
 for name in sorted({r['label'] for h in a['scenarios'] for r in h['runs']}):
  counts=collections.Counter();fail_classified=correct_class=0
  for h in a['scenarios']:
   run=next(r for r in h['runs'] if r['label']==name);by_id={r['response_id']:r for r in run['responses']}
   assert len(run['responses'])==4
   for e in run['evaluations']:
    ident=e['response_id'];label=labels[ident];verdict=label['verdict'];prediction=e['passed'];counts['total']+=1
    if verdict=='uncertain':counts['uncertain_reference']+=1
    else:
     counts['decided_reference']+=1;failure=verdict=='fail';counts['reference_fail' if failure else 'reference_pass']+=1
     if prediction is None:counts['automated_uncertain']+=1
     else:counts[{(True,False):'tp',(True,True):'fn',(False,False):'fp',(False,True):'tn'}[(failure,prediction)]]+=1
     if failure:
      classified=(e.get('failure_classification') or {}).get('status')=='classified'
      fail_classified+=int(classified);correct_class+=int(classified and e.get('failure_type')==label['failure_dimension'])
    # A taxonomy match is NOT inferred from a test dimension. These actual
    # responses omit facts or abstain; they do not apply Python, choose North/
    # South, or clearly assert MySQL as current. Preserve interpretation issues.
    response=by_id[ident]['response_text']
    if verdict=='fail':assert not any(token in response for token in ['Java','Python','North','South','PostgreSQL'])
    mapping.append({'response_id':ident,'run_id':run['run_id'],'reference_verdict':verdict,'frozen_defect_ids':None,'AI_mapping_status':'reference_uncertain' if verdict=='uncertain' else 'no_failure' if verdict=='pass' else 'inventory_definition_review_required','reason':'Frozen definitions describe affirmative stale/preference/conflict-choice errors. Actual omission/abstention is not automatically the same defect. Historical-MySQL wording needs explicit interpretation; no frozen inventory was edited.','observed_answer':response})
  def fraction(n,d):return n/d if d else None
  groups.append({'method':name,'counts':dict(counts),'conditional_precision':fraction(counts['tp'],counts['tp']+counts['fp']),'conditional_recall':fraction(counts['tp'],counts['tp']+counts['fn']),'conditional_false_positive_rate':fraction(counts['fp'],counts['fp']+counts['tn']),'classification_coverage_on_reference_failures':fraction(fail_classified,counts['reference_fail']),'classification_accuracy_among_classified':fraction(correct_class,fail_classified),'joint_detection_and_classification_recall':fraction(correct_class,counts['reference_fail']),'failure_discovery_rate':None})
 assert len(mapping)==36 and len({x['response_id'] for x in mapping})==36
 return {'scope':'Exploratory AI-assisted reference calibration following user-reported agreement; not independent blind reliability evidence','uncertain_policy':'Keep all6 ambiguous answers uncertain; exclude from decided-only reference metrics; preserve original automatic results','methods':groups,'formal_failure_discovery_rate':None,'formal_failure_detection_recall':None,'formal_status':'Not certified:6 unresolved references, incomplete explicit defect mapping and shared AI-result exposure','reference_authorship':'Chat-confirmed adoption of the AI case review; not separately authored blinded worksheets','mapping_review':mapping,'pipeline_changes':False,'new_model_calls':0}
def main():
 a=json.loads((D/'A-live.json').read_text());revision=json.loads((D/'human-reconciliation/A-chat-confirmed-revision-v1.json').read_text());cross=json.loads((D/'A-AI-cross-check.json').read_text())
 out=D/'human-reconciliation/A-reference-analysis-v1.json'
 if out.exists():raise SystemExit('Refuse to overwrite prior reference analysis')
 result=analyse(a,revision,cross);result['source_sha256']={name:hashlib.sha256((D/name).read_bytes()).hexdigest() for name in ['A-live.json','A-AI-cross-check.json','human-reconciliation/A-chat-confirmed-revision-v1.json']};out.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(out)
if __name__=='__main__':main()
