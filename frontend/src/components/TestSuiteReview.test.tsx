import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TestSuiteReview } from './TestSuiteReview';
import type { TestCase } from '../types/domain';

test('keeps unreviewed legacy questions pending and updates feedback after acceptance', async () => {
  const test: TestCase = { test_id: 'test', run_id: 'run', dimension: 'accuracy', prompt: 'Which database is used?', expected_behavior: 'PostgreSQL', supporting_memory_ids: [], generator_version: 'preview' };
  const review = vi.fn();
  const { rerender } = render(<TestSuiteReview tests={[test]} busy={false} onReview={review} onRegenerate={vi.fn()} />);
  expect(screen.getByText('1 question still needs review')).not.toBeNull();
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('0');
  await userEvent.click(screen.getByRole('button', { name: 'Accept' }));
  expect(review).toHaveBeenCalledWith(test, 'accepted');
  rerender(<TestSuiteReview tests={[{ ...test, quality_status: 'accepted' }]} busy={false} onReview={review} onRegenerate={vi.fn()} />);
  expect(screen.getByText('Quality decisions complete')).not.toBeNull();
  expect(screen.getByRole('status').textContent).toContain('ready for testing');
  expect((screen.getByRole('button', { name: '✓ Accepted' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('1');
  rerender(<TestSuiteReview tests={[{ ...test, quality_status: 'rejected' }]} busy={false} onReview={review} onRegenerate={vi.fn()} />);
  expect(screen.queryByText('Quality decisions complete')).toBeNull();
  expect(screen.getByText('1 rejected question blocks execution')).toBeTruthy();
  expect((screen.getByRole('button', { name: 'Accept' }) as HTMLButtonElement).disabled).toBe(false);
});

test('flags identical questions with different answers instead of declaring the suite ready', () => {
  const test: TestCase = { test_id: 'one', run_id: 'run', dimension: 'accuracy', prompt: 'Which task?', expected_behavior: 'First policy', supporting_memory_ids: [], generator_version: 'preview', quality_status: 'accepted' };
  render(<TestSuiteReview tests={[test, {...test, test_id: 'two', prompt: 'Which task!', expected_behavior: 'Second policy'}]} busy={false} onReview={vi.fn()} onRegenerate={vi.fn()} />);
  expect(screen.getByRole('alert').textContent).toContain('same wording');
  expect(screen.queryByText('Quality decisions complete')).toBeNull();
  expect(screen.getByText('Duplicate questions need repair')).toBeTruthy();
});

test('shows formal reference questions read-only without reject or regenerate controls', () => {
  const test: TestCase = { test_id: 'one', run_id: 'run', dimension: 'accuracy', prompt: 'Which fact?', expected_behavior: 'Reviewed value', supporting_memory_ids: [], generator_version: 'synthetic-formal-matrix-v3', quality_status: 'accepted' };
  render(<TestSuiteReview tests={[test]} busy={false} onReview={vi.fn()} onRegenerate={vi.fn()} />);
  expect(screen.getByRole('heading', {name: 'Frozen reference questions'})).toBeTruthy();
  expect(screen.getByText(/review and import a new dataset version/)).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Reject'})).toBeNull();
  expect(screen.queryByRole('button', {name: 'Regenerate'})).toBeNull();
  expect(screen.queryByRole('button', {name: '✓ Accepted'})).toBeNull();
});
