import { selectedUILabel, selectUIOption } from '../components/ui/testHelpers';
/**
 * Offline UI workflow smoke test.  It deliberately mocks only the transport
 * layer: state transitions remain those used by a browser running NewAudit.
 * The companion API smoke test exercises the same path against a real
 * temporary database and rule-based services.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NewAudit } from './NewAudit';

const apiMocks = vi.hoisted(() => ({
  targetProviders: vi.fn(),
  openRouterModels: vi.fn(),
  ollamaModels: vi.fn(),
  createConversation: vi.fn(),
  extract: vi.fn(),
  updateMemory: vi.fn(),
  addMemory: vi.fn(),
  confirm: vi.fn(),
  createExperiment: vi.fn(),
  createAudit: vi.fn(),
  generate: vi.fn(),
  testReview: vi.fn(),
  reviewTest: vi.fn(),
  regenerateTest: vi.fn(),
  execute: vi.fn(),
  evaluate: vi.fn(),
  cancel: vi.fn(),
  cancelExperiment: vi.fn(),
  results: vi.fn(),
  retry: vi.fn(),
  targetMemoryTrace: vi.fn(),
}));

vi.mock('../services/api', () => ({ api: apiMocks }));

const memory = {
  memory_id: 'M001', conversation_id: 'C001', canonical_value: 'The backend now uses PostgreSQL.',
  status: 'candidate', source_message_ids: ['MSG001'], relationships: [],
};
const confirmedMemory = { ...memory, status: 'confirmed' as const };
const pendingTest = {
  test_id: 'T001', run_id: 'RUN001', dimension: 'freshness' as const,
  prompt: 'Which database does the backend use now?',
  expected_behavior: 'Use PostgreSQL, not the earlier MySQL value.',
  supporting_memory_ids: ['M001'], generator_version: 'rule-based-v1',
  test_type: 'contextual' as const, quality_status: 'pending' as const,
  grounding_status: 'grounded' as const, validation_notes: 'Supported by confirmed memory.',
};
const acceptedTest = { ...pendingTest, quality_status: 'accepted' as const };
const result = {
  run_id: 'RUN001', overall_score: 100, tests_passed: 1, tests_total: 1,
  dimensions: [
    { dimension: 'accuracy' as const, percentage: null, passed: 0, total: 0 },
    { dimension: 'freshness' as const, percentage: 100, passed: 1, total: 1 },
    { dimension: 'conflict_resolution' as const, percentage: null, passed: 0, total: 0 },
    { dimension: 'appropriate_use' as const, percentage: null, passed: 0, total: 0 },
  ],
  failures: [],
};

beforeEach(() => {
  vi.resetAllMocks();
  apiMocks.openRouterModels.mockResolvedValue([{value: 'test/independent-judge', label: 'Independent judge'}]);
  apiMocks.ollamaModels.mockResolvedValue([{value: 'qwen3:1.7b', label: 'qwen3:1.7b'}, {value: 'qwen3:4b', label: 'qwen3:4b'}, ...Array.from({length: 9}, (_, i) => ({value: `qwen:${i}`, label: `qwen:${i}`}))]);
  apiMocks.targetProviders.mockResolvedValue([
    { provider: 'rule_based', label: 'Rule-Based Baseline', default_model: 'rule-based-v1', configured: true, description: 'Deterministic local target.' },
  ]);
  apiMocks.createConversation.mockResolvedValue({ conversation_id: 'C001' });
  apiMocks.extract.mockResolvedValue([memory]);
  apiMocks.updateMemory.mockResolvedValue(confirmedMemory);
  apiMocks.confirm.mockResolvedValue([confirmedMemory]);
  apiMocks.createExperiment.mockResolvedValue({ experiment_id: 'EXP001' });
  apiMocks.createAudit.mockResolvedValue({ run_id: 'RUN001' });
  apiMocks.generate.mockResolvedValue([pendingTest]);
  apiMocks.testReview.mockResolvedValue({ run_id: 'RUN001', canonical_run_id: 'RUN001', tests: [pendingTest] });
  apiMocks.reviewTest.mockResolvedValue(acceptedTest);
  apiMocks.execute.mockResolvedValue({ status: 'TESTS_EXECUTED' });
  apiMocks.evaluate.mockResolvedValue({ status: 'COMPLETED' });
  apiMocks.cancel.mockResolvedValue({ status: 'CANCELLED' });
  apiMocks.cancelExperiment.mockResolvedValue({ status: 'CANCELLED' });
  apiMocks.results.mockResolvedValue(result);
  apiMocks.targetMemoryTrace.mockResolvedValue({
    run_id: 'RUN001', memory_strategy: 'weak_first_hit',
    records: [{ memory_id: 'TM001', canonical_value: 'The backend now uses PostgreSQL.', lifecycle_state: 'ACTIVE', source_message_ids: ['MSG001'], write_order: 1, relationships: [] }],
    events: [{ event_id: 'EV001', event_type: 'WRITTEN', memory_id: 'TM001', source_message_ids: ['MSG001'], details: { writer_version: 'rule-based-v1' }, created_at: '2026-01-01T00:00:00Z' }],
    retrievals: [{ retrieval_id: 'RET001', test_id: 'T001', strategy: 'weak_first_hit', selected_memory_ids: ['TM001'], ranking_evidence: [{ memory_id: 'TM001', selected: true, reason: 'First related memory.' }], created_at: '2026-01-01T00:00:00Z' }],
  });
});

test('defaults all cloud roles to OpenRouter and freezes independent model selections', async () => {
  apiMocks.targetProviders.mockResolvedValue([
    { provider: 'rule_based', label: 'Rule-Based Baseline', default_model: 'rule-based-v1', configured: true, description: 'Offline.' },
    { provider: 'openrouter', label: 'OpenRouter', default_model: 'test/target', default_pipeline_model: 'test/pipeline', default_evaluator_model: 'test/judge', configured: true, description: 'Cloud gateway.' },
    { provider: 'deepseek', label: 'Legacy Direct Provider', default_model: 'legacy', configured: true, description: 'Historical connector.' },
  ]);
  const user = userEvent.setup();
  render(<NewAudit />);
  await user.click(screen.getByRole('checkbox', { name: /authorised to use this conversation/i }));
  await user.click(screen.getByRole('button', { name: 'Continue to Ground Truth' }));
  await screen.findByRole('heading', { name: 'Review Extracted Memories' });
  await user.click(screen.getByRole('button', { name: 'Accept' }));
  await user.click(screen.getByRole('button', { name: 'Confirm Ground Truth & Continue' }));
  await screen.findByRole('heading', { name: 'Configure Memory Audit' });
  expect(selectedUILabel('Test generation service')).toContain('OpenRouter');
  expect(selectedUILabel('Behaviour evaluator')).toContain('OpenRouter');
  expect(screen.queryByText('Legacy Direct Provider')).toBeNull();
  await chooseModel(user, 'Evaluator model', 'Independent judge');
  await user.click(screen.getByRole('button', { name: 'Start Memory Audit' }));
  expect(apiMocks.createAudit).toHaveBeenCalledWith(expect.objectContaining({
    provider: 'openrouter', model: 'test/target',
    pipeline_provider: 'openrouter', pipeline_model: 'test/pipeline',
    evaluator_provider: 'openrouter', evaluator_model: 'test/independent-judge',
  }));
});

test('completes the local audit workflow from consent through reviewed results and target trace', async () => {
  const user = userEvent.setup();
  render(<NewAudit />);

  await user.click(screen.getByRole('checkbox', { name: /authorised to use this conversation/i }));
  await user.click(screen.getByRole('button', { name: 'Continue to Ground Truth' }));
  await screen.findByRole('heading', { name: 'Review Extracted Memories' });

  await user.click(screen.getByRole('button', { name: 'Accept' }));
  await waitFor(() => expect(apiMocks.updateMemory).toHaveBeenCalledWith('M001', { status: 'confirmed' }));
  await user.click(screen.getByRole('button', { name: 'Confirm Ground Truth & Continue' }));
  await screen.findByRole('heading', { name: 'Configure Memory Audit' });

  await user.click(screen.getByRole('button', { name: 'Start Memory Audit' }));
  expect(apiMocks.createAudit).toHaveBeenCalledWith(expect.objectContaining({
    memory_strategy: 'weak_first_hit',
    memory_maintenance_policy: 'update_aware_consolidation',
    target_memory_capacity: 50,
    target_memory_writer: 'rule_based',
    model: 'rule-based-v1',
  }));
  await screen.findByRole('heading', { name: 'Prepare Memory Audit' });
  await user.click(screen.getByRole('button', { name: 'Generate Tests for Review' }));
  await screen.findByRole('heading', { name: 'Review Generated Test Suite' });

  await user.click(screen.getByRole('button', { name: 'Accept' }));
  await waitFor(() => expect(apiMocks.reviewTest).toHaveBeenCalledWith('RUN001', 'T001', 'accepted'));
  await user.click(screen.getByRole('button', { name: 'Run Audit & View Results' }));
  await screen.findByRole('heading', { name: 'Memory Health Report' });
  expect(apiMocks.execute).toHaveBeenCalledWith('RUN001');
  expect(apiMocks.evaluate).toHaveBeenCalledWith('RUN001');
  expect(screen.getAllByText('1 of 1 tests passed')).toHaveLength(2);

  await user.click(screen.getByRole('button', { name: 'Inspect Memory Trace' }));
  await screen.findByText('Stored memories');
  expect(screen.getAllByText('The backend now uses PostgreSQL.').length).toBeGreaterThan(0);
  expect(screen.getByText(/1 records retrieved/i)).toBeTruthy();
});

test('cancelling a running comparison stops the browser queue before its next condition', async () => {
  const user = userEvent.setup();
  let rejectExecution: ((reason?: unknown) => void) | undefined;
  apiMocks.createAudit
    .mockResolvedValueOnce({ run_id: 'RUN001' })
    .mockResolvedValueOnce({ run_id: 'RUN002' });
  apiMocks.execute.mockImplementationOnce(() => new Promise((_, reject) => { rejectExecution = reject; }));
  render(<NewAudit />);

  await user.click(screen.getByRole('checkbox', { name: /authorised to use this conversation/i }));
  await user.click(screen.getByRole('button', { name: 'Continue to Ground Truth' }));
  await screen.findByRole('heading', { name: 'Review Extracted Memories' });
  await user.click(screen.getByRole('button', { name: 'Accept' }));
  await user.click(screen.getByRole('button', { name: 'Confirm Ground Truth & Continue' }));
  await screen.findByRole('heading', { name: 'Configure Memory Audit' });
  await user.click(screen.getByRole('checkbox', { name: /Strong Rule-Based/i }));
  await user.click(screen.getByRole('button', { name: 'Start 2-Run Comparison' }));
  await user.click(screen.getByRole('button', { name: 'Generate Tests for Review' }));
  await screen.findByRole('heading', { name: 'Review Generated Test Suite' });
  await user.click(screen.getByRole('button', { name: 'Accept' }));
  await user.click(screen.getByRole('button', { name: 'Run Comparison & View Results' }));
  await screen.findByRole('button', { name: 'Cancel current run & stop queue' });

  await user.click(screen.getByRole('button', { name: 'Cancel current run & stop queue' }));
  expect(apiMocks.cancel).toHaveBeenCalledWith('RUN001');
  rejectExecution?.(new Error('cancelled by user'));

  await waitFor(() => expect(screen.getByText(/Execution was stopped/i)).toBeTruthy());
  expect(apiMocks.execute).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button', { name: 'Execution Queue Cancelled' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Regenerate' })).toBeDisabled();
  apiMocks.results.mockResolvedValue({ ...result, run_id: 'RUN002' });
  await user.click(screen.getByRole('button', { name: 'Continue Remaining Conditions' }));
  await screen.findByRole('heading', { name: 'Memory Health Report' });
  expect(screen.getByText('Incomplete comparison')).toBeTruthy();
  expect(screen.getByText(/1 of 2 planned runs completed · 1 cancelled · 0 unfinished/)).toBeTruthy();
  expect(apiMocks.execute).toHaveBeenCalledTimes(2);
});

test('keeps local Qwen visible and explicitly selects extraction before submitting', async () => {
  apiMocks.targetProviders.mockResolvedValue([
    { provider: 'rule_based', label: 'Rule-Based Baseline', default_model: 'rule-based-v1', configured: true, description: 'Offline.' },
    { provider: 'openrouter', label: 'OpenRouter', default_model: 'cloud', configured: false, description: 'Missing key.' },
    { provider: 'ollama', label: 'Local Qwen', default_model: 'qwen3:1.7b', configured: true, description: 'Local API.' },
  ]);
  const user = userEvent.setup();
  render(<NewAudit />);
  const extraction = await screen.findByLabelText('Memory extraction service');
  await waitFor(() => expect(selectedUILabel('Memory extraction service')).toContain('Rule-Based Baseline'));
  await user.click(extraction);
  expect(await screen.findAllByRole('option')).toHaveLength(2);
  await user.keyboard('{Escape}');
  await user.click(screen.getByRole('checkbox', { name: /authorised to use this conversation/i }));
  await user.click(screen.getByRole('button', { name: 'Continue to Ground Truth' }));
  await screen.findByRole('heading', { name: 'Review Extracted Memories' });
  expect(apiMocks.extract).toHaveBeenCalledWith('C001', 'rule_based', undefined);
  await user.click(screen.getByRole('button', { name: 'Accept' }));
  await user.click(screen.getByRole('button', { name: 'Confirm Ground Truth & Continue' }));
  expect(await screen.findByText('Local Qwen')).toBeTruthy();
  await selectUIOption(user, 'Behaviour evaluator', 'Local Qwen');
  expect(screen.getByRole('note').textContent).toContain('same model for answers and judging can share errors');
  expect(selectedUILabel('Evaluator model')).toContain('qwen3:1.7b');
  await user.click(screen.getByRole('button', { name: 'Start Memory Audit' }));
  expect(apiMocks.createExperiment).toHaveBeenCalledWith(expect.objectContaining({
    test_suite_configuration: expect.objectContaining({evaluator_provider: 'ollama', evaluator_model: 'qwen3:1.7b', pipeline_provider: 'rule_based'}),
  }));
  expect(apiMocks.createAudit).toHaveBeenCalledWith(expect.objectContaining({evaluator_provider: 'ollama', evaluator_model: 'qwen3:1.7b'}));
});


async function reachCreationConfiguration(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('checkbox', { name: /authorised to use this conversation/i }));
  await user.click(screen.getByRole('button', { name: 'Continue to Ground Truth' }));
  await screen.findByRole('heading', { name: 'Review Extracted Memories' });
  await user.click(screen.getByRole('button', { name: 'Accept' }));
  await user.click(screen.getByRole('button', { name: 'Confirm Ground Truth & Continue' }));
  await screen.findByRole('heading', { name: 'Configure Memory Audit' });
}

test('lost experiment response retries the frozen request identity before any model calls', async () => {
  apiMocks.createExperiment.mockRejectedValueOnce(new Error('Connection interrupted after save'));
  const user = userEvent.setup(); render(<NewAudit />);
  await reachCreationConfiguration(user);
  await user.click(screen.getByRole('button', { name: 'Start Memory Audit' }));
  await screen.findByRole('heading', { name: 'Continue Preparing Your Audit' });
  expect(screen.queryByLabelText('Target memory capacity')).toBeNull();
  const originalBody = apiMocks.createExperiment.mock.calls[0][0];
  expect(originalBody.creation_request_key).toMatch(/^[a-f0-9-]{36}$/);
  expect(apiMocks.createAudit).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Resume Audit Preparation' }));
  await screen.findByRole('heading', { name: 'Prepare Memory Audit' });
  expect(apiMocks.createExperiment.mock.calls[1][0]).toEqual(originalBody);
  expect(apiMocks.execute).not.toHaveBeenCalled();
});

test('partial comparison retries only the unknown condition with its original key', async () => {
  apiMocks.createAudit.mockResolvedValueOnce({ run_id: 'RUN001' }).mockRejectedValueOnce(new Error('Response lost')).mockResolvedValueOnce({ run_id: 'RUN002' });
  const user = userEvent.setup(); render(<NewAudit />);
  await reachCreationConfiguration(user);
  await user.click(screen.getByRole('checkbox', { name: /Scope-Aware/i }));
  await user.click(screen.getByRole('button', { name: 'Start 2-Run Comparison' }));
  await screen.findByRole('heading', { name: 'Continue Preparing Your Audit' });
  expect(screen.getByText(/1 of 2 conditions acknowledged/)).toBeTruthy();
  const unknownBody = apiMocks.createAudit.mock.calls[1][0];
  expect(unknownBody.creation_request_key).not.toEqual(apiMocks.createAudit.mock.calls[0][0].creation_request_key);
  await user.click(screen.getByRole('button', { name: 'Resume Audit Preparation' }));
  await screen.findByRole('heading', { name: 'Prepare Memory Audit' });
  expect(apiMocks.createExperiment).toHaveBeenCalledTimes(1);
  expect(apiMocks.createAudit).toHaveBeenCalledTimes(3);
  expect(apiMocks.createAudit.mock.calls[2][0]).toEqual(unknownBody);
  expect(apiMocks.execute).not.toHaveBeenCalled();
});


test('compares unique models on one service with identical frozen settings and distinct labels', async () => {
  apiMocks.targetProviders.mockResolvedValue([
    { provider: 'rule_based', label: 'Rule-Based Baseline', default_model: 'rule-based-v1', configured: true, description: 'Offline.' },
    { provider: 'ollama', label: 'Local models (Ollama)', default_model: 'qwen3:1.7b', configured: true, description: 'Local API.' },
  ]);
  apiMocks.createAudit.mockResolvedValueOnce({ run_id: 'RUN001' }).mockResolvedValueOnce({ run_id: 'RUN002' });
  apiMocks.results.mockImplementation(async (runId: string) => ({ ...result, run_id: runId }));
  const user = userEvent.setup(); render(<NewAudit />);
  await reachCreationConfiguration(user);
  await user.click(screen.getByRole('checkbox', { name: /Local models/ }));
  await user.click(screen.getByRole('checkbox', { name: /Rule-Based Baseline/ }));
  await chooseModel(user, 'Target model for Local models (Ollama)', 'qwen3:4b');
  expect(screen.getByText(/2 planned runs · up to 16 answer requests/)).toBeTruthy();
  await user.click(screen.getByRole('button', { name: 'Start 2-Run Comparison' }));
  await screen.findByRole('heading', { name: 'Prepare Memory Audit' });
  expect(apiMocks.createExperiment).toHaveBeenCalledTimes(1);
  const bodies = apiMocks.createAudit.mock.calls.map(([body]) => body);
  expect(bodies.map((body) => body.model)).toEqual(['qwen3:1.7b', 'qwen3:4b']);
  expect(bodies[0].creation_request_key).not.toEqual(bodies[1].creation_request_key);
  const { model: firstModel, creation_request_key: firstKey, ...firstSettings } = bodies[0];
  const { model: secondModel, creation_request_key: secondKey, ...secondSettings } = bodies[1];
  expect(firstSettings).toEqual(secondSettings);
  await user.click(screen.getByRole('button', { name: 'Generate Tests for Review' }));
  await screen.findByRole('heading', { name: 'Review Generated Test Suite' });
  await user.click(screen.getByRole('button', { name: 'Accept' }));
  await user.click(screen.getByRole('button', { name: 'Run Comparison & View Results' }));
  await screen.findByRole('heading', { name: 'Memory Health Model Comparison' });
  expect(apiMocks.generate).toHaveBeenCalledTimes(1);
  expect(apiMocks.execute.mock.calls).toEqual([['RUN001'], ['RUN002']]);
  expect(screen.getByText('Local models (Ollama) · qwen3:1.7b · Weak First-Hit detailed report')).toBeTruthy();
  expect(screen.getByText('Local models (Ollama) · qwen3:4b · Weak First-Hit detailed report')).toBeTruthy();
});

test('blocks empty model selections, caps the picker at eight and keeps rule identity fixed', async () => {
  apiMocks.targetProviders.mockResolvedValue([
    { provider: 'rule_based', label: 'Rule-Based Baseline', default_model: 'rule-based-v1', configured: true, description: 'Offline.' },
    { provider: 'ollama', label: 'Local models (Ollama)', default_model: 'qwen3:1.7b', configured: true, description: 'Local API.' },
  ]);
  const user = userEvent.setup(); render(<NewAudit />);
  await reachCreationConfiguration(user);
  expect(screen.getByLabelText(/Target model for Rule-Based Baseline/)).toBeDisabled();
  await user.click(screen.getByRole('checkbox', { name: /Local models/ }));
  const models = screen.getByRole('combobox', {name: 'Target model for Local models (Ollama)'});
  await user.click(models.closest('.ant-select')!.querySelector('.ant-select-selection-item-remove') as HTMLElement);
  expect(screen.getByRole('alert')).toHaveTextContent('Select at least one model for Local models (Ollama)');
  expect(screen.getByRole('button', { name: 'Start Memory Audit' })).toBeDisabled();
  for (let i = 0; i < 8; i++) await chooseModel(user, 'Target model for Local models (Ollama)', `qwen:${i}`);
  await user.click(models);
  await user.clear(models);
  await user.type(models, 'qwen:8');
  await user.keyboard('{Enter}');
  expect(models.closest('.ant-select')!.querySelectorAll('.ant-select-selection-item')).toHaveLength(8);
  expect(apiMocks.createAudit).not.toHaveBeenCalled();
});

async function chooseModel(user: ReturnType<typeof userEvent.setup>, label: string, option: string) {
  const input = screen.getByRole('combobox', {name: label});
  await user.click(input);
  await user.type(input, option);
  await user.click(await screen.findByText(option, {selector: '.ant-select-item-option-content'}));
  await user.keyboard('{Escape}');
}
