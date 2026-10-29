import { render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Ac3StabilitySummary } from './Ac3StabilitySummary';
afterEach(()=>vi.unstubAllGlobals());
it('distinguishes repeated verdict consistency from accuracy',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({format:'ac3-stability-descriptive-v1',history_count:10,pairs:40,same_exact_answer_count:13,same_automatic_verdict_count:39,human_reviewed_repeat_answers:false,evidence_file_sha256:'a'.repeat(64)})}));
  render(<Ac3StabilitySummary/>);
  expect(await screen.findByText('39/40 · 97.5%')).toBeTruthy();
  expect(screen.getByText('13/40 · 32.5%')).toBeTruthy();
  expect(screen.getByText(/not accuracy or AC3 acceptance/)).toBeTruthy();
});
