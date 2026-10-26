import { UIProvider } from '../components/ui';
import { selectUIOption } from '../components/ui/testHelpers';
import { configure, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Experiments, History, experimentSettingName, experimentChartRuns } from './StaticPages';

import { calculateExperimentStatistics } from '../components/ExperimentStatistics';
import type { ExperimentAnalytics } from '../types/domain';

const apiMocks = vi.hoisted(() => ({
  savedFormalRuns: vi.fn(), audits: vi.fn(), results: vi.fn(), retryPlan: vi.fn(), retry: vi.fn(),
  testReview: vi.fn(), reviewTest: vi.fn(), regenerateTest: vi.fn(),
  downloadConversationExport: vi.fn(), deleteConversation: vi.fn(),
  experimentGroups: vi.fn(), experimentResults: vi.fn(), cancelExperiment: vi.fn(),
  downloadExperimentCsv: vi.fn(), downloadExperimentBundle: vi.fn(), downloadExperimentArtifact: vi.fn(),
}));
const downloadMocks = vi.hoisted(() => ({ saveBlob: vi.fn() }));

vi.mock('../services/api', () => ({ api: apiMocks }));
vi.mock('../services/download', () => ({ saveBlob: downloadMocks.saveBlob }));

const baseRun = {
  conversation_id: 'C001', target_configuration: 'strong' as const, temperature: 0,
  random_seed: 42, test_budget: 12, prompt_template_version: 'research-v1',
  pipeline_provider: 'rule_based', pipeline_model: 'rule-based-v1', evaluator_provider: 'rule_based',
  evaluator_model: 'rule-based-v1', memory_maintenance_policy: 'update_aware_consolidation' as const,
  target_memory_writer: 'rule_based' as const, created_at: '2026-01-01T00:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.savedFormalRuns.mockResolvedValue({items:[],total:0,offset:0,limit:25});
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
  await selectUIOption(user, 'Filter by memory strategy', 'Match the task and project');
  expect(screen.getByRole('link', {name:'View report'})).not.toBeNull();
  expect(screen.queryByRole('button', {name:'View recovery plan'})).toBeNull();
  await user.click(screen.getByText(/Memory settings · Match the task and project/i));
  expect(screen.getByText('Test generation: Rule-based processing')).not.toBeNull();
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
  await screen.findByText(/Memory settings · Supply no memories/i);
  expect(screen.queryByText(/Strong Memory/i)).toBeNull();
});

test('shows background progress instead of offering duplicate recovery', async () => {
  const user = userEvent.setup();
  apiMocks.retryPlan.mockResolvedValueOnce({run_id: 'RUN-FAILED', next_stage: 'execute_tests', pending: 3, retryable: true, busy: true});
  render(<History />);
  await user.click(await screen.findByRole('button', {name: 'View recovery plan'}));
  await screen.findByText(/Work is still running in the background/);
  expect(screen.queryByRole('button', {name: 'Resume audit'})).toBeNull();
  expect(screen.queryByRole('button', {name: 'Review prepared tests'})).toBeNull();
  expect(apiMocks.retry).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', {name: 'Check progress again'}));
  await screen.findByRole('button', {name: 'Resume audit'});
  expect(apiMocks.retryPlan).toHaveBeenCalledTimes(2);
  expect(apiMocks.retry).not.toHaveBeenCalled();
});

