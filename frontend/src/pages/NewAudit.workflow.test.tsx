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
  apiMocks.results.mockResolvedValue(result);
  apiMocks.targetMemoryTrace.mockResolvedValue({
    run_id: 'RUN001', memory_strategy: 'weak_first_hit',
    records: [{ memory_id: 'TM001', canonical_value: 'The backend now uses PostgreSQL.', lifecycle_state: 'ACTIVE', source_message_ids: ['MSG001'], write_order: 1, relationships: [] }],
    events: [{ event_id: 'EV001', event_type: 'WRITTEN', memory_id: 'TM001', source_message_ids: ['MSG001'], details: { writer_version: 'rule-based-v1' }, created_at: '2026-01-01T00:00:00Z' }],
    retrievals: [{ retrieval_id: 'RET001', test_id: 'T001', strategy: 'weak_first_hit', selected_memory_ids: ['TM001'], ranking_evidence: [{ memory_id: 'TM001', selected: true, reason: 'First related memory.' }], created_at: '2026-01-01T00:00:00Z' }],
  });
});

test('completes the local audit workflow from consent through reviewed results and target trace', async () => {
  const user = userEvent.setup();
  render(<NewAudit />);

  await user.click(screen.getByRole('checkbox', { name: /authorised to use this conversation/i }));
  await user.click(screen.getByRole('button', { name: 'Continue to Ground Truth' }));
  await screen.findByRole('heading', { name: 'Review Extracted Memories' });

  await user.click(screen.getByRole('button', { name: 'Accept' }));
  await waitFor(() => expect(apiMocks.updateMemory).toHaveBeenCalledWith('M001', { status: 'confirmed', canonical_value: undefined }));
  await user.click(screen.getByRole('button', { name: 'Confirm Ground Truth & Continue' }));
  await screen.findByRole('heading', { name: 'Configure Memory Audit' });

  await user.click(screen.getByRole('button', { name: 'Start Memory Audit' }));
  expect(apiMocks.createAudit).toHaveBeenCalledWith(expect.objectContaining({
    memory_strategy: 'weak_first_hit',
    memory_maintenance_policy: 'update_aware_consolidation',
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
  await screen.findByText('Stored Memory Lifecycle');
  expect(screen.getByText('The backend now uses PostgreSQL.')).toBeTruthy();
  expect(screen.getByText(/selected TM001/i)).toBeTruthy();
});
