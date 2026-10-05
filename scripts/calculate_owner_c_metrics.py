"""Compute step 5 metrics from the hash-verified, adjudicated response release."""
import csv
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.schemas import EvaluationResult
from app.metrics.validity import AuditorValidityService
from app.metrics.service import MetricsService

BASE=ROOT/'artifacts/local/owner-c-heldout-v1'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def passed(value):
    value=value.strip().lower()
    if value not in {'true','false'}:raise ValueError(f'Invalid boolean: {value}')
    return value=='true'
def read(path):
    for enc in ('utf-8-sig','gb18030'):
        try:return list(csv.DictReader(io.StringIO(path.read_bytes().decode(enc))))
        except UnicodeError:pass
    raise ValueError('Unknown CSV encoding')

def main():
    step4=json.loads((ROOT/'handoff/owner-c/step4_comparison.json').read_text())
    final_path=BASE/'response_adjudication_final.csv'
    assert step4['status']=='completed' and sha(final_path)==step4['final_adjudication_sha256']
    freeze=json.loads((BASE/'freeze_manifest.json').read_text())
    assert sha(BASE/'frozen_suite.json')==freeze['suite_sha256']
    assert sha(BASE/'configuration.json')==freeze['configuration_sha256']
    results=json.loads((BASE/'results.json').read_text())
    final=read(final_path); labels={r['test_id']:passed(r['final_passed']) for r in final}
    assert len(final)==len(labels)==len(results)==9
    assert set(labels)=={r['test']['test_id'] for r in results}
    evaluations=[EvaluationResult.model_validate(r['evaluation']) for r in results]
    validity=asdict(AuditorValidityService().calculate(evaluations,labels))
    dimensions={r['test']['test_id']:r['test']['dimension'] for r in results}
    automated_overall,automated_scores=MetricsService().calculate(evaluations,dimensions)
    human_evaluations=[e.model_copy(update={'passed':labels[e.test_id],'failure_type':None if labels[e.test_id] else dimensions[e.test_id]}) for e in evaluations]
    human_overall,human_scores=MetricsService().calculate(human_evaluations,dimensions)
    per_dimension=[]
    for auto,human in zip(automated_scores,human_scores):
        ids={t for t,d in dimensions.items() if d==auto.dimension}
        per_dimension.append({'dimension':auto.dimension.value,'tests':auto.total,'automated_passed':auto.passed,
                              'automated_score':auto.percentage,'reference_passed':human.passed,'reference_score':human.percentage,
                              'evaluator_validity':asdict(AuditorValidityService().calculate([e for e in evaluations if e.test_id in ids],{t:labels[t] for t in ids}))})
    a,b=[read(BASE/n) for n in ('actual_response_review_1.csv','actual_response_review_2.csv')]
    for n in ('actual_response_review_1.csv','actual_response_review_2.csv'):
        assert sha(BASE/n)==step4['raw_review_sha256'][n]
    first={r['test_id']:passed(r['human_passed']) for r in a};second={r['test_id']:passed(r['human_passed']) for r in b}
    assert first.keys()==second.keys()==labels.keys()
    tp=sum(not first[t] and not second[t] for t in first)
    fp=sum(first[t] and not second[t] for t in first)
    tn=sum(first[t] and second[t] for t in first)
    fn=sum(not first[t] and second[t] for t in first)
    descriptive={'compared_rows':len(first),'verdict_agreements':tp+tn,'verdict_agreement_percent':round((tp+tn)/len(first)*100,1),
                 'verdict_cohens_kappa':AuditorValidityService._kappa(tp,fp,tn,fn),
                 'verdict_and_dimension_agreements':step4['raw_verdict_and_dimension_agreements'],
                 'qualification':'Descriptive worksheet agreement only, not independent blind human inter-rater reliability. Reviewer 1 received assistant judgement suggestions; reviewer 2 independence has not been established.'}
    report={'recorded_on':'2026-10-05','positive_class':'failure','reference':'User-confirmed step 4 adjudication',
            'input_sha256':{'final_adjudication':sha(final_path),'results':sha(BASE/'results.json'),'frozen_suite':sha(BASE/'frozen_suite.json')},
            'evaluator_validity':validity,'failure_f1':round(200 * validity['true_positives'] / (2 * validity['true_positives'] + validity['false_positives'] + validity['false_negatives']), 1) if (2 * validity['true_positives'] + validity['false_positives'] + validity['false_negatives']) else None,
            'failure_f1_note':'Computed directly as 2TP/(2TP+FP+FN); precision is separately undefined when no failure was predicted.',
            'automated_macro_dimension_score':automated_overall,'reference_macro_dimension_score':human_overall,
            'reference_micro_test_pass_rate':round(sum(labels.values())/len(labels)*100,1),
            'by_dimension':per_dimension,'raw_worksheet_agreement':descriptive,
            'coverage':{'source_scenarios':8,'scenarios_with_tests':7,'tests':9,'measured_dimensions':2,'unmeasured_dimensions':['freshness','conflict_resolution'],'empty_suite_scenarios':['A004']},
            'limitations':['Nine tests, including only one reference failure, cannot support broad generalisation.','Freshness and conflict-resolution dimensions were not tested; unmeasured scores are null, not zero.','Generic prompts allow more than one source-supported relevant fact; adjudication used a stated non-exhaustive-answer interpretation.','Suite expectations were derived from extracted memories, so automated pass scores alone do not establish extraction correctness.','Only the deterministic WEAK target was run; there is no paired strategy/model comparison or stochastic variance estimate.','Actual-reference provenance is qualified and does not establish two independent blind annotators.','This source-only engineering runner does not execute the persisted web application target-memory lifecycle.']}
    (ROOT/'handoff/owner-c/step5_metrics.json').write_text(json.dumps(report,indent=2)+'\n')
    with (ROOT/'handoff/owner-c/step5_dimension_scores.csv').open('w',newline='') as f:
        fields=['dimension','tests','automated_passed','automated_score','reference_passed','reference_score']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:r[k] for k in fields} for r in per_dimension)
    # Check independently derived contingency counts against the existing service.
    assert validity['true_positives']==0 and validity['false_positives']==0 and validity['true_negatives']==8 and validity['false_negatives']==1
    assert validity['accuracy']==88.9 and validity['failure_recall']==0.0 and validity['cohens_kappa']==0.0
    assert human_overall==50.0 and sum(labels.values())==8
    print(json.dumps({'validity':validity,'reference_macro_score':human_overall,'raw_worksheet_agreement':descriptive},indent=2))

if __name__=='__main__':main()
