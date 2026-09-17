import { useState } from 'react';
import { api } from '../services/api';
import type { Dimension, EvaluationCalibrationSummary, EvaluationReviewItem, HumanReviewRole } from '../types/domain';

const labels: Record<Dimension, string> = {
  accuracy: 'Accuracy', freshness: 'Freshness',
  conflict_resolution: 'Conflict Resolution', appropriate_use: 'Appropriate Use',
};

const percent = (value: number | null) => value === null ? 'Not measured' : `${value.toFixed(1)}%`;

/** Human labels are separate calibration evidence; they never change an audit verdict. */
export function EvaluationReview({ runId }: { runId: string }) {
  const [items, setItems] = useState<EvaluationReviewItem[] | null>(null);
  const [summary, setSummary] = useState<EvaluationCalibrationSummary | null>(null);
  const [reviewer, setReviewer] = useState('researcher-1');
  const [reviewRole, setReviewRole] = useState<HumanReviewRole>('independent');
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [failureDimensions, setFailureDimensions] = useState<Record<string, Dimension>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setBusy(true); setError('');
    try {
      setItems(await api.evaluationReview(runId));
      setSummary(await api.evaluationCalibration(runId));
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Evaluation review could not be loaded.'); }
    finally { setBusy(false); }
  };
  const save = async (item: EvaluationReviewItem, humanPassed: boolean) => {
    setBusy(true); setError('');
    try {
      await api.reviewEvaluation(runId, item.automated.evaluation_id, {
        human_passed: humanPassed,
        // An independent reviewer must decide the failure class themselves;
        // copying the automated dimension would invalidate dimension-level
        // calibration even if the PASS/FAIL label were independently chosen.
        human_failure_type: humanPassed ? null : failureDimensions[item.automated.evaluation_id] ?? item.test.dimension,
        reviewer_label: reviewer.trim() || 'researcher',
        review_role: reviewRole,
        based_on_review_ids: reviewRole === 'adjudication'
          ? item.human_reviews.filter((review) => review.review_role === 'independent').map((review) => review.review_id)
          : [],
        note: notes[item.automated.evaluation_id] || undefined,
      });
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The human review could not be saved.');
      setBusy(false);
    }
  };

  const blindIndependentReview = reviewRole === 'independent';
  return <section className="evaluation-review" aria-label="Evaluator calibration review">
    <div className="failure-heading"><div><h2>Evaluator Calibration Review</h2><p>{blindIndependentReview ? 'Independent mode is blind: review the question and response without seeing the automated verdict or other reviewers. Your label is calibration evidence and never overwrites the original audit result.' : 'Reference and adjudication modes show saved evidence for reconciliation; human labels never overwrite the original audit result.'}</p></div>{!items && <button type="button" className="secondary" disabled={busy} onClick={load}>{busy ? 'Loading reviews…' : 'Review Evaluations'}</button>}</div>
    {error && <p className="alert" role="alert">{error}</p>}
    {!blindIndependentReview && summary && <><p className="calibration-summary"><b>{summary.human_reviewed_count}</b> resolved labels · automated agreement {percent(summary.agreement_percentage)} · failure precision {percent(summary.failure_precision)} · recall {percent(summary.failure_recall)} · F1 {percent(summary.failure_f1)}</p><p className="calibration-summary"><b>{summary.independent_review_count}</b> independent labels across {summary.independently_reviewed_evaluation_count} evaluations · consensus {summary.independent_consensus_count} · conflicts {summary.independent_conflict_count} · pairwise κ {summary.independent_pair_kappa === null ? 'Not measured' : summary.independent_pair_kappa.toFixed(2)}</p></>}
    {items && <><div className="form-grid"><label>Reviewer pseudonym<input aria-label="Reviewer pseudonym" value={reviewer} maxLength={80} onChange={(event) => setReviewer(event.target.value)} /></label><label>Review role<select aria-label="Evaluation review role" value={reviewRole} onChange={(event) => setReviewRole(event.target.value as HumanReviewRole)}><option value="independent">Independent reviewer</option><option value="reference">Reference label</option><option value="adjudication">Adjudication</option></select><small>{blindIndependentReview ? 'Independent labels are blind and remain separate until adjudication.' : 'Adjudication cites all independent labels for each evaluation.'}</small></label></div><div className="evaluation-review-list">{items.map((item) => <article key={item.automated.evaluation_id} className="evaluation-review-card"><div className="row"><b>{labels[item.test.dimension]}</b><span>{blindIndependentReview ? 'Blind independent label' : `Automated: ${item.automated.passed ? 'Pass' : 'Fail'}`}</span></div><p><small>{item.test.prompt}</small></p><p><small>Response: {item.response.response_text}</small></p><label>Failure dimension<select aria-label={`Failure dimension ${item.automated.evaluation_id}`} value={failureDimensions[item.automated.evaluation_id] ?? item.test.dimension} onChange={(event) => setFailureDimensions((current) => ({ ...current, [item.automated.evaluation_id]: event.target.value as Dimension }))}><option value="accuracy">Accuracy</option><option value="freshness">Freshness</option><option value="conflict_resolution">Conflict Resolution</option><option value="appropriate_use">Appropriate Use</option></select><small>Used only if you choose Fail.</small></label><label>Calibration note<input aria-label={`Calibration note ${item.automated.evaluation_id}`} value={notes[item.automated.evaluation_id] ?? (blindIndependentReview ? '' : item.human_review?.note ?? '')} onChange={(event) => setNotes((current) => ({ ...current, [item.automated.evaluation_id]: event.target.value }))} /></label><div><button type="button" className="secondary" disabled={busy || (reviewRole === 'adjudication' && !item.human_reviews.some((review) => review.review_role === 'independent'))} onClick={() => save(item, true)}>{reviewRole === 'adjudication' ? 'Adjudicate: Pass' : 'Human: Pass'}</button><button type="button" disabled={busy || (reviewRole === 'adjudication' && !item.human_reviews.some((review) => review.review_role === 'independent'))} onClick={() => save(item, false)}>{reviewRole === 'adjudication' ? 'Adjudicate: Fail' : 'Human: Fail'}</button></div>{!blindIndependentReview && <>{item.human_reviews.length > 0 && <ul className="review-label-list">{item.human_reviews.map((review) => <li key={review.review_id}>{review.review_role}: {review.human_passed ? 'Pass' : 'Fail'} · {review.reviewer_label}</li>)}</ul>}{item.human_review && <small>Resolved label: {item.human_review.human_passed ? 'Pass' : 'Fail'} · {item.human_review.review_role}</small>}</>}</article>)}</div></>}
  </section>;
}
