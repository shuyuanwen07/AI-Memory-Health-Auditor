import '@testing-library/jest-dom/vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { AC3_PRIMARY_RUN_SHA, AC3_PRIMARY_STUDY_SHA, Ac3HeldoutResults, isAc3HeldoutSummary, isReviewedAc3Primary } from './Ac3HeldoutResults';
import { api } from '../services/api';

const rate = (n: number, d: number, threshold: number, direction: 'min' | 'max' = 'min') => ({
  metric: { numerator: n, denominator: d, value: d ? n / d : null }, threshold, direction, met_descriptively: null,
});
const fixture = {
  format: 'ac3-heldout-public-summary-v1', cases: 120, histories: 8,
  source_sha256: {frozen: AC3_PRIMARY_STUDY_SHA, run: AC3_PRIMARY_RUN_SHA, review_1: 'b'.repeat(64), review_2: 'c'.repeat(64)},
  acceptance: 'not_assessed', limitations: 'Synthetic data fixture.',
  human_reference: { unresolved: 2 }, automatic: { abstain_reference_fail: 1, abstain_reference_pass: 2 },
  history_bootstrap: { status: 'descriptive', intervals: { failure_recall_conservative: { lower: .5, upper: 1 } } },
  evidence_sufficiency: { status: 'insufficient', checks: { human_passes: { observed: 4, minimum: 30, met: false } } },
  threshold_comparison_descriptive: {
    failure_detection_recall_min: rate(3, 4, .75), failure_classification_accuracy_min: rate(2, 3, .8),
    test_validity_min: rate(32, 32, .9), false_positive_rate_max: rate(0, 4, .1, 'max'),
  },
};
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
it('displays verified aggregate data and preserves unresolved and abstained counts', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => fixture }));
  render(<Ac3HeldoutResults />);
  expect(await screen.findByText('AC3 · Main validation · ec20077e')).toBeInTheDocument();
  expect(screen.getByText('75.0% · 3/4')).toBeInTheDocument();
  expect(screen.getByText(/History resampling interval 50.0–100.0%/)).toBeInTheDocument();
  expect(screen.getByText('Insufficient evidence')).toBeInTheDocument();
  expect(screen.getByText(/Human unresolved: 2 · Auditor abstentions: 3/)).toBeInTheDocument();
  expect(screen.getByText(/Formal acceptance remains subject/)).toBeInTheDocument();
});
it('does not accept invalid or fabricated inconsistent percentages', () => {
  const bad = structuredClone(fixture);
  bad.threshold_comparison_descriptive.failure_detection_recall_min.metric.value = 1;
  expect(isAc3HeldoutSummary(bad)).toBe(false);
  expect(isAc3HeldoutSummary({ format: fixture.format })).toBe(false);
});
it('does not mistake another study or incomplete review hashes for this primary review', () => {
  const result={...fixture,cases:120,source_sha256:{frozen:AC3_PRIMARY_STUDY_SHA,run:'a'.repeat(64),review_1:'b'.repeat(64),review_2:'c'.repeat(64)}};
  const item={study_id:AC3_PRIMARY_STUDY_SHA,study_role:'primary_validation',summary:result};
  expect(isReviewedAc3Primary(item,AC3_PRIMARY_STUDY_SHA)).toBe(true);
  expect(isReviewedAc3Primary({...item,study_id:'d'.repeat(64)},AC3_PRIMARY_STUDY_SHA)).toBe(false);
  expect(isReviewedAc3Primary({...item,summary:{...result,source_sha256:{...result.source_sha256,review_2:result.source_sha256.review_1}}},AC3_PRIMARY_STUDY_SHA)).toBe(false);
});
it('distinguishes missing failure categories from incorrect classifications', async () => {
  const current = {
    ...fixture,
    automatic: { abstain_reference_fail: 1, abstain_reference_pass: 0, category_missing: 70 },
    metrics: { classification_accuracy_decided: { numerator: 0, denominator: 0, value: null } },
    threshold_comparison_descriptive: { ...fixture.threshold_comparison_descriptive,
      failure_classification_accuracy_min: rate(0, 70, .8), false_positive_rate_max: rate(8, 40, .1, 'max') },
  };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => current }));
  render(<Ac3HeldoutResults />);
  expect(await screen.findByText(/0\/70 classified · 70 unclassified/)).toBeInTheDocument();
  expect(screen.getByText(/not defined \(no classified cases\)/)).toBeInTheDocument();
  expect(screen.getAllByText('Target not met').length).toBeGreaterThanOrEqual(2);
  expect(screen.getByText('20.0% · 8/40')).toBeInTheDocument();
});
it('keeps archived primary visible when another study is returned', async () => {
  vi.spyOn(api, 'ac3StudySummaries').mockResolvedValue({ studies: [
    { study_id: 'other', study_role: 'stability_repeat', summary: fixture },
  ] } as never);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => fixture }));
  render(<Ac3HeldoutResults />);
  expect(await screen.findByText('AC3 · Main validation · ec20077e')).toBeInTheDocument();
  expect(screen.getByText('AC3 · Stability repeat · other')).toBeInTheDocument();
});
it('does not present an unrelated or unbound archive as the main validation', async () => {
  vi.spyOn(api, 'ac3StudySummaries').mockResolvedValue({ studies: [] } as never);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({...fixture,
    source_sha256: {...fixture.source_sha256, run: 'd'.repeat(64)}}) }));
  await act(async () => { render(<Ac3HeldoutResults />); });
  expect(fetch).toHaveBeenCalled();
  expect(screen.queryByText('AC3 · Main validation · ec20077e')).not.toBeInTheDocument();
});
