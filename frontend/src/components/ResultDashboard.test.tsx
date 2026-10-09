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
  expect(screen.getByText('1 flagged')).toBeTruthy();
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

test('labels incomplete coverage and shows original conversation evidence', () => {
  render(<ResultDashboard result={{...result,failures:[{...result.failures[0],source_statements:[{role:'user',content:'Atlas project now uses PostgreSQL.',timestamp:'2026-01-01T00:00:00Z'}]}]}}/>);
  expect(screen.getByText('TESTED ABILITY AVERAGE')).toBeTruthy();
  expect(screen.getByText(/A formal overall Memory Health score requires all four dimensions/)).toBeTruthy();
  expect(screen.getByText('Atlas project now uses PostgreSQL.')).toBeTruthy();
});


test('distinguishes completed uncertain answers from untested dimensions and exports that distinction', () => {
  const pending: AuditResult = {...result, uncertain_count: 1,
    dimensions: result.dimensions.map(d => d.dimension === 'appropriate_use' ? {...d, uncertain_count: 1} : d)};
  render(<ResultDashboard result={pending} />);
  expect(screen.getByText('Awaiting review', {selector:'strong'})).toBeTruthy();
  expect(screen.getByText('Completed answers need independent review')).toBeTruthy();
  expect(buildAuditResultCsv(pending)).toContain('Awaiting review');
});


test('explains excluded retrieval attempts instead of crediting an unfinished answer', () => {
  render(<ResultDashboard result={{...result, retrieval_quality:{
    tests_measured:0, unlinked_attempts_excluded:2,
    evidence_recall_at_k:null, evidence_precision_at_k:null,
    update_evidence_recall:null, conflict_evidence_coverage:null,
    unnecessary_memory_retrieval_rate:null,
  }}} />);
  expect(screen.getByText(/2 retrieval attempts without a linked saved answer are excluded/)).toBeTruthy();
  expect(screen.getByText(/No retrieval trace with source evidence is available/)).toBeTruthy();
});


test('shows uncertain answers beside the score rather than implying all completed answers passed', () => {
  render(<ResultDashboard result={{...result, overall_score:100, tests_total:4, tests_passed:4, uncertain_count:1}}/>);
  expect(screen.getByRole('region',{name:'Answer outcomes'})).toHaveTextContent('5 completed answers');
  expect(screen.getByRole('img',{name:'4 passed, 0 failed, 1 awaiting review out of 5 completed answers'})).toBeTruthy();
  expect(screen.getByText(/Awaiting review does not mean passed/)).toBeTruthy();
});

test('outcome chart includes failures and handles a wholly uncertain audit', () => {
  const view = render(<ResultDashboard result={{...result, tests_total:3, tests_passed:2, uncertain_count:2}}/>);
  expect(screen.getByRole('img',{name:'2 passed, 1 failed, 2 awaiting review out of 5 completed answers'})).toBeTruthy();
  view.rerender(<ResultDashboard result={{...result, uncertain_count:2}}/>);
  expect(screen.getByRole('img',{name:'0 passed, 0 failed, 2 awaiting review out of 2 completed answers'})).toBeTruthy();
  view.rerender(<ResultDashboard result={{...result, uncertain_count:0}}/>);
  expect(screen.getByText('No assessed answers are available.')).toBeTruthy();
});


test('whole pending audit headline and summary export acknowledge completed answers', () => {
  const pending = {...result, overall_score:null, tests_total:0,tests_passed:0,uncertain_count:5};
  render(<ResultDashboard result={pending}/>);
  expect(screen.getByRole('heading',{name:'Unscored'})).toBeTruthy();
  expect(screen.getByText('5 completed answers await review')).toBeTruthy();
  expect(screen.queryByText('No completed tests are available for scoring')).toBeNull();
  expect(buildAuditResultCsv(pending)).toContain('Awaiting review');
});
