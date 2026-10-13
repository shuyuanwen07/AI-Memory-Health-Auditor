import { MemoryRouter } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TargetMemoryTrace } from './TargetMemoryTrace';

const mocks = vi.hoisted(() => ({ targetMemoryTrace: vi.fn() }));
vi.mock('../services/api', () => ({ api: mocks }));

const trace = {
  run_id: 'RUN1', memory_strategy: 'full_context', memory_maintenance_policy: 'append_only',
  records: ['MySQL', 'PostgreSQL'].map((value, index) => ({ memory_id: `TM${index + 1}`, canonical_value: value, lifecycle_state: 'ACTIVE', source_message_ids: ['MSG1'], relationships: [], scope: 'episodic' })),
  events: [], retrievals: [{ retrieval_id: 'RET1', test_id: 'T-REAL', question: 'Which database applies now?', selected_memory_ids: ['TM1', 'TM2'], final_response_id: 'R1',
    ranking_evidence: [{ memory_id: 'TM2', selected: true }, { memory_id: 'TM1', selected: true }],
    memory_input: { version: 'v1', record_count: 1, sent_memory_ids: ['TM1'], context_sha256: 'abc' } }],
};

test('black-box target trace never claims an empty store or controlled capacity', async () => {
  mocks.targetMemoryTrace.mockResolvedValue({...trace,target_system_adapter:'external-http',records:[],events:[],retrievals:[]});
  render(<TargetMemoryTrace runId="EXTERNAL"/>);
  await userEvent.click(screen.getByRole('button',{name:'Inspect Memory Trace'}));
  expect(await screen.findByText(/internal memory writes, retrieval decisions and actual model input are unobserved/)).toBeTruthy();
  expect(screen.queryByRole('heading',{name:'Stored memories'})).toBeNull();
  expect(screen.queryByText(/Configured retained-record limit/)).toBeNull();
});

test('distinguishes retrieved candidates from final supplied memories and maps their real identities', async () => {
  mocks.targetMemoryTrace.mockResolvedValue(trace);
  render(<TargetMemoryTrace runId="RUN1" />);
  await userEvent.click(screen.getByRole('button', { name: 'Inspect Memory Trace' }));
  await userEvent.click(await screen.findByRole('button', { name: /Retrieval 1/ }));
  expect(screen.getByText(/Which database applies now/)).toBeTruthy();
  expect(screen.queryByText(/Question 1/)).toBeNull();
  const candidates = screen.getAllByRole('listitem');
  expect(candidates[0].textContent).toContain('Memory record 2 — retrieved; not supplied to target');
  expect(candidates[0].textContent).toContain('PostgreSQL');
  expect(candidates[1].textContent).toContain('Memory record 1 — retrieved; supplied to target');
});

test('historical traces show unknown input instead of claiming retrieved records were used', async () => {
  mocks.targetMemoryTrace.mockResolvedValue({ ...trace, retrievals: [{ ...trace.retrievals[0], memory_input: null }] });
  render(<TargetMemoryTrace runId="OLD" />);
  await userEvent.click(screen.getByRole('button', { name: 'Inspect Memory Trace' }));
  await userEvent.click(await screen.findByRole('button', { name: /Retrieval 1/ }));
  expect(screen.getByText(/Actual target input is unknown/)).toBeTruthy();
  expect(screen.getAllByRole('listitem')[0].textContent).toContain('sending unknown');
});

test('zero supplied memory explicitly warns that correctness cannot prove memory use', async () => {
  mocks.targetMemoryTrace.mockResolvedValue({ ...trace, retrievals: [{ ...trace.retrievals[0],
    memory_input: { ...trace.retrievals[0].memory_input, record_count: 0, sent_memory_ids: [] } }] });
  render(<TargetMemoryTrace runId="EMPTY" />);
  await userEvent.click(screen.getByRole('button', { name: 'Inspect Memory Trace' }));
  expect(await screen.findByText(/No memory was supplied for this answer/)).toBeTruthy();
});


test('shows supplied diagnostic evidence even when it is outside normal ranking', async () => {
  mocks.targetMemoryTrace.mockResolvedValue({ ...trace, records: [...trace.records, { ...trace.records[0], memory_id: 'PACKET', canonical_value: 'Authorised source statement: use Java', lifecycle_state: 'DIAGNOSTIC_ONLY' }], retrievals: [{ ...trace.retrievals[0], memory_input: { ...trace.retrievals[0].memory_input, sent_memory_ids: ['PACKET'] } }] });
  render(<TargetMemoryTrace runId="ORACLE" />);
  await userEvent.click(screen.getByRole('button', { name: 'Inspect Memory Trace' }));
  await userEvent.click(await screen.findByRole('button', { name: /Retrieval 1/ }));
  expect(screen.getByText('Memory record 3 · supplied to target')).toBeTruthy();
  expect(screen.getByText(/Supplied outside ordinary retrieval ranking/)).toBeTruthy();
});

test('clears original retrieval evidence when switching to another audit',async()=>{
  mocks.targetMemoryTrace.mockResolvedValue(trace);
  const view=render(<TargetMemoryTrace runId="RUN1"/>);
  await userEvent.click(screen.getByRole('button',{name:'Inspect Memory Trace'}));
  expect(await screen.findByRole('heading',{name:'Stored memories'})).toBeInTheDocument();
  view.rerender(<TargetMemoryTrace runId="RUN2"/>);
  expect(screen.queryByRole('heading',{name:'Stored memories'})).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Inspect Memory Trace'})).toBeEnabled();
});


test('saved-answer reuse is informational and directs evidence to the original execution',async()=>{
  mocks.targetMemoryTrace.mockResolvedValue({...trace,shared_answer_source_run_id:'ORIGINAL',records:[],retrievals:[]});
  render(<MemoryRouter><TargetMemoryTrace runId="REPLAY"/></MemoryRouter>);
  await userEvent.click(screen.getByRole('button',{name:'Inspect Memory Trace'}));
  expect(await screen.findByRole('status')).toHaveTextContent('reused the saved target answers without another model call');
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.getByRole('link',{name:'View the original memory and model-input evidence'})).toHaveAttribute('href','/audits/ORIGINAL');
});


test('missing saved update settings do not invent consolidation or a retained-record limit',async()=>{
  mocks.targetMemoryTrace.mockResolvedValue({...trace,memory_maintenance_policy:null,target_memory_capacity:null});
  render(<TargetMemoryTrace runId="LEGACY"/>);
  await userEvent.click(screen.getByRole('button',{name:'Inspect Memory Trace'}));
  expect(await screen.findByText(/Memory updates:/)).toHaveTextContent('Memory updates: Not recorded');
  expect(screen.getByText(/Configured retained-record limit/)).toHaveTextContent('Configured retained-record limit: Not recorded');
  expect(screen.queryByText(/Replace outdated facts/)).toBeNull();
});