test('refreshes a stale history row when background work has already completed', async () => {
  const user = userEvent.setup();
  apiMocks.retryPlan.mockResolvedValueOnce({run_id: 'RUN-FAILED', status: 'COMPLETED', completed_at: '2026-01-01T00:02:00Z', next_stage: null, pending: 0, retryable: false, busy: false});
  render(<History />);
  await user.click(await screen.findByRole('button', {name: 'View recovery plan'}));
  await screen.findByText('Background work completed. The report is now available.');
  expect(screen.getAllByRole('link', {name: 'View report'}).map(link => link.getAttribute('href'))).toContain('/audits/RUN-FAILED');
  expect(screen.queryByText('No recovery is required for this run.')).toBeNull();
  expect(apiMocks.retry).not.toHaveBeenCalled();
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
  await screen.findByRole('button', {name: 'Retry result summary'},{timeout:15000});
  expect(screen.getByRole('heading', {name: 'Scenario 1'})).toBeTruthy();
  expect(screen.getByRole('heading', {name: 'Scenario 2'})).toBeTruthy();
  expect(screen.queryByText(/Experiment groups could not be loaded/)).toBeNull();
  expect(apiMocks.experimentResults).toHaveBeenCalledTimes(3);
  apiMocks.experimentResults.mockImplementation(async (id: string) => ({experiment: groups.find(g => g.experiment_id === id), runs: [], conditions: [], paired_comparisons: []}));
  await user.click(screen.getByRole('button', {name: 'Retry result summary'}));
  await waitFor(() => expect(screen.queryByRole('button', {name: 'Retry result summary'})).toBeNull(),{timeout:15000});
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

test('downloads the loaded answer report JSON, including passed answers with their run and test IDs', async () => {
  const user = userEvent.setup();
  comparisonFixture();
  const report = await apiMocks.experimentResults();
  const passedAnswer = {
    run_id: 'RUN-0', test_id: 'TEST-PASS', response_id: 'RESP-PASS', evaluation_id: 'EVAL-PASS',
    dimension: 'accuracy', prompt: 'Which database is current?', expected_behavior: 'Say PostgreSQL.',
    answer: 'PostgreSQL.', outcome: 'pass', observed_category: null,
    failure_classification: {status:'unclassified',method:'not_classified',reason:'No failure was observed.'},
    evaluation_reason: 'The saved answer matches the current fact.', supporting_memory_ids: ['MEM-1'],
    source_evidence: [{memory_id:'MEM-1',canonical_value:'Current database: PostgreSQL',source_message_ids:['MSG-1']}],
    source_statements: [{role:'user',content:'We now use PostgreSQL.',timestamp:'2026-01-01T00:00:00Z'}],
  };
  const unassessedAnswer = {
    run_id:'RUN-0', test_id:'TEST-UNASSESSED', response_id:'RESP-UNASSESSED', evaluation_id:null,
    dimension:'freshness', prompt:'What is the latest update?', expected_behavior:'Report the saved update.',
    answer:'The update is saved.', outcome:'unassessed', observed_category:null,
    failure_classification:null, evaluation_reason:null, supporting_memory_ids:[],
    source_evidence:[], source_statements:[],
  };
  report.runs[0].answers = [passedAnswer, unassessedAnswer];
  apiMocks.experimentResults.mockResolvedValue(report);
  render(<Experiments />);
  await user.click(await screen.findByText('Export results & experiment settings'));
  const jsonButton = await screen.findByRole('button', {name:'Answer report (JSON)'});
  await waitFor(() => expect(jsonButton).toBeEnabled());
  await user.click(jsonButton);
  await waitFor(() => expect(downloadMocks.saveBlob).toHaveBeenCalledTimes(1));
  const [blob, filename] = downloadMocks.saveBlob.mock.calls[0] as [Blob, string];
  expect(filename).toBe('experiment-EXP-SUMMARY-results.json');
  const downloaded = JSON.parse(await blob.text());
  expect(downloaded.runs[0].answers).toEqual([passedAnswer, unassessedAnswer]);
  expect(downloaded.runs[0].answers[0]).toMatchObject({run_id:'RUN-0',test_id:'TEST-PASS',outcome:'pass'});
  expect(downloaded.runs[0].answers[1]).toMatchObject({run_id:'RUN-0',test_id:'TEST-UNASSESSED',outcome:'unassessed',evaluation_id:null});
});

test('shows accessible passed and unassessed answer rows with source evidence disclosures', async () => {
  const user = userEvent.setup();
  comparisonFixture();
  const report = await apiMocks.experimentResults();
  report.runs[0].answers = [
    {run_id:'RUN-0',test_id:'TEST-PASS',response_id:'RESP-PASS',evaluation_id:'EVAL-PASS',dimension:'accuracy',
      prompt:'Which database is current?',expected_behavior:'Say PostgreSQL.',answer:'PostgreSQL.',outcome:'pass',
      observed_category:null,failure_classification:{status:'unclassified',method:'not_classified',reason:'No failure.'},
      evaluation_reason:'The answer matches the latest source.',supporting_memory_ids:['MEM-1'],
      source_evidence:[{memory_id:'MEM-1',canonical_value:'Current database: PostgreSQL',source_message_ids:['MSG-1']}],
      source_statements:[{role:'user',content:'We now use PostgreSQL.',timestamp:'2026-01-01T00:00:00Z'}]},
    {run_id:'RUN-0',test_id:'TEST-UNASSESSED',response_id:'RESP-UNASSESSED',evaluation_id:null,dimension:'freshness',
      prompt:'What is the latest update?',expected_behavior:'Report the saved update.',answer:'The update is saved.',outcome:'unassessed',
      observed_category:null,failure_classification:null,evaluation_reason:null,supporting_memory_ids:[],source_evidence:[],source_statements:[]},
  ];
  apiMocks.experimentResults.mockResolvedValue(report);
  render(<Experiments />);
  await user.click(await screen.findByText('Inspect answers & detected problems'));
  await user.click(screen.getAllByRole('button', {name:/Local Ollama.*Completed/i})[0]);
  const savedAnswers = screen.getByRole('region', {name:'Saved answers'});
  const passed = within(savedAnswers).getByRole('listitem', {name:'Passed answer for TEST-PASS'});
  const unassessed = within(savedAnswers).getByRole('listitem', {name:'Unassessed answer for TEST-UNASSESSED'});
  expect(within(passed).getByText('Which database is current?')).toBeInTheDocument();
  expect(within(passed).getByText('Say PostgreSQL.')).toBeInTheDocument();
  expect(within(passed).getByText('PostgreSQL.')).toBeInTheDocument();
  expect(within(unassessed).getByText('What is the latest update?')).toBeInTheDocument();
  expect(within(unassessed).getByText('Report the saved update.')).toBeInTheDocument();
  expect(within(unassessed).getByText('The update is saved.')).toBeInTheDocument();
  await user.click(within(passed).getByText('Source evidence'));
  expect(within(passed).getByText('Current database: PostgreSQL')).toBeInTheDocument();
  expect(within(passed).getByText('Source message IDs: MSG-1')).toBeInTheDocument();
  const statementsDisclosure = within(passed).getByText('Source statements').closest('details')!;
  expect(statementsDisclosure).not.toHaveAttribute('open');
  await user.click(within(passed).getByText('Source statements'));
  expect(statementsDisclosure).toHaveAttribute('open');
  expect(within(passed).getByText('We now use PostgreSQL.')).toBeInTheDocument();
  expect(within(unassessed).getByText('No linked source memory evidence.')).toBeInTheDocument();
});

test.each([0, 4])('does not declare tied results with %i excluded assessments when questions cannot be paired', async (excluded) => {
  comparisonFixture(0);
  const fixture = await apiMocks.experimentResults();
  fixture.paired_comparisons[0].excluded_assessment_count = excluded;
  apiMocks.experimentResults.mockResolvedValue(fixture);
  render(<Experiments />);
  await screen.findByText('Results available · no shared-question comparison', {}, {timeout:15000});
  expect(screen.queryByText('Same overall pass rate on shared questions')).toBeNull();
  expect(screen.getByText(/do not establish a fair ranking/)).toBeTruthy();
  if (excluded) expect(screen.getByText(/Scores from different review methods do not establish memory improvement/)).toBeTruthy();
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
  expect(screen.getByRole('button',{name:'Resume audit'})).toBeDisabled();
  expect(apiMocks.retry).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', {name:'Accept'}));
  await waitFor(()=>expect(apiMocks.reviewTest).toHaveBeenCalledWith('RUN-FAILED','T-recovery','accepted'));
  expect(await screen.findByText(/This question is ready for testing/)).toBeTruthy();
  expect(screen.getByRole('button',{name:'Resume audit'})).toBeEnabled();
});


test('same-policy settings remain distinguishable by evaluator and repair profile',()=>{
  const run={...baseRun,run_id:'run',status:'COMPLETED',provider:'ollama',model:'qwen',memory_strategy:'weak_first_hit'} as import('../types/domain').AuditRun;
  expect(experimentSettingName({...run,reproducibility:{schema_version:'test',target_retry_policy:{max_attempts:1,timeout_seconds:60,retryable_status_codes:[]},auditor_method:'model_generation'}})).toContain('Model tests + rule review');
  expect(experimentSettingName({...run,reproducibility:{schema_version:'test',target_retry_policy:{max_attempts:1,timeout_seconds:60,retryable_status_codes:[]},auditor_method:'hybrid'}})).toContain('Model tests + hybrid review');
  expect(experimentSettingName({...run,target_memory_profile:{label:'Diagnosis-guided repair'} as import('../components/TargetProfileEditor').TargetMemoryProfile})).toContain('Diagnosis-guided repair');
});


test('explains incompatible recovery before offering another engine request', async () => {
  const user = userEvent.setup();
  const reason = 'The audit software has changed. Start a new audit. Existing answers are preserved.';
  apiMocks.retryPlan.mockResolvedValueOnce({run_id:'RUN-FAILED', next_stage:'execute_tests', pending:3,
    retryable:false, resume_blocked_reason:reason, busy:false});
  render(<History />);
  await user.click(await screen.findByRole('button', {name:'View recovery plan'}));
  expect(await screen.findByRole('alert')).toHaveTextContent(reason);
  expect(screen.queryByRole('button', {name:'Resume audit'})).toBeNull();
  expect(screen.queryByRole('button', {name:'Review prepared tests'})).toBeNull();
  expect(screen.queryByText('No recovery is required for this run.')).toBeNull();
  expect(screen.getByRole('link', {name:'Start a new audit'})).toHaveAttribute('href','/new-audit');
  expect(apiMocks.retry).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', {name:'Check compatibility again'}));
  expect(await screen.findByRole('button', {name:'Resume audit'})).toBeEnabled();
  expect(apiMocks.retry).not.toHaveBeenCalled();
});


test('successful partial recovery explains the saved stage without calling it an error', async () => {
  apiMocks.retry.mockResolvedValueOnce({...baseRun,run_id:'RUN-FAILED',status:'TESTS_EXECUTED',
    provider:'deepseek',model:'deepseek-chat',memory_strategy:'weak_first_hit'});
  render(<History />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button',{name:'View recovery plan'}));
  await user.click(await screen.findByRole('button',{name:'Resume audit'}));
  const saved = await screen.findByText('Saved progress: answers are saved. View the recovery plan to finish their assessment.');
  expect(saved).toHaveClass('success-message');
  expect(screen.queryByText(/Recovery stopped/)).toBeNull();
  expect(screen.getByRole('button',{name:'View recovery plan'})).toBeEnabled();
  expect(apiMocks.retry).toHaveBeenCalledTimes(1);
});

test('history identifies saved-answer reassessment and finds it by its friendly type', async () => {
  apiMocks.audits.mockResolvedValue([{...baseRun,run_id:'reassessment-private-id',status:'COMPLETED',provider:'ollama',model:'qwen3:1.7b',memory_strategy:'full_context',reproducibility:{assessment_source_run_id:'original-private-id'}}]);
  render(<History />);
  expect(await screen.findByText('Saved-answer reassessment')).toBeTruthy();
  expect(screen.getByRole('link',{name:'View original assessment'})).toHaveAttribute('href','/audits/original-private-id');
  expect(screen.queryByText('original-private-id')).toBeNull();
  const user=userEvent.setup();
  await user.type(screen.getByLabelText('Search audit history'),'reassessment');
  expect(screen.getByRole('link',{name:'View report'})).toBeTruthy();
});

test('single-setting results do not claim a comparison or all original context', async () => {
  const experiment={experiment_id:'single',conversation_id:'c',label:'Memory strategy comparison · custom · 2026-01-01T00:00:00.000Z',status:'COMPLETED',test_suite_metadata:{test_count:1},test_suite_configuration:{},created_at:'2026-01-01T00:00:00Z'};
  const run={...baseRun,run_id:'one',status:'COMPLETED',provider:'ollama',model:'qwen3:1.7b',memory_strategy:'full_context'};
  apiMocks.experimentGroups.mockResolvedValue([experiment]);
  apiMocks.experimentResults.mockResolvedValue({experiment,runs:[{run,result:{overall_score:0,tests_passed:0,tests_total:1,dimensions:[{dimension:'accuracy',percentage:0,passed:0,total:1}],failures:[]}}],conditions:[{condition_id:'one',label:'Full context',model:'qwen3:1.7b',memory_strategy:'full_context',run_ids:['one'],planned_runs:1,completed_runs:1,tests_passed:0,tests_total:1,overall_mean:0,overall_standard_deviation:null,mean_latency_ms:null,total_tokens:null,failure_count:0}],paired_comparisons:[]});
  render(<Experiments />);
  expect(await screen.findByText('ONE SETTING · SAVED RESULTS')).toBeTruthy();
  expect(screen.getByRole('heading',{name:'Audit result'})).toBeTruthy();
  expect(screen.queryByText('SAME QUESTIONS · DIFFERENT SETTINGS')).toBeNull();
  expect(screen.getByText(/Replaced historical facts may be excluded/)).toBeTruthy();
  expect(screen.getByText('Questions in this audit')).toBeTruthy();
  expect(screen.getByText(/Results for one saved memory setting/)).toBeTruthy();
  expect(screen.queryByText(/Compare how different memory settings/)).toBeNull();
  expect(screen.queryByText('Uses all available conversation context.')).toBeNull();
  const chart = await screen.findByRole('region', {name:'Single-setting result charts'}, {timeout:15000});
  expect(within(chart).getByRole('heading',{name:'Results by dimension'})).toBeTruthy();
  expect(within(chart).getByLabelText(/Dimension results\. Accuracy:.*0%.*Freshness:.*Not tested/)).toBeTruthy();
  expect(within(chart).queryByRole('heading',{name:'Visual Comparison'})).toBeNull();
  expect(within(chart).getByRole('region',{name:'Scrollable dimension chart'}).getAttribute('tabindex')).toBe('0');
});


test('multi-setting purpose does not infer fixed memory policies from the evaluator comparison flag',async()=>{
  comparisonFixture();
  const fixture=await apiMocks.experimentResults();
  fixture.experiment.test_suite_configuration.compare_evaluators=true;
  apiMocks.experimentResults.mockResolvedValue(fixture);
  render(<Experiments/>);
  expect(await screen.findByText(/2 saved settings on the shared questions/)).toBeTruthy();
  expect(screen.queryByText(/target model and memory policy stay fixed/)).toBeNull();
  expect(screen.getByRole('button',{name:'Settings & answer counts'})).toHaveAttribute('aria-expanded','false');
});


test('does not present a one-question confidence interval or conceal pending judgments', async () => {
  const user = userEvent.setup();
  comparisonFixture(1);
  const report = await apiMocks.experimentResults();
  Object.assign(report.experiment.test_suite_metadata, {test_count:2});
  report.paired_comparisons[0] = {...report.paired_comparisons[0], shared_question_count:2, excluded_uncertain_count:1,
    excluded_assessment_count:0, both_passed:1, both_failed:0, reference_only_passed:0, candidate_only_passed:0, two_sided_sign_test_p_value:1};
  report.conditions.forEach((condition: Record<string, unknown>) => Object.assign(condition, {tests_passed:1, tests_total:1, failure_count:0, overall_mean:100}));
  report.runs.forEach((item: {result: Record<string, unknown>}) => Object.assign(item.result, {tests_passed:1, tests_total:1, overall_score:100, uncertain_count:1, failures:[]}));
  apiMocks.experimentResults.mockResolvedValue(report);
  render(<Experiments />);
  await user.click(await screen.findByText('Detailed scores, runtime & statistics'));
  await user.click(await screen.findByText('Paired comparison signals'));
  expect(await screen.findByText('Not estimable from one question')).toBeInTheDocument();
  expect(screen.getByText(/A zero-width interval does not prove certainty/)).toBeInTheDocument();
  expect(screen.getByText(/Answers awaiting assessment are excluded from paired changes/)).toBeInTheDocument();
  const pairedTable = screen.getByRole('columnheader', {name:'Awaiting assessment'}).closest('table')!;
  expect(within(pairedTable).getAllByRole('cell').slice(1,5).map(cell=>cell.textContent)).toEqual(['2','1','1','0']);
  await user.click(screen.getByText('Inspect answers & detected problems'));
  const runSummaries = screen.getAllByRole('button', {name:/Local Ollama.*Completed/i});
  // Open by their accessible summary text rather than reaching into component state.
  for (const summary of runSummaries) await user.click(summary);
  expect(screen.getAllByText('No failures were detected among decided answers.')).toHaveLength(2);
  expect(screen.getAllByText(/1 answer still awaits review/)).toHaveLength(2);
});

test('chart groups use verified conditions and friendly settings instead of opaque saved labels', () => {
  const runs = [25,75].map((score,index) => ({run:{...baseRun,run_id:`RUN-${index}`,model:'qwen3:1.7b',memory_strategy:'weak_first_hit',status:'COMPLETED'},result:{overall_score:score,tests_passed:score/25,tests_total:4,dimensions:[],failures:[]}}));
  const report = {runs,conditions:[]} as unknown as ExperimentAnalytics;
  const separate = calculateExperimentStatistics(experimentChartRuns(report));
  expect(separate.map(group=>group.overallAverage)).toEqual([25,75]);
  expect(separate.every(group=>group.label.includes('First matching memory'))).toBe(true);
  expect(separate.every(group=>!group.label.includes('RUN-'))).toBe(true);
  report.conditions = [{condition_id:'verified-id',label:'Weak First Hit · RUN-INTERNAL',run_ids:['RUN-0','RUN-1']}] as ExperimentAnalytics['conditions'];
  const repeated = calculateExperimentStatistics(experimentChartRuns(report));
  expect(repeated).toHaveLength(1);
  expect(repeated[0].overallAverage).toBe(50);
  expect(repeated[0].label).toBe('qwen3:1.7b · First matching memory');
});

test.each(['low','medium'] as const)('shows saved optional %s reasoning request without calling it measured effort',async effort=>{
  const {defaultTargetProfile}=await import('../components/TargetProfileEditor');
  apiMocks.audits.mockResolvedValue([{...baseRun,run_id:'LOW-REQUEST',status:'COMPLETED',provider:'openrouter',model:'openai/gpt-6-luna',memory_strategy:'scope_aware',
    target_memory_profile:{...defaultTargetProfile,reasoning_effort:effort,identity_analysis_reasoning_effort:'low'}}]);
  render(<History/>);
  expect(await screen.findByText(`Configured final reasoning request: ${effort}`)).toBeInTheDocument();
  expect(screen.getByText('Configured identity reasoning request: low. Actual reasoning effort is not reported.')).toBeInTheDocument();
});
