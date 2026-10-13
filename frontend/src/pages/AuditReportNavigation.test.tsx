import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuditReportPage } from './StaticPages';
import type { AuditResult, AuditRun } from '../types/domain';
const mocks=vi.hoisted(()=>({results:vi.fn(),getAudit:vi.fn(),retryPlan:vi.fn(),retry:vi.fn()}));
vi.mock('../services/api',()=>({api:mocks}));
vi.mock('../components/ResultDashboard',()=>({ResultDashboard:({result,run}:{result:AuditResult;run?:AuditRun})=><><p>Loaded result {result.run_id}</p><p>Report export target: {run?.provider ?? 'Not recorded'} · {run?.model ?? 'Not recorded'}</p></>}));
vi.mock('../components/TargetMemoryTrace',()=>({TargetMemoryTrace:()=>null}));

beforeEach(()=>{mocks.getAudit.mockImplementation((run_id:string)=>Promise.resolve({run_id,model:'qwen3:1.7b',provider:'ollama',memory_strategy:'scope_aware',pipeline_provider:'rule_based',evaluator_provider:'rule_based',reproducibility:{}} as AuditRun));});

test('a delayed previous report cannot replace the newly selected audit',async()=>{
  let finishOld!:(value:AuditResult)=>void;
  mocks.results.mockImplementation((id:string)=>id==='OLD'?new Promise<AuditResult>(resolve=>{finishOld=resolve;}):Promise.resolve({run_id:'NEW'} as AuditResult));
  render(<MemoryRouter initialEntries={['/audits/OLD']}><Link to="/audits/NEW">Open newer audit</Link><Routes><Route path="/audits/:runId" element={<AuditReportPage/>}/></Routes></MemoryRouter>);
  await userEvent.click(screen.getByRole('link',{name:'Open newer audit'}));
  expect(await screen.findByText('Loaded result NEW')).toBeInTheDocument();
  await act(async()=>finishOld({run_id:'OLD'} as AuditResult));
  expect(screen.getByText('Loaded result NEW')).toBeInTheDocument();
  expect(screen.queryByText('Loaded result OLD')).not.toBeInTheDocument();
});


test('saved report identifies target model, memory approach and assessment without exposing internal IDs',async()=>{
  mocks.results.mockResolvedValue({run_id:'PRIVATE_RUN'} as AuditResult);
  render(<MemoryRouter initialEntries={['/audits/PRIVATE_RUN']}><Routes><Route path="/audits/:runId" element={<AuditReportPage/>}/></Routes></MemoryRouter>);
  const context=await screen.findByRole('region',{name:'Saved audit configuration'});
  expect(context).toHaveTextContent('qwen3:1.7b');
  expect(context).toHaveTextContent('Match the task and project');
  expect(context).toHaveTextContent('Answer assessment: Rule-based processing');
  expect(screen.getByText('Report export target: ollama · qwen3:1.7b')).toBeInTheDocument();
  expect(context).not.toHaveTextContent('PRIVATE_RUN');
});


test('missing saved settings do not hide the score or substitute current defaults',async()=>{
  mocks.getAudit.mockRejectedValue(new Error('Unavailable'));
  mocks.results.mockResolvedValue({run_id:'UNAVAILABLE'} as AuditResult);
  render(<MemoryRouter initialEntries={['/audits/UNAVAILABLE']}><Routes><Route path="/audits/:runId" element={<AuditReportPage/>}/></Routes></MemoryRouter>);
  expect(await screen.findByText('Loaded result UNAVAILABLE')).toBeInTheDocument();
  expect(await screen.findByRole('note')).toHaveTextContent('Saved model and assessment settings are unavailable');
  expect(screen.queryByText('qwen3:1.7b')).toBeNull();
});


test('saved cloud settings use readable provider names and omitted processing stays unrecorded',async()=>{
  mocks.getAudit.mockResolvedValue({run_id:'CLOUD', model:'qwen3:1.7b', provider:'ollama', memory_strategy:'scope_aware',pipeline_provider:'openrouter',pipeline_model:'google/gemini-2.5-flash-lite',reproducibility:{}} as AuditRun);
  mocks.results.mockResolvedValue({run_id:'CLOUD'} as AuditResult);
  render(<MemoryRouter initialEntries={['/audits/CLOUD']}><Routes><Route path="/audits/:runId" element={<AuditReportPage/>}/></Routes></MemoryRouter>);
  const context=await screen.findByRole('region',{name:'Saved audit configuration'});
  expect(context).toHaveTextContent('AI-assisted processing · OpenRouter');
  expect(context).toHaveTextContent('Answer assessment: Not recorded');
  expect(context).not.toHaveTextContent('Answer assessment: Rule-based processing');
});


test('saved report details distinguish absent memory settings from recorded defaults',async()=>{
  mocks.results.mockResolvedValue({run_id:'LEGACY'} as AuditResult);
  render(<MemoryRouter initialEntries={['/audits/LEGACY']}><Routes><Route path="/audits/:runId" element={<AuditReportPage/>}/></Routes></MemoryRouter>);
  await userEvent.click(await screen.findByRole('button',{name:'Memory settings · Match the task and project'}));
  expect(screen.getByText('Memory maintenance: Not recorded')).toBeInTheDocument();
  expect(screen.getByText('Target memory capacity: Not recorded')).toBeInTheDocument();
  expect(screen.getByText('Memory preparation: Not recorded')).toBeInTheDocument();
  expect(screen.getByText('Target system: Not recorded')).toBeInTheDocument();
});

test('opens incomplete progress and resumes scoring into the saved report',async()=>{
  const run={run_id:'PENDING',status:'TESTS_EXECUTED',model:'qwen3:1.7b',provider:'ollama',memory_strategy:'scope_aware'} as AuditRun;
  mocks.getAudit.mockResolvedValue(run);
  mocks.results.mockRejectedValueOnce(new Error('Results require completion')).mockResolvedValueOnce({run_id:'PENDING'} as AuditResult);
  mocks.retryPlan.mockResolvedValue({status:'TESTS_EXECUTED',retryable:true,next_stage:'evaluate_responses',pending:1,busy:false});
  mocks.retry.mockResolvedValue({...run,status:'COMPLETED'});
  render(<MemoryRouter initialEntries={['/audits/PENDING']}><Routes><Route path="/audits/:runId" element={<AuditReportPage/>}/></Routes></MemoryRouter>);
  const user=userEvent.setup();
  await user.click(await screen.findByRole('button',{name:'View recovery plan'}));
  expect(await screen.findByText(/evaluate pending responses/)).toBeInTheDocument();
  expect(screen.queryByText('Report unavailable')).toBeNull();
  await user.click(screen.getByRole('button',{name:'Resume audit'}));
  expect(await screen.findByText('Loaded result PENDING')).toBeInTheDocument();
  expect(mocks.retry).toHaveBeenCalledWith('PENDING');
});
