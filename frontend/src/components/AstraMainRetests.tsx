import { useEffect, useState } from 'react';

type Ratio = { numerator: number; denominator: number; value: number | null };
type AMethod = {
  label: string; planned_answers: number; answered: number; pass: number; fail: number;
  unresolved: number; safe_but_incomplete: number; candidate_patterns_exposed: number;
  candidate_pattern_pool: number; matched_ids: string[]; disputed_mapping_answers: number;
};
export type AstraAReport = {
  format: 'a-astra-max-retest-v2'; provider: 'openai'; model: 'gpt-6-astra'; reasoning_effort: 'max';
  review_model: 'gpt-6-astra'; review_reasoning_effort: 'max';
  review_status: 'ai_reviewed' | 'human_confirmed'; human_confirmation_pending: boolean;
  histories: 4; planned_answers: 48; answered: 48; methods: AMethod[];
};
type MatrixRow = { automatic_fail: number; automatic_pass: number; automatic_undecided: number };
type MetricKey = 'failure_recall_conservative' | 'false_positive_rate_decided' | 'decided_coverage'
  | 'classification_accuracy_detected_classifiable' | 'classification_accuracy_conservative_all_detected'
  | 'joint_detection_and_classification_recall';
type Scorer = {
  counts: { detected_reference_classifiable: number; category_correct: number; category_incorrect: number; category_missing: number };
  metrics: Record<MetricKey, Ratio>;
  confusion_matrix: { reference_fail: MatrixRow; reference_pass: MatrixRow };
  threshold_evaluation: { conservative_numerical_checks_met: boolean; acceptance_status: string };
};
type ModelSource = { provider: 'openai'; model: 'gpt-6-astra'; reasoning_effort: 'max' };
export type AstraAC3Report = {
  format: 'ac3-astra-max-paired-analysis-v1'; complete: true; status: string; human_confirmed: boolean;
  cohort: {
    scheduled_questions: 120; saved_target_answers: 120; histories: 30; candidate_finalized_slots: 120;
    answer_consensus: { agreed_fail: number; agreed_pass: number };
    question_validity: Ratio; gold_primary_type_coverage: Ratio;
    agreed_primary_failure_types: { accuracy: number; freshness: number; conflict_resolution: number; appropriate_use: number };
  };
  provenance: {
    target: ModelSource & { verified_answer_receipts: 120 };
    candidate_judge: ModelSource & { returned_receipts: 120; failed_or_ambiguous_receipts: 0 };
    reference_reviewers: Array<{ declarations: Array<{ model: string; effort?: string; reasoning_effort?: string; completed_independently: boolean; has_seen_other_reviewer_or_automatic_scores: boolean }> }>;
  };
  baseline: Scorer; candidate: Scorer;
};
const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const count = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v) && v >= 0;
const maxSource = (v: unknown): v is ModelSource & Record<string, unknown> => record(v) && v.provider === 'openai'
  && v.model === 'gpt-6-astra' && v.reasoning_effort === 'max';
const ratioValid = (v: unknown): v is Ratio => record(v) && count(v.numerator) && count(v.denominator)
  && v.numerator <= v.denominator && (v.denominator === 0 ? v.value === null
    : typeof v.value === 'number' && Number.isFinite(v.value) && Math.abs(v.value - v.numerator / v.denominator) < 1e-10);
const sameRatio = (r: Ratio, n: number, d: number) => r.numerator === n && r.denominator === d;
const metricKeys: MetricKey[] = ['failure_recall_conservative', 'false_positive_rate_decided', 'decided_coverage',
  'classification_accuracy_detected_classifiable', 'classification_accuracy_conservative_all_detected', 'joint_detection_and_classification_recall'];

