import { UIAlert, UICard } from './ui';
import { UIButton, UIInput, UISelect, UIOption, UIPanel, UISummary } from './ui';
import { useState } from 'react';
import { api } from '../services/api';
import { friendlyText } from '../services/display';
import type { Dimension, EvaluationCalibrationSummary, BlindEvaluationReviewItem, EvaluationReviewItem, HumanReviewRole } from '../types/domain';

const labels: Record<Dimension, string> = {
  accuracy: 'Accuracy', freshness: 'Freshness',
  conflict_resolution: 'Conflict Resolution', appropriate_use: 'Appropriate Use',
};

const percent = (value: number | null) => value === null ? 'Not measured' : `${value.toFixed(1)}%`;
function independentReviewerCount(item: BlindEvaluationReviewItem | EvaluationReviewItem) {
  if ('independent_reviewer_count' in item && item.independent_reviewer_count !== undefined) return item.independent_reviewer_count;
  return new Set(item.human_reviews.filter(review => review.review_role === 'independent').map(review => review.reviewer_label.trim().toLowerCase()).filter(Boolean)).size;
}

/** Review labels are separate calibration evidence; they never change an audit verdict. */
export function EvaluationReview(props: { runId: string; independentOnly?: boolean; exposedToAutomatedResults?: boolean }) {
  return <EvaluationReviewSession key={`${props.runId}:${Boolean(props.independentOnly)}:${Boolean(props.exposedToAutomatedResults)}`} {...props}/>;
}

