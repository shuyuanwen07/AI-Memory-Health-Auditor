import '@testing-library/jest-dom/vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {RetrievalImprovement, useRetrievalImprovement} from './RetrievalImprovement';
import type {RetrievalImprovementSummary} from '../services/api';

const mocks=vi.hoisted(()=>({retrievalImprovementLatest:vi.fn()}));
vi.mock('../services/api',()=>({api:mocks}));
afterEach(()=>{cleanup();vi.resetAllMocks();});
const report:RetrievalImprovementSummary={study_id:'paired-v1',status:'pending',planned_pairs:48,scenarios_completed:2,scenarios_planned:4,notice:'Four related synthetic histories.',methods:[{mode:'direct',label:'Direct questions',before:{passed:5,decided:16,review_basis:'single_human_reference'},after:{passed:0,decided:0,review_basis:'pending'},matched:0,improved:null,regressed:null,unresolved:16}]};

it('keeps unreviewed after results pending and labels the single human baseline',()=>{
  render(<RetrievalImprovement data={report}/>);
  expect(screen.getByText('5/16 · 31.3%')).toBeInTheDocument();
  expect(screen.getByText('Single human reference')).toBeInTheDocument();
  expect(screen.getByText('Awaiting review')).toBeInTheDocument();
  expect(screen.getByText(/Pair outcomes awaiting review/)).toBeInTheDocument();
  expect(screen.queryByText('0/0 · 0.0%')).not.toBeInTheDocument();
});

it('shows reviewed before and after counts and actual paired changes',()=>{
  const ready={...report,status:'complete',scenarios_completed:4,methods:[{...report.methods[0],after:{passed:11,decided:16,review_basis:'single_human_reference' as const},matched:16,improved:7,regressed:1,unresolved:0}]};
  render(<RetrievalImprovement data={ready}/>);
  expect(screen.getByText('11/16 · 68.8%')).toBeInTheDocument();
  expect(screen.getByText(/16 matched question pairs · 0 unresolved · 7 improved · 1 worsened/)).toBeInTheDocument();
});

it('refreshes the stored comparison when asked',async()=>{
  mocks.retrievalImprovementLatest.mockResolvedValueOnce(null).mockResolvedValue(report);
  function Screen(){const value=useRetrievalImprovement();return <><button onClick={value.refresh}>Refresh</button><RetrievalImprovement data={value.data}/></>;}
  render(<Screen/>); await waitFor(()=>expect(mocks.retrievalImprovementLatest).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Retrieval · Before and after')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Refresh'}));
  expect(await screen.findByText('Retrieval · Before and after')).toBeInTheDocument();
});
