import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { RepeatedBenchmarkRanking } from './RepeatedBenchmarkRanking';
import { UIProvider } from './ui';

const mocks=vi.hoisted(()=>({compareRepeatedBenchmarkRankings:vi.fn(),saveBlob:vi.fn()}));
vi.mock('../services/api',()=>({api:{compareRepeatedBenchmarkRankings:mocks.compareRepeatedBenchmarkRankings}}));
vi.mock('../services/download',()=>({saveBlob:mocks.saveBlob}));
afterEach(()=>{cleanup();vi.clearAllMocks();});

const input={planned_trial_ids:['t1','t2','t3'],trials:[1,2,3].map(i=>({trial_id:`t${i}`,comparison:{reference_run_id:`weak-${i}`,candidate_run_id:`strong-${i}`,reference_benchmark:{source_authorised:false},candidate_benchmark:{source_authorised:false}}}))};
async function upload(){
  fireEvent.change(screen.getByLabelText('Repeated ranking package'),{target:{files:[new File([JSON.stringify(input)],'repeated.json',{type:'application/json'})]}});
  await screen.findByText('repeated.json');await waitFor(()=>expect(screen.getByRole('button',{name:'Compare repeated rankings'})).not.toBeDisabled());
}

test('preserves missing trials and exports the exact partial report without zero imputation',async()=>{
  const user=userEvent.setup();render(<UIProvider><RepeatedBenchmarkRanking/></UIProvider>);
  expect(screen.getByLabelText('Repeated ranking package')).toBeDisabled();
  await user.click(screen.getByLabelText('Repeated ranking source authorisation'));
  await upload();
  const report={version:'fixture',status:'partial',planned_trials:3,measured_trials:2,missing_trials:1,invalid_trials:0,unmeasured_trials:0,directional_trials:2,consistent_trials:2,reversed_trials:0,both_tied_trials:0,inconclusive_tie_trials:0,ranking_agreement_percentage:null,
    suites:[{label:'Audit questions',score_basis:'dimension_macro_average',measured_trials:2,reference_mean_percentage:null,candidate_mean_percentage:null,reference_standard_deviation:null,candidate_standard_deviation:null,ordering:'unmeasured'}],
    trials:[{trial_id:'t1',status:'measured'},{trial_id:'t2',status:'measured'},{trial_id:'t3',status:'missing',reason:'No saved benchmark result.'}],notice:'Caller-declared plan; no pre-registration proof.'};
  mocks.compareRepeatedBenchmarkRankings.mockResolvedValue(report);
  await user.click(screen.getByRole('button',{name:'Compare repeated rankings'}));
  expect(await screen.findByText('Repeated comparison is incomplete')).toBeInTheDocument();
  expect(screen.getByText(/Ranking agreement:/)).toHaveTextContent('Not measured');
  expect(screen.getByText('No saved benchmark result.')).toBeInTheDocument();
  expect(screen.queryByText('0%')).not.toBeInTheDocument();
  const sent=mocks.compareRepeatedBenchmarkRankings.mock.calls[0][0];
  expect(sent.trials[0].comparison.reference_benchmark.source_authorised).toBe(true);
  expect(sent.trials[0].comparison.candidate_benchmark.source_authorised).toBe(true);
  await user.click(screen.getByRole('button',{name:'Download repeated comparison evidence'}));
  const exported=JSON.parse(await mocks.saveBlob.mock.calls[0][0].text());
  expect(exported).toEqual(report);
});

test('revoking source permission invalidates an in-flight file read',async()=>{
  const user=userEvent.setup();render(<UIProvider><RepeatedBenchmarkRanking/></UIProvider>);
  await user.click(screen.getByLabelText('Repeated ranking source authorisation'));
  let resolve!:(value:string)=>void;const file=new File(['pending'],'slow-repeats.json');
  Object.defineProperty(file,'text',{value:()=>new Promise<string>(done=>{resolve=done;})});
  fireEvent.change(screen.getByLabelText('Repeated ranking package'),{target:{files:[file]}});
  await user.click(screen.getByLabelText('Repeated ranking source authorisation'));
  await act(async()=>resolve(JSON.stringify(input)));
  expect(screen.getByText('No file selected')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Compare repeated rankings'})).toBeDisabled();
  expect(mocks.compareRepeatedBenchmarkRankings).not.toHaveBeenCalled();
});

test('shows complete repeat means with sample variability and all tie counts',async()=>{
  const user=userEvent.setup();render(<UIProvider><RepeatedBenchmarkRanking/></UIProvider>);
  await user.click(screen.getByLabelText('Repeated ranking source authorisation'));await upload();
  mocks.compareRepeatedBenchmarkRankings.mockResolvedValue({version:'fixture',status:'complete',planned_trials:3,measured_trials:3,missing_trials:0,invalid_trials:0,unmeasured_trials:0,directional_trials:2,consistent_trials:1,reversed_trials:1,both_tied_trials:1,inconclusive_tie_trials:0,ranking_agreement_percentage:50,
    model:'fixture-model',reference_strategy:'weak_first_hit',candidate_strategy:'strong_rule_based',
    suites:[{label:'Audit questions',score_basis:'dimension_macro_average',measured_trials:3,reference_mean_percentage:41.667,candidate_mean_percentage:33.333,reference_standard_deviation:28.868,candidate_standard_deviation:14.434,ordering:'reference_higher'}],
    trials:[{trial_id:'t1',status:'measured'},{trial_id:'t2',status:'measured'},{trial_id:'t3',status:'measured'}],notice:'Fixture only.'});
  await user.click(screen.getByRole('button',{name:'Compare repeated rankings'}));
  expect(await screen.findByText('All planned trials measured')).toBeInTheDocument();
  expect(screen.getByText(/Ranking agreement:/)).toHaveTextContent('50%');
  expect(screen.getByText(/41\.667%/)).toBeInTheDocument();
  expect(screen.getByText(/Sample SD: 28.868 percentage points/)).toBeInTheDocument();
  expect(screen.getByText(/Ranking agreement:/)).toHaveTextContent('1 both tied');
});

test('a frozen plan ID dispatches receipt-bound analysis and labels its provenance',async()=>{
 const user=userEvent.setup();
 const analyse=vi.fn().mockResolvedValue({version:'fixture',status:'partial',plan_provenance:'server_frozen_preexecution_plan',planned_trials:3,measured_trials:0,missing_trials:3,invalid_trials:0,unmeasured_trials:0,directional_trials:0,consistent_trials:0,reversed_trials:0,both_tied_trials:0,inconclusive_tie_trials:0,ranking_agreement_percentage:null,suites:[],trials:[],notice:'Simulated frozen report.'});
 const {api}=await import('../services/api');Object.assign(api,{analyseBenchmarkPlan:analyse});
 render(<UIProvider><RepeatedBenchmarkRanking/></UIProvider>);
 await user.click(screen.getByLabelText('Repeated ranking source authorisation'));await upload();
 await user.type(screen.getByLabelText('Ranking frozen execution plan ID'),'CP-fixture');
 await user.click(screen.getByRole('button',{name:'Compare repeated rankings'}));
 await screen.findByText('Repeated comparison is incomplete');
 expect(analyse).toHaveBeenCalledWith('CP-fixture',expect.objectContaining({planned_trial_ids:['t1','t2','t3']}));
 expect(mocks.compareRepeatedBenchmarkRankings).not.toHaveBeenCalled();
 expect(screen.getByText(/Analysis bound to a server plan/)).toBeInTheDocument();
});
