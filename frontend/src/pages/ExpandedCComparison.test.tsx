import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { EXPANDED_C_REPORT_PATH, ExpandedCComparisonPage, type ExpandedCReport } from './ExpandedCComparison';

class TestResizeObserver { observe() {} unobserve() {} disconnect() {} }
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.stubGlobal('ResizeObserver', TestResizeObserver); });

function segment(caseCount: number, weak: [number, number, number], strong: [number, number, number]) {
  return {
    case_count: caseCount,
    repetitions: 3,
    per_repetition: [1, 2, 3].map((repetition, index) => ({
      repetition, weak_correct: weak[index], strong_correct: strong[index], total: caseCount,
    })),
    aggregate: {
      weak: { correct: weak.reduce((sum, value) => sum + value, 0), total: caseCount * 3,
        accuracy_percent: weak.reduce((sum, value) => sum + value, 0) * 100 / (caseCount * 3) },
      strong: { correct: strong.reduce((sum, value) => sum + value, 0), total: caseCount * 3,
        accuracy_percent: strong.reduce((sum, value) => sum + value, 0) * 100 / (caseCount * 3) },
    },
    protocol_sha256: 'a'.repeat(64), run_sha256: 'b'.repeat(64), winner: 'strong_rule_based',
  };
}

function makeReport(): ExpandedCReport {
  return {
    format: 'phase4-c-expanded-v6', study_id: 'phase4-c-expanded-study-v6', generated_at: '2026-10-28T00:00:00Z',
    source: { revision: 'test-revision', license: 'MIT', source_sha256: 'c'.repeat(64), dataset: 'LongMemEval Oracle', citation: 'Test citation' },
    baseline_v5: segment(14, [4, 5, 6], [10, 10, 10]),
    extension_v6: segment(30, [12, 11, 13], [22, 24, 23]),
    combined: {
      ...segment(44, [16, 16, 19], [32, 34, 33]),
      interpretation: 'Strong scores higher in each repeat and in the combined cases.',
    },
    decision: { selected_strategy: 'strong_rule_based', rule: 'Prefer consistent higher accuracy.', reason: 'Strong leads in all three combined repeats.' },
    limitations: ['Automated grading needs independent human calibration.', 'Repeated runs reuse the same selected cases.'],
  };
}

function response(status: number, content: string) {
  return { status, ok: status >= 200 && status < 300, text: async () => content } as Response;
}

it('shows an empty state when the expanded report has not been published', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(404, '')));
  render(<ExpandedCComparisonPage/>);
  expect(await screen.findByText('Expanded C results are not published yet')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /separate four-strategy v7 supplement/ })).toHaveAttribute('href', '/four-strategy-comparison');
  expect(screen.getByRole('button', { name: /Refresh report/ })).toBeInTheDocument();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(EXPANDED_C_REPORT_PATH, { cache: 'no-store' });
});

it('shows preserved v5, new v6, combined totals and the selected strategy', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, JSON.stringify(makeReport()))));
  render(<ExpandedCComparisonPage/>);
  expect(await screen.findByRole('heading', { name: 'Current choice' })).toBeInTheDocument();
  expect(screen.getByText('Existing v5 subset')).toBeInTheDocument();
  expect(screen.getByText('New v6 cases')).toBeInTheDocument();
  expect(screen.getByText('Combined comparison')).toBeInTheDocument();
  expect(screen.getByText('Relationship-priority retrieval')).toBeInTheDocument();
  expect(screen.getByText('15/42 (35.7%)')).toBeInTheDocument();
  expect(screen.getByText('30/42 (71.4%)')).toBeInTheDocument();
  expect(screen.getByText('36/90 (40.0%)')).toBeInTheDocument();
  expect(screen.getByText('69/90 (76.7%)')).toBeInTheDocument();
  expect(screen.getByText('51/132 (38.6%)')).toBeInTheDocument();
  expect(screen.getByText('99/132 (75.0%)')).toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Limitations' })).toHaveTextContent('Automated grading needs independent human calibration.');
});

