import { useEffect, useState } from 'react';

const categories = ['accuracy', 'freshness', 'conflict_resolution', 'appropriate_use'] as const;
const arms = ['original', 'revised'] as const;
type Category = typeof categories[number];
type Arm = typeof arms[number];
type Ratio = { numerator: number; denominator: number; value: number | null };
type Progress = { planned: 150; returned: number; errors: number; remaining: number };
const predictions = [...categories, 'pass', 'unclassified_fail', 'uncertain', 'error_missing'] as const;
type Prediction = typeof predictions[number];
const actuals = [...categories, 'pass', 'unclassified_reference_failure', 'unresolved_reference'] as const;
type Actual = typeof actuals[number];
type Metrics = {
  joint_detection_and_correct_category: Ratio; failure_recall: Ratio;
  false_positive_rate_all_reference_passes: Ratio; false_positive_rate_upper_bound: Ratio;
  decided_coverage: Ratio;
};
type Scorer = {
  metrics: Metrics;
  per_category: Record<Category, { joint_detection_and_correct_category: Ratio; failure_recall: Ratio; status: string }>;
  counts: {
    planned_slots: number; reference_failures: number; reference_passes: number; reference_unresolved: number;
    reference_failures_without_single_type: number; detected_reference_failures: number; correct_category: number;
    detected_failures_without_predicted_type: number; false_positives: number; pass_controls_unresolved_or_error: number;
    returned_undecided: number; errors_or_missing: number; decided_verdicts: number;
  };
  confusion_matrix: Record<Actual, Record<Prediction, number>>;
};
type Analysis = {
  cohort: {
    planned_cases: 150; histories: 30; planned_grader_slots: 300; terminal_slots: 300; reference_gate_met: true;
    actual_reference_counts: Record<string, number>; actual_agreed_failure_type_counts: Record<Category, 30>;
    question_validity: Ratio; joint_question_reference_validity: Ratio;
  };
  original: Scorer; revised: Scorer;
  execution: {
    complete: true; planned_cases: 150; planned_slots: 300; terminal_slots: 300; pending_slots: 0;
    planned_pair_shared_input_hash_matches: 150;
    states: Record<Arm, Record<string, number>>;
    receipt_verification: Record<Arm, { returned_max_receipts?: number }>;
  };
};
export type BalancedDiagnosticReport = {
  format: 'ac3-balanced-diagnostic-dashboard-v1'; updated_at: string; protocol_sha256: string;
  provider: 'openai'; model: 'gpt-6-astra'; reasoning_effort: 'max'; curated_answers: true;
  histories: 30; cases: 150; planned_calls: 300; paired_order: { original_first: 75; revised_first: 75 };
  complete: boolean; human_confirmed: boolean;
  reference_review: {
    model: 'gpt-6-astra'; reasoning_effort: 'max'; independent_reviewers: 2; ready: true;
    actual_failure_types: Record<Category, 30>; passes: 30;
  };
  progress: Record<Arm, Progress>; analysis: Analysis | null;
};
const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const count = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v) && v >= 0;
const ratio = (v: unknown, n: number, d: number): v is Ratio => record(v) && v.numerator === n && v.denominator === d
  && (d === 0 ? v.value === null : typeof v.value === 'number' && Math.abs(v.value - n / d) < 1e-10);
const balancedTypes = (v: unknown) => record(v) && Object.keys(v).length === 4 && categories.every(k => v[k] === 30);

