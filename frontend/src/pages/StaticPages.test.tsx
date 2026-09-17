import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Experiments, History } from './StaticPages';

const apiMocks = vi.hoisted(() => ({
  audits: vi.fn(), results: vi.fn(), retryPlan: vi.fn(), retry: vi.fn(),
  downloadConversationExport: vi.fn(), deleteConversation: vi.fn(),
  experimentGroups: vi.fn(), experimentResults: vi.fn(), cancelExperiment: vi.fn(),
  downloadExperimentCsv: vi.fn(), downloadExperimentBundle: vi.fn(), downloadExperimentArtifact: vi.fn(),
}));

vi.mock('../services/api', () => ({ api: apiMocks }));

const baseRun = {
  conversation_id: 'C001', target_configuration: 'strong' as const, temperature: 0,
  random_seed: 42, test_budget: 12, prompt_template_version: 'research-v1',
  pipeline_provider: 'rule_based', pipeline_model: 'rule-based-v1', evaluator_provider: 'rule_based',
  evaluator_model: 'rule-based-v1', memory_maintenance_policy: 'update_aware_consolidation' as const,
  target_memory_writer: 'rule_based' as const, created_at: '2026-01-01T00:00:00Z',
};

beforeEach(() => {
  apiMocks.audits.mockResolvedValue([
    { ...baseRun, run_id: 'RUN-COMPLETE', status: 'COMPLETED', provider: 'rule_based', model: 'baseline-v1', memory_strategy: 'scope_aware', completed_at: '2026-01-01T00:01:00Z' },
    { ...baseRun, run_id: 'RUN-FAILED', status: 'FAILED', provider: 'deepseek', model: 'deepseek-chat', memory_strategy: 'weak_first_hit' },
  ]);
  apiMocks.retryPlan.mockResolvedValue({ run_id: 'RUN-FAILED', next_stage: 'execute_tests', pending: 3, retryable: true });
  apiMocks.retry.mockResolvedValue({ ...baseRun, run_id: 'RUN-FAILED', status: 'COMPLETED', provider: 'deepseek', model: 'deepseek-chat', memory_strategy: 'weak_first_hit' });
});

test('filters history by text and strategy, while retaining frozen settings', async () => {
  const user = userEvent.setup();
  render(<History />);
  await waitFor(() => expect(screen.getByText('RUN-COMPLETE')).not.toBeNull());
  expect(screen.getByRole('link', { name: 'View report' }).getAttribute('href')).toBe('/audits/RUN-COMPLETE');

  await user.type(screen.getByLabelText('Search audit history'), 'deepseek');
  expect(screen.getByText('RUN-FAILED')).not.toBeNull();
  expect(screen.queryByText('RUN-COMPLETE')).toBeNull();

  await user.clear(screen.getByLabelText('Search audit history'));
  await user.selectOptions(screen.getByLabelText('Filter by memory strategy'), 'scope_aware');
  expect(screen.getByText('RUN-COMPLETE')).not.toBeNull();
  expect(screen.queryByText('RUN-FAILED')).toBeNull();
  await user.click(screen.getByText(/Strong Memory · scope aware/i));
  expect(screen.getByText('Pipeline: rule_based / rule-based-v1')).not.toBeNull();
});

test('shows a recovery plan and can resume an interrupted audit', async () => {
  const user = userEvent.setup();
  render(<History />);
  await waitFor(() => expect(screen.getByText('RUN-FAILED')).not.toBeNull());
  await user.click(screen.getByRole('button', { name: 'View recovery plan' }));
  await waitFor(() => expect(apiMocks.retryPlan).toHaveBeenCalledWith('RUN-FAILED'));
  expect(screen.getByText(/3 items pending; recovery will execute unanswered tests/i)).not.toBeNull();
  await user.click(screen.getByRole('button', { name: 'Resume audit' }));
  await waitFor(() => expect(apiMocks.retry).toHaveBeenCalledWith('RUN-FAILED'));
  expect(screen.getByText('Recovery completed. The report is now available.')).not.toBeNull();
});

test('can cancel an unfinished persisted experiment and reports export errors', async () => {
  const user = userEvent.setup();
  const experiment = {
    experiment_id: 'EXP001', conversation_id: 'C001', label: 'Persisted comparison', status: 'RUNNING',
    test_suite_configuration: {
      test_budget: 4, random_seed: 42, prompt_template_version: 'rule-based-v1',
      pipeline_provider: 'rule_based', pipeline_model: 'rule-based-v2',
      evaluator_provider: 'rule_based', evaluator_model: 'rule-based-v2', dimensions: ['accuracy'], suite_mode: 'behavioural',
    },
    test_suite_metadata: { test_count: 4, dimensions: ['accuracy'] }, created_at: '2026-01-01T00:00:00Z',
  };
  const report = { experiment, runs: [], conditions: [], paired_comparisons: [] };
  apiMocks.experimentGroups.mockResolvedValue([experiment]);
  apiMocks.experimentResults.mockResolvedValue(report);
  apiMocks.cancelExperiment.mockResolvedValue({ ...experiment, status: 'CANCELLED' });
  apiMocks.downloadExperimentCsv.mockRejectedValue(new Error('CSV export unavailable'));
  vi.spyOn(window, 'confirm').mockReturnValue(true);

  render(<Experiments />);
  await screen.findByRole('button', { name: 'Cancel unfinished conditions' });
  await user.click(screen.getByRole('button', { name: 'Cancel unfinished conditions' }));
  await waitFor(() => expect(apiMocks.cancelExperiment).toHaveBeenCalledWith('EXP001'));
  expect(screen.getByText('The unfinished conditions were cancelled. Completed results remain available.')).not.toBeNull();

  await user.click(screen.getByRole('button', { name: 'Download group CSV' }));
  await waitFor(() => expect(screen.getByText('CSV export unavailable')).not.toBeNull());
});
