import {act,render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter,useNavigate} from 'react-router-dom';
import {GeneratorComparisonPage} from './GeneratorComparison';
import type {GeneratorComparisonBatch} from '../types/domain';

const mocks=vi.hoisted(()=>({generatorComparison:vi.fn(),generatorComparisons:vi.fn(),audits:vi.fn(),openRouterModels:vi.fn(),createGeneratorComparison:vi.fn(),
  prepareGeneratorComparison:vi.fn(),getAudit:vi.fn(),generate:vi.fn(),execute:vi.fn(),evaluate:vi.fn(),retry:vi.fn(),testReview:vi.fn()}));
vi.mock('../services/api',()=>({api:mocks}));
vi.mock('../components/ModelPicker',()=>({ModelPicker:()=>null}));
vi.mock('../components/ResultVisualizations',()=>({ComparisonVisualizations:()=> <div>Target result chart</div>}));
const source={run_id:'SOURCE-INTERNAL',model:'qwen3:1.7b',memory_strategy:'weak_first_hit',created_at:'2026-10-12T09:00:00Z',status:'COMPLETED'};
const quality={saved_questions:1,accepted:1,rejected:0,pending:0,accepted_percentage:100,
  dimensions:{accuracy:1,freshness:0,conflict_resolution:0,appropriate_use:0},initial_candidates_measured:false};
const batch={comparison_id:'BATCH-INTERNAL',source,created_at:source.created_at,runtime_matches:true,inputs_match:true,
  entries:[{selection:{provider:'rule_based'},run:{...source,run_id:'RULE-INTERNAL',status:'TESTS_GENERATED'},quality,result:null},
    {selection:{provider:'openrouter',model:'anthropic/fixed-generator'},run:{...source,run_id:'AI-INTERNAL',status:'CREATED'},
      quality:{...quality,saved_questions:0,accepted:0,accepted_percentage:null,dimensions:{accuracy:0,freshness:0,conflict_resolution:0,appropriate_use:0}},result:null}]} as unknown as GeneratorComparisonBatch;
beforeEach(()=>{vi.resetAllMocks();mocks.generatorComparison.mockResolvedValue(batch);mocks.prepareGeneratorComparison.mockResolvedValue(batch);mocks.openRouterModels.mockResolvedValue([]);});
const show=()=>render(<MemoryRouter initialEntries={['/generator-models?comparison=BATCH-INTERNAL']}><GeneratorComparisonPage/></MemoryRouter>);

test('restores separate question progress without starting target calls or inventing candidate quality',async()=>{
  show();await screen.findByText('1 of 2 suites · 0 results');
  expect(screen.getByText('Not generated')).toBeInTheDocument();
  expect(screen.queryByText(/BATCH-INTERNAL|SOURCE-INTERNAL|RULE-INTERNAL|AI-INTERNAL/)).toBeNull();
  expect(screen.getByRole('img',{name:'Accepted questions by ability and generator'})).toHaveAccessibleDescription(/not generated/);
  expect(screen.getByText(/Historical missing observations stay unknown/)).toBeInTheDocument();
  expect(mocks.execute).not.toHaveBeenCalled();expect(mocks.evaluate).not.toHaveBeenCalled();
});

test('generation resumes only the missing suite and never executes the target',async()=>{
  mocks.getAudit.mockImplementation(async(id:string)=>({...source,run_id:id,status:id==='AI-INTERNAL'?'CREATED':'TESTS_GENERATED'}));
  show();await screen.findByText('1 of 2 suites · 0 results');
  await userEvent.click(screen.getByRole('button',{name:'Continue question generation'}));
  await screen.findByRole('button',{name:'Continue question generation'});
  expect(mocks.generate).toHaveBeenCalledExactlyOnceWith('AI-INTERNAL');
  expect(mocks.execute).not.toHaveBeenCalled();expect(mocks.evaluate).not.toHaveBeenCalled();
});

