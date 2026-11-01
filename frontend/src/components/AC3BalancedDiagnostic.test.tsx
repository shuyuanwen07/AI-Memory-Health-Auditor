import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { act, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AC3BalancedDiagnostic, isBalancedDiagnosticReport, useBalancedDiagnostic, type BalancedDiagnosticReport } from './AC3BalancedDiagnostic';
import { CompactExperimentResults } from './CompactExperimentResults';

vi.mock('./DynamicStudies', () => ({ useDynamicStudies: () => ({ data: { a: null, campaign: null, errors: [] }, refresh: vi.fn() }), DynamicA: () => null }));
type Analysis = NonNullable<BalancedDiagnosticReport['analysis']>;
const categories = ['accuracy', 'freshness', 'conflict_resolution', 'appropriate_use'] as const;
const ratio = (n: number, d: number) => ({ numerator: n, denominator: d, value: d ? n / d : null });
function pending(): BalancedDiagnosticReport {
  return { format: 'ac3-balanced-diagnostic-dashboard-v1', updated_at: '2026-11-02T01:00:00Z', protocol_sha256: 'a'.repeat(64),
    provider: 'openai', model: 'gpt-6-astra', reasoning_effort: 'max', curated_answers: true, histories: 30, cases: 150, planned_calls: 300,
    paired_order: { original_first: 75, revised_first: 75 }, complete: false, human_confirmed: false,
    reference_review: { model: 'gpt-6-astra', reasoning_effort: 'max', independent_reviewers: 2, ready: true,
      actual_failure_types: { accuracy: 30, freshness: 30, conflict_resolution: 30, appropriate_use: 30 }, passes: 30 },
    progress: { original: { planned: 150, returned: 48, errors: 1, remaining: 101 }, revised: { planned: 150, returned: 50, errors: 0, remaining: 100 } }, analysis: null };
}

