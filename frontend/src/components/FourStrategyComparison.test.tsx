import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import {
  FOUR_STRATEGY_REPORT_PATH,
  FourStrategyComparisonSection,
  type FourStrategyReport,
} from './FourStrategyComparison';

class TestResizeObserver { observe() {} unobserve() {} disconnect() {} }
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.stubGlobal('ResizeObserver', TestResizeObserver); });

function makeReport(): FourStrategyReport {
  const strategies = [
    ['weak_first_hit', 'First-match retrieval', [1, 2]],
    ['strong_rule_based', 'Relationship-priority retrieval', [2, 2]],
    ['scope_aware', 'Match the task and project', [2, 1]],
    ['temporal_importance', 'Consider time and importance', [1, 1]],
  ] as const;
  const results = strategies.map(([id, label, correct]) => {
    const total = 6;
    const summed = correct.reduce((sum, value) => sum + value, 0);
    return {
      id, label, correct: summed, total, accuracy_percent: summed * 100 / total,
      per_repetition: correct.map((count, index) => ({
        repetition: index + 1, correct: count, total: 3, accuracy_percent: count * 100 / 3,
      })),
      categories: [{ category: 'single-session', correct: summed, total, accuracy_percent: summed * 100 / total }],
    };
  });
  return {
    format: 'phase4-c-four-strategy-v7', study_id: 'study-v7', generated_at: '2026-10-28T00:00:00Z',
    protocol_id: 'protocol-v7', protocol_sha256: 'a'.repeat(64), run_sha256: 'b'.repeat(64), source_revision: 'source-rev-v7',
    collection_status: 'completed', complete_for_decision: true, recommended_strategy: 'strong_rule_based', decision_rule: 'A unique leader must beat each competitor in at least two repeats.',
    case_count: 3, repetitions: 2, total_target_answers: 24, total_usable_grades: 24,
    estimated_cost_usd: 0.2, usage_based_cost_estimate_usd: 0.18, request_dispatches: 26,
    strategies: results,
    pairwise: [
      { left: 'strong_rule_based', right: 'weak_first_hit', left_only: 2, right_only: 0, both: 3, neither: 1, total: 6, left_accuracy_percent: 83.3, right_accuracy_percent: 50, difference_pp: 33.3 },
      { left: 'scope_aware', right: 'temporal_importance', left_only: 2, right_only: 1, both: 1, neither: 2, total: 6, left_accuracy_percent: 50, right_accuracy_percent: 33.3, difference_pp: 16.7 },
    ],
    limitations: ['The four strategies were assessed on only three selected cases.', 'Grades are automatic and need independent review.'],
  };
}

function response(status: number, body: string) {
  return { status, ok: status >= 200 && status < 300, text: async () => body } as Response;
}

it('shows loading and a clear empty state before the report is published', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(404, '')));
  render(<FourStrategyComparisonSection />);
  expect(screen.getByRole('status', { name: 'Loading four-strategy report' })).toBeInTheDocument();
  expect(await screen.findByText('The v7 four-strategy report is not published yet')).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(FOUR_STRATEGY_REPORT_PATH, { cache: 'no-store' });
  expect(screen.getByRole('button', { name: /Refresh supplement/ })).toBeInTheDocument();
});

it('shows four exact strategy labels, pooled and repeat denominators, paired evidence, provenance and limitations', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, JSON.stringify(makeReport()))));
  render(<FourStrategyComparisonSection />);
  expect(await screen.findByRole('region', { name: 'Four-strategy comparison' })).toHaveTextContent('Exploratory supplement');
  expect(screen.getByRole('img', { name: /First-match retrieval: 50.0 percent, 3 of 6 usable grades/ })).toBeInTheDocument();
  for (const label of ['First-match retrieval', 'Relationship-priority retrieval', 'Match the task and project', 'Consider time and importance']) {
    expect(screen.getAllByText(label).length).toBeGreaterThan(0);
  }
  const pooled = screen.getByRole('region', { name: 'Four-strategy pooled results' });
  expect(within(pooled).getAllByRole('img', { name: /3 of 6 usable grades/ })).toHaveLength(2);
  expect(screen.getAllByText(/Repeat mean/)).toHaveLength(4);
  expect(screen.getByRole('region', { name: 'Four-strategy repeat trend' })).toBeInTheDocument();
  expect(screen.getByRole('img', { name: /Line chart of repeat accuracy from 0 to 100 percent/ })).toBeInTheDocument();
  const detailDisclosure = screen.getByText('Detailed repeat, paired-case, category and provenance tables');
  expect(detailDisclosure.closest('details')).not.toHaveAttribute('open');
  fireEvent.click(detailDisclosure.closest('summary')!);
  expect(detailDisclosure.closest('details')).toHaveAttribute('open');
  expect(within(screen.getByRole('region', { name: 'Four-strategy comparison' })).getAllByRole('table')[0]).toHaveTextContent('3/6');
  expect(screen.getByRole('region', { name: 'Results by repetition' })).toHaveTextContent('Repetition');
  expect(screen.getByRole('region', { name: 'Paired outcomes' })).toHaveTextContent('33.3 pp');
  expect(screen.getByRole('region', { name: 'Protocol and run provenance' })).toHaveTextContent('protocol-v7');
  fireEvent.click(screen.getByText('Exploratory limitations'));
  expect(screen.getByText('Grades are automatic and need independent review.')).toBeInTheDocument();
});