export function isAstraAReport(v: unknown): v is AstraAReport {
  if (!maxSource(v) || !record(v) || v.format !== 'a-astra-max-retest-v2' || v.review_model !== 'gpt-6-astra'
    || v.review_reasoning_effort !== 'max' || !['ai_reviewed', 'human_confirmed'].includes(String(v.review_status))
    || v.human_confirmation_pending !== (v.review_status !== 'human_confirmed') || v.histories !== 4
    || v.planned_answers !== 48 || v.answered !== 48 || !Array.isArray(v.methods) || v.methods.length !== 3) return false;
  const methods = v.methods;
  return ['Direct questions', 'Fixed templates', 'Contextual/indirect Auditor tests'].every(label => methods.filter(m => record(m) && m.label === label).length === 1)
    && methods.every(m => record(m) && m.planned_answers === 16 && m.answered === 16
      && ['pass', 'fail', 'unresolved', 'safe_but_incomplete', 'candidate_patterns_exposed', 'disputed_mapping_answers'].every(k => count(m[k]))
      && (m.pass as number) + (m.fail as number) + (m.unresolved as number) === 16
      && (m.safe_but_incomplete as number) <= (m.fail as number) && (m.disputed_mapping_answers as number) <= 16
      && m.candidate_pattern_pool === 16 && (m.candidate_patterns_exposed as number) <= 16
      && Array.isArray(m.matched_ids) && m.matched_ids.every(id => typeof id === 'string' && id.length > 0)
      && new Set(m.matched_ids).size === m.matched_ids.length && m.matched_ids.length === m.candidate_patterns_exposed);
}

function isScorer(v: unknown, failed: number, passed: number, typed: number): v is Scorer {
  if (!record(v) || !record(v.metrics) || !metricKeys.every(k => ratioValid((v.metrics as Record<string, unknown>)[k]))
    || !record(v.counts) || !['detected_reference_classifiable', 'category_correct', 'category_incorrect', 'category_missing'].every(k => count((v.counts as Record<string, unknown>)[k]))
    || !record(v.confusion_matrix) || !record(v.threshold_evaluation)
    || typeof v.threshold_evaluation.conservative_numerical_checks_met !== 'boolean' || typeof v.threshold_evaluation.acceptance_status !== 'string') return false;
  const { reference_fail: f, reference_pass: p } = v.confusion_matrix;
  const row = (r: unknown, total: number): r is MatrixRow => record(r)
    && ['automatic_fail', 'automatic_pass', 'automatic_undecided'].every(k => count(r[k]))
    && (r.automatic_fail as number) + (r.automatic_pass as number) + (r.automatic_undecided as number) === total;
  if (!row(f, failed) || !row(p, passed)) return false;
  const c = v.counts as Scorer['counts'], m = v.metrics as Scorer['metrics'];
  return c.detected_reference_classifiable <= Math.min(typed, f.automatic_fail)
    && c.category_correct + c.category_incorrect + c.category_missing === c.detected_reference_classifiable
    && sameRatio(m.failure_recall_conservative, f.automatic_fail, failed)
    && sameRatio(m.false_positive_rate_decided, p.automatic_fail, p.automatic_fail + p.automatic_pass)
    && sameRatio(m.decided_coverage, f.automatic_fail + f.automatic_pass + p.automatic_fail + p.automatic_pass, failed + passed)
    && sameRatio(m.classification_accuracy_detected_classifiable, c.category_correct, c.detected_reference_classifiable)
    && sameRatio(m.classification_accuracy_conservative_all_detected, c.category_correct, f.automatic_fail)
    && sameRatio(m.joint_detection_and_classification_recall, c.category_correct, failed);
}