function validScorer(value: unknown, progress: Progress): value is Scorer {
  if (!record(value) || !record(value.confusion_matrix) || !record(value.counts) || !record(value.metrics) || !record(value.per_category)) return false;
  const matrix = value.confusion_matrix;
  if (Object.keys(matrix).length !== actuals.length || !actuals.every(a => record(matrix[a])
    && Object.keys(matrix[a]).length === predictions.length && predictions.every(p => count((matrix[a] as Record<string, unknown>)[p]))
    && predictions.reduce((n, p) => n + (matrix[a] as Record<string, number>)[p], 0) === (categories.includes(a as Category) || a === 'pass' ? 30 : 0))) return false;
  const m = matrix as Scorer['confusion_matrix'];
  const correct = categories.reduce((n, k) => n + m[k][k], 0);
  const failedPredictions: Prediction[] = [...categories, 'unclassified_fail'];
  const detected = categories.reduce((n, a) => n + failedPredictions.reduce((sum, p) => sum + m[a][p], 0), 0);
  const falsePositives = failedPredictions.reduce((n, p) => n + m.pass[p], 0);
  const untyped = categories.reduce((n, a) => n + m[a].unclassified_fail, 0);
  const undecided = actuals.reduce((n, a) => n + m[a].uncertain, 0);
  const errors = actuals.reduce((n, a) => n + m[a].error_missing, 0);
  const controlUnknown = m.pass.uncertain + m.pass.error_missing;
  const expectedCounts: Scorer['counts'] = {
    planned_slots: 150, reference_failures: 120, reference_passes: 30, reference_unresolved: 0,
    reference_failures_without_single_type: 0, detected_reference_failures: detected, correct_category: correct,
    detected_failures_without_predicted_type: untyped, false_positives: falsePositives,
    pass_controls_unresolved_or_error: controlUnknown, returned_undecided: undecided,
    errors_or_missing: errors, decided_verdicts: 150 - undecided - errors,
  };
  const c = value.counts, s = value.metrics;
  return Object.entries(expectedCounts).every(([k, n]) => c[k] === n) && errors === progress.errors
    && ratio(s.joint_detection_and_correct_category, correct, 120) && ratio(s.failure_recall, detected, 120)
    && ratio(s.false_positive_rate_all_reference_passes, falsePositives, 30)
    && ratio(s.false_positive_rate_upper_bound, falsePositives + controlUnknown, 30)
    && ratio(s.decided_coverage, expectedCounts.decided_verdicts, 150)
    && categories.every(k => {
      const item = (value.per_category as Record<string, unknown>)[k];
      return record(item) && item.status === 'measured' && ratio(item.joint_detection_and_correct_category, m[k][k], 30)
        && ratio(item.failure_recall, failedPredictions.reduce((n, p) => n + m[k][p], 0), 30);
    });
}

export function isBalancedDiagnosticReport(v: unknown): v is BalancedDiagnosticReport {
  if (!record(v) || v.format !== 'ac3-balanced-diagnostic-dashboard-v1' || v.provider !== 'openai'
    || v.model !== 'gpt-6-astra' || v.reasoning_effort !== 'max' || v.curated_answers !== true
    || v.histories !== 30 || v.cases !== 150 || v.planned_calls !== 300 || typeof v.complete !== 'boolean'
    || typeof v.human_confirmed !== 'boolean' || typeof v.updated_at !== 'string' || !Number.isFinite(Date.parse(v.updated_at))
    || typeof v.protocol_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(v.protocol_sha256)
    || !record(v.paired_order) || v.paired_order.original_first !== 75 || v.paired_order.revised_first !== 75
    || !record(v.reference_review) || v.reference_review.model !== 'gpt-6-astra' || v.reference_review.reasoning_effort !== 'max'
    || v.reference_review.independent_reviewers !== 2 || v.reference_review.ready !== true
    || !balancedTypes(v.reference_review.actual_failure_types) || v.reference_review.passes !== 30 || !record(v.progress)) return false;
  const progress = v.progress;
  if (!arms.every(arm => {
    const p = progress[arm];
    return record(p) && p.planned === 150 && count(p.returned) && count(p.errors) && count(p.remaining)
      && p.returned + p.errors + p.remaining === 150;
  })) return false;
  const p = progress as Record<Arm, Progress>, terminal = arms.reduce((n, arm) => n + p[arm].returned + p[arm].errors, 0);
  if (v.complete && terminal !== 300) return false;
  if (v.analysis === null) return true;
  if (!v.complete || !record(v.analysis) || !record(v.analysis.cohort) || !record(v.analysis.execution)) return false;
  const a = v.analysis, c = a.cohort as Record<string, unknown>, e = a.execution as Record<string, unknown>;
  if (c.planned_cases !== 150 || c.histories !== 30 || c.planned_grader_slots !== 300 || c.terminal_slots !== 300
    || c.reference_gate_met !== true || !balancedTypes(c.actual_agreed_failure_type_counts)
    || !record(c.actual_reference_counts) || c.actual_reference_counts.pass !== 30
    || !categories.every(k => (c.actual_reference_counts as Record<string, unknown>)[k] === 30)
    || Object.values(c.actual_reference_counts).reduce<number>((sum, n) => sum + (count(n) ? n : NaN), 0) !== 150
    || !ratio(c.question_validity, 150, 150) || !ratio(c.joint_question_reference_validity, 150, 150)
    || e.complete !== true || e.planned_cases !== 150 || e.planned_slots !== 300 || e.terminal_slots !== 300
    || e.pending_slots !== 0 || e.planned_pair_shared_input_hash_matches !== 150
    || !record(e.receipt_verification) || !record(e.states)) return false;
  return arms.every(arm => {
    const receipts = (e.receipt_verification as Record<string, unknown>)[arm], states = (e.states as Record<string, unknown>)[arm];
    return record(receipts) && (receipts.returned_max_receipts ?? 0) === p[arm].returned && record(states)
      && (states.returned ?? 0) === p[arm].returned
      && Object.values(states).every(count) && Object.values(states).reduce<number>((n, x) => n + (x as number), 0) === 150
      && validScorer(a[arm], p[arm]);
  });
}