it('shows v6 category gaps, operational trade-offs and pending blind human review', async () => {
  const report = makeReport();
  report.extension_v6 = {
    ...segment(30, [6, 6, 7], [22, 19, 20]),
    category_results: [{
      category: 'multi-session', case_count: 5, repetitions: 3,
      weak: {correct: 0, total: 15, accuracy_percent: 0},
      strong: {correct: 0, total: 15, accuracy_percent: 0},
    }],
    coverage: {target_answers: 180, usable_grades: 180, complete: true},
    operational_diagnostics: {
      target_latency_ms_mean: {weak: 4035, strong: 6800},
      target_input_tokens: {weak: 168849, strong: 388620}, estimated_cost_usd: 0.1783,
      billing_uncertain: true, recovered_http_429_attempts: 3, unresolved_requests: 0,
      note: 'Cost estimate, not an invoice.',
    },
    human_review: {status: 'pending', review_items: 180, independent_histories: 30},
  };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, JSON.stringify(report))));
  render(<ExpandedCComparisonPage/>);
  expect(await screen.findByRole('region', {name: 'v6 category results'})).toHaveTextContent('multi-session');
  expect(screen.getByRole('region', {name: 'Operational trade-offs'})).toHaveTextContent('6.80 s');
  expect(screen.getByRole('region', {name: 'Operational trade-offs'})).toHaveTextContent('US$0.178');
  expect(screen.getByText(/Human review: pending \(180 blinded answer rows from 30 source histories\)/)).toBeInTheDocument();
  expect(screen.getByText(/180 target answers and 180 usable automatic grades/)).toBeInTheDocument();
});

it('overlays later human-review status without replacing automatic scores', async () => {
  const report = makeReport();
  report.extension_v6 = { ...segment(30, [6, 6, 7], [22, 19, 20]),
    coverage: {target_answers: 180, usable_grades: 180, complete: true},
    human_review: {status: 'pending', review_items: 180, independent_histories: 30} };
  const later = {format:'proposal-final-results-dashboard-v1', proposal_c:{expanded_v5_v6:{
    v6_human_review:{status:'received; 168 agreed, 12 unresolved',review_items:180,independent_histories:30}}}};
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(url === EXPANDED_C_REPORT_PATH
    ? response(200, JSON.stringify(report)) : {ok:true,json:async () => later})));
  render(<ExpandedCComparisonPage/>);
  expect(await screen.findByText(/Human review: received; 168 agreed, 12 unresolved/)).toBeInTheDocument();
  expect(screen.getByText('19/90 (21.1%)')).toBeInTheDocument();
  expect(screen.getByRole('region', {name:'Limitations'})).toHaveTextContent('original declarations conflict');
});

it('keeps missing extension scores visible as unavailable and tolerates partial aggregates', async () => {
  const partial = makeReport();
  partial.extension_v6 = undefined;
  partial.combined = undefined;
  partial.decision = undefined;
  partial.baseline_v5.aggregate = { weak: { correct: 12, total: 42 }, strong: null };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, JSON.stringify(partial))));
  render(<ExpandedCComparisonPage/>);
  expect(await screen.findByText('12/42 (28.6%)')).toBeInTheDocument();
  expect(screen.getAllByText('Not available')).toHaveLength(4);
  expect(screen.getByText('Not chosen', { exact: true })).toBeInTheDocument();
});

it('reports malformed JSON schema without showing invented scores', async () => {
  const malformed = {...makeReport(), format: 'wrong-version'};
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, JSON.stringify(malformed))));
  render(<ExpandedCComparisonPage/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('does not match the required v6 schema');
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

it('rejects impossible aggregate counts while preserving the report’s missing-data support', async () => {
  const malformed = makeReport();
  malformed.combined!.aggregate!.weak!.correct = 133;
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, JSON.stringify(malformed))));
  render(<ExpandedCComparisonPage/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('does not match the required v6 schema');
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

it('treats an SPA HTML fallback as an unpublished report', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, '<!doctype html><html></html>')));
  render(<ExpandedCComparisonPage/>);
  expect(await screen.findByText('Expanded C results are not published yet')).toBeInTheDocument();
});
