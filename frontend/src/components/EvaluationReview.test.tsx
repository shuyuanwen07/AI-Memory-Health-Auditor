import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EvaluationReview } from './EvaluationReview';

const apiMocks = vi.hoisted(() => ({
  evaluationReview: vi.fn(), evaluationCalibration: vi.fn(), reviewEvaluation: vi.fn(),
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
  apiMocks.evaluationCalibration.mockResolvedValue({ human_reviewed_count: 0, agreement_percentage: null, failure_precision: null, failure_recall: null, failure_f1: null, independent_review_count: 0, independently_reviewed_evaluation_count: 0, independent_consensus_count: 0, independent_conflict_count: 0, independent_pair_kappa: null });
  apiMocks.reviewEvaluation.mockResolvedValue({});
});

test('keeps automated verdict and summaries hidden in independent blind review mode', async () => {
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" />);
  await user.click(screen.getByRole('button', { name: 'Review Evaluations' }));
  await waitFor(() => expect(screen.getByText('Blind independent label')).toBeTruthy());
  expect(screen.queryByText('Automated: Fail')).toBeNull();
  expect(screen.queryByText(/automated agreement/)).toBeNull();
  await user.selectOptions(screen.getByLabelText('Evaluation review role'), 'reference');
  expect(screen.getByText('Automated: Fail')).toBeTruthy();
});

test('uses the reviewer-selected failure dimension rather than the automated class', async () => {
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" />);
  await user.click(screen.getByRole('button', { name: 'Review Evaluations' }));
  await waitFor(() => expect(screen.getByText('Blind independent label')).toBeTruthy());
  await user.selectOptions(screen.getByLabelText('Failure dimension E1'), 'appropriate_use');
  await user.click(screen.getByRole('button', { name: 'Human: Fail' }));
  await waitFor(() => expect(apiMocks.reviewEvaluation).toHaveBeenCalledWith('RUN1', 'E1', expect.objectContaining({ human_failure_type: 'appropriate_use', review_role: 'independent' })));
});