export function useBalancedDiagnostic(refreshToken = 0) {
  const [report, setReport] = useState<BalancedDiagnosticReport | null>(null);
  useEffect(() => {
    let active = true;
    const refresh = () => fetch('/reports/ac3-balanced-diagnostic-v1.json', { cache: 'no-store' })
      .then(r => r.ok ? r.json() : null).then(v => { if (active && isBalancedDiagnosticReport(v)) setReport(v); }).catch(() => {});
    void refresh(); const timer = window.setInterval(() => void refresh(), 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, [refreshToken]);
  return report;
}
const labels: Record<Category, string> = { accuracy: 'Accuracy', freshness: 'Freshness', conflict_resolution: 'Conflict resolution', appropriate_use: 'Appropriate use' };
const armLabels: Record<Arm, string> = { original: 'Original rubric', revised: 'Revised rubric' };
const textRatio = (r: Ratio) => r.value === null ? `${r.numerator}/${r.denominator} unmeasured` : `${r.numerator}/${r.denominator} (${(100 * r.value).toFixed(1)}%)`;

export function AC3BalancedDiagnostic({ report }: { report: BalancedDiagnosticReport }) {
  const analysis = report.analysis;
  const remaining = arms.reduce((n, arm) => n + report.progress[arm].remaining, 0);
  return <figure className="scope-replay" aria-label="AC3 controlled curated-answer diagnostic">
    <figcaption>Controlled error-injection diagnostic · curated answers</figcaption>
    <p className="compact-note">30 new synthetic histories · 150 designed answers · OpenAI Astra max. Only the scoring rubric changes; paired order is balanced 75/75.</p>
    <p role="status">{report.human_confirmed ? 'Reference labels for this 150-case set: two independent people confirmed the AI-assisted review.' : 'New 150-case reference set: independent Astra max AI review · human confirmation pending.'}</p>
    {!analysis ? <>
      {arms.map(arm => <div className="scope-replay-row" key={arm}><span>{armLabels[arm]}</span>
        <div className="scope-replay-track" role="img" aria-label={`${armLabels[arm]}: ${report.progress[arm].returned}/150 judgments returned; ${report.progress[arm].errors} request errors; ${report.progress[arm].remaining} pending`}><i style={{ width: `${100 * report.progress[arm].returned / 150}%`, background: '#9aaec2' }}/></div>
        <small>{report.progress[arm].returned}/150 returned · {report.progress[arm].errors} request errors · {report.progress[arm].remaining} pending</small>
      </div>)}
      <p className="compact-note">{remaining ? 'Comparison is running. Correctness metrics appear after every slot and receipt is checked.' : 'All grader calls finished. Paired analysis and receipt checks are pending.'}</p>
    </> : <>
      <div className="scope-replay-legend"><span><i style={{ background: '#9aaec2' }}/>Original rubric</span><span><i className="scope-accepted"/>Revised rubric</span></div>
      <p className="scope-replay-subtitle">Detected and correctly classified / 30 actual errors of each type</p>
      {categories.map(category => <div className="scope-replay-row" key={category}><span>{labels[category]}</span>
        <div style={{ display: 'grid', gap: 3 }}>{arms.map(arm => {
          const r = analysis[arm].per_category[category].joint_detection_and_correct_category;
          return <div className="scope-replay-track" key={arm} role="img" aria-label={`${labels[category]}, ${armLabels[arm]}: ${textRatio(r)} detected and correctly classified`}><i style={{ width: `${100 * (r.value ?? 0)}%`, background: arm === 'original' ? '#9aaec2' : '#147e87' }}/></div>;
        })}</div><small>{textRatio(analysis.original.per_category[category].joint_detection_and_correct_category)} → <b>{textRatio(analysis.revised.per_category[category].joint_detection_and_correct_category)}</b></small>
      </div>)}
      <div className="compact-values" aria-label="Controlled diagnostic totals"><div className="compact-value-header"><span>Measure</span><b>Original</b><b>Revised</b></div>
        <div><span>Detected + correct type</span><b>{textRatio(analysis.original.metrics.joint_detection_and_correct_category)}</b><b>{textRatio(analysis.revised.metrics.joint_detection_and_correct_category)}</b></div>
        <div><span>False alarms / correct controls ↓</span><b>{textRatio(analysis.original.metrics.false_positive_rate_all_reference_passes)}</b><b>{textRatio(analysis.revised.metrics.false_positive_rate_all_reference_passes)}</b></div>
        <div><span>Decided judgments</span><b>{textRatio(analysis.original.metrics.decided_coverage)}</b><b>{textRatio(analysis.revised.metrics.decided_coverage)}</b></div>
      </div>
      <p className="compact-note" aria-label="Controlled diagnostic comparison">{analysis.original.counts.correct_category === analysis.revised.counts.correct_category
        ? `Both rubrics verified ${analysis.original.counts.correct_category}/120 designed errors. No overall gain observed.`
        : `Net change in detected and correctly typed cases: ${analysis.revised.counts.correct_category > analysis.original.counts.correct_category ? '+' : ''}${analysis.revised.counts.correct_category - analysis.original.counts.correct_category} out of 120 designed errors.`}</p>
      {arms.map(arm => {
        const c = analysis[arm].counts;
        return <p className="compact-note" key={arm}>{armLabels[arm]}: {c.detected_failures_without_predicted_type} detected but untyped · {c.returned_undecided} undecided · {c.errors_or_missing} request errors.
          {c.pass_controls_unresolved_or_error > 0 && <> {c.pass_controls_unresolved_or_error}/30 correct controls unresolved or errored; sample false-positive bounds: {textRatio(analysis[arm].metrics.false_positive_rate_all_reference_passes)} to {textRatio(analysis[arm].metrics.false_positive_rate_upper_bound)}.</>}</p>;
      })}
    </>}
    <p className="compact-note">Actual error types come from source review, rather than the question dimension. Curated answers test the scorer, not target-model answer quality. Natural-study results stay unchanged. Shared Astra reviewers and synthetic sources limit generalisation; numerical thresholds alone do not certify AC3.</p>
    <a href="/reports/ac3-balanced-diagnostic-v1.json">Diagnostic data and review status →</a>
  </figure>;
}
