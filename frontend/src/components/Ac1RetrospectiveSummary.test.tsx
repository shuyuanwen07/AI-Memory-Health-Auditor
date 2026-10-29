import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Ac1RetrospectiveSummary } from './Ac1RetrospectiveSummary';

const summary = {
  format: 'ac1-retrospective-adjudicated-v1', scope: 'retrospective',
  candidate_valid: { numerator: 27, denominator: 27, agreed_original: 21, later_adjudicated: 6 },
  reference_coverage: { full: 18, partial: 6, total: 24 },
  limitations: ['Reference list not exhaustive.', 'Adjudication not independently blinded.'],
};
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('shows confirmed candidate counts, coverage, and limits', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => summary }));
  render(<Ac1RetrospectiveSummary />);
  expect(await screen.findByText('AC1 · Retrospective source review')).toBeInTheDocument();
  expect(screen.getByText('27/27')).toBeInTheDocument();
  expect(screen.getByRole('img', { name: /18 full, 6 partial/ })).toBeInTheDocument();
  expect(screen.getByText(/do not establish complete recall or AC1 acceptance/)).toBeInTheDocument();
});
it('rejects inconsistent reference totals', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...summary, reference_coverage: { ...summary.reference_coverage, total: 25 } }) }));
  const { findByText } = render(<Ac1RetrospectiveSummary />);
  await expect(findByText('AC1 · Retrospective source review', {}, { timeout: 100 })).rejects.toThrow();
});
