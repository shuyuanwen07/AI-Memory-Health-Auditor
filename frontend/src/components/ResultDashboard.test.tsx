import { render, screen } from '@testing-library/react';
import { buildAuditResultCsv, ResultDashboard } from './ResultDashboard';
import type { AuditResult } from '../types/domain';

const result: AuditResult = {
  run_id: 'RUN001', overall_score: null, tests_passed: 0, tests_total: 0,
  dimensions: [
    { dimension: 'accuracy', percentage: null, passed: 0, total: 0 },
    { dimension: 'freshness', percentage: 50, passed: 1, total: 2 },
    { dimension: 'conflict_resolution', percentage: null, passed: 0, total: 0 },
    { dimension: 'appropriate_use', percentage: null, passed: 0, total: 0 },
  ],
  failures: [{
    failure_id: 'E001',
    test: { test_id: 'T001', run_id: 'RUN001', dimension: 'freshness', prompt: 'Which database is current?', expected_behavior: 'Use the current value: PostgreSQL', supporting_memory_ids: ['M001'], generator_version: 'rule-based-v1' },
    response: { response_id: 'R001', test_id: 'T001', run_id: 'RUN001', response_text: 'MySQL', model: 'baseline', temperature: 0, created_at: '2026-01-01T00:00:00Z' },
    evaluation: { evaluation_id: 'E001', test_id: 'T001', response_id: 'R001', passed: false, failure_type: 'freshness', reason: 'The response retained an older value.', evidence_memory_ids: [], evaluator: 'rule-based-v1' },
    evidence: [],
  }],
};

test('explains untested dimensions and makes failure evidence inspectable', () => {
  render(<ResultDashboard result={result} />);

  expect(screen.getAllByText('Not tested')).toHaveLength(4);
  expect(screen.getByText(/Untested dimensions are excluded from the macro-average/)).toBeTruthy();
  expect(screen.getByText('Download CSV')).toBeTruthy();
  expect(screen.getByText('1 detected')).toBeTruthy();
  expect(screen.getByText('Expected behaviour')).toBeTruthy();
  expect(screen.getByText(/No traceable ground-truth evidence/)).toBeTruthy();
});

test('creates a local CSV report containing summaries and traceable failure details', () => {
  const csv = buildAuditResultCsv(result);

  expect(csv).toContain('"Audit summary"');
  expect(csv).toContain('"Dimension summary"');
  expect(csv).toContain('"Failure detail"');
  expect(csv).toContain('"The response retained an older value."');
  expect(csv).toContain('"MySQL"');
});
