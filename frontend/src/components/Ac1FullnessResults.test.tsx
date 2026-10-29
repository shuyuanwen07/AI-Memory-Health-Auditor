import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Ac1FullnessResults } from './Ac1FullnessResults';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const good = { format: 'ac1-fullness-public-summary-v1', source_sha256: 'fixture', review_provenance: 'AI-assisted review.',
  complete_29_histories: { matched_references: 228, full: 210, partial: 17, none: 0, unresolved: 1, unmatched_prior_references: 3 },
  including_partial_observed_output: { matched_references: 236, full: 214, partial: 21, none: 0, unresolved: 1, unmatched_prior_references: 3 } };

it('shows the actual reviewed denominator, partial matches, unresolved and unmatched separately', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => good }));
  render(<Ac1FullnessResults />);
  expect(await screen.findByText('210/228')).toBeInTheDocument();
  expect(screen.getByText(/Partial 17/)).toBeInTheDocument();
  expect(screen.getByText(/3 other references had no common mapping/)).toBeInTheDocument();
});

it('rejects inconsistent counts', async () => {
  const broken = structuredClone(good); broken.complete_29_histories.full = 228;
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => broken }));
  render(<Ac1FullnessResults />);
  expect(await screen.queryByText('228/228')).not.toBeInTheDocument();
});
