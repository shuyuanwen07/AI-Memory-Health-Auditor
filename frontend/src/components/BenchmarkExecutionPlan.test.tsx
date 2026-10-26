import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { BenchmarkExecutionPlan } from './BenchmarkExecutionPlan';
import { UIProvider } from './ui';
const mocks=vi.hoisted(()=>({createBenchmarkPlan:vi.fn(),restoreBenchmarkPlan:vi.fn(),executeBenchmarkPlan:vi.fn(),listBenchmarkPlans:vi.fn(),saveBlob:vi.fn()}));
vi.mock('../services/api',()=>({api:mocks}));
vi.mock('../services/download',()=>({saveBlob:mocks.saveBlob}));
afterEach(()=>{cleanup();vi.resetAllMocks();});
const plan={plan_id:'CP-fixture',created_at:'2026-10-13T00:00:00Z',plan_fingerprint_sha256:'a'.repeat(64),protocol:{trials:[{trial_id:'repeat-1',reference_run_id:'W1',candidate_run_id:'S1'}],sampling_rule:'Simulated fixture inventory only.',evaluator_model:'fixture-reviewer',evaluator_revision:'0'.repeat(40),planned_target_calls:2,benchmark:{case_ids:['fixture-case'],configuration:{}}},executions:{},notice:'Simulated plan metadata only.'};
const input={benchmark:{payload:[],source_authorised:false},trials:plan.protocol.trials,sampling_rule:plan.protocol.sampling_rule,evaluator_model:'fixture-reviewer',evaluator_revision:'0'.repeat(40)};
async function load(){
  fireEvent.change(screen.getByLabelText('Benchmark execution plan file'),{target:{files:[new File([JSON.stringify(input)],'plan.json',{type:'application/json'})]}});
  await screen.findByText('plan.json');
}

test('requires processing and storage consent, freezes the plan and preserves downloadable original answers',async()=>{
 const user=userEvent.setup(),ready=vi.fn();render(<UIProvider><BenchmarkExecutionPlan onPlanReady={ready}/></UIProvider>);
 expect(screen.getByLabelText('Benchmark execution plan file')).toBeDisabled();
 await user.click(screen.getByLabelText('Planned benchmark source authorisation'));await load();
 expect(screen.getByRole('button',{name:'Save frozen benchmark plan'})).toBeDisabled();
 await user.click(screen.getByLabelText('Benchmark plan metadata permission'));
 mocks.createBenchmarkPlan.mockResolvedValue(plan);mocks.restoreBenchmarkPlan.mockResolvedValue({...plan,executions:{'repeat-1':{status:'COMPLETED'}}});
 await user.click(screen.getByRole('button',{name:'Save frozen benchmark plan'}));await screen.findByText('Execution plan saved');
 expect(mocks.createBenchmarkPlan).toHaveBeenCalledWith(expect.objectContaining({metadata_storage_authorised:true,benchmark:{...input.benchmark,source_authorised:true}}));
 expect(ready).toHaveBeenCalledWith('CP-fixture');
 const evidence={run_id:'LB-fixture',conditions:[{strategy:'weak_first_hit',cases:[{response_text:'Simulated reply'}]}]};mocks.executeBenchmarkPlan.mockResolvedValue(evidence);
 await user.click(screen.getByRole('button',{name:'Run benchmark repeat-1'}));await screen.findByText('Original answers available for repeat-1');
 expect(await screen.findByText('COMPLETED')).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Run benchmark repeat-1'})).toBeDisabled();
 await user.click(screen.getByRole('button',{name:'Download original benchmark answers'}));
 expect(JSON.parse(await mocks.saveBlob.mock.calls[0][0].text())).toEqual(evidence);
});