export function isAstraAC3Report(v: unknown): v is AstraAC3Report {
  if (!record(v) || v.format !== 'ac3-astra-max-paired-analysis-v1' || v.complete !== true
    || typeof v.status !== 'string' || typeof v.human_confirmed !== 'boolean' || !record(v.cohort) || !record(v.provenance)) return false;
  const c = v.cohort, p = v.provenance;
  if (c.scheduled_questions !== 120 || c.saved_target_answers !== 120 || c.histories !== 30 || c.candidate_finalized_slots !== 120
    || !record(c.answer_consensus) || !count(c.answer_consensus.agreed_fail) || !count(c.answer_consensus.agreed_pass)
    || c.answer_consensus.agreed_fail + c.answer_consensus.agreed_pass !== 120 || !ratioValid(c.question_validity)
    || c.question_validity.denominator !== 120 || !ratioValid(c.gold_primary_type_coverage)
    || c.gold_primary_type_coverage.denominator !== c.answer_consensus.agreed_fail || !record(c.agreed_primary_failure_types)
    || !['accuracy', 'freshness', 'conflict_resolution', 'appropriate_use'].every(k => count((c.agreed_primary_failure_types as Record<string, unknown>)[k]))
    || Object.values(c.agreed_primary_failure_types).reduce<number>((sum, n) => sum + (n as number), 0) !== c.gold_primary_type_coverage.numerator
    || !maxSource(p.target) || !record(p.target) || p.target.verified_answer_receipts !== 120
    || !maxSource(p.candidate_judge) || !record(p.candidate_judge) || p.candidate_judge.returned_receipts !== 120
    || p.candidate_judge.failed_or_ambiguous_receipts !== 0 || !Array.isArray(p.reference_reviewers) || p.reference_reviewers.length !== 2
    || !p.reference_reviewers.every(r => record(r) && Array.isArray(r.declarations) && r.declarations.length > 0
      && r.declarations.every(d => record(d) && d.model === 'gpt-6-astra' && (d.reasoning_effort ?? d.effort) === 'max'
        && d.completed_independently === true && d.has_seen_other_reviewer_or_automatic_scores === false))) return false;
  return isScorer(v.baseline, c.answer_consensus.agreed_fail, c.answer_consensus.agreed_pass, c.gold_primary_type_coverage.numerator)
    && isScorer(v.candidate, c.answer_consensus.agreed_fail, c.answer_consensus.agreed_pass, c.gold_primary_type_coverage.numerator);
}

function useValidatedReport<T>(path: string, validate: (v: unknown) => v is T, refreshToken: number) {
  const [report, setReport] = useState<T | null>(null);
  useEffect(() => {
    let active = true;
    const refresh = () => fetch(path, { cache: 'no-store' }).then(r => r.ok ? r.json() : null)
      .then(v => { if (active && validate(v)) setReport(v); }).catch(() => {});
    void refresh(); const timer = window.setInterval(() => void refresh(), 30000);
    return () => { active = false; window.clearInterval(timer); };
  }, [path, validate, refreshToken]);
  return report;
}
export const useAstraARetest = (refreshToken = 0) => useValidatedReport('/reports/a-astra-max-retest-v2.json', isAstraAReport, refreshToken);
export const useAstraAC3Retest = (refreshToken = 0) => useValidatedReport('/reports/ac3-astra-max-retest-v2.json', isAstraAC3Report, refreshToken);
const ratioText = (r: Ratio) => r.value === null ? `${r.numerator}/${r.denominator} · unmeasured` : `${r.numerator}/${r.denominator} · ${(100 * r.value).toFixed(1)}%`;

export function AstraARetest({ report }: { report: AstraAReport }) {
  const largestCount = Math.max(1, ...report.methods.map(m => m.candidate_patterns_exposed));
  const incomplete = report.methods.reduce((n, m) => n + m.safe_but_incomplete, 0);
  const disputed = report.methods.reduce((n, m) => n + m.disputed_mapping_answers, 0);
  return <figure className="scope-replay" aria-label="A Astra max audit-method retest">
    <p className="compact-note">OpenAI GPT-6 Astra · max reasoning · 4 histories · 16 answers per method.</p>
    <p role="status">{report.human_confirmation_pending ? 'Independent Astra max AI reviews · human confirmation pending' : 'Human-confirmed AI-assisted reviews'}</p>
    <figcaption>Distinct candidate patterns exposed</figcaption>
    <div className="compact-methods">{report.methods.map(m => <div className="compact-method" key={m.label}>
      <span>{m.label}</span><div className="compact-track" role="img" aria-label={`${m.label}: ${m.candidate_patterns_exposed} distinct candidate patterns exposed`}><i style={{ width: `${100 * m.candidate_patterns_exposed / largestCount}%` }}/></div><strong>{m.candidate_patterns_exposed}</strong>
      <small>Target answers: {m.pass}/{m.planned_answers} passed · {m.fail} failed · {m.unresolved} unresolved</small>
    </div>)}</div>
    <p className="compact-note">16 predefined possible patterns; these counts show observed matches, not failure recall. {incomplete} safe but incomplete answers remain within failures. {disputed} disputed mapping; errors outside the inventory are retained.</p>
    <p className="compact-note">One run across four related synthetic scenarios. <a href="/reports/a-astra-max-retest-v2.json">Counts and review status →</a></p>
  </figure>;
}

