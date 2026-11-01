import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { AstraComparison, AstraExtractionReview, AstraDiverseQuestions, AstraPolicyReview } from './CompactExperimentResults';

afterEach(() => vi.unstubAllGlobals());

it('keeps the complete paired policy denominator and missing outcomes visible', async () => {
  const report=JSON.parse(readFileSync(resolve(process.cwd(),'public/reports/b-astra-four-strategy-v1.json'),'utf8'));
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>report})));
  render(<AstraPolicyReview/>);
  expect(await screen.findAllByText('3/12 · 25.0% pass · 0 unresolved')).toHaveLength(2);
  expect(screen.getAllByText('0/12 · 0.0% pass · 0 unresolved')).toHaveLength(2);
  expect(screen.getByText(/52\/64 answers saved overall/)).toHaveTextContent('12 missing');
});

it('shows invalid and missing question slots in the diverse product-flow check', async () => {
  const report=JSON.parse(readFileSync(resolve(process.cwd(),'public/reports/ac2-astra-ten-source-v1.json'),'utf8'));
  delete report.ten_scene_retest;
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>report})));
  render(<AstraDiverseQuestions/>);
  expect(await screen.findByText('14 valid · 14 invalid · 0 unresolved · 12 not generated')).toBeInTheDocument();
  expect(screen.getByText(/7\/10 histories produced questions/)).toHaveTextContent('operator confirmation was simulated');
});

it('shows human-confirmed source-only extraction counts with their scope', async () => {
  const report = JSON.parse(readFileSync(resolve(process.cwd(),'public/reports/ac1-astra-four-source-v1.json'),'utf8'));
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>report})));
  render(<AstraExtractionReview/>);
  expect(await screen.findByText('30/30 · 100.0%')).toBeInTheDocument();
  expect(screen.getByText('32/32 · 100.0%')).toBeInTheDocument();
  expect(screen.getAllByText('12/12 · 100.0%')).toHaveLength(2);
  expect(screen.getByText(/not strict atomic recall/)).toBeInTheDocument();
});

it('loads the published comparison and shows both scheduled-slot results', async () => {
  const fetchReport = vi.fn(async (path: string) => {
    const file = resolve(process.cwd(), `public${path}`);
    try { return { ok: true, json: async () => JSON.parse(readFileSync(file, 'utf8')) }; }
    catch { return { ok: false }; }
  });
  vi.stubGlobal('fetch', fetchReport);
  render(<AstraComparison />);
  expect(await screen.findByText('62/120 · 51.7% valid')).toBeInTheDocument();
  expect(screen.getByText('120/120 · 100.0% valid')).toBeInTheDocument();
  expect(screen.getByText(/Product-flow follow-up: 16\/16 agreed valid/)).toHaveTextContent('User-reported human checks of AI-assisted judgments');
  expect(screen.getByText(/Separate 1-history integration smoke/)).toHaveTextContent('1 failure unclassified');
  expect(screen.getByText(/Exploratory Astra retrieval retest/)).toHaveTextContent('1/4 → 3/4 passed');
  expect(screen.getByText(/Exploratory Astra memory-writer retest/)).toHaveTextContent('3/4 → 4/4 passed');
  expect(screen.getByText(/Four-history writer comparison/)).toHaveTextContent('12/16 → 16/16 passed');
  expect(fetchReport).toHaveBeenCalledWith('/reports/ac2-astra-comparison-v1.json', {cache:'no-store'});
});

it('reloads the research snapshot when the refresh control requests it', async () => {
  const report = JSON.parse(readFileSync(resolve(process.cwd(),'public/reports/ac2-astra-comparison-v1.json'),'utf8'));
  const fetchReport = vi.fn(async () => ({ok:true,json:async()=>report}));
  vi.stubGlobal('fetch',fetchReport);
  const page=render(<AstraComparison refreshToken={0}/>);
  await screen.findByText('120/120 · 100.0% valid');
  const initialCalls=fetchReport.mock.calls.length;
  page.rerender(<AstraComparison refreshToken={1}/>);
  await waitFor(()=>expect(fetchReport.mock.calls.length).toBeGreaterThan(initialCalls));
});
