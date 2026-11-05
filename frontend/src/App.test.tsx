import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';

const mocks = vi.hoisted(() => ({ compareAudits: vi.fn().mockResolvedValue({before:{result:{tests_passed:1,tests_total:2}},after:{result:{tests_passed:2,tests_total:2}},warnings:[],counts:{fixed:1,regressed:0},paired_tests:[]}), audits: vi.fn(), results: vi.fn(), experimentGroups: vi.fn().mockResolvedValue([]), experimentResults: vi.fn(), methodComparisonResults: vi.fn(), listBenchmarkPlans: vi.fn().mockResolvedValue([]), listBenchmarkAnalyses: vi.fn().mockResolvedValue([]), ac3StudySummaries: vi.fn(), retrievalImprovementLatest:vi.fn().mockResolvedValue(null) }));
class TestResizeObserver { observe() {} unobserve() {} disconnect() {} }
vi.mock('./services/api', () => ({ api: mocks }));
vi.mock('./components/AccessBoundary', () => ({
  AccessBoundary: ({ children }: { children: (signOut: (() => Promise<void>) | null, signingOut: boolean) => ReactNode }) => children(null, false),
}));

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.stubGlobal('ResizeObserver', TestResizeObserver); });
beforeEach(() => {
  vi.clearAllMocks();
  mocks.audits.mockResolvedValue([]);
  mocks.ac3StudySummaries.mockResolvedValue({ studies: [] });
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const path = String(input);
    if(path.startsWith('/reports/')) {
      try { const body=readFileSync(resolve(process.cwd(),`public${path}`),'utf8');return {status:200,ok:true,text:async()=>body,json:async()=>JSON.parse(body)} as Response; }
      catch { /* A missing report remains unavailable. */ }
    }
    return { status: 404, ok: false, text: async () => '' } as Response;
  }));
});

it('uses the root route as a results-only dashboard with experiment and audit summaries', async () => {
  const { container } = render(<MemoryRouter initialEntries={['/']}><App /></MemoryRouter>);
  expect(await screen.findByRole('heading', { name: 'Audit and experiment results' })).toBeInTheDocument();
  expect(await screen.findByText('A · Audit methods')).toBeInTheDocument();
  expect(await screen.findByText('B & C · Astra repeated comparison')).toBeInTheDocument();
  expect(await screen.findByText('AC3 · Astra max scoring retest')).toBeInTheDocument();
  expect(screen.queryByText('B · Four memory strategies')).not.toBeInTheDocument();
  expect(screen.queryByText('AC3 · Auditor before and after')).not.toBeInTheDocument();
  expect(screen.queryByText('B · Original two-policy study')).not.toBeInTheDocument();
  expect(screen.queryByText('C · Original two-policy LongMemEval')).not.toBeInTheDocument();
  expect(await screen.findByRole('heading', { name: 'Before and after comparison' })).toBeInTheDocument();
  expect(await screen.findByText('There are no comparable decided questions for this pair.')).toBeInTheDocument();
  expect(container.querySelector('[aria-label="Selected completed audit results"]')).not.toBeInTheDocument();
  expect(container.querySelector('.maple-demo')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'History' })).toHaveAttribute('href', '/history');
  expect(screen.queryByText('Unfinished audits')).not.toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Recent activity' })).not.toBeInTheDocument();
});
