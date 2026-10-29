import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Ac1ExtractionProgress } from './Ac1ExtractionProgress';

const fixture={format:'ac1-extraction-progress-v1',observed_at_utc:'2026-10-28T10:00:00Z',expected_histories:30,
  result_histories:5,started_without_result:1,not_yet_observed:24,
  outcomes:{completed:4,partial:1,failed:0,runtime_changed:0},
  stage_outcomes:{memory_extraction:{completed:5,failed:0,other:0},relationship_analysis:{completed:4,failed:1,other:0},
    independent_memory_review:{completed:5,failed:0,other:0}},
  protocol_sha256:'a'.repeat(64),runtime_source_sha256:'b'.repeat(64),result_receipts_sha256:'c'.repeat(64),
  interpretation:'Count-only snapshot.'};
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
it('shows snapshot counts, preserves partial runs, and allows manual refresh',async()=>{
  const fetcher=vi.fn().mockResolvedValue({ok:true,json:async()=>fixture});vi.stubGlobal('fetch',fetcher);
  render(<Ac1ExtractionProgress/>);
  expect((await screen.findAllByText('5/30')).length).toBeGreaterThan(0);
  expect(screen.getByText(/4 complete · 1 partial/)).toBeInTheDocument();
  expect(screen.getByText(/not correctness or AC1 acceptance/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Refresh'}));
  await waitFor(()=>expect(fetcher).toHaveBeenCalledTimes(2));
});
it('does not display inconsistent or malformed data',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({...fixture,not_yet_observed:25})}));
  render(<Ac1ExtractionProgress/>);
  await expect(screen.findByText('AC1 · Extraction collection',{},{timeout:100})).rejects.toThrow();
});
