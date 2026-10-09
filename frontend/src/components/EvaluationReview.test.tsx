import { selectUIOption } from './ui/testHelpers';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EvaluationReview } from './EvaluationReview';

const apiMocks = vi.hoisted(() => ({
  evaluationReview: vi.fn(), blindEvaluationReview: vi.fn(), evaluationCalibration: vi.fn(), reviewEvaluation: vi.fn(),
}));
vi.mock('../services/api', () => ({ api: apiMocks }));

const item = {
  test: { test_id: 'T1', run_id: 'RUN1', dimension: 'freshness', prompt: 'Which database applies now?', expected_behavior: 'PostgreSQL', supporting_memory_ids: ['M1'], generator_version: 'v1' },
  response: { response_id: 'R1', test_id: 'T1', run_id: 'RUN1', response_text: 'MySQL', model: 'local', temperature: 0, created_at: '2026-01-01T00:00:00Z' },
  automated: { evaluation_id: 'E1', test_id: 'T1', response_id: 'R1', passed: false, failure_type: 'freshness', reason: 'Expected PostgreSQL.', evidence_memory_ids: ['M1'], evaluator: 'rule-based-v4' },
  human_reviews: [], human_review: null,
};

beforeEach(() => {
  apiMocks.evaluationReview.mockResolvedValue([item]);
  apiMocks.blindEvaluationReview.mockResolvedValue([{...item, test:{test_id:item.test.test_id,prompt:item.test.prompt,expected_behavior:item.test.expected_behavior}, response:{response_text:item.response.response_text}, automated:{evaluation_id:"E1"}}]);
  apiMocks.evaluationCalibration.mockResolvedValue({ human_reviewed_count: 0, agreement_percentage: null, failure_precision: null, failure_recall: null, failure_f1: null, independent_review_count: 0, independently_reviewed_evaluation_count: 0, independent_consensus_count: 0, independent_conflict_count: 0, independent_pair_kappa: null });
  apiMocks.reviewEvaluation.mockResolvedValue({});
});

test('keeps automated verdict and summaries hidden in independent blind review mode', async () => {
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" />);
  await user.click(screen.getByRole('button', { name: 'Review Evaluations' }));
  await waitFor(() => expect(screen.getByText('Blind independent label')).toBeTruthy());
  expect(screen.getByText('Reference behaviour:')).toBeTruthy();
  expect(screen.getByText(/PostgreSQL/, { selector: '.review-reference small' })).toBeTruthy();
  expect(screen.queryByText('Expected PostgreSQL.')).toBeNull();
  expect(screen.queryByText('Automated: Fail')).toBeNull();
  expect(screen.queryByText(/automated agreement/)).toBeNull();
  await selectUIOption(user, 'Evaluation review role', 'Reference label');
  await user.click(screen.getByRole('button', {name:'Review Evaluations'}));
  expect(await screen.findByText('Automated: Fail')).toBeTruthy();
  expect(screen.getByText('Expected PostgreSQL.')).toBeTruthy();
});

test('uses the reviewer-selected failure dimension rather than the automated class', async () => {
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" />);
  await user.click(screen.getByRole('button', { name: 'Review Evaluations' }));
  await waitFor(() => expect(screen.getByText('Blind independent label')).toBeTruthy());
  await selectUIOption(user, 'Failure dimension 1', 'Appropriate Use');
  await user.click(screen.getByRole('button', { name: 'Human: Fail' }));
  await waitFor(() => expect(apiMocks.reviewEvaluation).toHaveBeenCalledWith('RUN1', 'E1', expect.objectContaining({ human_failure_type: 'appropriate_use', review_role: 'independent' })));
});

test('shows recorded judge requests only outside blind mode and leaves historical cost unknown', async () => {
  apiMocks.evaluationReview.mockResolvedValue([{...item, automated:{...item.automated, judge_execution:{request_attempts:2,failed_http_attempts:1,elapsed_ms:1200,reported_total_tokens:null}}}]);
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" />);
  await user.click(screen.getByRole('button', {name:'Review Evaluations'}));
  expect(await screen.findByText('Blind independent label')).toBeTruthy();
  expect(screen.queryByText(/Assessment requests:/)).toBeNull();
  await selectUIOption(user, 'Evaluation review role', 'Reference label');
  await user.click(screen.getByRole('button', {name:'Review Evaluations'}));
  expect(await screen.findByText(/Assessment requests: 2/)).toBeTruthy();
  expect(screen.getByText(/failed HTTP attempts: 1/).textContent).toContain('reported tokens: Unknown');
  apiMocks.evaluationReview.mockResolvedValue([item]);
  await selectUIOption(user, 'Evaluation review role', 'Adjudication');
  await user.click(screen.getByRole('button', {name:'Review Evaluations'}));
  expect(await screen.findByText('Assessment request evidence was not recorded for this result. Costs remain unknown.')).toBeTruthy();
});

test('confirms a saved blind label without revealing the automated verdict', async () => {
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" />);
  await user.click(screen.getByRole('button', { name: 'Review Evaluations' }));
  await waitFor(() => expect(screen.getByText('Blind independent label')).toBeTruthy());
  await selectUIOption(user, 'Failure dimension 1', 'Freshness');
  await user.click(screen.getByRole('button', { name: 'Human: Fail' }));
  expect((await screen.findByRole('status')).textContent).toContain('Your independent label was saved: Fail. It is recorded as calibration evidence.');
  expect(screen.queryByText('Automated: Fail')).toBeNull();
});

test('requires an explicit independent failure class without exposing the test dimension as a heading', async () => {
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" />);
  await user.click(screen.getByRole('button', { name: 'Review Evaluations' }));
  await screen.findByText('Blind independent label');
  expect(screen.getByRole('button', { name: 'Human: Fail' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Human: Pass' })).toBeEnabled();
  expect(screen.queryByText('Freshness', { selector: '.evaluation-review-card .row b' })).toBeNull();
  await selectUIOption(user, 'Failure dimension 1', 'Accuracy');
  expect(screen.getByRole('button', { name: 'Human: Fail' })).toBeEnabled();
});
