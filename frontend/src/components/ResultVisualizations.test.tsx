import { render, screen } from '@testing-library/react';
import { ComparisonVisualizations, ScoreRadarChart } from './ResultVisualizations';
import type { AuditResult } from '../types/domain';

function result(runId: string, overall: number, freshness: number): AuditResult {
  return {
    run_id: runId,
    overall_score: overall,
    tests_passed: 3,
    tests_total: 4,
    dimensions: [
      { dimension: 'accuracy', percentage: 100, passed: 1, total: 1 },
      { dimension: 'freshness', percentage: freshness, passed: freshness / 100, total: 1 },
      { dimension: 'conflict_resolution', percentage: 50, passed: 1, total: 2 },
      { dimension: 'appropriate_use', percentage: 75, passed: 3, total: 4 },
    ],
    failures: Array.from({ length: freshness < 100 ? 1 : 0 }, (_, index) => ({
      failure_id: `${runId}-failure-${index}`,
      test: { test_id: `T-${runId}-${index}`, run_id: runId, dimension: 'freshness', prompt: 'What database is current?', expected_behavior: 'Use PostgreSQL.', supporting_memory_ids: ['M002'], generator_version: 'test-v1' },
      response: { response_id: `R-${runId}-${index}`, test_id: `T-${runId}-${index}`, run_id: runId, response_text: 'MySQL', model: 'target', temperature: 0, created_at: '2026-01-01T00:00:00Z' },
      evaluation: { evaluation_id: `E-${runId}-${index}`, test_id: `T-${runId}-${index}`, response_id: `R-${runId}-${index}`, passed: false, failure_type: 'freshness', reason: 'An outdated value was used.', evidence_memory_ids: ['M002'], evaluator: 'rule-v1' },
      evidence: [],
    })),
  };
}

test('renders the accessible four-dimension Memory Health profile', () => {
  render(<ScoreRadarChart result={result('RUN-RADAR', 68.75, 50)} />);

  expect(screen.getByRole('heading', { name: 'Memory Health Profile' })).toBeTruthy();
  expect(screen.getByRole('img', { name: /Radar chart: Accuracy: 100%; Freshness: 50%/ })).toBeTruthy();
  expect(screen.getByText(/Conflict Resolution: 50%/)).toBeTruthy();
  expect(screen.getByText(/Appropriate Use: 75%/)).toBeTruthy();
});

test('renders overall, dimension, and failure comparison charts for experimental conditions', () => {
  render(<ComparisonVisualizations runs={[
    { label: 'Weak run one', groupLabel: 'Weak Memory', result: result('RUN-WEAK-1', 50, 0) },
    { label: 'Weak run two', groupLabel: 'Weak Memory', result: result('RUN-WEAK-2', 60, 25) },
    { label: 'Strong run', groupLabel: 'Strong Memory', result: result('RUN-STRONG-1', 90, 100) },
  ]} />);

  expect(screen.getByRole('heading', { name: 'Visual Comparison' })).toBeTruthy();
  expect(screen.getByRole('heading', { name: 'Overall Memory Health by Condition' })).toBeTruthy();
  expect(screen.getByRole('heading', { name: 'Dimension Comparison' })).toBeTruthy();
  expect(screen.getByRole('heading', { name: 'Detected Failure Distribution' })).toBeTruthy();
  expect(screen.getByRole('img', { name: /Horizontal bar chart\. Weak Memory: 55%.*Strong Memory: 90%/ })).toBeTruthy();
  expect(screen.getByRole('img', { name: /Grouped bar chart\. Accuracy: Weak Memory 100%, Strong Memory 100%/ })).toBeTruthy();
  expect(screen.getByRole('img', { name: /Grouped failure bar chart\. .*Freshness: Weak Memory 2, Strong Memory 0/ })).toBeTruthy();
});