test('a revoked source cannot restore a late file read',async()=>{
 const user=userEvent.setup();render(<UIProvider><BenchmarkExecutionPlan onPlanReady={()=>{}}/></UIProvider>);
 await user.click(screen.getByLabelText('Planned benchmark source authorisation'));
 let resolve!:(value:string)=>void;const file=new File([''],'slow.json',{type:'application/json'});file.text=()=>new Promise(r=>{resolve=r;});
 fireEvent.change(screen.getByLabelText('Benchmark execution plan file'),{target:{files:[file]}});
 await user.click(screen.getByLabelText('Planned benchmark source authorisation'));
 await act(async()=>resolve(JSON.stringify(input)));
 expect(screen.queryByText('slow.json')).not.toBeInTheDocument();expect(mocks.createBenchmarkPlan).not.toHaveBeenCalled();
});

test('restores server failure receipts without permitting a second dispatch',async()=>{
 const user=userEvent.setup();render(<UIProvider><BenchmarkExecutionPlan onPlanReady={()=>{}}/></UIProvider>);
 mocks.listBenchmarkPlans.mockResolvedValue([{...plan,executions:{'repeat-1':{status:'FAILED'}}}]);
 await user.click(screen.getByRole('button',{name:'Find saved benchmark plans'}));
 await user.click(await screen.findByRole('button',{name:'CP-fixture'}));
 expect(await screen.findByText('FAILED')).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Run benchmark repeat-1'})).toBeDisabled();
 expect(mocks.executeBenchmarkPlan).not.toHaveBeenCalled();
});

test('keeps original evidence on screen when the status refresh fails',async()=>{
 const user=userEvent.setup();render(<UIProvider><BenchmarkExecutionPlan onPlanReady={()=>{}}/></UIProvider>);
 await user.click(screen.getByLabelText('Planned benchmark source authorisation'));await load();
 await user.click(screen.getByLabelText('Benchmark plan metadata permission'));mocks.createBenchmarkPlan.mockResolvedValue(plan);
 await user.click(screen.getByRole('button',{name:'Save frozen benchmark plan'}));await screen.findByText('Execution plan saved');
 mocks.executeBenchmarkPlan.mockResolvedValue({run_id:'original-reply'});mocks.restoreBenchmarkPlan.mockRejectedValue(new Error('Status refresh unavailable'));
 await user.click(screen.getByRole('button',{name:'Run benchmark repeat-1'}));
 expect(await screen.findByText('Original answers available for repeat-1')).toBeInTheDocument();
 await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('Status refresh unavailable'));
 expect(screen.getByRole('button',{name:'Download original benchmark answers'})).toBeEnabled();
});

test('preserves earlier original answers when the next repeat finishes',async()=>{
 const user=userEvent.setup();render(<UIProvider><BenchmarkExecutionPlan onPlanReady={()=>{}}/></UIProvider>);
 const two={...plan,protocol:{...plan.protocol,trials:[...plan.protocol.trials,{trial_id:'repeat-2',reference_run_id:'W2',candidate_run_id:'S2'}]}};
 mocks.createBenchmarkPlan.mockResolvedValue(two);
 await user.click(screen.getByLabelText('Planned benchmark source authorisation'));await load();
 await user.click(screen.getByLabelText('Benchmark plan metadata permission'));
 await user.click(screen.getByRole('button',{name:'Save frozen benchmark plan'}));await screen.findByText('Execution plan saved');
 mocks.executeBenchmarkPlan.mockResolvedValueOnce({run_id:'first-original'}).mockResolvedValueOnce({run_id:'second-original'});
 mocks.restoreBenchmarkPlan.mockResolvedValueOnce({...two,executions:{'repeat-1':{status:'COMPLETED'}}}).mockResolvedValueOnce({...two,executions:{'repeat-1':{status:'COMPLETED'},'repeat-2':{status:'COMPLETED'}}});
 await user.click(screen.getByRole('button',{name:'Run benchmark repeat-1'}));await screen.findByText('Original answers available for repeat-1');
 await waitFor(()=>expect(screen.getByRole('button',{name:'Run benchmark repeat-2'})).toBeEnabled());
 await user.click(screen.getByRole('button',{name:'Run benchmark repeat-2'}));await screen.findByText('Original answers available for repeat-2');
 expect(screen.getByText('Original answers available for repeat-1')).toBeInTheDocument();
 expect(screen.getAllByRole('button',{name:'Download original benchmark answers'})).toHaveLength(2);
});
