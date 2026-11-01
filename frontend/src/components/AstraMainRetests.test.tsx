import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AstraARetest, AstraAC3Retest, isAstraAReport, isAstraAC3Report, useAstraARetest, type AstraAReport, type AstraAC3Report } from './AstraMainRetests';

const read = (name: string) => JSON.parse(readFileSync(resolve(process.cwd(), `public/reports/${name}.json`), 'utf8'));
// Keep explicit pending fixtures so source approval cannot disable pending-state coverage.
const a = (): AstraAReport => ({ ...read('a-astra-max-retest-v2'), review_status: 'ai_reviewed', human_confirmation_pending: true });
const ac3 = (): AstraAC3Report => ({ ...read('ac3-astra-max-retest-v2'), human_confirmed: false });
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('Astra max research source validation', () => {
  it('accepts the saved A result and rejects foreign models or unmatched pattern counts', () => {
    const report = a();
    expect(isAstraAReport(report)).toBe(true);
    expect(isAstraAReport({ ...report, model: 'gpt-6-luna' })).toBe(false);
    expect(isAstraAReport({ ...report, review_reasoning_effort: 'high' })).toBe(false);
    report.methods[0].candidate_patterns_exposed += 1;
    expect(isAstraAReport(report)).toBe(false);
  });

  it('validates AC3 ratios against the actual confusion counts and max provenance', () => {
    const report = ac3();
    expect(isAstraAC3Report(report)).toBe(true);
    expect(isAstraAC3Report({ ...report, complete: false })).toBe(false);
    const foreign = ac3();
    Object.assign(foreign.provenance.candidate_judge, { provider: 'openrouter' });
    expect(isAstraAC3Report(foreign)).toBe(false);
    const highReview = ac3();
    Object.assign(highReview.provenance.reference_reviewers[0].declarations[0], { reasoning_effort: 'high' });
    expect(isAstraAC3Report(highReview)).toBe(false);
    report.candidate.metrics.failure_recall_conservative.numerator -= 1;
    expect(isAstraAC3Report(report)).toBe(false);
  });

  it('does not equate unclassifiable references with confirmed wrong types', () => {
    const report = ac3();
    expect(report.cohort.gold_primary_type_coverage.numerator).toBe(42);
    expect(report.candidate.metrics.classification_accuracy_detected_classifiable.denominator).toBe(42);
    expect(report.candidate.metrics.classification_accuracy_conservative_all_detected.denominator).toBe(63);
    report.cohort.gold_primary_type_coverage.numerator = 69;
    report.cohort.gold_primary_type_coverage.value = 1;
    expect(isAstraAC3Report(report)).toBe(false);
  });
});

describe('Astra max result presentation', () => {
  it('shows A discovery counts separately from target-answer correctness', () => {
    render(<AstraARetest report={a()}/>);
    expect(screen.getByRole('img', { name: 'Direct questions: 1 distinct candidate patterns exposed' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Contextual/indirect Auditor tests: 3 distinct candidate patterns exposed' })).toBeInTheDocument();
    expect(screen.getAllByText('Target answers: 5/16 passed · 11 failed · 0 unresolved')).toHaveLength(3);
    expect(screen.getByText(/16 predefined possible patterns/)).toHaveTextContent('not failure recall');
    expect(screen.getByText(/14 safe but incomplete/)).toHaveTextContent('1 disputed mapping');
    expect(screen.getByRole('status')).toHaveTextContent('human confirmation pending');
    expect(screen.queryByText('3/16')).not.toBeInTheDocument();
  });

  it('keeps AC3 conditional and whole-cohort denominators visible alongside pending acceptance', () => {
    render(<AstraAC3Retest report={ac3()}/>);
    expect(screen.getByRole('img', { name: 'Failure detection ↑, baseline: 55/69 · 79.7%' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Failure detection ↑, candidate: 63/69 · 91.3%' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'False positives ↓, candidate: 0/51 · 0.0%' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Type accuracy · agreed types, candidate: 35/42 · 83.3%' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Verified type / all detected, candidate: 35/63 · 55.6%' })).toBeInTheDocument();
    expect(screen.getByText(/Agreed failure types: 42\/69; 27 remain unclassified/)).toHaveTextContent('freshness sensitivity is unmeasured');
    expect(screen.getByText(/Verified detection \+ type across all failures/)).toHaveTextContent('35/69 · 50.7%');
    expect(screen.getByText(/Conservative classification target remains unmet/)).toHaveTextContent('provisional until human confirmation');
    expect(screen.getByRole('status')).toHaveTextContent('human confirmation pending');
    expect(screen.queryByText(/61\/68/)).not.toBeInTheDocument();
  });

  it('renders an absent metric as unmeasured instead of a zero score', () => {
    const report = ac3();
    report.candidate.metrics.false_positive_rate_decided = { numerator: 0, denominator: 0, value: null };
    render(<AstraAC3Retest report={report}/>);
    expect(screen.getByRole('img', { name: 'False positives ↓, candidate: 0/0 · unmeasured' })).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'False positives ↓, candidate: 0/0 · 0.0%' })).not.toBeInTheDocument();
  });

  it('polls without cache and retains the last valid result when a later update is invalid', async () => {
    vi.useFakeTimers();
    const current = a();
    let calls = 0;
    const fetcher = vi.fn(async () => {
      calls += 1;
      return calls === 1 ? { ok: false } : { ok: true, json: async () => calls === 2 ? current : { ...current, model: 'other-model' } };
    });
    vi.stubGlobal('fetch', fetcher);
    function Probe() { const report = useAstraARetest(); return report ? <AstraARetest report={report}/> : <p>Retained fallback</p>; }
    await act(async () => { render(<Probe/>); });
    expect(screen.getByText('Retained fallback')).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(screen.getByLabelText('A Astra max audit-method retest')).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(screen.getByLabelText('A Astra max audit-method retest')).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledWith('/reports/a-astra-max-retest-v2.json', { cache: 'no-store' });
  });
});

it('shows the explicit human verification without resolving unknown failure categories', () => {
  const currentA: AstraAReport = read('a-astra-max-retest-v2');
  const currentAC3: AstraAC3Report = read('ac3-astra-max-retest-v2');
  expect(isAstraAReport(currentA)).toBe(true);
  expect(isAstraAC3Report(currentAC3)).toBe(true);
  render(<><AstraARetest report={currentA}/><AstraAC3Retest report={currentAC3}/></>);
  expect(screen.getAllByRole('status').every(s => s.textContent?.startsWith('Human-confirmed AI-assisted'))).toBe(true);
  expect(screen.getByText(/Agreed failure types: 42\/69; 27 remain unclassified/)).toBeInTheDocument();
  expect(screen.getByText(/Conservative classification target remains unmet/)).toBeInTheDocument();
});
