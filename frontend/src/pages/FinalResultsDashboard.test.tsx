import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FinalResultsDashboard } from './FinalResultsDashboard';

const mocks = vi.hoisted(() => ({
  compareAudits: vi.fn(), audits: vi.fn(), results: vi.fn(),
  experimentGroups: vi.fn().mockResolvedValue([]), experimentResults: vi.fn(), methodComparisonResults: vi.fn(),
  listBenchmarkPlans: vi.fn().mockResolvedValue([]), listBenchmarkAnalyses: vi.fn().mockResolvedValue([]),
  ac3StudySummaries: vi.fn().mockResolvedValue({ studies: [] }), retrievalImprovementLatest: vi.fn().mockResolvedValue(null),
}));
class TestResizeObserver { observe() {} unobserve() {} disconnect() {} }
vi.mock('../services/api', () => ({ api: mocks }));

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('ResizeObserver', TestResizeObserver);
  mocks.audits.mockResolvedValue([]);
  mocks.compareAudits.mockResolvedValue({
    before: {result:{tests_passed:3,tests_total:4}}, after: {result:{tests_passed:4,tests_total:4}},
    counts:{fixed:1,regressed:0}, warnings:[], paired_tests:[],
  });
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.startsWith('/reports/')) {
      try {
        const body = readFileSync(resolve(process.cwd(), `public${path}`), 'utf8');
        return {status:200,ok:true,text:async()=>body,json:async()=>JSON.parse(body)} as Response;
      } catch { /* A missing report remains unavailable. */ }
    }
    return {status:404,ok:false,text:async()=>''} as Response;
  }));
});

it('keeps the comparison and research findings while removing the completed-audit aggregate', async () => {
  render(<FinalResultsDashboard />);
  expect(await screen.findByRole('heading', {name:'Before and after comparison'})).toBeInTheDocument();
  expect(await screen.findByLabelText('Automated assessment comparison')).toHaveTextContent('3/4');
  expect(screen.getByLabelText('Automated assessment comparison')).toHaveTextContent('4/4');
  expect(await screen.findByText('A · Audit methods')).toBeInTheDocument();
  expect(await screen.findByText('B & C · Astra repeated comparison')).toBeInTheDocument();
  expect(await screen.findByLabelText('Four-history writer repair results')).toHaveTextContent('12/16 · 75.0% passed');
  expect(screen.getByLabelText('Four-history writer repair results')).toHaveTextContent('16/16 · 100.0% passed');
  expect(await screen.findByText('AC3 · Astra max scoring retest')).toBeInTheDocument();
  expect(screen.getByRole('link', {name:'Audit history'})).toHaveAttribute('href','/history');
  expect(screen.queryByRole('heading', {name:'Completed audits'})).not.toBeInTheDocument();
  expect(screen.queryByText('Completed audit outcomes')).not.toBeInTheDocument();
  expect(mocks.results).not.toHaveBeenCalled();
});