test('target testing does not silently generate a missing suite',async()=>{
  mocks.getAudit.mockImplementation(async(id:string)=>({...source,run_id:id,status:id==='RULE-INTERNAL'?'COMPLETED':'CREATED'}));
  show();await screen.findByText('1 of 2 suites · 0 results');
  await userEvent.click(screen.getByRole('button',{name:'Run target tests'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Generate and inspect questions');
  expect(mocks.generate).not.toHaveBeenCalled();expect(mocks.execute).not.toHaveBeenCalled();
});

test('input drift blocks both stages while retaining the saved evidence links',async()=>{
  mocks.generatorComparison.mockResolvedValue({...batch,inputs_match:false});
  show();await screen.findByText('1 of 2 suites · 0 results');
  expect(screen.getByRole('button',{name:'Continue question generation'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Run target tests'})).toBeDisabled();
  expect(screen.queryByRole('img',{name:'Accepted questions by ability and generator'})).toBeNull();
  expect(screen.getAllByRole('link',{name:'Open saved progress'})).toHaveLength(2);
});

test('a rejected question suite cannot enable target execution',async()=>{
  mocks.generatorComparison.mockResolvedValue({...batch,entries:batch.entries.map(entry=>({...entry,
    quality:{...entry.quality,accepted:0,rejected:entry.quality.saved_questions}}))});
  show();await screen.findByText('1 of 2 suites · 0 results');
  expect(screen.getByRole('button',{name:'Run target tests'})).toBeDisabled();
  expect(mocks.execute).not.toHaveBeenCalled();
});

test('cancelled conditions retain evidence without enabling either execution stage',async()=>{
  mocks.generatorComparison.mockResolvedValue({...batch,entries:batch.entries.map(entry=>({...entry,
    run:{...entry.run!,status:'CANCELLED'}}))});
  show();await screen.findByText('1 of 2 suites · 0 results');
  expect(screen.getAllByText('Cancelled')).toHaveLength(2);
  expect(screen.getByRole('button',{name:'Run target tests'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Continue question generation'})).toBeDisabled();
});

test('late generation preparation cannot overwrite a newly selected comparison',async()=>{
  let finish!:(value:GeneratorComparisonBatch)=>void;
  mocks.prepareGeneratorComparison.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
  const next={...batch,comparison_id:'NEXT-INTERNAL',entries:batch.entries.map(entry=>({...entry,quality}))};
  mocks.generatorComparison.mockImplementation(async(id:string)=>id==='NEXT-INTERNAL'?next:batch);
  function Navigation(){const navigate=useNavigate();return <button onClick={()=>navigate('/generator-models?comparison=NEXT-INTERNAL')}>Switch comparison</button>;}
  render(<MemoryRouter initialEntries={['/generator-models?comparison=BATCH-INTERNAL']}><Navigation/><GeneratorComparisonPage/></MemoryRouter>);
  await screen.findByText('1 of 2 suites · 0 results');
  await userEvent.click(screen.getByRole('button',{name:'Continue question generation'}));
  await screen.findByText('Preparing fixed target settings');
  await userEvent.click(screen.getByRole('button',{name:'Switch comparison'}));
  await screen.findByText('2 of 2 suites · 0 results');
  await act(async()=>{finish(batch);});
  expect(screen.getByText('2 of 2 suites · 0 results')).toBeInTheDocument();
  expect(mocks.generate).not.toHaveBeenCalled();expect(mocks.getAudit).not.toHaveBeenCalled();
});


test('software drift preserves verified historical charts while blocking all further execution',async()=>{
  mocks.generatorComparison.mockResolvedValue({...batch,runtime_matches:false});
  show();await screen.findByText('1 of 2 suites · 0 results');
  expect(screen.getByRole('img',{name:'Accepted questions by ability and generator'})).toBeInTheDocument();
  expect(screen.getByRole('img',{name:'Recorded generation time by generator'})).toBeInTheDocument();
  expect(screen.getByText(/Saved charts and reports are read-only/)).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Continue question generation'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Run target tests'})).toBeDisabled();
  expect(mocks.generate).not.toHaveBeenCalled();expect(mocks.execute).not.toHaveBeenCalled();
});
