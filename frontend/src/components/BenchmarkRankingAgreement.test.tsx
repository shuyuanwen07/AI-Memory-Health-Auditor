import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { BenchmarkRankingAgreement } from './BenchmarkRankingAgreement';
import { UIProvider } from './ui';
import { selectUIOption } from './ui/testHelpers';
const mocks=vi.hoisted(()=>({audits:vi.fn(),compareBenchmarkRankings:vi.fn()}));
vi.mock('../services/api',()=>({api:mocks}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
beforeEach(()=>{mocks.audits.mockResolvedValue([
  {run_id:'secret-before',status:'COMPLETED',experiment_id:'frozen',model:'fixture-model',provider:'ollama',memory_strategy:'weak_first_hit',created_at:'2026-10-01T00:00:00Z'},
  {run_id:'secret-after',status:'COMPLETED',experiment_id:'frozen',model:'fixture-model',provider:'ollama',memory_strategy:'strong_rule_based',created_at:'2026-10-02T00:00:00Z'}]);});
async function upload(kind:string,name:string){fireEvent.change(screen.getByLabelText(`Ranking ${kind} assessments`),{target:{files:[new File([JSON.stringify({source:[],evidence:{},rows:[],strategy:kind})],name,{type:'application/json'})]}});await screen.findByText(name);await waitFor(()=>expect(screen.getByLabelText(`Ranking ${kind} assessments`)).not.toBeDisabled());}
test('gates missing evidence, calls saved-result check and separates scores across suites',async()=>{
  const user=userEvent.setup();render(<UIProvider><BenchmarkRankingAgreement/></UIProvider>);
  expect(screen.getByLabelText('Ranking reference assessments')).toBeDisabled();
  expect(screen.getByLabelText('Ranking candidate assessments')).toBeDisabled();
  expect(screen.getByRole('button',{name:'Check ranking agreement'})).toBeDisabled();
  await user.click(screen.getByLabelText('Ranking benchmark source authorisation'));
  await selectUIOption(user,'Ranking reference audit',/First matching memory/);
  await selectUIOption(user,'Ranking candidate audit',/Prioritise requirements and updates/);
  await upload('reference','first.json');await upload('candidate','second.json');
  mocks.compareBenchmarkRankings.mockResolvedValue({version:'fixture',provider:'ollama',model:'fixture-model',reference_strategy:'weak_first_hit',candidate_strategy:'strong_rule_based',agreement:'consistent',notice:'Independent validation required.',suites:[{label:'Audit questions',total:4,reference_correct:1,candidate_correct:2,reference_percentage:25,candidate_percentage:50,ordering:'candidate_higher'},{label:'Benchmark questions',total:10,reference_correct:6,candidate_correct:7,reference_percentage:60,candidate_percentage:70,ordering:'candidate_higher'}]});
  await user.click(screen.getByRole('button',{name:'Check ranking agreement'}));
  expect(await screen.findByText('Both question sets favour the same strategy')).toBeInTheDocument();
  expect(screen.getByText('Strategy 2: 2 / 4 · 50%')).toBeInTheDocument();
  expect(screen.getByText('Strategy 2: 7 / 10 · 70%')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Download comparison evidence'})).toBeInTheDocument();
  expect(screen.queryByText('secret-before')).not.toBeInTheDocument();
  expect(mocks.compareBenchmarkRankings).toHaveBeenCalledWith(expect.objectContaining({reference_run_id:'secret-before',candidate_run_id:'secret-after'}));
});
test('shows incompatible evidence errors without a ranking chart',async()=>{
  const user=userEvent.setup();render(<UIProvider><BenchmarkRankingAgreement/></UIProvider>);
  await user.click(screen.getByLabelText('Ranking benchmark source authorisation'));
  await selectUIOption(user,'Ranking reference audit',/First matching memory/);await selectUIOption(user,'Ranking candidate audit',/Prioritise requirements and updates/);
  await upload('reference','first.json');await upload('candidate','second.json');
  mocks.compareBenchmarkRankings.mockRejectedValue(new Error('Frozen context budgets differ between suites.'));
  await user.click(screen.getByRole('button',{name:'Check ranking agreement'}));
  expect(await screen.findByText('Frozen context budgets differ between suites.')).toBeInTheDocument();
  expect(screen.queryByRole('figure',{name:'Policy ranking across question sets'})).not.toBeInTheDocument();
});

test('ignores a late ranking file read after source authorisation is revoked',async()=>{
  const user=userEvent.setup();render(<UIProvider><BenchmarkRankingAgreement/></UIProvider>);
  await user.click(screen.getByLabelText('Ranking benchmark source authorisation'));
  let resolveRead!:(value:string)=>void;
  const file=new File(['pending'],'slow.json',{type:'application/json'});
  Object.defineProperty(file,'text',{value:()=>new Promise<string>(resolve=>{resolveRead=resolve;})});
  fireEvent.change(screen.getByLabelText('Ranking reference assessments'),{target:{files:[file]}});
  await user.click(screen.getByLabelText('Ranking benchmark source authorisation'));
  await act(async()=>resolveRead('{"source":[],"evidence":{},"rows":[],"strategy":"weak_first_hit"}'));
  expect(screen.queryByText('slow.json')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Ranking reference assessments')).toBeDisabled();
  expect(mocks.compareBenchmarkRankings).not.toHaveBeenCalled();
});

test('shows Auditor macro-average separately from pooled passed-answer counts',async()=>{
  const user=userEvent.setup();render(<UIProvider><BenchmarkRankingAgreement/></UIProvider>);
  await user.click(screen.getByLabelText('Ranking benchmark source authorisation'));
  await selectUIOption(user,'Ranking reference audit',/First matching memory/);
  await selectUIOption(user,'Ranking candidate audit',/Prioritise requirements and updates/);
  await upload('reference','macro-before.json');await upload('candidate','macro-after.json');
  mocks.compareBenchmarkRankings.mockResolvedValue({agreement:'consistent',reference_strategy:'weak_first_hit',candidate_strategy:'strong_rule_based',notice:'Fixture only.',
    suites:[{label:'Audit questions',total:12,reference_correct:9,candidate_correct:3,reference_percentage:25,candidate_percentage:75,score_basis:'dimension_macro_average',ordering:'candidate_higher',
      dimensions:[{dimension:'accuracy',total:9,reference_percentage:100,candidate_percentage:0},{dimension:'freshness',total:1,reference_percentage:0,candidate_percentage:100},{dimension:'conflict_resolution',total:1,reference_percentage:0,candidate_percentage:100},{dimension:'appropriate_use',total:1,reference_percentage:0,candidate_percentage:100}]}]});
  await user.click(screen.getByRole('button',{name:'Check ranking agreement'}));
  expect(await screen.findByText('Strategy 1: Overall Memory Health 25%')).toBeInTheDocument();
  expect(screen.getByText(/9 of 12 valid answers passed/)).toBeInTheDocument();
  expect(screen.queryByText('Strategy 1: 9 / 12 · 25%')).not.toBeInTheDocument();
});

test('missing Auditor dimensions show no zero-score ranking',async()=>{
  const user=userEvent.setup();render(<UIProvider><BenchmarkRankingAgreement/></UIProvider>);
  await user.click(screen.getByLabelText('Ranking benchmark source authorisation'));
  await selectUIOption(user,'Ranking reference audit',/First matching memory/);
  await selectUIOption(user,'Ranking candidate audit',/Prioritise requirements and updates/);
  await upload('reference','missing-before.json');await upload('candidate','missing-after.json');
  mocks.compareBenchmarkRankings.mockResolvedValue({agreement:'inconclusive_missing_dimensions',reference_strategy:'weak_first_hit',candidate_strategy:'strong_rule_based',notice:'Fixture only.',
    suites:[{label:'Audit questions',total:2,reference_correct:1,candidate_correct:2,reference_percentage:null,candidate_percentage:null,score_basis:'dimension_macro_average',ordering:'unmeasured'}]});
  await user.click(screen.getByRole('button',{name:'Check ranking agreement'}));
  expect(await screen.findByText('Auditor dimension coverage is incomplete — ranking is not measured')).toBeInTheDocument();
  expect(screen.getByText('Strategy 1: Not measured')).toBeInTheDocument();
  expect(screen.queryByText(/Overall Memory Health 0%/)).not.toBeInTheDocument();
});
