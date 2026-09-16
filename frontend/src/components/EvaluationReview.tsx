import { useState } from 'react';
import { api } from '../services/api';
import type { Dimension, EvaluationCalibrationSummary, EvaluationReviewItem } from '../types/domain';

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
  const [notes, setNotes] = useState<Record<string, string>>({});
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
        human_failure_type: humanPassed ? null : item.automated.failure_type ?? item.test.dimension,
        reviewer_label: reviewer.trim() || 'researcher',
        note: notes[item.automated.evaluation_id] || undefined,
      });
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The human review could not be saved.');
      setBusy(false);
    }
  };

  return <section className="evaluation-review" aria-label="Evaluator calibration review">
    <div className="failure-heading"><div><h2>Evaluator Calibration Review</h2><p>Independently review automated verdicts. Human labels are calibration evidence and never overwrite the original audit result.</p></div>{!items && <button type="button" className="secondary" disabled={busy} onClick={load}>{busy ? 'Loading reviews…' : 'Review Evaluations'}</button>}</div>
    {error && <p className="alert" role="alert">{error}</p>}
    {summary && <p className="calibration-summary"><b>{summary.human_reviewed_count}</b> human-reviewed · agreement {percent(summary.agreement_percentage)} · failure precision {percent(summary.failure_precision)} · recall {percent(summary.failure_recall)} · F1 {percent(summary.failure_f1)}</p>}
    {items && <><label>Reviewer pseudonym<input aria-label="Reviewer pseudonym" value={reviewer} maxLength={80} onChange={(event) => setReviewer(event.target.value)} /></label><div className="evaluation-review-list">{items.map((item) => <article key={item.automated.evaluation_id} className="evaluation-review-card"><div className="row"><b>{labels[item.test.dimension]}</b><span>Automated: {item.automated.passed ? 'Pass' : 'Fail'}</span></div><p><small>{item.test.prompt}</small></p><p><small>Response: {item.response.response_text}</small></p><label>Calibration note<input aria-label={`Calibration note ${item.automated.evaluation_id}`} value={notes[item.automated.evaluation_id] ?? item.human_review?.note ?? ''} onChange={(event) => setNotes((current) => ({ ...current, [item.automated.evaluation_id]: event.target.value }))} /></label><div><button type="button" className="secondary" disabled={busy} onClick={() => save(item, true)}>Human: Pass</button><button type="button" disabled={busy} onClick={() => save(item, false)}>Human: Fail</button></div>{item.human_review && <small>Saved human verdict: {item.human_review.human_passed ? 'Pass' : 'Fail'} · {item.human_review.reviewer_label}</small>}</article>)}</div></>}
  </section>;
}
