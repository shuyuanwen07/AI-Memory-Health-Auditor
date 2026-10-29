import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Ac2AiFollowupSummary, isAc2AiFollowupSummary } from './Ac2AiFollowupSummary';

const fixture = {format:'ac2-ai-followup-public-v1',status:'human_confirmed_ai_followup',
  original_human_adjudicated_structural:{valid:8,invalid:13,unresolved:99,denominator:120},
  mixed_structural:{valid:8,invalid:37,unresolved:75,denominator:120},
  ai_followup_counts:{invalid:24,uncertain:75},limitations:['AI-only fixture']};
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

it('shows prior adjudication and separately human-confirmed AI follow-up',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>fixture}));
  render(<Ac2AiFollowupSummary/>);
  expect(await screen.findByText('AC2 · Structural follow-up')).toBeInTheDocument();
  expect(screen.getByRole('img',{name:/Original human-confirmed adjudication: Valid 8, Invalid 13, Unresolved 99/})).toBeInTheDocument();
  expect(screen.getByRole('img',{name:/With human-confirmed AI follow-up: Valid 8, Invalid 37, Unresolved 75/})).toBeInTheDocument();
  expect(screen.getByText(/not independently blinded first-pass/)).toBeInTheDocument();
});

it('refuses malformed or falsely human-labelled summaries',()=>{
  expect(isAc2AiFollowupSummary({...fixture,status:'independent_blind_review'})).toBe(false);
  expect(isAc2AiFollowupSummary({...fixture,mixed_structural:{...fixture.mixed_structural,invalid:99}})).toBe(false);
});
