import type { ReactNode } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import App from '../App';
import { Experiments } from './StaticPages';

const mocks = vi.hoisted(() => ({
  experimentGroups: vi.fn(), experimentResults: vi.fn(), results: vi.fn(), getAudit: vi.fn(),
  retryPlan: vi.fn(), retry: vi.fn(),
}));
vi.mock('../services/api', () => ({ api: mocks }));
vi.mock('../components/ResearchValidation', () => ({ ResearchValidation: () => <p>Research tools</p> }));
vi.mock('../components/TargetMemoryTrace', () => ({ TargetMemoryTrace: () => null }));
vi.mock('../components/ResultDashboard', () => ({ ResultDashboard: ({result}: {result: {run_id: string}}) => <p>Saved report {result.run_id}</p> }));
vi.mock('../components/AccessBoundary', () => ({ AccessBoundary: ({children}: {children: (signOut: null, signingOut: boolean) => ReactNode}) => children(null, false) }));

const group = (experiment_id: string, label: string) => ({
  experiment_id, conversation_id: 'C-DEMO', label, status: 'COMPLETED',
  test_suite_configuration: {}, test_suite_metadata: {test_count: 8}, created_at: '2026-10-23T00:00:00Z',
});
const demo = group('DEMO', 'Saved presentation demonstration');
const old = Array.from({length: 5}, (_, i) => group(`OLD-${i}`, `Scenario ${i + 1}`));
const groups = [...old, demo];

beforeEach(() => {
  vi.clearAllMocks();
  mocks.experimentGroups.mockResolvedValue(groups);
  mocks.experimentResults.mockImplementation(async (id: string) => ({
    experiment: groups.find(item => item.experiment_id === id), runs: [], conditions: [], paired_comparisons: [],
  }));
  mocks.getAudit.mockResolvedValue({run_id: 'RUN-DEMO', provider: 'openrouter', model: 'openai/gpt-6-luna',
    memory_strategy: 'strong_rule_based', pipeline_provider: 'rule_based', evaluator_provider: 'rule_based', reproducibility: {}});
  mocks.results.mockResolvedValue({run_id: 'RUN-DEMO'});
});

function renderGroup(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/experiments/:experimentId" element={<Experiments/>}/>
    <Route path="/experiments" element={<Experiments/>}/>
  </Routes></MemoryRouter>);
}

test('direct saved group link loads only its analytics even when outside the first list page', async () => {
  renderGroup('/experiments/DEMO');
  expect(await screen.findByRole('heading', {name: demo.label})).toBeInTheDocument();
  await waitFor(() => expect(mocks.experimentResults).toHaveBeenCalledTimes(1));
  expect(mocks.experimentResults).toHaveBeenCalledWith('DEMO');
  expect(screen.queryByRole('heading', {name: 'Scenario 1'})).not.toBeInTheDocument();
  expect(screen.queryByRole('navigation', {name: 'Experiment pages'})).not.toBeInTheDocument();
  expect(screen.getByRole('link', {name: 'All experiment groups'})).toHaveAttribute('href', '/experiments');
});

test('unknown group is explicit and never loads unrelated analytics', async () => {
  renderGroup('/experiments/UNKNOWN');
  expect(await screen.findByText('Experiment group not found')).toBeInTheDocument();
  expect(screen.getByRole('link', {name: 'All experiment groups'})).toHaveAttribute('href', '/experiments');
  expect(mocks.experimentResults).not.toHaveBeenCalled();
  expect(screen.queryByText('No experiments yet')).not.toBeInTheDocument();
});

test('all-groups route retains its original three-group page and next-page loading', async () => {
  renderGroup('/experiments');
  expect(await screen.findByRole('heading', {name: 'Scenario 1'})).toBeInTheDocument();
  await waitFor(() => expect(mocks.experimentResults).toHaveBeenCalledTimes(3));
  expect(screen.getByRole('navigation', {name: 'Experiment pages'})).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', {name: 'Next experiments'}));
  expect(await screen.findByRole('heading', {name: demo.label})).toBeInTheDocument();
  await waitFor(() => expect(mocks.experimentResults).toHaveBeenCalledTimes(6));
});

test('navigation to another saved group cannot show a delayed previous result', async () => {
  let finish!: (value: unknown) => void;
  mocks.experimentResults.mockImplementation((id: string) => id === 'OLD-0'
    ? new Promise(resolve => { finish = resolve; })
    : Promise.resolve({experiment: demo, runs: [], conditions: [], paired_comparisons: []}));
  render(<MemoryRouter initialEntries={['/experiments/OLD-0']}><Link to="/experiments/DEMO">Open demo group</Link>
    <Routes><Route path="/experiments/:experimentId" element={<Experiments/>}/></Routes></MemoryRouter>);
  await waitFor(() => expect(mocks.experimentResults).toHaveBeenCalledWith('OLD-0'));
  await userEvent.click(screen.getByRole('link', {name: 'Open demo group'}));
  expect(await screen.findByRole('heading', {name: demo.label})).toBeInTheDocument();
  await act(async () => finish({experiment: old[0], runs: [], conditions: [], paired_comparisons: []}));
  expect(screen.queryByRole('heading', {name: old[0].label})).not.toBeInTheDocument();
  expect(screen.getByRole('heading', {name: demo.label})).toBeInTheDocument();
});

test('application registers the existing saved experiment URL', async () => {
  render(<MemoryRouter initialEntries={['/experiments/DEMO']}><App/></MemoryRouter>);
  expect(await screen.findByRole('heading', {name: demo.label})).toBeInTheDocument();
  expect(screen.queryByRole('heading', {name: 'Page not found'})).not.toBeInTheDocument();
});

test('application accepts the recorded audit results URL as the saved report alias', async () => {
  render(<MemoryRouter initialEntries={['/audits/RUN-DEMO/results']}><App/></MemoryRouter>);
  expect(await screen.findByText('Saved report RUN-DEMO')).toBeInTheDocument();
  expect(mocks.getAudit).toHaveBeenCalledWith('RUN-DEMO');
  expect(mocks.results).toHaveBeenCalledWith('RUN-DEMO');
  expect(screen.queryByRole('heading', {name: 'Page not found'})).not.toBeInTheDocument();
});