// Designed test judgments, separate from the real diagnostic's outcomes.
function scorer(successes: number[], withUnknowns = false): Analysis['original'] {
  const actuals = [...categories, 'pass', 'unclassified_reference_failure', 'unresolved_reference'] as const;
  const predictions = [...categories, 'pass', 'unclassified_fail', 'uncertain', 'error_missing'] as const;
  const matrix = Object.fromEntries(actuals.map(a => [a, Object.fromEntries(predictions.map(p => [p, 0]))])) as Analysis['original']['confusion_matrix'];
  categories.forEach((k, i) => { matrix[k][k] = successes[i]; matrix[k].pass = 30 - successes[i]; });
  matrix.pass.pass = 28; matrix.pass.accuracy = 2;
  if (withUnknowns) {
    matrix.accuracy.pass -= 3; matrix.accuracy.unclassified_fail = 1; matrix.accuracy.uncertain = 1; matrix.accuracy.error_missing = 1;
    matrix.pass.pass -= 1; matrix.pass.uncertain = 1;
  }
  const correct = successes.reduce((n, c) => n + c, 0), detected = correct + (withUnknowns ? 1 : 0);
  const errors = withUnknowns ? 1 : 0, undecided = withUnknowns ? 2 : 0;
  return { metrics: { joint_detection_and_correct_category: ratio(correct, 120), failure_recall: ratio(detected, 120),
    false_positive_rate_all_reference_passes: ratio(2, 30), false_positive_rate_upper_bound: ratio(withUnknowns ? 3 : 2, 30), decided_coverage: ratio(150 - errors - undecided, 150) },
    per_category: Object.fromEntries(categories.map((k, i) => [k, { joint_detection_and_correct_category: ratio(successes[i], 30), failure_recall: ratio(successes[i] + (withUnknowns && i === 0 ? 1 : 0), 30), status: 'measured' }])) as Analysis['original']['per_category'],
    counts: { planned_slots: 150, reference_failures: 120, reference_passes: 30, reference_unresolved: 0,
      reference_failures_without_single_type: 0, detected_reference_failures: detected, correct_category: correct,
      detected_failures_without_predicted_type: withUnknowns ? 1 : 0, false_positives: 2, pass_controls_unresolved_or_error: withUnknowns ? 1 : 0,
      returned_undecided: undecided, errors_or_missing: errors, decided_verdicts: 150 - errors - undecided }, confusion_matrix: matrix };
}
function complete(withUnknowns = false): BalancedDiagnosticReport {
  const report = pending(); report.complete = true;
  report.progress.original = { planned: 150, returned: withUnknowns ? 149 : 150, errors: withUnknowns ? 1 : 0, remaining: 0 };
  report.progress.revised = { planned: 150, returned: 150, errors: 0, remaining: 0 };
  report.analysis = { cohort: { planned_cases: 150, histories: 30, planned_grader_slots: 300, terminal_slots: 300, reference_gate_met: true,
    actual_reference_counts: { accuracy: 30, freshness: 30, conflict_resolution: 30, appropriate_use: 30, pass: 30 },
    actual_agreed_failure_type_counts: { accuracy: 30, freshness: 30, conflict_resolution: 30, appropriate_use: 30 },
    question_validity: ratio(150, 150), joint_question_reference_validity: ratio(150, 150) },
    original: scorer([18, 12, 15, 9], withUnknowns), revised: scorer([27, 24, 28, 25]),
    execution: { complete: true, planned_cases: 150, planned_slots: 300, terminal_slots: 300, pending_slots: 0, planned_pair_shared_input_hash_matches: 150,
      states: { original: { returned: withUnknowns ? 149 : 150, failed_without_retry: withUnknowns ? 1 : 0 }, revised: { returned: 150 } },
      receipt_verification: { original: { returned_max_receipts: withUnknowns ? 149 : 150 }, revised: { returned_max_receipts: 150 } } } };
  return report;
}
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('controlled AC3 diagnostic evidence', () => {
  it('accepts the current published source summary', () => {
    const published = JSON.parse(readFileSync(resolve(process.cwd(), 'public/reports/ac3-balanced-diagnostic-v1.json'), 'utf8'));
    expect(isBalancedDiagnosticReport(published)).toBe(true);
  });

  it('shows progress without inventing zero correctness scores', () => {
    const report = pending(); expect(isBalancedDiagnosticReport(report)).toBe(true);
    render(<AC3BalancedDiagnostic report={report}/>);
    expect(screen.getByRole('status')).toHaveTextContent('New 150-case reference set');
    expect(screen.getByRole('status')).toHaveTextContent('human confirmation pending');
    expect(screen.getByText('48/150 returned · 1 request errors · 101 pending')).toBeInTheDocument();
    expect(screen.queryByText(/0\/120/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Controlled diagnostic totals')).not.toBeInTheDocument();
    expect(screen.getByText(/Curated answers test the scorer/)).toHaveTextContent('Natural-study results stay unchanged');
  });

  it('keeps finished calls in an analysis-pending state until checked metrics exist', () => {
    const report = complete(); report.analysis = null;
    expect(isBalancedDiagnosticReport(report)).toBe(true);
    render(<AC3BalancedDiagnostic report={report}/>);
    expect(screen.getByText(/All grader calls finished/)).toHaveTextContent('receipt checks are pending');
    expect(screen.queryByLabelText('Controlled diagnostic totals')).not.toBeInTheDocument();
  });

  it('limits human confirmation to the new reference labels', () => {
    const report = complete(); report.human_confirmed = true;
    render(<AC3BalancedDiagnostic report={report}/>);
    expect(screen.getByRole('status')).toHaveTextContent('Reference labels for this 150-case set');
    expect(screen.getByRole('status')).toHaveTextContent('two independent people');
    expect(screen.getByRole('status')).not.toHaveTextContent('human confirmation pending');
  });

  it('rejects mixed model provenance, natural answers and unbalanced reference counts', () => {
    const report = complete(); expect(isBalancedDiagnosticReport(report)).toBe(true);
    expect(isBalancedDiagnosticReport({ ...report, provider: 'openrouter' })).toBe(false);
    expect(isBalancedDiagnosticReport({ ...report, reasoning_effort: 'high' })).toBe(false);
    expect(isBalancedDiagnosticReport({ ...report, curated_answers: false })).toBe(false);
    report.reference_review.actual_failure_types.freshness = 0 as 30;
    expect(isBalancedDiagnosticReport(report)).toBe(false);
  });

  it('rejects altered denominators, incomplete pair evidence and unmatched receipt counts', () => {
    const wrongDenominator = complete(); wrongDenominator.analysis!.original.per_category.accuracy.joint_detection_and_correct_category.denominator = 6;
    expect(isBalancedDiagnosticReport(wrongDenominator)).toBe(false);
    const wrongReceipt = complete(); wrongReceipt.analysis!.execution.receipt_verification.original.returned_max_receipts = 149;
    expect(isBalancedDiagnosticReport(wrongReceipt)).toBe(false);
    const wrongPair = complete(); Object.assign(wrongPair.analysis!.execution, { planned_pair_shared_input_hash_matches: 149 });
    expect(isBalancedDiagnosticReport(wrongPair)).toBe(false);
    const wrongMatrix = complete(); wrongMatrix.analysis!.revised.confusion_matrix.freshness.freshness += 1;
    expect(isBalancedDiagnosticReport(wrongMatrix)).toBe(false);
    const premature = pending(); premature.analysis = complete().analysis;
    expect(isBalancedDiagnosticReport(premature)).toBe(false);
  });

  it('compares all four actual error types on the same denominator and retains untyped/errors', () => {
    const report = complete(true); expect(isBalancedDiagnosticReport(report)).toBe(true);
    render(<AC3BalancedDiagnostic report={report}/>);
    expect(screen.getAllByRole('img', { name: /detected and correctly classified/ })).toHaveLength(8);
    expect(screen.getByRole('img', { name: 'Freshness, Revised rubric: 24/30 (80.0%) detected and correctly classified' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Appropriate use, Revised rubric: 25/30 (83.3%) detected and correctly classified' })).toBeInTheDocument();
    expect(screen.getByLabelText('Controlled diagnostic totals')).toHaveTextContent('54/120 (45.0%)');
    expect(screen.getByLabelText('Controlled diagnostic totals')).toHaveTextContent('104/120 (86.7%)');
    expect(screen.getByLabelText('Controlled diagnostic totals')).toHaveTextContent('147/150 (98.0%)');
    expect(screen.getByText(/Original rubric: 1 detected but untyped/)).toHaveTextContent('2 undecided · 1 request errors');
    expect(screen.getByText(/Original rubric: 1 detected but untyped/)).toHaveTextContent('2/30 (6.7%) to 3/30 (10.0%)');
    expect(screen.getByRole('status')).toHaveTextContent('human confirmation pending');
    expect(screen.queryByText(/certified|all AC3 requirements passed/i)).not.toBeInTheDocument();
  });

  it('reports a tied rubric outcome without inventing an improvement', () => {
    const report = complete(); report.analysis!.revised = scorer([18, 12, 15, 9]);
    expect(isBalancedDiagnosticReport(report)).toBe(true);
    render(<AC3BalancedDiagnostic report={report}/>);
    expect(screen.getByLabelText('Controlled diagnostic comparison')).toHaveTextContent('Both rubrics verified 54/120 designed errors. No overall gain observed.');
  });

  it('refreshes without cache and keeps the last verified snapshot when a later payload is invalid', async () => {
    vi.useFakeTimers(); let current: unknown = pending();
    const fetcher = vi.fn(async () => ({ ok: true, json: async () => current })); vi.stubGlobal('fetch', fetcher);
    function Probe({ refreshToken = 0 }: { refreshToken?: number }) { const report = useBalancedDiagnostic(refreshToken); return report ? <AC3BalancedDiagnostic report={report}/> : null; }
    let page: ReturnType<typeof render>;
    await act(async () => { page = render(<Probe/>); });
    expect(screen.getByText('48/150 returned · 1 request errors · 101 pending')).toBeInTheDocument();
    current = complete(); await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(screen.getByLabelText('Controlled diagnostic totals')).toHaveTextContent('104/120');
    current = { ...complete(), model: 'gpt-6-luna' };
    await act(async () => { page!.rerender(<Probe refreshToken={1}/>); });
    expect(screen.getByLabelText('Controlled diagnostic totals')).toHaveTextContent('104/120');
    expect(fetcher).toHaveBeenCalledWith('/reports/ac3-balanced-diagnostic-v1.json', { cache: 'no-store' });
  });

  it('adds the diagnostic inside the existing AC3 card without replacing natural-answer evidence', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/reports/ac3-balanced-diagnostic-v1.json') return { ok: true, json: async () => complete() };
      try { const report = JSON.parse(readFileSync(resolve(process.cwd(), `public${url}`), 'utf8')); return { ok: true, json: async () => report }; }
      catch { return { ok: false }; }
    }));
    render(<CompactExperimentResults/>);
    const natural = await screen.findByLabelText('AC3 Astra max paired retest');
    const card = natural.closest('.ant-card') as HTMLElement;
    expect(within(card).getByLabelText('AC3 controlled curated-answer diagnostic')).toBeInTheDocument();
    expect(natural).toHaveTextContent('63/69 · 91.3%');
    expect(natural).toHaveTextContent('42/69; 27 remain unclassified');
    expect(within(card).getByLabelText('Controlled diagnostic totals')).toHaveTextContent('104/120');
    expect(within(within(card).getByLabelText('AC3 controlled curated-answer diagnostic')).getByRole('status')).toHaveTextContent('human confirmation pending');
  });
});
