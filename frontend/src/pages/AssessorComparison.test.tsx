import {act,render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter,useNavigate} from 'react-router-dom';
import {AssessorComparisonPage} from './AssessorComparison';
import type {AssessorComparisonBatch} from '../types/domain';

const mocks=vi.hoisted(()=>({assessorComparison:vi.fn(),assessorComparisons:vi.fn(),audits:vi.fn(),openRouterModels:vi.fn(),
  createAssessorComparison:vi.fn(),prepareAssessorComparison:vi.fn(),getAudit:vi.fn(),retry:vi.fn(),evaluate:vi.fn()}));
vi.mock('../services/api',()=>({api:mocks}));
vi.mock('../components/ModelPicker',()=>({ModelPicker:()=>null}));
vi.mock('../components/ResultVisualizations',()=>({ComparisonVisualizations:()=> <div>Saved result chart</div>}));
const source={run_id:'SOURCE-INTERNAL',model:'qwen3:1.7b',memory_strategy:'weak_first_hit',created_at:'2026-10-12T09:00:00Z',status:'COMPLETED'};
const result={run_id:'RULE-INTERNAL',tests_passed:1,tests_total:1,uncertain_count:0,dimensions:[],failures:[],overall_score:100};
const batch={comparison_id:'BATCH-INTERNAL',source,created_at:source.created_at,runtime_matches:true,inputs_match:true,
  entries:[{selection:{evaluator_provider:'rule_based'},run:{...source,run_id:'RULE-INTERNAL'},result},
    {selection:{evaluator_provider:'openrouter',evaluator_model:'anthropic/claude-fixed'},run:{...source,run_id:'AI-INTERNAL',status:'FAILED'},result:null}]} as unknown as AssessorComparisonBatch;
beforeEach(()=>{vi.resetAllMocks();mocks.assessorComparison.mockResolvedValue(batch);mocks.prepareAssessorComparison.mockResolvedValue(batch);mocks.openRouterModels.mockResolvedValue([]);});
const show=()=>render(<MemoryRouter initialEntries={['/assessor-models?comparison=BATCH-INTERNAL']}><AssessorComparisonPage/></MemoryRouter>);

test('restores database progress and hides internal identifiers without inventing missing scores',async()=>{
  show();
  expect(await screen.findByText('1 of 2 complete')).toBeInTheDocument();
  expect(screen.getByText('Needs attention')).toBeInTheDocument();
  expect(screen.getByText('1 passed · 0 failed · 0 awaiting review')).toBeInTheDocument();
  expect(screen.queryByText(/BATCH-INTERNAL|SOURCE-INTERNAL|RULE-INTERNAL|AI-INTERNAL/)).toBeNull();
  expect(screen.getByText(/not assessor accuracy/)).toBeInTheDocument();
  expect(mocks.evaluate).not.toHaveBeenCalled();
});

test('resumes the failed evaluation stage and does not repeat a completed assessor',async()=>{
  mocks.getAudit.mockResolvedValueOnce({...source,run_id:'AI-INTERNAL',status:'FAILED'})
    .mockResolvedValueOnce({...source,run_id:'AI-INTERNAL',status:'COMPLETED'});
  mocks.retry.mockResolvedValue({...source,run_id:'AI-INTERNAL',status:'TESTS_EXECUTED'});
  show();await screen.findByText('1 of 2 complete');
  await userEvent.click(screen.getByRole('button',{name:'Continue unfinished assessments'}));
  expect(await screen.findByRole('button',{name:'Continue unfinished assessments'})).toBeInTheDocument();
  expect(mocks.retry).toHaveBeenCalledWith('AI-INTERNAL');
  expect(mocks.evaluate).toHaveBeenCalledExactlyOnceWith('AI-INTERNAL');
  expect(mocks.createAssessorComparison).not.toHaveBeenCalled();
});

test('keeps persisted results inspectable when preparation cannot continue',async()=>{
  mocks.prepareAssessorComparison.mockRejectedValue(new Error('Evaluation service unavailable.'));
  show();await screen.findByText('1 of 2 complete');
  await userEvent.click(screen.getByRole('button',{name:'Continue unfinished assessments'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Evaluation service unavailable.');
  expect(screen.getByRole('link',{name:'Inspect answers & evidence'})).toHaveAttribute('href','/audits/RULE-INTERNAL');
  expect(mocks.evaluate).not.toHaveBeenCalled();
});

test('software drift permits reading while blocking unfinished assessments',async()=>{
  mocks.assessorComparison.mockResolvedValue({...batch,runtime_matches:false});
  show();await screen.findByText('1 of 2 complete');
  expect(screen.getByRole('button',{name:'Continue unfinished assessments'})).toBeDisabled();
  expect(screen.getByText(/Software changed/)).toBeInTheDocument();
});

test('unverified reference inputs retain reports but do not present a controlled comparison chart',async()=>{
  mocks.assessorComparison.mockResolvedValue({...batch,inputs_match:false});
  show();await screen.findByText('1 of 2 complete');
  expect(screen.getByRole('button',{name:'Continue unfinished assessments'})).toBeDisabled();
  expect(screen.queryByText('Saved result chart')).toBeNull();
  expect(screen.getByRole('link',{name:'Inspect answers & evidence'})).toBeInTheDocument();
  expect(screen.getByText(/Comparison inputs unverified/)).toBeInTheDocument();
});

test('navigation discards late preparation results and stops the old queue',async()=>{
  let finishPreparation!:(value:AssessorComparisonBatch)=>void;
  mocks.prepareAssessorComparison.mockImplementation(()=>new Promise(resolve=>{finishPreparation=resolve;}));
  const next={...batch,comparison_id:'NEXT-INTERNAL',entries:batch.entries.map(entry=>({...entry,
    run:{...source,run_id:entry.run!.run_id,status:'COMPLETED'},result}))};
  mocks.assessorComparison.mockImplementation(async(id:string)=>id==='NEXT-INTERNAL'?next:batch);
  function Navigation(){const navigate=useNavigate();return <button onClick={()=>navigate('/assessor-models?comparison=NEXT-INTERNAL')}>Switch comparison</button>;}
  render(<MemoryRouter initialEntries={['/assessor-models?comparison=BATCH-INTERNAL']}><Navigation/><AssessorComparisonPage/></MemoryRouter>);
  await screen.findByText('1 of 2 complete');
  await userEvent.click(screen.getByRole('button',{name:'Continue unfinished assessments'}));
  await screen.findByText('Preparing the same saved answers');
  await userEvent.click(screen.getByRole('button',{name:'Switch comparison'}));
  await screen.findByText('2 of 2 complete');
  await act(async()=>{finishPreparation(batch);});
  expect(screen.getByText('2 of 2 complete')).toBeInTheDocument();
  expect(mocks.getAudit).not.toHaveBeenCalled();
  expect(mocks.evaluate).not.toHaveBeenCalled();
});