export function AstraAC3Retest({ report }: { report: AstraAC3Report }) {
  const rows: Array<{ label: string; key: MetricKey }> = [
    { label: 'Failure detection ↑', key: 'failure_recall_conservative' },
    { label: 'False positives ↓', key: 'false_positive_rate_decided' },
    { label: 'Type accuracy · agreed types', key: 'classification_accuracy_detected_classifiable' },
    { label: 'Verified type / all detected', key: 'classification_accuracy_conservative_all_detected' },
  ];
  const c = report.cohort, untyped = c.answer_consensus.agreed_fail - c.gold_primary_type_coverage.numerator;
  const undecided = report.candidate.confusion_matrix.reference_fail.automatic_undecided + report.candidate.confusion_matrix.reference_pass.automatic_undecided;
  return <figure className="scope-replay" aria-label="AC3 Astra max paired retest">
    <p className="compact-note">Same 120 saved Astra max answers · 30 related synthetic histories.</p>
    <p role="status">{report.human_confirmed ? 'Human-confirmed AI-assisted reference review' : 'Independent Astra max AI references · human confirmation pending'}</p>
    <div className="scope-replay-legend"><span><i style={{ background: '#9aaec2' }}/>Rule baseline</span><span><i className="scope-accepted"/>Astra max judge</span></div>
    {rows.map(row => <div className="scope-replay-row" key={row.key}>
      <span>{row.label}</span><div style={{ display: 'grid', gap: 3 }}>{(['baseline', 'candidate'] as const).map(arm => {
        const metric = report[arm].metrics[row.key];
        return <div className="scope-replay-track" key={arm} role="img" aria-label={`${row.label}, ${arm}: ${ratioText(metric)}`}>
          {metric.value !== null && <i style={{ width: `${100 * metric.value}%`, background: arm === 'baseline' ? '#9aaec2' : '#218b78' }}/>}
        </div>;
      })}</div><small>{ratioText(report.baseline.metrics[row.key])} → <b>{ratioText(report.candidate.metrics[row.key])}</b></small>
    </div>)}
    <p className="compact-note">Agreed failure types: {c.gold_primary_type_coverage.numerator}/{c.gold_primary_type_coverage.denominator}; {untyped} remain unclassified. {c.agreed_primary_failure_types.freshness === 0 ? 'No agreed freshness-positive failures; freshness sensitivity is unmeasured.' : `${c.agreed_primary_failure_types.freshness} agreed freshness-positive failures.`}</p>
    <p className="compact-note">Verified detection + type across all failures: {ratioText(report.candidate.metrics.joint_detection_and_classification_recall)}. Automatic decisions: {ratioText(report.candidate.metrics.decided_coverage)}; {undecided} undecided. Question validity: {ratioText(c.question_validity)}.</p>
    <p className="compact-note">{report.candidate.threshold_evaluation.conservative_numerical_checks_met ? 'Conservative numerical checks met.' : 'Conservative classification target remains unmet.'} {report.human_confirmed ? 'Acceptance also depends on the agreed study protocol.' : 'AC3 acceptance is provisional until human confirmation.'} Baseline rules were replayed on these same answers; this measures scoring improvement.</p>
    <p className="compact-note">Shared model family and reused synthetic histories limit generalisation. Zero observed false positives does not establish zero future risk. <a href="/reports/ac3-astra-max-retest-v2.json">Metrics, denominators and evidence →</a></p>
  </figure>;
}
