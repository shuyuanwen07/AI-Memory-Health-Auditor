import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { completedAuditOptionLabel, defaultCompletedAuditId, FinalResultsDashboard } from './FinalResultsDashboard';
import { auditDisplayNames } from '../services/display';
import type { AuditResult, AuditRun } from '../types/domain';

const mocks = vi.hoisted(() => ({ audits: vi.fn(), results: vi.fn(), ac3StudySummaries: vi.fn().mockResolvedValue({ studies: [] }) }));
class TestResizeObserver { observe() {} unobserve() {} disconnect() {} }
vi.mock('../services/api', () => ({ api: mocks }));

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.stubGlobal('ResizeObserver', TestResizeObserver); });

function installFetch() {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    if (String(input).includes('proposal-final-results-v1.json')) {
      const body = readFileSync(resolve(process.cwd(), 'public/reports/proposal-final-results-v1.json'), 'utf8');
      return { status: 200, ok: true, text: async () => body } as Response;
    }
    return { status: 404, ok: false, text: async () => '' } as Response;
  }));
}

beforeEach(() => { vi.clearAllMocks(); installFetch(); });

it('loads one saved completed repair audit with ability scores, issues, and evidence links', async () => {
  const run = {
    run_id: 'RUN12345678', conversation_id: 'CONV12345678', experiment_id: 'EXP12345678', status: 'COMPLETED',
    target_configuration: 'strong', provider: 'openrouter', model: 'openai/gpt-6-luna', temperature: 0,
    random_seed: 42, test_budget: 4, prompt_template_version: 'v1', pipeline_provider: 'rule_based', pipeline_model: 'rules',
    evaluator_provider: 'rule_based', evaluator_model: 'rules', memory_strategy: 'strong_rule_based',
    reproducibility: { study_role: 'diagnostic_intervention', assessment_source_run_id: 'RUN87654321', schema_version: '1', target_retry_policy: { max_attempts: 1 } },
    created_at: '2026-10-27T10:00:00Z', completed_at: '2026-10-27T11:00:00Z',
  } as unknown as AuditRun;
  const result = {
    run_id: run.run_id, overall_score: 83.3, formal_overall_score: null, tests_passed: 3, tests_total: 4,
    dimensions: [
      { dimension: 'accuracy', percentage: 100, passed: 1, total: 1, uncertain_count: 0 },
      { dimension: 'freshness', percentage: 50, passed: 1, total: 2, uncertain_count: 0 },
      { dimension: 'conflict_resolution', percentage: 100, passed: 1, total: 1, uncertain_count: 0 },
      { dimension: 'appropriate_use', percentage: null, passed: 0, total: 0, uncertain_count: 1 },
    ],
    uncertain_count: 1,
    failures: [{
      failure_id: 'FAIL12345678',
      test: { test_id: 'TEST12345678', run_id: run.run_id, dimension: 'freshness', prompt: 'Which current budget applies?', expected_behavior: 'Use the revised budget.', supporting_memory_ids: [], generator_version: 'v1' },
      response: { response_id: 'RESP12345678', test_id: 'TEST12345678', run_id: run.run_id, response_text: 'The old budget applies.', model: run.model, created_at: run.completed_at },
      evaluation: { evaluation_id: 'EVAL12345678', test_id: 'TEST12345678', response_id: 'RESP12345678', passed: false, failure_type: 'freshness', reason: 'The outdated budget was returned.', evidence_memory_ids: [], evaluator: 'rule_based' },
      evidence: [],
    }],
    uncertain_answers: [{
      test: { test_id: 'TEST_UNCERTAIN', run_id: run.run_id, dimension: 'appropriate_use', prompt: 'Is the exception project-specific?', expected_behavior: 'Use only in that project.', supporting_memory_ids: [], generator_version: 'v1' },
      response: { response_id: 'RESP_UNCERTAIN', test_id: 'TEST_UNCERTAIN', run_id: run.run_id, response_text: 'Unclear.', model: run.model, created_at: run.completed_at },
      evaluation: { evaluation_id: 'EVAL_UNCERTAIN', test_id: 'TEST_UNCERTAIN', response_id: 'RESP_UNCERTAIN', passed: null, reason: 'Not enough evidence.', evidence_memory_ids: [], evaluator: 'rule_based' },
      evidence: [],
    }],
  } as unknown as AuditResult;
  const unfinishedRun = { ...run, run_id: 'RUN11111111', status: 'FAILED', created_at: '2026-10-27T09:00:00Z', completed_at: undefined } as AuditRun;
  const allSavedRuns = [run, unfinishedRun];
  mocks.audits.mockResolvedValue(allSavedRuns);
  mocks.results.mockResolvedValue(result);
  render(<FinalResultsDashboard />);

  expect(await screen.findByText('Completed audits')).toBeInTheDocument();
  expect(await screen.findByText(/3\/4 passed/)).toBeInTheDocument();
  expect(await screen.findByText('A · Which audit method finds problems?')).toBeInTheDocument();
  expect(screen.getByText('B & C · Four memory strategies')).toBeInTheDocument();
  expect(screen.getByText('Auditor · Before and after improvement')).toBeInTheDocument();
  expect(screen.getByText(/same 3 of 9 predefined defects/)).toBeInTheDocument();
  expect(screen.getByRole('img', {name:'Human-invalid: 17 rejected, 37 pending review, 0 accepted'})).toBeInTheDocument();
  expect(screen.getByRole('img', {name:'Human-valid: 9 rejected, 53 pending review, 1 accepted'})).toBeInTheDocument();
  expect(screen.getByRole('img', {name:'Human-valid: 13 newly pending, 1 accepted'})).toBeInTheDocument();
  expect(screen.getByRole('img', {name:'Human-invalid: 14 already rejected by the per-question rule'})).toBeInTheDocument();
  expect(screen.getByText(/Per-question rule and scope check reconstructed afterwards, not the full production workflow/)).toBeInTheDocument();
  expect(screen.getByRole('img', {name:'Human-invalid: model labelled 2 invalid, 12 uncertain, 0 valid'})).toBeInTheDocument();
  expect(screen.getByRole('img', {name:'Human-valid: model labelled 3 invalid, 1 uncertain, 10 valid'})).toBeInTheDocument();
  expect(screen.getByText(/4\/33 responses could not be parsed and count as uncertain/)).toBeInTheDocument();
  expect(screen.getByText(/this candidate is not deployed and does not establish a safety improvement/)).toBeInTheDocument();
  expect(screen.getByText('Overall memory health across measured abilities')).toBeInTheDocument();
  expect(screen.getByText('83.3%')).toBeInTheDocument();
  expect(screen.getByText(/3\/4 abilities measured/)).toBeInTheDocument();
  expect(screen.getByText(/formal four-ability score unavailable/i)).toBeInTheDocument();
  expect(screen.getByText(/saved automated assessments/i)).toBeInTheDocument();
  expect(screen.getByText((_, element) => element?.tagName === 'P' && Boolean(element.textContent?.includes('completed 2026-10-27')))).toBeInTheDocument();
  const optionOne = completedAuditOptionLabel(run, auditDisplayNames(allSavedRuns)[run.run_id]);
  const optionTwo = completedAuditOptionLabel({ ...run, completed_at: '2026-10-27T11:30:00Z' }, 'Audit 2');
  expect(optionOne).toContain('diagnostic intervention · diagnosis / repair / retest');
  expect(optionOne).toContain('Audit 2');
  expect(optionOne).toContain('2026-10-27 11:00');
  expect(optionTwo).toContain('2026-10-27 11:30');
  expect(optionOne).not.toBe(optionTwo);
  expect(optionOne).not.toContain(run.run_id);
  expect(screen.getByRole('img', { name: /Horizontal bar chart of the four measured abilities/ })).toBeInTheDocument();
  expect(screen.getAllByText('Conflict resolution').length).toBeGreaterThan(0);
  expect(screen.getByRole('img', { name: /Donut chart of decided and uncertain audit outcomes/ })).toBeInTheDocument();
  expect(screen.getByText('Not measured')).toBeInTheDocument();
  expect(screen.getByText(/Small sample: at least one ability has only one decided question/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Open full saved audit evidence →' })).toHaveAttribute('href', `/audits/${run.run_id}`);
  expect(screen.getByRole('link', { name: 'Open diagnosis / repair experiment →' })).toHaveAttribute('href', `/experiments/${run.experiment_id}`);
  expect(screen.getByRole('link', { name: 'Open original target run →' })).toHaveAttribute('href', '/audits/RUN87654321');
});

it('defaults to the newest completed audit, preserves an explicit selection, and falls back if it disappears', () => {
  const olderRepair = { run_id: 'OLDER', status: 'COMPLETED', created_at: '2026-10-26T00:00:00Z', completed_at: '2026-10-26T01:00:00Z', reproducibility: { study_role: 'repair_comparison' } } as unknown as AuditRun;
  const newestAudit = { run_id: 'NEWEST', status: 'COMPLETED', created_at: '2026-10-27T00:00:00Z', completed_at: '2026-10-27T01:00:00Z' } as unknown as AuditRun;
  expect(defaultCompletedAuditId([newestAudit, olderRepair], '', false)).toBe('NEWEST');
  expect(defaultCompletedAuditId([newestAudit, olderRepair], 'OLDER', true)).toBe('OLDER');
  expect(defaultCompletedAuditId([newestAudit], 'OLDER', true)).toBe('NEWEST');
  expect(defaultCompletedAuditId([], '', false)).toBe('');
});

it('still shows research results when there are no completed audits', async () => {
  mocks.audits.mockResolvedValue([]);
  render(<FinalResultsDashboard />);
  expect(await screen.findByText('A · Which audit method finds problems?')).toBeInTheDocument();
  expect(await screen.findByText(/No completed audits are available yet/)).toBeInTheDocument();
});
