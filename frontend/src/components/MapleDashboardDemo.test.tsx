import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { MapleDashboardDemo } from './MapleDashboardDemo';

const mocks = vi.hoisted(() => ({compareAudits: vi.fn(), audits: vi.fn().mockResolvedValue([])}));
vi.mock('../services/api', () => ({api: mocks}));

it('shows the saved paired question and its actual before and after answers', async () => {
  mocks.compareAudits.mockResolvedValue({
    before: {result:{tests_passed:3,tests_total:4}}, after: {result:{tests_passed:4,tests_total:4}},
    warnings: [], counts:{fixed:1,regressed:0}, paired_tests:[{dimension:'conflict_resolution',outcome:'fixed',prompt:'How should the conflict be handled?',before:{passed:false,response_text:'No venue in memory.'},after:{passed:true,response_text:'**Both venues** conflict.'}}],
  });
  render(<MapleDashboardDemo />);
  expect(await screen.findByText('No venue in memory.')).toBeInTheDocument();
  expect(screen.getByText('Both venues conflict.')).toBeInTheDocument();
  expect(screen.getByLabelText('Automated assessment comparison')).toHaveTextContent('3/4');
  expect(screen.getByLabelText('Automated assessment comparison')).toHaveTextContent('4/4');
  expect(mocks.compareAudits).toHaveBeenCalledWith('RUN1FDDFC16B9F0406E9AD4B1CE6945E081','RUN22924F327B0F4D00AB920E69C55542CF');
});

it('loads the comparison for a newly selected completed audit', async () => {
  mocks.audits.mockResolvedValue([{run_id:'OTHER', status:'COMPLETED', model:'rules', created_at:'2026-10-27T00:00:00Z'}]);
  mocks.compareAudits.mockResolvedValue({before:{result:{tests_passed:1,tests_total:2}},after:{result:{tests_passed:2,tests_total:2}},warnings:[],counts:{fixed:1,regressed:0},paired_tests:[]});
  render(<MapleDashboardDemo />);
  const selector = await screen.findByLabelText('Before audit');
  await screen.findAllByRole('option', {name:/rules/});
  fireEvent.change(selector, {target:{value:'OTHER'}});
  await waitFor(() => expect(mocks.compareAudits).toHaveBeenCalledWith('OTHER','RUN22924F327B0F4D00AB920E69C55542CF'));
  expect(await screen.findByLabelText('Automated assessment comparison')).toHaveTextContent('1/2');
});
