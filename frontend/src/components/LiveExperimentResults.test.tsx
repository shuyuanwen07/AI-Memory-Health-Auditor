import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { LiveExperimentResults } from './LiveExperimentResults';

const mocks = vi.hoisted(() => ({ experimentGroups: vi.fn(), experimentResults: vi.fn() }));
vi.mock('../services/api', () => ({api:mocks}));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('refreshes completed groups and compares only selected experiment conditions', async () => {
  const group = (id:string, status='COMPLETED') => ({experiment_id:id, label:id, status, created_at:'2026-10-30T01:00:00Z'});
  mocks.experimentGroups.mockResolvedValueOnce([group('old'),group('unfinished','RUNNING')]).mockResolvedValue([group('new'),group('old')]);
  mocks.experimentResults.mockImplementation(async (id:string) => ({conditions:[{condition_id:id,label:id,model:'rule-based-target-ai',memory_strategy:'weak_first_hit',overall_mean:50,tests_passed:1,tests_total:2,completed_runs:1,planned_runs:1,dimensions:[{uncertain_count:1}]}]}));
  render(<LiveExperimentResults />);
  expect(await screen.findByText('1/2 decided passed · 1/1 runs completed · 1 uncertain')).toBeInTheDocument();
  expect(screen.queryByRole('option',{name:/unfinished/})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Refresh experiments'}));
  expect(await screen.findByRole('option',{name:/new/})).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Experiment'),{target:{value:'new'}});
  await waitFor(() => expect(mocks.experimentResults).toHaveBeenCalledWith('new'));
  expect(await screen.findByText(/new · First-match retrieval/)).toBeInTheDocument();
});