it('keeps a missing repetition as a line-chart gap rather than converting it to zero', async () => {
  const report = makeReport();
  const strategy = report.strategies.find(item => item.id === 'scope_aware')!;
  strategy.per_repetition[0] = { repetition: 1, correct: 0, total: 0, accuracy_percent: null };
  strategy.correct = 1;
  strategy.total = 3;
  strategy.accuracy_percent = 100 / 3;
  strategy.categories = [{ category: 'single-session', correct: 1, total: 3, accuracy_percent: 100 / 3 }];
  report.total_usable_grades -= 3;
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, JSON.stringify(report))));
  render(<FourStrategyComparisonSection />);
  expect(await screen.findByRole('img', { name: /Match the task and project: missing, 33\.3%/ })).toBeInTheDocument();
});

it('marks budget-paused partial reports as incomplete and never displays a strategy winner', async () => {
  const partial = makeReport();
  partial.collection_status = 'paused_cost_ceiling';
  partial.complete_for_decision = false;
  partial.recommended_strategy = 'no_clear_winner';
  partial.total_target_answers = 8;
  partial.total_usable_grades = 8;
  partial.strategies = partial.strategies.map(strategy => ({
    ...strategy, total: 2, correct: 0, accuracy_percent: 0,
    per_repetition: strategy.per_repetition.map(repetition => ({ ...repetition, total: 1, correct: 0, accuracy_percent: 0 })),
  }));
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, JSON.stringify(partial))));
  render(<FourStrategyComparisonSection />);
  expect(await screen.findByText('Partial collection · no winner can be declared')).toBeInTheDocument();
  expect(screen.getByText(/stopped at “paused_cost_ceiling”/)).toBeInTheDocument();
  expect(screen.queryByText(/decision rule selects/)).not.toBeInTheDocument();
});

it('keeps completed scores descriptive when protocol timing is unverified', async () => {
  const unverified = makeReport();
  unverified.collection_status = 'complete_automatic_collection';
  unverified.complete_for_decision = false;
  unverified.recommended_strategy = 'no_clear_winner';
  unverified.limitations = ['One inter-dispatch interval was below the protocol minimum and had no monotonic trace.'];
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, JSON.stringify(unverified))));
  render(<FourStrategyComparisonSection />);
  expect(await screen.findByText('Collection complete · timing unverified · no winner')).toBeInTheDocument();
  expect(screen.getByRole('img', { name: /Relationship-priority retrieval: 66\.7 percent/ })).toBeInTheDocument();
  expect(screen.getByRole('img', { name: /Line chart of repeat accuracy from 0 to 100 percent/ })).toBeInTheDocument();
  expect(screen.queryByText(/decision rule selects/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByText('Exploratory limitations'));
  expect(screen.getByText(/One inter-dispatch interval was below the protocol minimum/)).toBeInTheDocument();
});

it('rejects inconsistent counts instead of displaying invented scores', async () => {
  const malformed = makeReport();
  malformed.strategies[0].per_repetition[0].correct = 0;
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, JSON.stringify(malformed))));
  render(<FourStrategyComparisonSection />);
  expect(await screen.findByRole('alert')).toHaveTextContent('does not match the required phase4-c-four-strategy-v7 contract');
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

it('handles a report service failure and an SPA HTML fallback without inventing data', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(503, 'offline')).mockResolvedValueOnce(response(200, '<!doctype html>')));
  const { unmount } = render(<FourStrategyComparisonSection />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Report request failed (503).');
  unmount();
  render(<FourStrategyComparisonSection />);
  expect(await screen.findByText('The v7 four-strategy report is not published yet')).toBeInTheDocument();
});
