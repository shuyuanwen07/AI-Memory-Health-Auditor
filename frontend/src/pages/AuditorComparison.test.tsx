import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuditorComparisonPage } from './AuditorComparison';

const mocks = vi.hoisted(() => ({ experimentResults: vi.fn(), experimentGroups: vi.fn() }));
vi.mock('../services/api', () => ({ api: mocks }));

function report(id: string, pipeline: string, methods: string[], identity = 'comparison-v1') {
  return {
    experiment: { experiment_id: id, conversation_id: 'C1', created_at: '2026-10-11T00:00:00Z',
      test_suite_configuration: { pipeline_provider: pipeline, auditor_comparison_id: identity } },
    runs: methods.map((method, index) => ({ run: { run_id: `${id}-${index}`, model: 'Qwen', memory_strategy: 'scope_aware', reproducibility: { auditor_method: method } },
      result: { run_id: `${id}-${index}`, overall_score: 50, tests_passed: 1, tests_total: 2, uncertain_count: 1,
        dimensions: ['accuracy', 'freshness', 'conflict_resolution', 'appropriate_use'].map(dimension => ({ dimension, percentage: dimension === 'accuracy' ? 50 : null, passed: dimension === 'accuracy' ? 1 : 0, total: dimension === 'accuracy' ? 2 : 0 })), failures: [] } })),
  };
}

beforeEach(() => { vi.resetAllMocks(); });

test('restores three methods from saved groups and distinguishes score charts from validity', async () => {
  mocks.experimentResults.mockImplementation(async id => id === 'rules' ? report(id, 'rule_based', ['rules']) : report(id, 'openrouter', ['model_generation', 'hybrid']));
  render(<MemoryRouter initialEntries={['/audit-methods?groups=rules,model']}><AuditorComparisonPage /></MemoryRouter>);
  expect(await screen.findByText('3 of 3 planned runs completed.')).toBeTruthy();
  expect(await screen.findByRole('heading', { name: 'Dimension Comparison' }, { timeout: 15000 })).toBeTruthy();
  expect(screen.getAllByText(/Model tests \+ hybrid review/).length).toBeGreaterThan(0);
  expect(screen.getByText(/not auditor accuracy/)).toBeTruthy();
  expect(screen.getByText('3 answers await review')).toBeTruthy();
});

test('rejects unrelated groups instead of presenting an invalid comparison', async () => {
  mocks.experimentResults.mockImplementation(async id => report(id, id === 'rules' ? 'rule_based' : 'openrouter', ['rules'], id));
  render(<MemoryRouter initialEntries={['/audit-methods?groups=rules,model']}><AuditorComparisonPage /></MemoryRouter>);
  expect(await screen.findByText('These test groups do not belong to the same saved audit-method comparison.')).toBeTruthy();
  expect(screen.queryByRole('heading', { name: 'Dimension Comparison' })).toBeNull();
});

test('index shows saved comparisons without exposing internal identifiers as labels', async () => {
  mocks.experimentGroups.mockResolvedValue([report('rules', 'rule_based', []).experiment, report('model', 'openrouter', []).experiment]);
  render(<MemoryRouter initialEntries={['/audit-methods']}><AuditorComparisonPage /></MemoryRouter>);
  expect(await screen.findByRole('link', { name: 'Open three-method results' })).toHaveAttribute('href', '/audit-methods?groups=rules%2Cmodel');
});


test('does not treat same-named configurations without verified grouping as repeated samples',async()=>{
  mocks.experimentResults.mockImplementation(async id => id==='rules'?report(id,'rule_based',['rules']):report(id,'openrouter',['hybrid','hybrid']));
  render(<MemoryRouter initialEntries={['/audit-methods?groups=rules,model']}><AuditorComparisonPage/></MemoryRouter>);
  await screen.findByText('3 of 3 planned runs completed.');
  expect(await screen.findByRole('heading',{name: 'Dimension Comparison'},{timeout:15000})).toBeInTheDocument();
  expect(screen.getAllByText(/Setting 3/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Setting 2/).length).toBeGreaterThan(0);
  expect(screen.queryByText(/unverified-run:/)).toBeNull();
});

test('verified repeated runs retain one condition and measured variation',async()=>{
  mocks.experimentResults.mockImplementation(async id=>{
    const value=report(id,id==='rules'?'rule_based':'openrouter',id==='rules'?['rules']:['hybrid','hybrid']);
    return {...value,conditions:[{condition_id:`verified-${id}`,run_ids:value.runs.map(item=>item.run.run_id)}]};
  });
  render(<MemoryRouter initialEntries={['/audit-methods?groups=rules,model']}><AuditorComparisonPage/></MemoryRouter>);
  const figure=await screen.findByRole('figure',{name:/Tested ability average comparison/},{timeout:15000});
  expect(figure).toHaveAccessibleName(/± 0%/);
  expect(screen.queryByText(/Setting [23]/)).toBeNull();
  expect(screen.queryByText(/verified-model/)).toBeNull();
});


test('diagnostic children do not make their original comparison appear incomplete', async () => {
  const child = { ...report('follow-up', 'openrouter', []).experiment, test_suite_metadata: { study_role: 'adaptive_follow_up' } };
  mocks.experimentGroups.mockResolvedValue([child, report('rules', 'rule_based', []).experiment, report('model', 'openrouter', []).experiment]);
  render(<MemoryRouter initialEntries={['/audit-methods']}><AuditorComparisonPage /></MemoryRouter>);
  expect(await screen.findByRole('link', { name: 'Open three-method results' })).toHaveAttribute('href', '/audit-methods?groups=rules%2Cmodel');
  expect(screen.queryByText(/Preparation is incomplete/)).toBeNull();
});

test('a diagnostic child cannot be substituted for a primary comparison group', async () => {
  mocks.experimentResults.mockImplementation(async id => {
    const value = report(id, id === 'rules' ? 'rule_based' : 'openrouter', ['rules']);
    return id === 'child' ? { ...value, experiment: { ...value.experiment, test_suite_metadata: { study_role: 'repair_comparison' } } } : value;
  });
  render(<MemoryRouter initialEntries={['/audit-methods?groups=rules,child']}><AuditorComparisonPage /></MemoryRouter>);
  expect(await screen.findByText('These test groups do not belong to the same saved audit-method comparison.')).toBeTruthy();
});
