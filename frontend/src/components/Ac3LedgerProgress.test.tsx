import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Ac3LedgerProgress } from './Ac3LedgerProgress';
import { api } from '../services/api';
import { AC3_PRIMARY_STUDY_SHA } from './Ac3HeldoutResults';

vi.mock('../services/api', () => ({ api: { ac3StudySummaries: vi.fn(async () => ({ studies: [] })) } }));

const fixture={format:'ac3-ledger-progress-v1',observed_at_utc:'2026-10-28T10:00:00Z',
  primary:{expected:120,settled:30,dispatched:1,unknown:0,not_dispatched:89,scope_observed:true},
  repeat:{expected:40,settled:0,dispatched:0,unknown:0,not_dispatched:40,scope_observed:false},
  frozen_sha256:{primary:'ec20077e07ead83925fa38bb67936d81773098e0762c1e4627ae3b94d8ff0f58',
    repeat:'d5f88c4d118ffd0ffb941d564cf1c33cce82dd10ee78f8aaa33f91e508df2246'},
  interpretation:'Count-only snapshot.'};
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.mocked(api.ac3StudySummaries).mockReset().mockResolvedValue({studies:[]});});
it('shows settled request counts without claiming accuracy and refreshes',async()=>{
  const review={format:'ac3-review-progress-v1',questions:120,reviewer_declarations_complete:0,run_sha256:'a'.repeat(64)};
  const fetcher=vi.fn().mockImplementation(async (url:string)=>({ok:true,json:async()=>url.includes('review-progress')?review:fixture}));vi.stubGlobal('fetch',fetcher);
  render(<Ac3LedgerProgress/>);
  expect(await screen.findByText('30/120 requests settled')).toBeInTheDocument();
  expect(screen.getByText('No ledger scope observed yet')).toBeInTheDocument();
  expect(screen.getByText(/not accuracy or acceptance results/)).toBeInTheDocument();
  expect(await screen.findByText('Review template snapshot: 0/2')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Refresh'}));
  await waitFor(()=>expect(fetcher).toHaveBeenCalledTimes(4));
});
it('uses the linked primary aggregate rather than the stale blank-template snapshot',async()=>{
  const review={format:'ac3-review-progress-v1',questions:120,reviewer_declarations_complete:0,run_sha256:'a'.repeat(64)};
  const metric={metric:{numerator:1,denominator:1,value:1},threshold:.8,direction:'min',met_descriptively:true};
  const verified={format:'ac3-heldout-public-summary-v1',cases:120,histories:30,acceptance:'not_assessed',limitations:'Synthetic.',
    human_reference:{unresolved:0},automatic:{abstain_reference_fail:0,abstain_reference_pass:0},
    threshold_comparison_descriptive:{failure_detection_recall_min:metric,failure_classification_accuracy_min:metric,test_validity_min:metric,false_positive_rate_max:metric},
    source_sha256:{frozen:AC3_PRIMARY_STUDY_SHA,run:'a'.repeat(64),review_1:'b'.repeat(64),review_2:'c'.repeat(64)}};
  vi.mocked(api.ac3StudySummaries).mockResolvedValueOnce({studies:[{study_id:AC3_PRIMARY_STUDY_SHA,study_role:'primary_validation',summary:verified}]});
  vi.stubGlobal('fetch',vi.fn().mockImplementation(async (url:string)=>({ok:true,json:async()=>url.includes('review-progress')?review:fixture})));
  render(<Ac3LedgerProgress/>);
  expect(await screen.findByText('Human-review declarations: 2/2')).toBeInTheDocument();
  expect(screen.queryByText('Review template snapshot: 0/2')).not.toBeInTheDocument();
  expect(screen.getByText(/independence and identity are user-reported/)).toBeInTheDocument();
});
it('rejects a mismatched frozen study',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({...fixture,frozen_sha256:{...fixture.frozen_sha256,primary:'x'}})}));
  render(<Ac3LedgerProgress/>);
  await expect(screen.findByText('AC3 · Collection progress',{},{timeout:100})).rejects.toThrow();
});
