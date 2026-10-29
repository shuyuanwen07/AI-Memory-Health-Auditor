import { render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Ac2GenerationSummary } from './Ac2GenerationSummary';

afterEach(() => vi.unstubAllGlobals());

it('separates automated gate counts from human validity review', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true, json:async () => ({format:'ac2-generation-summary-v1', histories:30, questions:120, automatic_question_gate:{accepted:96,rejected:24}, automatic_suite_gate:{accepted:7,rejected:23}, reviewers_declared_complete:0, source_sha256:'abc', corrected_offline:true})}));
  render(<Ac2GenerationSummary />);
  expect(await screen.findByText('96/120 accepted')).toBeTruthy();
  expect(screen.getByText('7/30 accepted')).toBeTruthy();
  expect(screen.getByText('Reviewer declarations 0/2')).toBeTruthy();
  expect(screen.getByText(/not human validity judgments/)).toBeTruthy();
});
