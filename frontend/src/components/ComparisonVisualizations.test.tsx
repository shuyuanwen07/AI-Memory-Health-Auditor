import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { AuditComparison } from '../types/domain';
import { ComparisonVisualizations } from './ComparisonVisualizations';

// Unpaired questions improve the overall scores; only one canonical pair
// belongs in the default comparison chart.
const data = {
  before: { run: { model: 'Qwen', run_id: 'BEFORE' }, result: { dimensions: [
    { dimension: 'accuracy', passed: 4, total: 10, percentage: 40 },
  ] } },
  after: { run: { model: 'Qwen', run_id: 'AFTER' }, result: { dimensions: [
    { dimension: 'accuracy', passed: 9, total: 10, percentage: 90 },
  ] } },
  paired_tests: [{ dimension: 'accuracy', before: { passed: true }, after: { passed: false } }],
  counts: { fixed: 0, regressed: 1, still_failed: 0, still_passed: 0 },
} as unknown as AuditComparison;

test('charts actual paired outcomes, including regressions, rather than full-suite improvement', async () => {
  render(<ComparisonVisualizations data={data} />);
  const chart = screen.getByRole('img');
  expect(chart.textContent).toContain('before 100% (1/1), after 0% (0/1), change -100 pp');
  expect(chart.textContent).toContain('Freshness: before Not scored');
  await userEvent.click(screen.getByRole('button', { name: 'Full test suites' }));
  expect(chart.textContent).toContain('before 40% (4/10), after 90% (9/10), change No comparison');
});

test('does not invent zero bars or a delta when no frozen questions can be paired', () => {
  render(<ComparisonVisualizations data={{ ...data, paired_tests: [] }} />);
  expect(screen.queryByRole('img')).toBeNull();
  expect(screen.getByText(/No shared questions to chart/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Save chart (SVG)' })).toBeNull();
});
