import { render, screen } from '@testing-library/react';
import { calculateExperimentStatistics, ExperimentStatistics } from './ExperimentStatistics';
import type { AuditResult } from '../types/domain';

function auditResult(runId: string, overall: number | null, freshness: number | null, failures = 0): AuditResult {
  return {
    run_id: runId,
    overall_score: overall,
    tests_passed: 3,
    tests_total: 4,
    dimensions: [
      { dimension: 'accuracy', percentage: 100, passed: 1, total: 1 },
      { dimension: 'freshness', percentage: freshness, passed: freshness === null ? 0 : freshness / 100, total: freshness === null ? 0 : 1 },
      { dimension: 'conflict_resolution', percentage: 50, passed: 1, total: 2 },
      { dimension: 'appropriate_use', percentage: 100, passed: 1, total: 1 },
    ],
    failures: Array.from({ length: failures }, (_, index) => ({
      failure_id: `${runId}-${index}`,
      test: { test_id: `T${index}`, run_id: runId, dimension: 'freshness', prompt: 'Prompt', expected_behavior: 'Expected', supporting_memory_ids: [], generator_version: 'v1' },
      response: { response_id: `R${index}`, test_id: `T${index}`, run_id: runId, response_text: 'Response', model: 'model', temperature: 0, created_at: '2026-01-01T00:00:00Z' },
      evaluation: { evaluation_id: `E${index}`, test_id: `T${index}`, response_id: `R${index}`, passed: false, failure_type: 'freshness', reason: 'Old value used', evidence_memory_ids: [], evaluator: 'v1' },
      evidence: [],
    })),
  };
}

test('aggregates repeated runs by group while excluding untested dimensions from averages', () => {
  const groups = calculateExperimentStatistics([
    { label: 'Run one', groupLabel: 'DeepSeek × Strong', result: auditResult('R1', 75, 50, 1) },
    { label: 'Run two', groupLabel: 'DeepSeek × Strong', result: auditResult('R2', 95, null, 0) },
    { label: 'Run three', groupLabel: 'Gemini × Weak', result: auditResult('R3', null, 0, 2) },
  ]);

  expect(groups).toHaveLength(2);
  expect(groups[0]).toMatchObject({ label: 'DeepSeek × Strong', runs: 2, overallAverage: 85, failureCount: 1, measuredDimensionRuns: 7, totalDimensionRuns: 8 });
  expect(groups[0].dimensions.find((item) => item.dimension === 'freshness')).toMatchObject({ average: 50, measuredRuns: 1, failures: 1 });
  expect(groups[1]).toMatchObject({ label: 'Gemini × Weak', overallAverage: null, failureCount: 2 });
});

test('explains when the selected comparison does not contain repeated runs', () => {
  render(<ExperimentStatistics runs={[{ label: 'DeepSeek × Strong', result: auditResult('R1', 75, 50, 1) }]} />);

  expect(screen.getByText('Research Comparison')).toBeTruthy();
  expect(screen.getAllByText(/Repeat-run statistics are not available yet/)).toHaveLength(2);
  expect(screen.getByText('4 / 4 dimension-runs')).toBeTruthy();
  expect(screen.getByText('3 / 4')).toBeTruthy();
});

test('shows variation once a condition has repeated runs', () => {
  render(<ExperimentStatistics runs={[
    { label: 'First', groupLabel: 'Rule agent', result: auditResult('R1', 60, 50) },
    { label: 'Second', groupLabel: 'Rule agent', result: auditResult('R2', 80, 50) },
  ]} />);

  expect(screen.queryByText(/^Repeat-run statistics are not available yet\. Complete/)).toBeNull();
  expect(screen.getByText(/Overall standard deviation: 10%/)).toBeTruthy();
});