function EvaluationReviewSession({ runId, independentOnly = false, exposedToAutomatedResults = false }: { runId: string; independentOnly?: boolean; exposedToAutomatedResults?: boolean }) {
  const [hasSeenAutomatedResults, setHasSeenAutomatedResults] = useState(exposedToAutomatedResults);
  const exposed = exposedToAutomatedResults || hasSeenAutomatedResults;
  const [items, setItems] = useState<Array<BlindEvaluationReviewItem | EvaluationReviewItem> | null>(null);
  const [sourceHistory, setSourceHistory] = useState<Array<{role?:string;content:string;timestamp:string}>>([]);
  const [summary, setSummary] = useState<EvaluationCalibrationSummary | null>(null);
  const [reviewer, setReviewer] = useState('');
  const [reviewRole, setReviewRole] = useState<HumanReviewRole>(exposedToAutomatedResults ? 'reference' : 'independent');
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [failureDimensions, setFailureDimensions] = useState<Record<string, Dimension>>({});
  const [savedLabels, setSavedLabels] = useState<Record<string, { humanPassed: boolean; reviewRole: HumanReviewRole }>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setBusy(true); setError('');
    try {
      if (reviewRole === 'independent') {
        const answers = await api.blindEvaluationReview(runId);
        setSourceHistory(answers[0]?.source_statements ?? []);
        setItems(answers); setSummary(null);
      } else {
        const [answers, calibration, source] = await Promise.all([
          api.evaluationReview(runId), api.evaluationCalibration(runId), api.auditSourceHistory(runId),
        ]);
        setHasSeenAutomatedResults(true);
        setSourceHistory(source); setItems(answers); setSummary(calibration);
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Evaluation review could not be loaded.'); }
    finally { setBusy(false); }
  };
  const save = async (item: BlindEvaluationReviewItem | EvaluationReviewItem, humanPassed: boolean) => {
    if (exposed && reviewRole === 'independent') {setError('Independent review must be completed by someone who has not seen the automated results.');return;}
    if (!reviewer.trim()) {setError('Enter your reviewer pseudonym before saving a label.');return;}
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
        reviewer_label: reviewer.trim(),
        review_role: reviewRole,
        based_on_review_ids: reviewRole === 'adjudication'
          ? item.human_reviews.filter((review) => review.review_role === 'independent').map((review) => review.review_id)
          : [],
        based_on_review_versions: reviewRole === 'adjudication'
          ? Object.fromEntries(item.human_reviews.filter(review => review.review_role === 'independent').map(review => [review.review_id, review.updated_at]))
          : {},
        note: notes[item.automated.evaluation_id] || undefined,
      });
      setSavedLabels((current) => ({
        ...current,
        [item.automated.evaluation_id]: { humanPassed, reviewRole },
      }));
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The review label could not be saved.');
      setBusy(false);
    }
  };

  const blindIndependentReview = reviewRole === 'independent';
  return <section className="evaluation-review" aria-label="Evaluator calibration review">
    <div className="failure-heading"><div><h2>Evaluator Calibration Review</h2><p>{blindIndependentReview ? 'Independent mode is blind: review the question, reference behaviour and response without seeing the automated verdict or other reviewers. Your label is calibration evidence and never overwrites the original audit result.' : 'Reference and adjudication modes show saved evidence for reconciliation; labels never overwrite the original audit result.'}</p></div>{!items && <UIButton type="button" className="secondary" disabled={busy} onClick={load}>{busy ? 'Loading reviews…' : 'Review Evaluations'}</UIButton>}</div>
    {exposed && <p className="review-instructions"><b>This report has shown the automated results.</b> Your review here is a reference or final decision, not an independent blind review. Ask another reviewer who has not seen these results to use the <a href={`/blind-review/${encodeURIComponent(runId)}`}>separate blind review page</a>.</p>}
    {items && <UIButton type="button" className="secondary" disabled={busy} onClick={load}>{busy ? 'Loading reviews…' : 'Refresh review evidence'}</UIButton>}
    {error && <UIAlert className="alert" role="alert">{error}</UIAlert>}
    {!blindIndependentReview && summary && <><p className="calibration-summary"><b>{summary.human_reviewed_count}</b> resolved labels · automated agreement {percent(summary.agreement_percentage)} · failure precision {percent(summary.failure_precision)} · recall {percent(summary.failure_recall)} · F1 {percent(summary.failure_f1)}</p><p className="calibration-summary"><b>{summary.independent_review_count}</b> independent labels across {summary.independently_reviewed_evaluation_count} evaluations · pass/fail agreement groups {summary.independent_consensus_count} · pass/fail disagreements {summary.independent_conflict_count} · pass/fail pairwise κ {summary.independent_pair_kappa === null ? 'Not measured' : summary.independent_pair_kappa.toFixed(2)}</p><p className="calibration-summary">{summary.independent_failure_category_compared_count===undefined?'Failure-category agreement: Not recorded.':`Failure-category agreement: ${summary.independent_failure_category_compared_count?`${summary.independent_failure_category_agreement_count??0}/${summary.independent_failure_category_compared_count} evaluated groups`:'Not measured'} · ${summary.independent_failure_category_conflict_count??0} category disagreements · ${summary.independent_failure_category_missing_count??0} groups missing categories.`} Categories are compared only when every independent reviewer marks Fail and records a category.</p></>}
    {items && <>
      {items.length === 0 && <p className="empty">There are no assessed answers to review in this batch. Open a completed audit from History.</p>}
      {blindIndependentReview && items.length > 0 && <div className="review-instructions">
        <p><b>Before choosing Pass or Fail</b> · Read the full source, check that the proposed reference is supported, then judge what the answer actually says. Mentioning the right words is not enough if the answer contradicts them.</p>
        <p><b>Choosing a failure category</b> · Accuracy: an incorrect fact. Freshness: an outdated fact. Conflict Resolution: unresolved requirements are ignored or one is chosen without justification. Appropriate Use: a valid memory is applied to the wrong task or project.</p>
        <p>If the source or question is unclear, pause and record the issue for the experiment owner rather than guessing a label. An AI suggestion is not your independent review.</p>
        <p>Saved for this reviewer in this session: {items.filter(item => savedLabels[item.automated.evaluation_id]?.reviewRole === reviewRole).length} of {items.length}. Reloading this page clears this session counter; it does not delete submitted labels.</p>
      </div>}
      {items.length > 0 && <UIPanel className="review-source-history"><UISummary>Read the complete original conversation · {sourceHistory.length} {sourceHistory.length === 1 ? 'message' : 'messages'}</UISummary>
        <p>Check the original statements before judging whether the reference behaviour and answer are correct. This is source evidence, not the context sent to the target model.</p>
        {sourceHistory.length ? <ol>{sourceHistory.map((source,index) => <li key={index}><b>{source.role?.toLowerCase() === 'user' ? 'User' : source.role?.toLowerCase() === 'assistant' ? 'Assistant' : source.role?.toLowerCase() === 'system' ? 'System' : 'Source'}:</b> {source.content} <small>· {new Date(source.timestamp).toLocaleString()}</small></li>)}</ol>
          : <p>No original conversation is available. Verify the reference separately before submitting a label.</p>}
      </UIPanel>}
      <div className="form-grid"><label>Reviewer pseudonym<UIInput aria-label="Reviewer pseudonym" value={reviewer} disabled={busy} placeholder="Enter your distinct reviewer pseudonym" maxLength={80} onChange={(event) => {setReviewer(event.target.value);setSavedLabels({});setNotes({});setFailureDimensions({});}} /><small>Enter your distinct pseudonym to enable label submission. Each independent reviewer must use their own name.</small></label><label>Review role<UISelect aria-label="Evaluation review role" disabled={independentOnly || busy} value={reviewRole} onChange={(event) => {setReviewRole(event.target.value as HumanReviewRole);setItems(null);setSummary(null);setSavedLabels({});setFailureDimensions({});setNotes({});}}><UIOption value="independent" disabled={exposed}>Independent reviewer</UIOption><UIOption value="reference">Reference label</UIOption><UIOption value="adjudication">Adjudication</UIOption></UISelect><small>{blindIndependentReview ? 'Independent labels are blind and remain separate until adjudication.' : 'Adjudication cites all independent labels for each evaluation.'}</small></label></div><div className="evaluation-review-list">{items.map((item, index) => { const saved = savedLabels[item.automated.evaluation_id]; return <UICard key={item.automated.evaluation_id} className="evaluation-review-card"><div className="row"><b>{blindIndependentReview ? `Response ${index + 1}` : (item.test.dimension ? labels[item.test.dimension] : 'Response')}</b><span>{blindIndependentReview ? 'Blind independent label' : `Automated: ${item.automated.passed === null ? 'Uncertain' : item.automated.passed ? 'Pass' : 'Fail'}`}</span></div><p><small>{item.test.prompt}</small></p><p className="review-reference"><small><b>Reference behaviour:</b> {item.test.expected_behavior}</small></p><p><small>Response: {item.response.response_text}</small></p>{!blindIndependentReview && <p><small>Answer limit sent with this request: {'execution_metadata' in item.response && item.response.execution_metadata?.requested_output_token_limit != null ? `${item.response.execution_metadata.requested_output_token_limit} tokens` : 'Not recorded'}.</small></p>}{!blindIndependentReview && 'reason' in item.automated && <p className="review-evaluator-reason"><small><b>Automated assessment reasoning:</b> {friendlyText(item.automated.reason)}</small></p>}{!blindIndependentReview && 'reason' in item.automated && <p className="review-execution-evidence"><small>{item.automated.judge_execution ? <>Assessment requests: {item.automated.judge_execution.request_attempts} · failed HTTP attempts: {item.automated.judge_execution.failed_http_attempts} · elapsed: {(item.automated.judge_execution.elapsed_ms / 1000).toFixed(2)} s · reported tokens: {item.automated.judge_execution.reported_total_tokens ?? 'Unknown'}<br/>Usage covers the last successful provider reply. Failed-attempt usage and monetary cost are unknown.</> : item.automated.evaluator.startsWith('rule-based') ? 'Rule-based assessment runs locally; no assessment model request was made.' : 'Assessment request evidence was not recorded for this result. Costs remain unknown.'}</small></p>}<label>Failure dimension<UISelect aria-label={`Failure dimension ${index + 1}`} disabled={busy} value={failureDimensions[item.automated.evaluation_id] ?? (blindIndependentReview ? '' : item.test.dimension ?? '')} onChange={(event) => setFailureDimensions((current) => ({ ...current, [item.automated.evaluation_id]: event.target.value as Dimension }))}><UIOption value="" disabled>Choose a failure dimension</UIOption><UIOption value="accuracy">Accuracy</UIOption><UIOption value="freshness">Freshness</UIOption><UIOption value="conflict_resolution">Conflict Resolution</UIOption><UIOption value="appropriate_use">Appropriate Use</UIOption></UISelect><small>{blindIndependentReview ? 'Choose independently before selecting Fail; Pass needs no failure category.' : 'Used only if you choose Fail.'}</small></label><label>Review note<UIInput aria-label={`Calibration note ${index + 1}`} disabled={busy} value={notes[item.automated.evaluation_id] ?? (blindIndependentReview ? '' : item.human_review?.note ?? '')} onChange={(event) => setNotes((current) => ({ ...current, [item.automated.evaluation_id]: event.target.value }))} /></label><div><UIButton type="button" className="secondary" disabled={busy || !reviewer.trim() || (reviewRole === 'adjudication' && independentReviewerCount(item) < 2)} onClick={() => save(item, true)}>{reviewRole === 'adjudication' ? 'Adjudicate: Pass' : 'Record Pass label'}</UIButton><UIButton type="button" disabled={busy || !reviewer.trim() || (blindIndependentReview && !failureDimensions[item.automated.evaluation_id]) || (reviewRole === 'adjudication' && independentReviewerCount(item) < 2)} onClick={() => save(item, false)}>{reviewRole === 'adjudication' ? 'Adjudicate: Fail' : 'Record Fail label'}</UIButton></div>{saved && <p className="review-save-confirmation" role="status">Your {saved.reviewRole} label was saved: <b>{saved.humanPassed ? 'Pass' : 'Fail'}</b>. It is recorded as calibration evidence.</p>}{!blindIndependentReview && <>{item.human_reviews.length > 0 && <ul className="review-label-list">{item.human_reviews.map((review) => <li key={review.review_id}>{({independent:'Independent reviewer',reference:'Reference label',adjudication:'Final decision'} as Record<string,string>)[review.review_role]}: {review.human_passed ? 'Pass' : 'Fail'}{!review.human_passed && ` · ${review.human_failure_type?labels[review.human_failure_type]:'Category not recorded'}`} · {review.reviewer_label}</li>)}</ul>}{item.human_review && <small>Resolved label: {item.human_review.human_passed ? 'Pass' : 'Fail'} · {item.human_review.review_role}</small>}</>}</UICard>; })}</div></>}
  </section>;
}
