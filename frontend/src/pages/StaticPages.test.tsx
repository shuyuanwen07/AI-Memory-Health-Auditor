import { UIProvider } from '../components/ui';
import { selectUIOption } from '../components/ui/testHelpers';
import { configure, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Experiments, History } from './StaticPages';

const apiMocks = vi.hoisted(() => ({
  audits: vi.fn(), results: vi.fn(), retryPlan: vi.fn(), retry: vi.fn(),
  testReview: vi.fn(), reviewTest: vi.fn(), regenerateTest: vi.fn(),
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
  vi.clearAllMocks();
  // Group headers load before page summaries; allow both UI update stages.
  configure({asyncUtilTimeout: 5000});
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
  await waitFor(() => expect(screen.getByRole('link', {name:'View report'})).not.toBeNull());
  expect(screen.getByRole('link', { name: 'View report' }).getAttribute('href')).toBe('/audits/RUN-COMPLETE');

  await user.type(screen.getByLabelText('Search audit history'), 'deepseek');
  expect(screen.getByRole('button', {name:'View recovery plan'})).not.toBeNull();
  expect(screen.queryByRole('link', {name:'View report'})).toBeNull();

  await user.clear(screen.getByLabelText('Search audit history'));
  await selectUIOption(user, 'Filter by memory strategy', 'scope aware');
  expect(screen.getByRole('link', {name:'View report'})).not.toBeNull();
  expect(screen.queryByRole('button', {name:'View recovery plan'})).toBeNull();
  await user.click(screen.getByText(/Memory settings · scope aware/i));
  expect(screen.getByText('Test preparation: Rule-based processing')).not.toBeNull();
});

test('shows a recovery plan and can resume an interrupted audit', async () => {
  const user = userEvent.setup();
  render(<History />);
  await waitFor(() => expect(screen.getByRole('button', {name:'View recovery plan'})).not.toBeNull());
  await user.click(screen.getByRole('button', { name: 'View recovery plan' }));
  await waitFor(() => expect(apiMocks.retryPlan).toHaveBeenCalledWith('RUN-FAILED'));
  expect(screen.getByText(/3 items pending; recovery will execute unanswered tests/i)).not.toBeNull();
  await user.click(screen.getByRole('button', { name: 'Resume audit' }));
  await waitFor(() => expect(apiMocks.retry).toHaveBeenCalledWith('RUN-FAILED'));
  expect(screen.getByText('Recovery completed. The report is now available.')).not.toBeNull();
});

test('does not label a no-memory reference as strong memory', async () => {
  apiMocks.audits.mockResolvedValue([{ ...baseRun, run_id: 'RUN-NONE', status: 'COMPLETED', provider: 'ollama', model: 'qwen3:1.7b', memory_strategy: 'no_memory' }]);
  render(<History />);
  await screen.findByText(/Memory settings · no memory/i);
  expect(screen.queryByText(/Strong Memory/i)).toBeNull();
});

test('loads reports for the visible page and retains usable groups when one report fails', async () => {
  const user = userEvent.setup();
  const groups = Array.from({length: 5}, (_, i) => ({
    experiment_id: `EXP-page-${i}`, conversation_id: 'C001', label: `Scenario ${i + 1}`,
    status: 'COMPLETED', test_suite_configuration: {},
    test_suite_metadata: {test_count: 4}, created_at: '2026-01-01T00:00:00Z',
  }));
  apiMocks.experimentGroups.mockResolvedValue(groups);
  apiMocks.experimentResults.mockImplementation(async (id: string) => {
    if (id === 'EXP-page-1') throw new Error('Single report unavailable');
    return {experiment: groups.find(g => g.experiment_id === id), runs: [], conditions: [], paired_comparisons: []};
  });
  render(<Experiments />);
  await screen.findByRole('button', {name: 'Retry result summary'});
  expect(screen.getByRole('heading', {name: 'Scenario 1'})).toBeTruthy();
  expect(screen.getByRole('heading', {name: 'Scenario 2'})).toBeTruthy();
  expect(screen.queryByText(/Experiment groups could not be loaded/)).toBeNull();
  expect(apiMocks.experimentResults).toHaveBeenCalledTimes(3);
  apiMocks.experimentResults.mockImplementation(async (id: string) => ({experiment: groups.find(g => g.experiment_id === id), runs: [], conditions: [], paired_comparisons: []}));
  await user.click(screen.getByRole('button', {name: 'Retry result summary'}));
  await waitFor(() => expect(screen.queryByRole('button', {name: 'Retry result summary'})).toBeNull());
  expect(apiMocks.experimentResults).toHaveBeenCalledTimes(4);
  await user.click(screen.getByRole('button', {name: 'Next experiments'}));
  await screen.findByRole('heading', {name: 'Scenario 4'});
  await waitFor(() => expect(apiMocks.experimentResults).toHaveBeenCalledTimes(6));
  await user.click(screen.getByRole('button', {name: 'Previous experiments'}));
  await screen.findByRole('heading', {name: 'Scenario 1'});
  expect(apiMocks.experimentResults).toHaveBeenCalledTimes(6);
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

  render(<UIProvider><Experiments /></UIProvider>);
  await screen.findByRole('button', { name: 'Cancel unfinished conditions' });
  await user.click(screen.getByRole('button', { name: 'Cancel unfinished conditions' }));
  const dialog = await screen.findByRole('dialog');
  expect(apiMocks.cancelExperiment).not.toHaveBeenCalled();
  await user.click(within(dialog).getByRole('button', { name: 'Keep running' }));
  expect(apiMocks.cancelExperiment).not.toHaveBeenCalled();
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  await user.click(screen.getByRole('button', { name: 'Cancel unfinished conditions' }));
  await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel unfinished conditions' }));
  await waitFor(() => expect(apiMocks.cancelExperiment).toHaveBeenCalledWith('EXP001'));
  expect(screen.getByText('The unfinished conditions were cancelled. Completed results remain available.')).not.toBeNull();

  await user.click(screen.getByText('Export results & experiment settings'));
  await user.click(screen.getByRole('button', { name: 'Results table (CSV)' }));
  await waitFor(() => expect(screen.getByText('CSV export unavailable')).not.toBeNull());
});

function comparisonFixture(shared = 4) {
  const experiment = {
    experiment_id: 'EXP-SUMMARY', conversation_id: 'C001',
    label: 'Memory strategy comparison 2026-10-08T09:49:20.264Z', status: 'COMPLETED',
    test_suite_configuration: { test_budget: 6, random_seed: 42 },
    test_suite_metadata: { test_count: 4 }, created_at: '2026-10-08T09:49:20.264Z',
  };
  const conditions = ['strong_score_based', 'temporal_importance'].map((strategy, index) => ({
    condition_id: strategy, label: strategy.replaceAll('_', ' '), model: 'qwen3:1.7b',
    memory_strategy: strategy, run_ids: [`RUN-${index}`], planned_runs: 1, completed_runs: 1,
    tests_passed: 1, tests_total: 4, overall_mean: 25, overall_standard_deviation: null,
    mean_latency_ms: null, total_tokens: null, failure_count: 3,
  }));
  const runs = conditions.map((condition, index) => ({
    run: { ...baseRun, run_id: `RUN-${index}`, status: 'COMPLETED', model: condition.model,
      provider: 'ollama', memory_strategy: condition.memory_strategy },
    result: { overall_score: 25, tests_passed: 1, tests_total: 4, failures: [], dimensions: [] },
  }));
  const paired_comparisons = [{
    reference_run_id: 'RUN-0', candidate_run_id: 'RUN-1',
    reference_label: 'Relevance scoring', candidate_label: 'Time and importance',
    shared_tests: shared, both_passed: 0, both_failed: 2,
    reference_only_passed: 1, candidate_only_passed: 1,
    candidate_delta_percentage_points: shared ? 0 : null,
    candidate_delta_confidence_interval_low: null, candidate_delta_confidence_interval_high: null,
    two_sided_sign_test_p_value: null,
  }];
  apiMocks.experimentGroups.mockResolvedValue([experiment]);
  apiMocks.experimentResults.mockResolvedValue({ experiment, runs, conditions, paired_comparisons });
}

test('explains equal scores without implying identical answers or general superiority', async () => {
  comparisonFixture();
  render(<Experiments />);
  await screen.findByText('Same overall pass rate on shared questions');
  expect(screen.getByText(/Equal totals can still contain different correct answers/)).toBeTruthy();
  expect(screen.getAllByText('1 of 4 answers passed')).toHaveLength(2);
  expect(screen.getByText('Runs completed · not questions passed')).toBeTruthy();
  expect(screen.getByRole('heading', { name: 'Memory strategy comparison' })).toBeTruthy();
  expect(screen.queryByText(/2026-10-08T09:49:20/)).toBeNull();
  expect(screen.getByText(/Requested question limit: 6 · Questions generated: 4/)).toBeTruthy();
  expect(screen.getByText(/answered correctly by only one setting/).textContent).toContain('2');
});

test('does not declare tied results when questions cannot be paired', async () => {
  comparisonFixture(0);
  render(<Experiments />);
  await screen.findByText('Results available · no shared-question comparison');
  expect(screen.queryByText('Same overall pass rate on shared questions')).toBeNull();
  expect(screen.getByText(/do not establish a fair ranking/)).toBeTruthy();
});


test('shows frozen prepared questions during recovery before requesting model answers', async () => {
  const user = userEvent.setup();
  const pending = { test_id:'T-recovery', run_id:'RUN-FAILED', dimension:'accuracy', prompt:'What is the recorded city?', expected_behavior:'State Albury.', supporting_memory_ids:[], generator_version:'fixture', test_type:'direct', quality_status:'pending', grounding_status:'grounded', validation_notes:'Needs review.' };
  apiMocks.testReview.mockResolvedValue({tests:[pending]});
  apiMocks.reviewTest.mockResolvedValue({...pending,quality_status:'accepted'});
  render(<History />);
  await screen.findByRole('button', {name:'View recovery plan'});
  await user.click(screen.getByRole('button', {name:'View recovery plan'}));
  await user.click(await screen.findByRole('button', {name:'Review prepared tests'}));
  await screen.findByText('What is the recorded city?');
  expect(apiMocks.retry).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', {name:'Accept'}));
  await waitFor(()=>expect(apiMocks.reviewTest).toHaveBeenCalledWith('RUN-FAILED','T-recovery','accepted'));
  expect(await screen.findByText(/This question is ready for testing/)).toBeTruthy();
});
