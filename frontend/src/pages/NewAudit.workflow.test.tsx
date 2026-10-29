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
import { defaultTargetProfile } from '../components/TargetProfileEditor';
import presentationDemo from '../data/presentationDemo.json';
import presentationDemoRaw from '../data/presentationDemo.json?raw';
import {saveBlob} from '../services/download';
vi.mock('../services/download',()=>({saveBlob:vi.fn()}));

const apiMocks = vi.hoisted(() => ({
  targetProviders: vi.fn(),
  getConversation: vi.fn(),
  conversationMemories: vi.fn(),
  conversationAgentExecutions: vi.fn(),
  audits: vi.fn(),
  openRouterModels: vi.fn(),
  openRouterModelChecks: vi.fn(),
  checkOpenRouterModel: vi.fn(),
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
  reviewQuestionScopes: vi.fn(),
  reviewTest: vi.fn(),
  regenerateTest: vi.fn(),
  execute: vi.fn(),
  reuseAnswers: vi.fn(),
  evaluate: vi.fn(),
  cancel: vi.fn(),
  cancelExperiment: vi.fn(),
  results: vi.fn(),
  retry: vi.fn(),
  retryPlan: vi.fn(),
  continueGeneration: vi.fn(),
  targetMemoryTrace: vi.fn(),
  targetSystems: vi.fn(),
  coveragePreview: vi.fn(),
  auditorQuality: vi.fn(),
  experimentGroups: vi.fn(),
  savedFormalRuns: vi.fn(),
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
  sessionStorage.clear();
  vi.resetAllMocks();
  apiMocks.getConversation.mockResolvedValue({conversation_id:'C001',authorised:true,messages:[{message_id:'MSG001',role:'user',content:'The backend now uses PostgreSQL.',timestamp:'2026-01-01T00:00:00Z'}]});
  apiMocks.conversationMemories.mockResolvedValue([confirmedMemory]);
  apiMocks.conversationAgentExecutions.mockResolvedValue([]);
  apiMocks.audits.mockResolvedValue([]);
  const verifiedMockModels = ['test/independent-judge', 'test/target', 'test/pipeline', 'test/judge', 'test/generator', 'cloud', 'cloud/new-default', 'changed/cloud-default', 'target']
    .map(value => ({ value, label: value === 'test/independent-judge' ? 'Independent judge' : value, status: 'available' as const, checked_at: '2026-10-12T00:00:00Z' }));
  apiMocks.openRouterModels.mockResolvedValue(verifiedMockModels.map(({ value, label }) => ({ value, label })));
  apiMocks.openRouterModelChecks.mockResolvedValue(verifiedMockModels);
  apiMocks.ollamaModels.mockResolvedValue([{value: 'qwen3:1.7b', label: 'qwen3:1.7b'}, {value: 'qwen3:4b', label: 'qwen3:4b'}, ...Array.from({length: 9}, (_, i) => ({value: `qwen:${i}`, label: `qwen:${i}`}))]);
  apiMocks.targetProviders.mockResolvedValue([
    { provider: 'rule_based', label: 'Rule-Based Baseline', default_model: 'rule-based-v1', configured: true, description: 'Deterministic local target.' },
  ]);
  apiMocks.targetSystems.mockResolvedValue([{value:'controlled-memory',label:'Controlled memory',configured:true}]);
  apiMocks.coveragePreview.mockImplementation(async (_id: string, budget: number) => ({
    requested_test_count: budget, minimum_met: budget >= 4,
    dimensions: ['accuracy','freshness','conflict_resolution','appropriate_use'].map((dimension, index) => {
      const required = budget < 4 ? 1 : Math.floor(budget / 4) + Number(index < budget % 4);
      return {
        dimension, evidence_supported: true, reason: 'Synthetic workflow fixture.',
        planned_question_count: required, required_question_count: required,
        available_question_count: 8, accepted_question_count: 0,
      };
    }),
  }));
  apiMocks.createConversation.mockResolvedValue({ conversation_id: 'C001' });
  apiMocks.auditorQuality.mockRejectedValue(new Error('not available in this workflow fixture'));
  apiMocks.experimentGroups.mockResolvedValue([]);
  apiMocks.savedFormalRuns.mockResolvedValue({ items: [] });
  apiMocks.extract.mockResolvedValue([memory]);
  apiMocks.updateMemory.mockResolvedValue(confirmedMemory);
  apiMocks.confirm.mockResolvedValue([confirmedMemory]);
  apiMocks.createExperiment.mockResolvedValue({ experiment_id: 'EXP001' });
  apiMocks.createAudit.mockResolvedValue({ run_id: 'RUN001' });
  apiMocks.generate.mockResolvedValue([pendingTest]);
  apiMocks.testReview.mockResolvedValue({ run_id: 'RUN001', canonical_run_id: 'RUN001', tests: [pendingTest] });
  apiMocks.reviewQuestionScopes.mockResolvedValue({ run_id: 'RUN001', canonical_run_id: 'RUN001', tests: [pendingTest] });
  apiMocks.reviewTest.mockResolvedValue(acceptedTest);
  apiMocks.retryPlan.mockResolvedValue({busy:false,retryable:true,next_stage:'evaluate_responses',pending:1});
  apiMocks.execute.mockResolvedValue({ status: 'TESTS_EXECUTED' });
  apiMocks.reuseAnswers.mockResolvedValue({status:'TESTS_EXECUTED'});
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

test('keeps pasted drafts out of browser storage until consent and clears them when consent is withdrawn',async()=>{
  const user=userEvent.setup();render(<NewAudit/>);
  await user.type(screen.getByLabelText('Authorised conversation text'),'A local draft');
  expect(sessionStorage.getItem('mha-new-audit-draft-v1')).toBeNull();
  await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
  await waitFor(()=>expect(JSON.parse(sessionStorage.getItem('mha-new-audit-draft-v1')!).text).toContain('A local draft'));
  await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
  await waitFor(()=>expect(sessionStorage.getItem('mha-new-audit-draft-v1')).toBeNull());
});

test('configured OpenRouter defaults to three methods with two reviewed suites and a saved comparison', async () => {
  apiMocks.targetProviders.mockResolvedValue([
    { provider: 'rule_based', label: 'Rule-Based Baseline', default_model: 'rule-based-v1', configured: true, description: 'Offline.' },
    { provider: 'openrouter', label: 'OpenRouter', default_model: 'test/target', default_pipeline_model: 'test/pipeline', default_evaluator_model: 'test/judge', configured: true, description: 'Cloud.' },
  ]);
  let experimentCount = 0, runCount = 0;
  apiMocks.createExperiment.mockImplementation(async () => ({ experiment_id: `EXP${++experimentCount}` }));
  apiMocks.createAudit.mockImplementation(async () => ({ run_id: `RUN${++runCount}` }));
  apiMocks.testReview.mockImplementation(async (runId: string) => ({ tests: [{ ...acceptedTest, run_id: runId, test_id: `T-${runId}` }] }));
  apiMocks.results.mockImplementation(async (runId: string) => ({ ...result, run_id: runId }));
  const user = userEvent.setup();
  render(<NewAudit />);
  await user.click(screen.getByRole('checkbox', { name: /authorised to use this conversation/i }));
  await user.click(screen.getByRole('button', { name: 'Continue to Ground Truth' }));
  await screen.findByRole('heading', { name: 'Review Extracted Memories' });
  await user.click(screen.getByRole('button', { name: 'Accept' }));
  await user.click(screen.getByRole('button', { name: 'Confirm Ground Truth & Continue' }));
  expect(await screen.findByRole('checkbox', { name: /compare all three audit methods/i })).toBeChecked();
  await user.click(screen.getByRole('button', { name: 'Start 3-Run Comparison' }));
  await screen.findByRole('heading', { name: 'Prepare Memory Audit' });
  expect(apiMocks.createExperiment).toHaveBeenCalledTimes(2);
  const configurations = apiMocks.createExperiment.mock.calls.map(([body]) => body.test_suite_configuration);
  expect(configurations[0].auditor_comparison_id).toBe(configurations[1].auditor_comparison_id);
  expect(configurations[1].compare_evaluators).toBe(true);
  expect(apiMocks.createAudit.mock.calls.every(([body]) => body.target_memory_profile.output_token_limit === 2048)).toBe(true);
  expect(apiMocks.createAudit.mock.calls.map(([body]) => [body.pipeline_provider, body.evaluator_provider])).toEqual([
    ['rule_based', 'rule_based'], ['openrouter', 'rule_based'], ['openrouter', 'openrouter'],
  ]);
  await user.click(screen.getByRole('button', { name: 'Generate Tests for Review' }));
  await screen.findByRole('heading', { name: 'Model-generated questions · shared by both reviewers' });
  expect(apiMocks.generate).toHaveBeenCalledTimes(2);
  await user.click(screen.getByRole('button', { name: 'Run Comparison & View Results' }));
  await screen.findByRole('heading', { name: 'Audit Method Comparison' });
  expect(apiMocks.execute).toHaveBeenCalledTimes(2);
  expect(apiMocks.reuseAnswers).toHaveBeenCalledWith('RUN3','RUN2');
  expect(screen.getByRole('link', { name: 'Open saved three-method comparison' })).toHaveAttribute('href', '/audit-methods?groups=EXP1%2CEXP2');
});

test('defaults internal Agents to the shared OpenRouter model and freezes its use', async () => {
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
  expect(screen.getByRole('checkbox', {name: /compare all three audit methods/i})).toBeChecked();
  expect(screen.getByText(/OpenRouter · test\/pipeline/)).toBeTruthy();
  expect(screen.queryByText('Legacy Direct Provider')).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Start 3-Run Comparison' }));
  expect(apiMocks.createAudit).toHaveBeenCalledWith(expect.objectContaining({
    provider: 'openrouter', model: 'test/target',
    pipeline_provider: 'openrouter', pipeline_model: 'test/pipeline',
    evaluator_provider: 'openrouter', evaluator_model: 'test/pipeline',
  }));
});

test('explains Agents and ground truth at setup without changing the workflow labels', async () => {
  const user = userEvent.setup();
  render(<NewAudit />);

  await screen.findByRole('combobox', { name: 'Shared Agent service' });
  expect(screen.getByText(/An Agent is an AI task worker for one audit step/)).toBeInTheDocument();

  await user.click(screen.getByRole('checkbox', { name: /authorised to use this conversation/i }));
  await user.click(screen.getByRole('button', { name: 'Continue to Ground Truth' }));
  await screen.findByRole('heading', { name: 'Review Extracted Memories' });
  await user.click(screen.getByRole('button', { name: 'Accept' }));
  await user.click(screen.getByRole('button', { name: 'Confirm Ground Truth & Continue' }));
  await screen.findByRole('heading', { name: 'Configure Memory Audit' });
  expect(screen.getByText(/Ground truth is the set of conversation-supported facts you confirmed/)).toBeInTheDocument();
  expect(screen.getByText(/The Agent needs at least one distinct, evidence-backed question for each ability/)).toBeInTheDocument();
  expect(screen.getByText(/Proposal Category Coverage also counts a dimension once it has at least one valid question/)).toBeInTheDocument();
});

test('allocates an eight-question budget around a single conflict evidence slot', async () => {
  apiMocks.targetProviders.mockResolvedValue([
    { provider: 'rule_based', label: 'Rule-Based Baseline', default_model: 'rule-based-v1', configured: true, description: 'Offline.' },
    { provider: 'openrouter', label: 'OpenRouter', default_model: 'test/target', default_pipeline_model: 'test/pipeline', default_evaluator_model: 'test/judge', configured: true, description: 'Cloud.' },
  ]);
  const dimensions = ['accuracy','freshness','conflict_resolution','appropriate_use'];
  const required = [3,2,1,2];
  const available = [6,2,1,2];
  apiMocks.coveragePreview.mockResolvedValue({
    requested_test_count: 8, minimum_met: true,
    dimensions: dimensions.map((dimension, index) => ({
      dimension, evidence_supported: true, reason: 'Synthetic source fixture.',
      planned_question_count: required[index], required_question_count: required[index],
      available_question_count: available[index], accepted_question_count: 0,
    })),
  });

  const user = userEvent.setup();
  render(<NewAudit />);
  await reachCreationConfiguration(user);

  expect(await screen.findByText(/Evidence-based question allocation: accuracy 3 · freshness 2 · conflict resolution 1 · appropriate use 2\./)).toBeInTheDocument();
  expect(screen.queryByText(/Insufficient coverage:/)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Start 3-Run Comparison' })).toBeEnabled();
  expect(apiMocks.createAudit).not.toHaveBeenCalled();
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

  await user.click(screen.getByRole('button', { name: 'Check question scope against source' }));
  await waitFor(() => expect(apiMocks.reviewQuestionScopes).toHaveBeenCalledWith('RUN001'));
  expect(screen.getByRole('button', { name: 'Run Audit & View Results' })).toBeDisabled();

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
  await user.click(screen.getByRole('checkbox', { name: /Relationship-priority retrieval/i }));
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

test('selects local Qwen as the shared Agent before extracting and freezes it for the audit', async () => {
  apiMocks.targetProviders.mockResolvedValue([
    { provider: 'rule_based', label: 'Rule-Based Baseline', default_model: 'rule-based-v1', configured: true, description: 'Offline.' },
    { provider: 'openrouter', label: 'OpenRouter', default_model: 'cloud', configured: false, description: 'Missing key.' },
    { provider: 'ollama', label: 'Local Qwen', default_model: 'qwen3:1.7b', configured: true, description: 'Local API.' },
  ]);
  const user = userEvent.setup();
  render(<NewAudit />);
  await screen.findByLabelText('Shared Agent service');
  await selectUIOption(user, 'Shared Agent service', 'Local Qwen');
  await user.click(screen.getByRole('checkbox', { name: /authorised to use this conversation/i }));
  await user.click(screen.getByRole('button', { name: 'Continue to Ground Truth' }));
  await screen.findByRole('heading', { name: 'Review Extracted Memories' });
  expect(apiMocks.extract).toHaveBeenCalledWith('C001', 'ollama', 'qwen3:1.7b');
  await user.click(screen.getByRole('button', { name: 'Accept' }));
  await user.click(screen.getByRole('button', { name: 'Confirm Ground Truth & Continue' }));
  expect(await screen.findByText(/Local Qwen · qwen3:1.7b/)).toBeTruthy();
  await user.click(screen.getByRole('button', { name: 'Start 3-Run Comparison' }));
  expect(apiMocks.createAudit).toHaveBeenCalledWith(expect.objectContaining({pipeline_provider: 'ollama', pipeline_model: 'qwen3:1.7b', evaluator_provider: 'ollama', evaluator_model: 'qwen3:1.7b'}));
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
  await user.click(screen.getByRole('checkbox', { name: /Match the task and project/i }));
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
  await user.click(screen.getByRole('checkbox', {name:/compare all three audit methods/i}));
  await chooseModel(user, 'Target model for Local models (Ollama)', 'qwen3:4b');
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
  expect(screen.getByText('Local models (Ollama) · qwen3:1.7b · AI retrieval Agent detailed report')).toBeTruthy();
  expect(screen.getByText('Local models (Ollama) · qwen3:4b · AI retrieval Agent detailed report')).toBeTruthy();
});

test('blocks empty model selections, caps the picker at eight and keeps rule identity fixed', async () => {
  apiMocks.targetProviders.mockResolvedValue([
    { provider: 'rule_based', label: 'Rule-Based Baseline', default_model: 'rule-based-v1', configured: true, description: 'Offline.' },
    { provider: 'ollama', label: 'Local models (Ollama)', default_model: 'qwen3:1.7b', configured: true, description: 'Local API.' },
  ]);
  const user = userEvent.setup(); render(<NewAudit />);
  await reachCreationConfiguration(user);
  await user.click(screen.getByRole('checkbox', {name:/compare all three audit methods/i}));
  await user.click(screen.getByRole('checkbox', {name:/Rule-Based Baseline/}));
  expect(screen.getByRole('combobox', { name: /Target model for Rule-Based Baseline/ })).toBeDisabled();
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
  const optionContent = await waitFor(() => {
    const match = [...document.querySelectorAll('.ant-select-dropdown .ant-select-item-option-content')]
      .find(element => element.textContent?.trim() === option);
    if (!match) throw new Error(`Visible model option not found: ${option}`);
    return match;
  });
  await user.click(optionContent);
  await user.keyboard('{Escape}');
}


test('uses one selected shared Agent model for extraction and audit preparation',async()=>{
  apiMocks.targetProviders.mockResolvedValue([
    {provider:'rule_based',label:'Rule-Based Baseline',default_model:'rules',configured:true,description:'Offline.'},
    {provider:'openrouter',label:'OpenRouter',default_model:'target',default_pipeline_model:'test/generator',default_evaluator_model:'test/judge',configured:true,description:'Cloud.'},
  ]);
  const user=userEvent.setup();
  render(<NewAudit/>);
  await screen.findByLabelText('Shared Agent service');
  await waitFor(()=>expect(selectedUILabel('Shared Agent service')).toContain('OpenRouter'));
  await reachCreationConfiguration(user);
  expect(apiMocks.extract).toHaveBeenCalledWith('C001','openrouter','test/generator');
  expect(screen.getByText(/OpenRouter · test\/generator/)).toBeTruthy();
  const target=screen.getByRole('checkbox',{name:/OpenRouter.*Cloud/i});
  await user.click(target);
  expect(target).not.toBeChecked();
  expect(screen.getByRole('button',{name:'Start Memory Audit'})).toBeDisabled();
  expect(screen.getByText(/Choose at least one target service/)).toBeTruthy();
  await user.click(target);
  await user.click(screen.getByRole('button',{name:'Start 3-Run Comparison'}));
  await screen.findByRole('heading',{name:'Prepare Memory Audit'});
  expect(apiMocks.createAudit.mock.calls.map(([body])=>body.pipeline_provider)).toEqual(['rule_based','openrouter','openrouter']);
  expect(apiMocks.createAudit.mock.calls[1][0].pipeline_model).toBe('test/generator');
});

test('one recovery action finishes durable stages for every interrupted comparison condition',async()=>{
  apiMocks.targetProviders.mockResolvedValue([{provider:'openrouter',label:'OpenRouter',default_model:'test/target',default_pipeline_model:'test/pipeline',default_evaluator_model:'test/judge',configured:true,description:'Cloud.'}]);
  let experimentCount=0,runCount=0;
  apiMocks.createExperiment.mockImplementation(async()=>({experiment_id:`EXP${++experimentCount}`}));
  apiMocks.createAudit.mockImplementation(async()=>({run_id:`RUN${++runCount}`}));
  apiMocks.testReview.mockImplementation(async(runId:string)=>({tests:[{...acceptedTest,run_id:runId,test_id:`T-${runId}`}]}));
  apiMocks.results.mockImplementation(async(runId:string)=>({...result,run_id:runId}));
  apiMocks.execute.mockResolvedValueOnce({status:'TESTS_EXECUTED'}).mockRejectedValueOnce(new Error('Connection interrupted'));
  apiMocks.reuseAnswers.mockRejectedValueOnce(new Error('Source condition still running'));
  const recoveryCounts=new Map<string,number>();
  apiMocks.retry.mockImplementation(async(id:string)=>{const count=(recoveryCounts.get(id)||0)+1;recoveryCounts.set(id,count);return {status:count===1?'TESTS_EXECUTED':'COMPLETED'};});
  const user=userEvent.setup();render(<NewAudit/>);
  await reachCreationConfiguration(user);
  await user.click(screen.getByRole('button',{name:'Start 3-Run Comparison'}));
  await user.click(await screen.findByRole('button',{name:'Generate Tests for Review'}));
  await user.click(await screen.findByRole('button',{name:'Run Comparison & View Results'}));
  await user.click(await screen.findByRole('button',{name:'Check progress & resume'}));
  await waitFor(()=>expect(screen.queryByRole('button',{name:'Check progress & resume'})).toBeNull());
  expect(apiMocks.retry.mock.calls.map(([id])=>id)).toEqual(['RUN2','RUN2','RUN3','RUN3']);
  expect(apiMocks.execute).toHaveBeenCalledTimes(2);
  expect(apiMocks.reuseAnswers).toHaveBeenCalledTimes(1);
});


test('an interrupted single audit exposes recovery and checks a live stage without executing again',async()=>{
  apiMocks.execute.mockRejectedValueOnce(new Error('Connection interrupted'));
  apiMocks.retryPlan.mockResolvedValueOnce({busy:true,busy_reason:'this_run',retryable:true,next_stage:'execute_tests',pending:1}).mockResolvedValue({busy:false,retryable:true,next_stage:'evaluate_responses',pending:1});
  apiMocks.retry.mockResolvedValue({status:'COMPLETED'});
  const user=userEvent.setup();render(<NewAudit/>);
  await reachCreationConfiguration(user);
  await user.click(screen.getByRole('button',{name:'Start Memory Audit'}));
  await user.click(await screen.findByRole('button',{name:'Generate Tests for Review'}));
  await user.click(await screen.findByRole('button',{name:'Accept'}));
  await user.click(screen.getByRole('button',{name:'Run Audit & View Results'}));
  expect(await screen.findByRole('heading',{name:'Audit needs attention'})).toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Check progress & resume'}));
  expect(await screen.findByText(/Work is still running in the background/)).toBeInTheDocument();
  expect(apiMocks.retry).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Check progress & resume'}));
  expect(await screen.findByRole('heading',{name:'Memory Health Report'})).toBeInTheDocument();
  expect(apiMocks.execute).toHaveBeenCalledTimes(1);
  expect(apiMocks.retry).toHaveBeenCalledTimes(1);
});

test('refresh restores saved review decisions and full source without another extraction or creation', async () => {
  const user = userEvent.setup();
  const first = render(<NewAudit/>);
  await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
  await user.click(screen.getByRole('button',{name:'Continue to Ground Truth'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  await user.click(screen.getByRole('button',{name:'Accept'}));
  first.unmount();
  apiMocks.conversationMemories.mockResolvedValue([confirmedMemory,{...memory,memory_id:'M002',canonical_value:'Background explanation',status:'rejected'}]);
  render(<NewAudit/>);
  expect(screen.getByRole('region',{name:'Unfinished memory review'})).toBeTruthy();
  await user.click(screen.getByRole('button',{name:'Resume saved review'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  expect(screen.getByText(/Saved review.*restored/)).toBeTruthy();
  expect(screen.getByRole('status',{name:'Memory review summary'})).toHaveTextContent('Rejected 1');
  await user.click(screen.getByRole('button',{name:/Read the complete original conversation/}));
  expect(await screen.findByText('The backend now uses PostgreSQL.',{selector:'.review-source-history p'})).toBeTruthy();
  expect(apiMocks.createConversation).toHaveBeenCalledTimes(1);
  expect(apiMocks.extract).toHaveBeenCalledTimes(1);
  expect(apiMocks.execute).not.toHaveBeenCalled();
});

test('failed review recovery remains retryable without creating new source data', async () => {
  sessionStorage.setItem('mha-new-audit-review-v1',JSON.stringify({conversationId:'C001'}));
  apiMocks.getConversation.mockRejectedValueOnce(new Error('Connection interrupted'));
  const user=userEvent.setup();render(<NewAudit/>);
  await user.click(screen.getByRole('button',{name:'Resume saved review'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Connection interrupted');
  await user.click(screen.getByRole('button',{name:'Resume saved review'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  expect(apiMocks.createConversation).not.toHaveBeenCalled();
  expect(apiMocks.extract).not.toHaveBeenCalled();
});

test('recovery redirects frozen reference memories to history instead of offering edits', async () => {
  sessionStorage.setItem('mha-new-audit-review-v1',JSON.stringify({conversationId:'C001'}));
  apiMocks.audits.mockResolvedValue([{conversation_id:'C001',run_id:'RUN001'}]);
  const user=userEvent.setup();render(<NewAudit/>);
  await user.click(screen.getByRole('button',{name:'Resume saved review'}));
  expect(await screen.findByText(/An audit already uses this conversation/)).toBeTruthy();
  expect(screen.queryByRole('heading',{name:'Review Extracted Memories'})).toBeNull();
  expect(apiMocks.updateMemory).not.toHaveBeenCalled();
  expect(apiMocks.execute).not.toHaveBeenCalled();
});

test('configuration survives refresh and configured cloud defaults cannot replace restored selections', async () => {
  const user=userEvent.setup();const first=render(<NewAudit/>);
  await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
  await user.click(screen.getByRole('button',{name:'Continue to Ground Truth'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  await user.click(screen.getByRole('button',{name:'Accept'}));
  await user.click(screen.getByRole('button',{name:'Confirm Ground Truth & Continue'}));
  await screen.findByRole('heading',{name:'Configure Memory Audit'});
  await user.clear(screen.getByRole('spinbutton',{name:/Requested test count/}));await user.type(screen.getByRole('spinbutton',{name:/Requested test count/}),'3');
  await user.clear(screen.getByLabelText('Answer length limit'));await user.type(screen.getByLabelText('Answer length limit'),'256');
  await user.type(screen.getByLabelText('Additional target instructions'),'Use the latest facts for the current task.');
  first.unmount();
  apiMocks.targetProviders.mockResolvedValue([
    {provider:'rule_based',label:'Rule-Based Baseline',configured:true,default_model:'changed-baseline'},
    {provider:'openrouter',label:'OpenRouter',configured:true,default_model:'cloud/new-default'}]);
  render(<NewAudit/>);
  await user.click(screen.getByRole('button',{name:'Resume saved review'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  await user.click(screen.getByRole('button',{name:'Confirm Ground Truth & Continue'}));
  expect(await screen.findByRole('heading',{name:'Configure Memory Audit'})).toBeTruthy();
  expect(screen.getByRole('spinbutton',{name:/Requested test count/})).toHaveValue('3');
  expect(screen.getByLabelText('Answer length limit')).toHaveValue('256');
  expect(screen.getByLabelText('Additional target instructions')).toHaveValue('Use the latest facts for the current task.');
  expect(screen.getByRole('checkbox',{name:/compare all three audit methods/i})).not.toBeChecked();
  expect(screen.getByRole('checkbox',{name:/Rule-Based Baseline/})).toBeChecked();
  await user.click(screen.getByRole('button',{name:'Start Memory Audit'}));
  await screen.findByRole('heading',{name:'Prepare Memory Audit'});
  expect(screen.queryByText(/Saved review and audit settings restored/)).toBeNull();
  expect(apiMocks.createAudit.mock.calls[0][0].test_budget).toBe(3);
  expect(apiMocks.createAudit.mock.calls[0][0].target_memory_profile.output_token_limit).toBe(256);
  expect(apiMocks.createConversation).toHaveBeenCalledTimes(1);
  expect(apiMocks.extract).toHaveBeenCalledTimes(1);
  expect(apiMocks.execute).not.toHaveBeenCalled();
});

test('an explicitly blank restored shared Agent model must not silently select a default model', async () => {
  const user=userEvent.setup();
  apiMocks.targetProviders.mockResolvedValue([
    {provider:'rule_based',label:'Rule-Based Baseline',configured:true,default_model:'rule-based-v1'},
    {provider:'openrouter',label:'OpenRouter',configured:true,default_model:'test/independent-judge'}]);
  sessionStorage.setItem('mha-new-audit-review-v1', JSON.stringify({conversationId:'C001', settings:{
    selectedStrategies:['scope_aware'],targetProviders:['rule_based'],targetModels:{rule_based:'rule-based-v1'},
    pipelineProvider:'openrouter',evaluatorProvider:'openrouter',pipelineModel:'',evaluatorModel:'test/independent-judge',
    budget:4,repetitions:1,suiteMode:'behavioural',maintenancePolicy:'update_aware_consolidation',targetMemoryCapacity:50,
    targetMemoryWriter:'rule_based',targetProfile:{...defaultTargetProfile,label:'Review check'},targetSystem:'controlled-memory',compareAuditors:false
  }}));
  render(<NewAudit/>);
  await user.click(screen.getByRole('button',{name:'Resume saved review'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  await user.click(screen.getByRole('button',{name:'Confirm Ground Truth & Continue'}));
  await screen.findByRole('heading',{name:'Configure Memory Audit'});
  expect(screen.getByRole('alert')).toHaveTextContent('Choose the shared Agent model');
  expect(screen.getByRole('button',{name:'Start Memory Audit'})).toBeDisabled();
  expect(apiMocks.createExperiment).not.toHaveBeenCalled();
  expect(apiMocks.createAudit).not.toHaveBeenCalled();
});

test('three-method comparison uses the configured shared model for the AI review', async () => {
  const user=userEvent.setup();
  apiMocks.targetProviders.mockResolvedValue([
    {provider:'rule_based',label:'Rule-Based Baseline',configured:true,default_model:'rules'},
    {provider:'openrouter',label:'OpenRouter',configured:true,default_model:'test/independent-judge'}]);
  sessionStorage.setItem('mha-new-audit-review-v1',JSON.stringify({conversationId:'C001',settings:{
    selectedStrategies:['scope_aware'],targetProviders:['rule_based'],targetModels:{rule_based:'rules'},
    pipelineProvider:'openrouter',evaluatorProvider:'rule_based',pipelineModel:null,evaluatorModel:null,
    budget:4,repetitions:1,suiteMode:'behavioural',maintenancePolicy:'update_aware_consolidation',targetMemoryCapacity:50,
    targetMemoryWriter:'rule_based',targetProfile:defaultTargetProfile,targetSystem:'controlled-memory',compareAuditors:true
  }}));
  const view=render(<NewAudit/>);
  await user.click(screen.getByRole('button',{name:'Resume saved review'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  await user.click(screen.getByRole('button',{name:'Confirm Ground Truth & Continue'}));
  await screen.findByRole('heading',{name:'Configure Memory Audit'});
  expect(screen.getByText(/OpenRouter · test\/independent-judge/)).toBeTruthy();
  await waitFor(()=>expect(JSON.parse(sessionStorage.getItem('mha-new-audit-review-v1')!).settings.pipelineModel).toBe('test/independent-judge'));
  view.unmount();render(<NewAudit/>);
  await user.click(screen.getByRole('button',{name:'Resume saved review'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  await user.click(screen.getByRole('button',{name:'Confirm Ground Truth & Continue'}));
  await user.click(await screen.findByRole('button',{name:'Start 3-Run Comparison'}));
  await screen.findByRole('heading',{name:'Prepare Memory Audit'});
  const hybrid=apiMocks.createAudit.mock.calls.map(call=>call[0]).find(body=>body.evaluator_provider==='openrouter');
  expect(hybrid.evaluator_model).toBe('test/independent-judge');
  expect(apiMocks.execute).not.toHaveBeenCalled();
});

test('lost conversation response survives refresh and replays the original submission identity and source', async () => {
  const user=userEvent.setup();const first=render(<NewAudit/>);
  apiMocks.createConversation.mockRejectedValueOnce(new Error('Connection interrupted'));
  await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
  await user.click(screen.getByRole('button',{name:'Continue to Ground Truth'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Connection interrupted');
  const original=apiMocks.createConversation.mock.calls[0];
  expect(original[3]).toMatch(/^[a-f0-9-]{36}$/);
  first.unmount();render(<NewAudit/>);
  expect(screen.getByRole('region',{name:'Unfinished conversation submission'})).toBeTruthy();
  await user.click(screen.getByRole('button',{name:'Continue saved submission'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  expect(apiMocks.createConversation.mock.calls[1]).toEqual(original);
  expect(apiMocks.extract).toHaveBeenCalledTimes(1);
  expect(apiMocks.execute).not.toHaveBeenCalled();
});

test('interrupted extraction recovers a committed empty result without extracting or creating again', async () => {
  const user=userEvent.setup();const first=render(<NewAudit/>);
  apiMocks.extract.mockRejectedValueOnce(new Error('Connection interrupted'));
  await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
  await user.click(screen.getByRole('button',{name:'Continue to Ground Truth'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Connection interrupted');
  first.unmount();
  apiMocks.getConversation.mockResolvedValue({conversation_id:'C001',messages:[],extraction_provenance:{provider:'rule_based',candidate_count:0}});
  apiMocks.conversationMemories.mockResolvedValue([]);
  render(<NewAudit/>);
  await user.click(screen.getByRole('button',{name:'Continue saved submission'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  expect(screen.getByText('No candidate memories were found. Add a memory to continue.')).toBeTruthy();
  expect(apiMocks.createConversation).toHaveBeenCalledTimes(1);
  expect(apiMocks.extract).toHaveBeenCalledTimes(1);
  expect(apiMocks.execute).not.toHaveBeenCalled();
});

test('unfinished extraction retries the frozen extractor rather than new cloud defaults', async () => {
  const user=userEvent.setup();const first=render(<NewAudit/>);
  apiMocks.extract.mockRejectedValueOnce(new Error('Memory extraction is still running.'));
  await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
  await user.click(screen.getByRole('button',{name:'Continue to Ground Truth'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Memory extraction is still running');
  first.unmount();
  apiMocks.targetProviders.mockResolvedValue([
    {provider:'rule_based',configured:true,default_model:'rules',label:'Rule-Based Baseline'},
    {provider:'openrouter',configured:true,default_model:'changed/cloud-default',label:'OpenRouter'}]);
  render(<NewAudit/>);
  await user.click(screen.getByRole('button',{name:'Continue saved submission'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  expect(apiMocks.extract.mock.calls).toEqual([['C001','rule_based',undefined],['C001','rule_based',undefined]]);
  expect(apiMocks.createConversation).toHaveBeenCalledTimes(1);
});

test('service loading keeps the source editable but blocks submission until services are known',async()=>{
  let finish!: (items:unknown[])=>void;
  apiMocks.targetProviders.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  const user=userEvent.setup();render(<NewAudit/>);
  expect(screen.getByRole('status',{name:'Model service availability'})).toHaveTextContent('Loading available model services');
  expect(screen.queryByRole('combobox',{name:'Shared Agent service'})).toBeNull();
  await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
  expect(screen.getByRole('button',{name:'Continue to Ground Truth'})).toBeDisabled();
  expect(apiMocks.createConversation).not.toHaveBeenCalled();
  finish([{provider:'rule_based',label:'Rule-Based Baseline',configured:true,default_model:'rule-based-v1',description:'Local processing'}]);
  await waitFor(()=>expect(screen.getByRole('button',{name:'Continue to Ground Truth'})).toBeEnabled());
  expect(selectedUILabel('Shared Agent service')).toBe('Rule-Based Baseline');
});

test.each(['failed','empty'])('service %s result offers a safe retry without submitting source or showing internal service names',async(mode)=>{
  if(mode==='failed')apiMocks.targetProviders.mockRejectedValueOnce(new Error('PRIVATE diagnostic'));
  else apiMocks.targetProviders.mockResolvedValueOnce([]);
  const user=userEvent.setup();render(<NewAudit/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('We could not load the available model services');
  expect(screen.queryByText('PRIVATE diagnostic')).toBeNull();
  expect(screen.queryByRole('combobox',{name:'Shared Agent service'})).toBeNull();
  await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
  expect(screen.getByRole('button',{name:'Continue to Ground Truth'})).toBeDisabled();
  await user.click(screen.getByRole('button',{name:'Retry loading services'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Continue to Ground Truth'})).toBeEnabled());
  expect(apiMocks.targetProviders).toHaveBeenCalledTimes(2);
  expect(apiMocks.createConversation).not.toHaveBeenCalled();
  expect(apiMocks.extract).not.toHaveBeenCalled();
  expect(screen.getByRole('checkbox',{name:/authorised to use this conversation/i})).toBeChecked();
});

test('retrying failed services preserves restored audit choices instead of applying cloud defaults',async()=>{
  sessionStorage.setItem('mha-new-audit-review-v1',JSON.stringify({conversationId:'C001',settings:{selectedStrategies:['scope_aware'],targetProviders:['ollama'],targetModels:{ollama:'qwen3:1.7b'},pipelineProvider:'rule_based',evaluatorProvider:'rule_based',pipelineModel:null,evaluatorModel:null,budget:3,repetitions:1,suiteMode:'behavioural',maintenancePolicy:'update_aware_consolidation',targetMemoryCapacity:50,targetMemoryWriter:'rule_based',targetProfile:{...defaultTargetProfile,label:'Preserved settings',output_token_limit:256},targetSystem:'controlled-memory',compareAuditors:false}}));
  apiMocks.targetProviders.mockRejectedValueOnce(new Error('Connection interrupted')).mockResolvedValue([
    {provider:'rule_based',label:'Rule-Based Baseline',configured:true,default_model:'rule-based-v1'},
    {provider:'openrouter',label:'OpenRouter',configured:true,default_model:'test/independent-judge'},
    {provider:'ollama',label:'Local models (Ollama)',configured:true,default_model:'qwen3:1.7b'},
  ]);
  const user=userEvent.setup();render(<NewAudit/>);
  await screen.findByRole('alert');
  await user.click(screen.getByRole('button',{name:'Resume saved review'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  await user.click(screen.getByRole('button',{name:'Confirm Ground Truth & Continue'}));
  expect(screen.queryByRole('button',{name:'Start Memory Audit'})).toBeNull();
  await user.click(screen.getByRole('button',{name:'Retry loading services'}));
  await screen.findByRole('button',{name:'Start Memory Audit'});
  expect(screen.getByRole('checkbox',{name:/Compare all three audit methods/})).not.toBeChecked();
  expect(screen.getByRole('checkbox',{name:/Local models \(Ollama\)/})).toBeChecked();
  expect(screen.getByRole('checkbox',{name:/Match the task and project/})).toBeChecked();
  expect(screen.getByRole('spinbutton',{name:'Answer length limit'})).toHaveValue('256');
  expect(apiMocks.createAudit).not.toHaveBeenCalled();
});


test('starts a separate audit from prepared questions without executing or cancelling saved records',async()=>{
 const user=userEvent.setup();render(<NewAudit/>);
 await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
 await user.click(screen.getByRole('button',{name:'Continue to Ground Truth'}));
 await user.click(await screen.findByRole('button',{name:'Accept'}));
 await user.click(screen.getByRole('button',{name:'Confirm Ground Truth & Continue'}));
 await screen.findByRole('heading',{name:'Configure Memory Audit'});
 await user.click(screen.getByRole('button',{name:'Start Memory Audit'}));
 await screen.findByRole('heading',{name:'Prepare Memory Audit'});
 let finish!:(value:typeof pendingTest[])=>void;
 apiMocks.generate.mockReturnValueOnce(new Promise(resolve=>finish=resolve));
 await user.click(screen.getByRole('button',{name:'Generate Tests for Review'}));
 expect(screen.getByRole('button',{name:'Start a separate audit'})).toBeDisabled();
 finish([pendingTest]);
 await screen.findByRole('heading',{name:'Review Generated Test Suite'});
 await user.click(screen.getByRole('button',{name:'Start a separate audit'}));
 expect(await screen.findByLabelText('Authorised conversation text')).toHaveValue('');
 expect(screen.getByRole('checkbox',{name:/authorised to use this conversation/i})).not.toBeChecked();
 expect(screen.queryByRole('heading',{name:'Review Generated Test Suite'})).toBeNull();
 expect(apiMocks.execute).not.toHaveBeenCalled();expect(apiMocks.cancel).not.toHaveBeenCalled();
 expect(apiMocks.createAudit).toHaveBeenCalledTimes(1);
});

test('a separate audit resets a structured writer when restoring default three-method comparison',async()=>{
 apiMocks.targetProviders.mockResolvedValue([{provider:'openrouter',label:'OpenRouter',configured:true,
  default_model:'test/target',default_pipeline_model:'test/pipeline',default_evaluator_model:'test/judge'}]);
 const user=userEvent.setup();render(<NewAudit/>);
 await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
 await user.click(screen.getByRole('button',{name:'Continue to Ground Truth'}));
 await user.click(await screen.findByRole('button',{name:'Accept'}));
 await user.click(screen.getByRole('button',{name:'Confirm Ground Truth & Continue'}));
 const comparison=await screen.findByRole('checkbox',{name:'Compare all three audit methods (recommended)'}) as HTMLInputElement;
 expect(comparison).toBeChecked();
 if(comparison.checked) await user.click(comparison);
 expect(comparison).not.toBeChecked();
 expect(screen.getByRole('combobox',{name:'Target memory writer'})).toBeEnabled();
 await user.click(screen.getByRole('combobox',{name:'Target memory writer'}));
 const structuredWriter=await screen.findByRole('option',{name:'Structured LLM writer'});
 expect(structuredWriter).toBeEnabled();
 await user.click(structuredWriter);
 await waitFor(()=>expect(selectedUILabel('Target memory writer')).toContain('Structured LLM writer'));
 await user.click(screen.getByRole('button',{name:'Start Memory Audit'}));
 await screen.findByRole('heading',{name:'Prepare Memory Audit'});
 expect(apiMocks.createAudit.mock.calls[0][0].target_memory_writer).toBe('llm_structured');
 await user.click(screen.getByRole('button',{name:'Start a separate audit'}));
 await user.type(screen.getByRole('textbox',{name:'Authorised conversation text'}),'[User] The backend now uses PostgreSQL.');
 await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
 await user.click(screen.getByRole('button',{name:'Continue to Ground Truth'}));
 await user.click(await screen.findByRole('button',{name:'Accept'}));
 await user.click(screen.getByRole('button',{name:'Confirm Ground Truth & Continue'}));
 expect(await screen.findByRole('checkbox',{name:'Compare all three audit methods (recommended)'})).toBeChecked();
 expect(selectedUILabel('Target memory writer')).toContain('Rule-based writer');
 expect(apiMocks.execute).not.toHaveBeenCalled();
});


test('opening an unfinished submission never calls extraction and starting new removes the old failure',async()=>{
 const user=userEvent.setup();const first=render(<NewAudit/>);
 apiMocks.extract.mockRejectedValueOnce(new Error('The configured pipeline model returned an invalid memory relationship reference.'));
 await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
 await user.click(screen.getByRole('button',{name:'Continue to Ground Truth'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('This saved submission did not finish');
 expect(screen.getByRole('alert')).toHaveTextContent('missing record or to itself');
 first.unmount();render(<NewAudit/>);
 expect(screen.getByRole('heading',{name:'Previous unfinished submission'})).toBeInTheDocument();
 expect(screen.queryByRole('alert')).toBeNull();
 expect(apiMocks.extract).toHaveBeenCalledTimes(1);
 expect(apiMocks.createConversation).toHaveBeenCalledTimes(1);
 await user.click(screen.getByRole('button',{name:'Start a new conversation'}));
 expect(await screen.findByRole('textbox',{name:'Authorised conversation text'})).toBeInTheDocument();
 expect(screen.queryByRole('heading',{name:'Previous unfinished submission'})).toBeNull();
 expect(screen.queryByRole('alert')).toBeNull();
 expect(apiMocks.extract).toHaveBeenCalledTimes(1);
 expect(apiMocks.execute).not.toHaveBeenCalled();
});

test.each(['openrouter','ollama'])('unfinished %s submission can explicitly switch to Luna while preserving its saved source and identity',async(provider)=>{
 const user=userEvent.setup();
 const checkpoint={requestKey:'1234567890123456',conversationId:'C001',text:'Preserved source',messages:null,sourceOrigin:'synthetic',provider,model:'old/model'};
 sessionStorage.setItem('mha-new-audit-intake-v1',JSON.stringify(checkpoint));
 apiMocks.targetProviders.mockResolvedValue([{provider:'openrouter',configured:true,default_model:'openai/gpt-6-luna',label:'OpenRouter'}]);
 apiMocks.getConversation.mockResolvedValue({conversation_id:'C001',messages:[],extraction_provenance:{status:'failed'}});
 render(<NewAudit/>);
 await user.click(await screen.findByRole('button',{name:'Use GPT 6 Luna for the next extraction'}));
 expect(apiMocks.extract).not.toHaveBeenCalled();
 expect(JSON.parse(sessionStorage.getItem('mha-new-audit-intake-v1')!)).toEqual({...checkpoint,provider:'openrouter',model:'openai/gpt-6-luna'});
 await user.click(screen.getByRole('button',{name:'Continue saved submission'}));
 await screen.findByRole('heading',{name:'Review Extracted Memories'});
 expect(apiMocks.extract).toHaveBeenCalledWith('C001','openrouter','openai/gpt-6-luna');
 expect(apiMocks.createConversation).not.toHaveBeenCalled();
 expect(apiMocks.execute).not.toHaveBeenCalled();
});

test.each(['low','medium'] as const)('preserves optional %s target settings in restored profile clones and surfaces backend unsupported-model rejection',async effort=>{
  sessionStorage.setItem('mha-new-audit-review-v1',JSON.stringify({conversationId:'C001',settings:{
    selectedStrategies:['weak_first_hit'],targetProviders:['rule_based'],targetModels:{rule_based:'rule-based-v1'},
    pipelineProvider:'rule_based',evaluatorProvider:'rule_based',pipelineModel:'rules',evaluatorModel:'rules',budget:4,repetitions:1,
    suiteMode:'behavioural',maintenancePolicy:'update_aware_consolidation',targetMemoryCapacity:50,targetMemoryWriter:'rule_based',
    targetProfile:{...defaultTargetProfile,reasoning_effort:effort,identity_analysis_reasoning_effort:'low'},targetSystem:'controlled-memory',compareAuditors:false}}));
  apiMocks.createAudit.mockRejectedValue(new Error('Requested reasoning is supported only for OpenRouter Luna.'));
  const user=userEvent.setup();render(<NewAudit/>);
  await user.click(screen.getByRole('button',{name:'Resume saved review'}));await screen.findByRole('heading',{name:'Review Extracted Memories'});
  await user.click(screen.getByRole('button',{name:'Confirm Ground Truth & Continue'}));await screen.findByRole('heading',{name:'Configure Memory Audit'});
  await user.click(screen.getByRole('button',{name:'Start Memory Audit'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Requested reasoning is supported only for OpenRouter Luna.');
  expect(apiMocks.createAudit.mock.calls[0][0].target_memory_profile).toMatchObject({reasoning_effort:effort,identity_analysis_reasoning_effort:'low',output_token_limit:2048});
  expect(apiMocks.execute).not.toHaveBeenCalled();
});

test('loads the substantial synthetic presentation JSON without authorising or calling a model', async()=>{
  render(<NewAudit/>);
  const preview=presentationDemo.messages.map(message=>`[${message.role}] ${message.content}`).join('\n');
  expect(presentationDemo.messages).toHaveLength(28);
  expect(preview.length).toBeGreaterThan(4500);
  expect(screen.getByLabelText('Authorised conversation text')).toHaveValue(preview);
  expect(screen.getByRole('checkbox',{name:/authorised to use this conversation/i})).not.toBeChecked();
  expect(screen.getByRole('button',{name:'Continue to Ground Truth'})).toBeDisabled();
  expect(screen.getByRole('link',{name:'Download example JSON'})).toHaveAttribute('download','presentation-conversation.json');
  expect(apiMocks.createConversation).not.toHaveBeenCalled();
  expect(apiMocks.extract).not.toHaveBeenCalled();
});

test('submits exact presentation message IDs, speakers and timestamps after explicit consent',async()=>{
  const user=userEvent.setup();render(<NewAudit/>);
  await waitFor(()=>expect(selectedUILabel('Shared Agent service')).toContain('Rule-Based Baseline'));
  await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
  await user.click(screen.getByRole('button',{name:'Continue to Ground Truth'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  expect(apiMocks.createConversation).toHaveBeenCalledWith(true,expect.any(String),presentationDemo.messages,expect.any(String),'synthetic');
});

test('preserves a saved personal draft until the presentation example is explicitly loaded',async()=>{
  sessionStorage.setItem('mha-new-audit-draft-v1',JSON.stringify({text:'[User] My existing draft.',consent:false,sourceOrigin:'unknown'}));
  const user=userEvent.setup();render(<NewAudit/>);
  expect(screen.getByLabelText('Authorised conversation text')).toHaveValue('[User] My existing draft.');
  await user.click(screen.getByRole('button',{name:'Load presentation example'}));
  expect(screen.getByLabelText('Authorised conversation text')).toHaveValue(presentationDemo.messages.map(message=>`[${message.role}] ${message.content}`).join('\n'));
  expect(apiMocks.extract).not.toHaveBeenCalled();
});

test('presentation preset selects two memory strategies and three repeats without starting execution',async()=>{
  apiMocks.targetProviders.mockResolvedValue([
    {provider:'rule_based',label:'Rule-Based Baseline',default_model:'rule-based-v1',configured:true,description:'Offline.'},
    {provider:'openrouter',label:'OpenRouter',default_model:'openai/gpt-6-luna',default_pipeline_model:'openai/gpt-6-luna',default_evaluator_model:'openai/gpt-6-luna',configured:true,description:'Cloud.'},
  ]);
  const user=userEvent.setup();render(<NewAudit/>);
  await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
  await user.click(screen.getByRole('button',{name:'Continue to Ground Truth'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  await user.click(screen.getByRole('button',{name:'Accept'}));
  await user.click(screen.getByRole('button',{name:'Confirm Ground Truth & Continue'}));
  await user.click(await screen.findByRole('button',{name:'Use presentation settings · 3 repeats per retrieval strategy'}));
  expect(screen.getByRole('checkbox',{name:/compare all three audit methods/i})).not.toBeChecked();
  expect(screen.getByLabelText(/Requested test count/)).toHaveValue('8');
  expect(screen.getByLabelText(/Repeated runs per condition/)).toHaveValue('3');
  expect(screen.getByRole('button',{name:'Start 6-Run Comparison'})).toBeInTheDocument();
  expect(screen.getByLabelText('Configuration name')).toHaveValue('Harbour presentation demo');
  expect(apiMocks.createAudit).not.toHaveBeenCalled();
  expect(apiMocks.execute).not.toHaveBeenCalled();
});


test('downloads the exact default JSON bytes through the shared download helper',async()=>{
  const user=userEvent.setup();render(<NewAudit/>);
  await user.click(screen.getByRole('link',{name:'Download example JSON'}));
  expect(saveBlob).toHaveBeenCalledTimes(1);
  const [blob,name]=vi.mocked(saveBlob).mock.calls[0];
  expect(name).toBe('presentation-conversation.json');
  const contents=await new Promise<string>((resolve,reject)=>{
    const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(reader.error);reader.readAsText(blob);
  });
  expect(contents).toBe(presentationDemoRaw);
  expect(JSON.parse(contents).messages).toEqual(presentationDemo.messages);
  expect(apiMocks.createConversation).not.toHaveBeenCalled();
});

test('partial coverage survives browser review restoration and formal comparison temporarily applies strict',async()=>{
  apiMocks.targetProviders.mockResolvedValue([{provider:'openrouter',label:'OpenRouter',configured:true,default_model:'test/target',default_pipeline_model:'test/pipeline',default_evaluator_model:'test/judge'}]);
  apiMocks.coveragePreview.mockImplementation(async (_id:string,budget:number,policy:string)=>({
    requested_test_count:budget,planned_test_count:policy==='evidence_supported_only_v1'?1:budget,minimum_met:true,
    dimensions:['accuracy','freshness','conflict_resolution','appropriate_use'].map((dimension,index)=>({dimension,evidence_supported:index===0?true:null,reason:'fixture',planned_question_count:index===0?1:0,required_question_count:index===0?1:0,available_question_count:index===0?1:0,accepted_question_count:0}))
  }));
  const user=userEvent.setup();const first=render(<NewAudit/>);
  await reachCreationConfiguration(user);
  const compare=screen.getByRole('checkbox',{name:/compare all three audit methods/i});
  if((compare as HTMLInputElement).checked)await user.click(compare);
  await selectUIOption(user,'Coverage policy','Only locally identified evidence slots');
  await waitFor(()=>expect(selectedUILabel('Coverage policy')).toContain('Only locally identified evidence slots'));
  await waitFor(()=>expect(screen.getByText(/Partial coverage: 1 planned/)).toBeInTheDocument());
  expect(screen.getByText(/This is a maximum/)).toBeInTheDocument();
  expect(screen.queryByText(/The Agent needs at least one distinct, evidence-backed question for each ability/)).toBeNull();
  first.unmount();render(<NewAudit/>);
  await user.click(screen.getByRole('button',{name:'Resume saved review'}));
  await screen.findByRole('heading',{name:'Review Extracted Memories'});
  await user.click(screen.getByRole('button',{name:'Confirm Ground Truth & Continue'}));
  await screen.findByRole('heading',{name:'Configure Memory Audit'});
  expect(selectedUILabel('Coverage policy')).toContain('Only locally identified evidence slots');
  await user.click(screen.getByRole('checkbox',{name:/compare all three audit methods/i}));
  expect(screen.queryByRole('combobox',{name:'Coverage policy'})).toBeNull();
  expect(screen.getByText(/Strict coverage applies to this setup/)).toBeInTheDocument();
  await user.click(screen.getByRole('checkbox',{name:/compare all three audit methods/i}));
  expect(selectedUILabel('Coverage policy')).toContain('Only locally identified evidence slots');
  expect(apiMocks.execute).not.toHaveBeenCalled();
});

test('partial creation retry preserves the exact frozen request and selection',async()=>{
  apiMocks.targetProviders.mockResolvedValue([{provider:'openrouter',label:'OpenRouter',configured:true,default_model:'test/target',default_pipeline_model:'test/pipeline',default_evaluator_model:'test/judge'}]);
  apiMocks.createExperiment.mockRejectedValueOnce(new Error('response lost'));
  const user=userEvent.setup();render(<NewAudit/>);await reachCreationConfiguration(user);
  const compare=screen.getByRole('checkbox',{name:/compare all three audit methods/i});
  if((compare as HTMLInputElement).checked)await user.click(compare);
  await selectUIOption(user,'Coverage policy','Only locally identified evidence slots');
  await waitFor(()=>expect(selectedUILabel('Coverage policy')).toContain('Only locally identified evidence slots'));
  await user.click(screen.getByRole('button',{name:'Start Memory Audit'}));
  await screen.findByRole('heading',{name:'Continue Preparing Your Audit'});
  const frozen=apiMocks.createExperiment.mock.calls[0][0];
  expect(frozen.test_suite_configuration.coverage_policy).toBe('evidence_supported_only_v1');
  await user.click(screen.getByRole('button',{name:'Resume Audit Preparation'}));
  await screen.findByRole('heading',{name:'Prepare Memory Audit'});
  expect(apiMocks.createExperiment.mock.calls[1][0]).toEqual(frozen);
  expect(apiMocks.execute).not.toHaveBeenCalled();
});

test('review renders frozen server coverage policy instead of the mutable form selection',async()=>{
  apiMocks.testReview.mockResolvedValue({run_id:'RUN001',canonical_run_id:'RUN001',coverage_policy:'evidence_supported_only_v1',planned_test_count:1,tests:[pendingTest],dimension_coverage:['accuracy','freshness','conflict_resolution','appropriate_use'].map((dimension,index)=>({dimension,evidence_supported:index===0?true:null,reason:'unknown',required_question_count:index===0?1:0,planned_question_count:index===0?1:0,available_question_count:index===0?1:0,accepted_question_count:0}))});
  const user=userEvent.setup();render(<NewAudit/>);await reachCreationConfiguration(user);
  await user.click(screen.getByRole('button',{name:'Start Memory Audit'}));
  await screen.findByRole('heading',{name:'Prepare Memory Audit'});
  await user.click(screen.getByRole('button',{name:'Generate Tests for Review'}));
  expect(await screen.findByText(/This does not prove that source evidence is absent/)).toBeInTheDocument();
  expect(apiMocks.testReview).toHaveBeenCalledWith('RUN001');
});

test('starting a separate audit resets an earlier partial opt-in to strict',async()=>{
  apiMocks.targetProviders.mockResolvedValue([{provider:'openrouter',label:'OpenRouter',configured:true,default_model:'test/target',default_pipeline_model:'test/pipeline',default_evaluator_model:'test/judge'}]);
  const user=userEvent.setup();render(<NewAudit/>);await reachCreationConfiguration(user);
  const compare=screen.getByRole('checkbox',{name:/compare all three audit methods/i});
  if((compare as HTMLInputElement).checked)await user.click(compare);
  await selectUIOption(user,'Coverage policy','Only locally identified evidence slots');
  await waitFor(()=>expect(selectedUILabel('Coverage policy')).toContain('Only locally identified evidence slots'));
  await user.click(screen.getByRole('button',{name:'Start Memory Audit'}));
  await screen.findByRole('heading',{name:'Prepare Memory Audit'});
  await user.click(screen.getByRole('button',{name:'Start a separate audit'}));
  await user.type(screen.getByRole('textbox',{name:'Authorised conversation text'}),'[User] I prefer Python.');
  await user.click(screen.getByRole('checkbox',{name:/authorised to use this conversation/i}));
  await user.click(screen.getByRole('button',{name:'Continue to Ground Truth'}));
  await user.click(await screen.findByRole('button',{name:'Accept'}));
  await user.click(screen.getByRole('button',{name:'Confirm Ground Truth & Continue'}));
  const freshCompare=await screen.findByRole('checkbox',{name:/compare all three audit methods/i});
  if((freshCompare as HTMLInputElement).checked)await user.click(freshCompare);
  expect(selectedUILabel('Coverage policy')).toContain('All four abilities required');
  expect(apiMocks.execute).not.toHaveBeenCalled();
});
