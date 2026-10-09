import { UIAlert, UICard } from './ui';
import { UIButton, UIInput, UISelect, UIOption } from './ui';
import { useState } from 'react';
import { api } from '../services/api';
import { friendlyText } from '../services/display';
import type { Dimension, EvaluationCalibrationSummary, BlindEvaluationReviewItem, EvaluationReviewItem, HumanReviewRole } from '../types/domain';

const labels: Record<Dimension, string> = {
  accuracy: 'Accuracy', freshness: 'Freshness',
  conflict_resolution: 'Conflict Resolution', appropriate_use: 'Appropriate Use',
};

const percent = (value: number | null) => value === null ? 'Not measured' : `${value.toFixed(1)}%`;

/** Human labels are separate calibration evidence; they never change an audit verdict. */
export function EvaluationReview({ runId, independentOnly = false }: { runId: string; independentOnly?: boolean }) {
  const [items, setItems] = useState<Array<BlindEvaluationReviewItem | EvaluationReviewItem> | null>(null);
  const [summary, setSummary] = useState<EvaluationCalibrationSummary | null>(null);
  const [reviewer, setReviewer] = useState('researcher-1');
  const [reviewRole, setReviewRole] = useState<HumanReviewRole>('independent');
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [failureDimensions, setFailureDimensions] = useState<Record<string, Dimension>>({});
  const [savedLabels, setSavedLabels] = useState<Record<string, { humanPassed: boolean; reviewRole: HumanReviewRole }>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setBusy(true); setError('');
    try {
      setItems(await (reviewRole === "independent" ? api.blindEvaluationReview(runId) : api.evaluationReview(runId)));
      setSummary(reviewRole === "independent" ? null : await api.evaluationCalibration(runId));
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Evaluation review could not be loaded.'); }
    finally { setBusy(false); }
  };
  const save = async (item: BlindEvaluationReviewItem | EvaluationReviewItem, humanPassed: boolean) => {
    if (!humanPassed && reviewRole === 'independent' && !failureDimensions[item.automated.evaluation_id]) {
      setError('Choose a failure dimension before saving an independent Fail label.');
      return;
    }
    setBusy(true); setError('');
    try {
      await api.reviewEvaluation(runId, item.automated.evaluation_id, {
        human_passed: humanPassed,
        // An independent reviewer must decide the failure class themselves;
        // copying the automated dimension would invalidate dimension-level
        // calibration even if the PASS/FAIL label were independently chosen.
        human_failure_type: humanPassed ? null : failureDimensions[item.automated.evaluation_id] ?? (reviewRole === 'independent' ? null : item.test.dimension ?? null),
        reviewer_label: reviewer.trim() || 'researcher',
        review_role: reviewRole,
        based_on_review_ids: reviewRole === 'adjudication'
          ? item.human_reviews.filter((review) => review.review_role === 'independent').map((review) => review.review_id)
          : [],
        note: notes[item.automated.evaluation_id] || undefined,
      });
      setSavedLabels((current) => ({
        ...current,
        [item.automated.evaluation_id]: { humanPassed, reviewRole },
      }));
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The human review could not be saved.');
      setBusy(false);
    }
  };

  const blindIndependentReview = reviewRole === 'independent';
  return <section className="evaluation-review" aria-label="Evaluator calibration review">
    <div className="failure-heading"><div><h2>Evaluator Calibration Review</h2><p>{blindIndependentReview ? 'Independent mode is blind: review the question, reference behaviour and response without seeing the automated verdict or other reviewers. Your label is calibration evidence and never overwrites the original audit result.' : 'Reference and adjudication modes show saved evidence for reconciliation; human labels never overwrite the original audit result.'}</p></div>{!items && <UIButton type="button" className="secondary" disabled={busy} onClick={load}>{busy ? 'Loading reviews…' : 'Review Evaluations'}</UIButton>}</div>
    {error && <UIAlert className="alert" role="alert">{error}</UIAlert>}
    {!blindIndependentReview && summary && <><p className="calibration-summary"><b>{summary.human_reviewed_count}</b> resolved labels · automated agreement {percent(summary.agreement_percentage)} · failure precision {percent(summary.failure_precision)} · recall {percent(summary.failure_recall)} · F1 {percent(summary.failure_f1)}</p><p className="calibration-summary"><b>{summary.independent_review_count}</b> independent labels across {summary.independently_reviewed_evaluation_count} evaluations · consensus {summary.independent_consensus_count} · conflicts {summary.independent_conflict_count} · pairwise κ {summary.independent_pair_kappa === null ? 'Not measured' : summary.independent_pair_kappa.toFixed(2)}</p></>}
    {items && <><div className="form-grid"><label>Reviewer pseudonym<UIInput aria-label="Reviewer pseudonym" value={reviewer} maxLength={80} onChange={(event) => setReviewer(event.target.value)} /></label><label>Review role<UISelect aria-label="Evaluation review role" disabled={independentOnly} value={reviewRole} onChange={(event) => {setReviewRole(event.target.value as HumanReviewRole);setItems(null);setSummary(null);setSavedLabels({});setFailureDimensions({});}}><UIOption value="independent">Independent reviewer</UIOption><UIOption value="reference">Reference label</UIOption><UIOption value="adjudication">Adjudication</UIOption></UISelect><small>{blindIndependentReview ? 'Independent labels are blind and remain separate until adjudication.' : 'Adjudication cites all independent labels for each evaluation.'}</small></label></div><div className="evaluation-review-list">{items.map((item, index) => { const saved = savedLabels[item.automated.evaluation_id]; return <UICard key={item.automated.evaluation_id} className="evaluation-review-card"><div className="row"><b>{blindIndependentReview ? `Response ${index + 1}` : (item.test.dimension ? labels[item.test.dimension] : 'Response')}</b><span>{blindIndependentReview ? 'Blind independent label' : `Automated: ${item.automated.passed === null ? 'Uncertain' : item.automated.passed ? 'Pass' : 'Fail'}`}</span></div><p><small>{item.test.prompt}</small></p><p className="review-reference"><small><b>Reference behaviour:</b> {item.test.expected_behavior}</small></p><p><small>Response: {item.response.response_text}</small></p>{!blindIndependentReview && 'reason' in item.automated && <p className="review-evaluator-reason"><small><b>Automated assessment reasoning:</b> {friendlyText(item.automated.reason)}</small></p>}{!blindIndependentReview && 'reason' in item.automated && <p className="review-execution-evidence"><small>{item.automated.judge_execution ? <>Assessment requests: {item.automated.judge_execution.request_attempts} · failed HTTP attempts: {item.automated.judge_execution.failed_http_attempts} · elapsed: {(item.automated.judge_execution.elapsed_ms / 1000).toFixed(2)} s · reported tokens: {item.automated.judge_execution.reported_total_tokens ?? 'Unknown'}<br/>Usage covers the last successful provider reply. Failed-attempt usage and monetary cost are unknown.</> : 'Assessment request evidence was not recorded for this result. Costs remain unknown.'}</small></p>}{blindIndependentReview&&<div><b>Supporting source statements</b>{'source_statements' in item && item.source_statements?.length?<ul>{item.source_statements.map((source,index)=><li key={index}>{source.content} <small>· {new Date(source.timestamp).toLocaleString()}</small></li>)}</ul>:<p>No source excerpts are available. Verify the reference separately before submitting a label.</p>}</div>}<label>Failure dimension<UISelect aria-label={`Failure dimension ${index + 1}`} value={failureDimensions[item.automated.evaluation_id] ?? (blindIndependentReview ? '' : item.test.dimension ?? '')} onChange={(event) => setFailureDimensions((current) => ({ ...current, [item.automated.evaluation_id]: event.target.value as Dimension }))}><UIOption value="" disabled>Choose a failure dimension</UIOption><UIOption value="accuracy">Accuracy</UIOption><UIOption value="freshness">Freshness</UIOption><UIOption value="conflict_resolution">Conflict Resolution</UIOption><UIOption value="appropriate_use">Appropriate Use</UIOption></UISelect><small>{blindIndependentReview ? 'Choose independently before selecting Fail; Pass needs no failure category.' : 'Used only if you choose Fail.'}</small></label><label>Calibration note<UIInput aria-label={`Calibration note ${index + 1}`} value={notes[item.automated.evaluation_id] ?? (blindIndependentReview ? '' : item.human_review?.note ?? '')} onChange={(event) => setNotes((current) => ({ ...current, [item.automated.evaluation_id]: event.target.value }))} /></label><div><UIButton type="button" className="secondary" disabled={busy || (reviewRole === 'adjudication' && new Set(item.human_reviews.filter(review => review.review_role === 'independent').map(review => review.reviewer_label)).size < 2)} onClick={() => save(item, true)}>{reviewRole === 'adjudication' ? 'Adjudicate: Pass' : 'Human: Pass'}</UIButton><UIButton type="button" disabled={busy || (blindIndependentReview && !failureDimensions[item.automated.evaluation_id]) || (reviewRole === 'adjudication' && new Set(item.human_reviews.filter(review => review.review_role === 'independent').map(review => review.reviewer_label)).size < 2)} onClick={() => save(item, false)}>{reviewRole === 'adjudication' ? 'Adjudicate: Fail' : 'Human: Fail'}</UIButton></div>{saved && <p className="review-save-confirmation" role="status">Your {saved.reviewRole} label was saved: <b>{saved.humanPassed ? 'Pass' : 'Fail'}</b>. It is recorded as calibration evidence.</p>}{!blindIndependentReview && <>{item.human_reviews.length > 0 && <ul className="review-label-list">{item.human_reviews.map((review) => <li key={review.review_id}>{review.review_role}: {review.human_passed ? 'Pass' : 'Fail'} · {review.reviewer_label}</li>)}</ul>}{item.human_review && <small>Resolved label: {item.human_review.human_passed ? 'Pass' : 'Fail'} · {item.human_review.review_role}</small>}</>}</UICard>; })}</div></>}
  </section>;
}
