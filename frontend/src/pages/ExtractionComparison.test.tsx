import {render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {ExtractionComparisonPage} from './ExtractionComparison';
import type {ExtractionComparison} from '../types/domain';
const mocks=vi.hoisted(()=>({extractionComparison:vi.fn(),extractComparisonEntry:vi.fn()}));
vi.mock('../services/api',()=>({api:mocks}));
vi.mock('../components/ModelPicker',()=>({ModelPicker:()=>null}));
const usage={recorded_invocations:0,receipt_count:0,unfinished_operations:false,timed_invocations:0,observed_elapsed_ms:null,
 request_attempts:null,failed_http_attempts:null,cost_reported_invocations:0,observed_cost_credits:null,complete_cost_coverage:false,
 token_reported_invocations:0,observed_total_tokens:null,scope:'fixture'};
const plan={comparison_id:'EC-INTERNAL',source:{run_id:'SOURCE-INTERNAL',model:'qwen3:1.7b',created_at:'2026-10-12T09:00:00Z'},
 created_at:'2026-10-12T09:00:00Z',inputs_match:true,runtime_matches:true,reference_memories:[{memory_id:'M-INTERNAL',canonical_value:'The user prefers Rust.'}],
 entries:[{selection:{provider:'rule_based'},status:'completed',candidates:[],operations:[{operation_id:'PRIVATE',status:'completed'}],usage,
 checks:{candidate_count:0,reference_fact_count:1,exact_fact_matches:0,reference_relationship_count:0,exact_relationship_matches:0,fact_coverage_percent:0,relationship_coverage_percent:null,scope:'fixture'}},
 {selection:{provider:'openrouter',model:'openai/gpt-4.1'},status:'pending',candidates:null,operations:[],usage,checks:null}]} as unknown as ExtractionComparison;
beforeEach(()=>{vi.resetAllMocks();mocks.extractionComparison.mockResolvedValue(plan);mocks.extractComparisonEntry.mockResolvedValue(plan);});
const show=()=>render(<MemoryRouter initialEntries={['/extraction-models?comparison=EC-INTERNAL']}><ExtractionComparisonPage/></MemoryRouter>);

test('restores outputs without calls or internal identities and separates unknown from zero',async()=>{
 show();await screen.findByText(/1 of 2 outputs saved/);
 expect(screen.getByRole('img',{name:'Exact fact and relationship coverage by extractor'})).toHaveAccessibleDescription(/Rules 0%, GPT 4.1 Not extracted/);
 expect(screen.queryByText(/EC-INTERNAL|SOURCE-INTERNAL|M-INTERNAL|PRIVATE/)).toBeNull();
 expect(mocks.extractComparisonEntry).not.toHaveBeenCalled();
});
test('software drift retains verified charts but blocks calls; input drift hides controlled charts',async()=>{
 mocks.extractionComparison.mockResolvedValue({...plan,runtime_matches:false});show();await screen.findByText(/1 of 2 outputs saved/);
 expect(screen.getByRole('img',{name:'Exact fact and relationship coverage by extractor'})).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Continue unfinished extractions'})).toBeDisabled();
});
test('continues only unfinished model entries and never re-extracts the saved rules result',async()=>{
 show();await screen.findByText(/1 of 2 outputs saved/);await userEvent.click(screen.getByRole('button',{name:'Continue unfinished extractions'}));
 expect(mocks.extractComparisonEntry).toHaveBeenCalledWith('EC-INTERNAL',1);
 expect(mocks.extractComparisonEntry).toHaveBeenCalledTimes(1);
});

test('changed reference inputs hide comparison charts but preserve reference and output inspection',async()=>{
 mocks.extractionComparison.mockResolvedValue({...plan,inputs_match:false});show();await screen.findByText(/1 of 2 outputs saved/);
 expect(screen.queryByRole('img',{name:'Exact fact and relationship coverage by extractor'})).toBeNull();
 expect(screen.getByRole('button',{name:'Continue unfinished extractions'})).toBeDisabled();
 expect(screen.getByText(/Original outputs and reference snapshot remain available/)).toBeInTheDocument();
 expect(mocks.extractComparisonEntry).not.toHaveBeenCalled();
});
