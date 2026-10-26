import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Dashboard } from './Dashboard';
import type { AuditRun } from '../types/domain';
const mocks = vi.hoisted(() => ({audits:vi.fn()}));
vi.mock('../services/api',()=>({api:mocks}));
const run = (id:string,status:string,date:string,extra:Partial<AuditRun> = {}) => ({run_id:id,status,created_at:date,model:'qwen3:1.7b',memory_strategy:'scope_aware',...extra} as AuditRun);
beforeEach(()=>mocks.audits.mockReset());

test('saved model names and source dates are distinct from benchmark study results',async()=>{
  mocks.audits.mockResolvedValue([
    run('old-qwen','CREATED','2026-10-12T14:07:15.561000'),
    run('new-luna','COMPLETED','2026-10-23T09:00:00Z',{model:'openai/gpt-6-luna'}),
  ]);
  render(<Dashboard/>);
  expect(await screen.findByText(/Model names below belong to saved audits/)).toHaveTextContent('Saving a setup does not run its model');
  expect(screen.getByRole('link',{name:'Experiments'})).toHaveAttribute('href','/experiments');
  const oldHeading=screen.getByRole('heading',{name:/qwen3:1.7b/});
  const oldCard=oldHeading.closest('li')!;
  expect(within(oldCard).getByText('2026-10-12')).toHaveAttribute('datetime','2026-10-12T14:07:15.561000');
  expect(oldCard).toHaveTextContent('Setup saved');
  expect(oldCard).not.toHaveTextContent('GPT 6 Luna');
  const newCard=screen.getByRole('heading',{name:/GPT 6 Luna/}).closest('li')!;
  expect(within(newCard).getByText('2026-10-23')).toHaveAttribute('datetime','2026-10-23T09:00:00Z');
  expect(newCard).toHaveTextContent('Report ready');
});

test('workflow counts separate errors, unfinished stages and cancelled runs from model accuracy',async()=>{
  mocks.audits.mockResolvedValue([
    run('private-complete','COMPLETED','2026-01-01'),run('private-new','TESTS_EXECUTED','2026-01-05'),
    run('private-failed','FAILED','2026-01-03'),run('private-cancelled','CANCELLED','2026-01-02'),
    run('private-reassessment','COMPLETED','2026-01-04',{reproducibility:{schema_version:'v1',target_retry_policy:{max_attempts:1,timeout_seconds:10,retryable_status_codes:[]},assessment_source_run_id:'private-complete'}}),
  ]);
  render(<Dashboard/>);
  const metrics=await screen.findByLabelText('Saved audit progress');
  expect(within(metrics).getByText('Reports ready').parentElement).toHaveTextContent('2');
  expect(within(metrics).getByText('Unfinished audits').parentElement).toHaveTextContent('1');
  expect(within(metrics).getByText('Interrupted runs').parentElement).toHaveTextContent('1');
  expect(screen.getByText(/workflow counts, not a measure of model accuracy/)).toBeInTheDocument();
  expect(screen.getByText(/Saved-answer reassessment/)).toBeInTheDocument();
  expect(screen.getByRole('link',{name:'View Audit 4 report'})).toHaveAttribute('href','/audits/private-reassessment');
  expect(screen.getByRole('link',{name:'Find Audit 5 in History'})).toHaveAttribute('href','/history');
  expect(screen.queryByText('private-reassessment')).not.toBeInTheDocument();
  expect(screen.getAllByRole('heading',{level:3})[0]).toHaveTextContent('Audit 5');
});

test('empty workspace explains the first step without presenting a health score',async()=>{
  mocks.audits.mockResolvedValue([]);render(<Dashboard/>);
  expect(await screen.findByRole('heading',{name:'Start with a conversation'})).toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Start a new audit'})).toHaveAttribute('href','/new-audit');
  expect(screen.queryByRole('heading',{name:'Recent activity'})).not.toBeInTheDocument();
});

test('failed loading does not display zero counts and retry reveals saved progress',async()=>{
  mocks.audits.mockRejectedValueOnce(new Error('internal-private-error')).mockResolvedValueOnce([run('hidden','TESTS_EXECUTED','2026-01-01')]);
  render(<Dashboard/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Workspace progress could not be loaded');
  expect(screen.queryByLabelText('Saved audit progress')).not.toBeInTheDocument();
  expect(screen.queryByText('internal-private-error')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button',{name:'Try again'}));
  expect(await screen.findByText('Answers ready to assess',{exact:false})).toBeInTheDocument();
});

test('refresh shows loading before replacing previous counts and ignores results after unmount',async()=>{
  let finish!:(runs:AuditRun[])=>void;
  mocks.audits.mockResolvedValueOnce([run('one','COMPLETED','2026-01-01')]).mockImplementationOnce(()=>new Promise<AuditRun[]>(resolve=>{finish=resolve;}));
  const view=render(<Dashboard/>);
  await screen.findByLabelText('Saved audit progress');
  await userEvent.click(screen.getByRole('button',{name:'Refresh progress'}));
  expect(screen.getByRole('status')).toHaveTextContent('Loading workspace progress');
  expect(screen.queryByLabelText('Saved audit progress')).not.toBeInTheDocument();
  view.unmount();await act(async()=>finish([]));
  expect(screen.queryByText('Start with a conversation')).not.toBeInTheDocument();
});
