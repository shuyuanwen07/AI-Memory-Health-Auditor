import { selectedUILabel } from '../components/ui/testHelpers';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useNavigate } from 'react-router-dom';
import { AuditComparisonPage } from './AuditComparison';
const mocks = vi.hoisted(() => ({audits:vi.fn(),compareAudits:vi.fn()}));
vi.mock('../services/api', () => ({api:mocks}));
const run = (id:string) => ({run_id:id,status:'COMPLETED',model:'Qwen',memory_strategy:'scope_aware',created_at:'2026-10-08T00:00:00Z'});
const result = (score:number) => ({overall_score:score,tests_passed:score/25,tests_total:4,dimensions:[{dimension:'freshness',percentage:score,passed:score/25,total:4}]});
const pair = (id:string,outcome:string) => ({suite_test_id:id,prompt:`Question ${id}`,dimension:'freshness',outcome,expected_behavior:'PostgreSQL',before:{passed:false,response_text:'MySQL',reason:'Old value'},after:{passed:true,response_text:'PostgreSQL',reason:'Current value'}});
const data = {before:{run:run('BEFORE'),result:result(25)},after:{run:run('AFTER'),result:result(75)},warnings:[],setting_differences:[],counts:{fixed:2,regressed:0,still_failed:1,still_passed:1},paired_delta_percentage_points:50,unpaired_before:0,unpaired_after:0,paired_tests:[pair('1','fixed'),pair('2','still_failed')]};
beforeEach(() => {mocks.audits.mockResolvedValue([run('BEFORE'),run('AFTER')]);mocks.compareAudits.mockResolvedValue(data);});

test('shows before/after scores, paired delta, and repaired question evidence', async () => {
  render(<MemoryRouter initialEntries={['/compare?before=BEFORE&after=AFTER']}><AuditComparisonPage /></MemoryRouter>);
  expect((await screen.findAllByText('+50.0 pp')).length).toBeGreaterThan(0);
  expect(screen.getAllByText('25.0%').length).toBeGreaterThan(0);
  await userEvent.click(screen.getByRole('button',{name:'2 Fixed'}));
  expect(screen.getByText(/Question 1/)).toBeTruthy();
  expect(screen.queryByText(/Question 2/)).toBeNull();
  expect(screen.getByText('MySQL')).toBeTruthy();
  expect(screen.getAllByText('PostgreSQL').length).toBeGreaterThan(0);
});

test('warns about incomparable runs and does not invent a paired improvement', async () => {
  mocks.compareAudits.mockResolvedValue({...data, warnings:['No identical frozen questions can be paired.'],paired_delta_percentage_points:null,paired_tests:[]});
  render(<MemoryRouter initialEntries={['/compare?before=BEFORE&after=AFTER']}><AuditComparisonPage /></MemoryRouter>);
  expect(await screen.findByText('No identical frozen questions can be paired.')).toBeTruthy();
  expect(screen.getAllByText('Unmeasured').length).toBeGreaterThan(0);
  expect(screen.getByRole('region', { name: 'Comparison takeaway' }).classList.contains('neutral')).toBe(true);
});

test('explains an empty outcome filter and can show all questions again', async () => {
  render(<MemoryRouter initialEntries={['/compare?before=BEFORE&after=AFTER']}><AuditComparisonPage /></MemoryRouter>);
  await screen.findByRole('button', { name: '0 Regressed' });
  await userEvent.click(screen.getByRole('button', { name: '0 Regressed' }));
  expect(screen.getByText(/No shared questions are/)).toBeTruthy();
  await userEvent.click(screen.getByRole('button', { name: 'Show all shared questions' }));
  expect(screen.getByText(/Question 1/)).toBeTruthy();
});

test('searches saved audits without replacing the selected comparison', async () => {
  mocks.audits.mockResolvedValue([run('BEFORE'), run('AFTER'), { ...run('OTHER'), model: 'Different model' }]);
  render(<MemoryRouter initialEntries={['/compare?before=BEFORE&after=AFTER']}><AuditComparisonPage /></MemoryRouter>);
  await screen.findByText('2 answers improved');
  await userEvent.type(screen.getByRole('textbox', { name: 'Find saved audits' }), 'Different');
  expect(screen.getByText(/1 matching audits/)).toBeTruthy();
  expect(selectedUILabel('Before improvement')).toContain('Audit 2');
  expect(selectedUILabel('After improvement')).toContain('Audit 1');
  await userEvent.click(screen.getByRole('button', { name: 'Swap before & after' }));
  expect(selectedUILabel('Before improvement')).toContain('Audit 1');
});

function ComparisonBackButton() { const navigate = useNavigate(); return <button onClick={() => navigate(-1)}>Back to previous comparison</button>; }

test('restores comparison selectors when navigating back in browser history', async () => {
  render(<MemoryRouter initialEntries={['/compare?before=BEFORE&after=AFTER', '/compare?before=AFTER&after=BEFORE']} initialIndex={1}><ComparisonBackButton /><AuditComparisonPage /></MemoryRouter>);
  await screen.findByText('2 answers improved');
  expect(selectedUILabel('Before improvement')).toContain('Audit 1');
  await userEvent.click(screen.getByRole('button', { name: 'Back to previous comparison' }));
  expect(selectedUILabel('Before improvement')).toContain('Audit 2');
  expect(selectedUILabel('After improvement')).toContain('Audit 1');
});

test('opens a shareable presentation link and restores controls when exiting', async () => {
  render(<MemoryRouter initialEntries={['/compare?before=BEFORE&after=AFTER&view=presentation']}><AuditComparisonPage /></MemoryRouter>);
  await screen.findByText('2 answers improved');
  expect(screen.getByRole('button', { name: 'Exit presentation view' }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.queryByRole('textbox', { name: 'Find saved audits' })).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'Exit presentation view' }));
  expect(screen.getByRole('textbox', { name: 'Find saved audits' })).toBeTruthy();
  expect(selectedUILabel('Before improvement')).toContain('Audit 2');
});


test('keeps pending judgments visible in presentation cards and the main takeaway', async () => {
  mocks.compareAudits.mockResolvedValue({...data, after:{...data.after, result:{...data.after.result,uncertain_count:1}}});
  render(<MemoryRouter initialEntries={['/compare?before=BEFORE&after=AFTER&view=presentation']}><AuditComparisonPage /></MemoryRouter>);
  expect(await screen.findByText(/Awaiting review: before 0, after 1/)).toBeTruthy();
  expect(screen.getByText(/1 answer awaiting review/)).toBeTruthy();
  expect(screen.getByText('3 / 4 decided tests passed')).toBeTruthy();
});

test('keeps changed assessment evidence visible without claiming improvement', async () => {
  mocks.compareAudits.mockResolvedValue({...data, counts:{fixed:0,regressed:0,still_failed:0,still_passed:0}, paired_tests:[],paired_delta_percentage_points:null,
    excluded_assessments:[{prompt:'Where do I live?', dimension:'accuracy',before_passed:false,after_passed:true,before_response:'Dubbo',after_response:'Dubbo',reason:'Assessment rule versions differ.'}]});
  render(<MemoryRouter initialEntries={['/compare?before=BEFORE&after=AFTER&view=presentation']}><AuditComparisonPage /></MemoryRouter>);
  expect(await screen.findByText('Assessment standards changed')).toBeTruthy();
  expect(screen.queryByText('2 answers improved')).toBeNull();
  expect(screen.getByText('A direct improvement comparison is not available')).toBeTruthy();
  await userEvent.click(screen.getByText('Where do I live?'));
  expect(screen.getAllByText(/Dubbo/)).toHaveLength(2);
});


test('exact dimension changes use canonical paired answers, not different full-suite denominators', async () => {
  const { before, after } = data;
  mocks.compareAudits.mockResolvedValue({...data, before:{...before,result:{...before.result,dimensions:[{dimension:'accuracy',passed:4,total:10,percentage:40}]}},after:{...after,result:{...after.result,dimensions:[{dimension:'accuracy',passed:9,total:10,percentage:90}]}},paired_tests:[]});
  render(<MemoryRouter initialEntries={['/compare?before=BEFORE&after=AFTER']}><AuditComparisonPage /></MemoryRouter>);
  await screen.findByText('A direct improvement comparison is not available');
  await userEvent.click(screen.getByText('View exact dimension scores'));
  expect(screen.getByRole('row',{name:/Accuracy.*Unmeasured/})).toHaveTextContent('Unmeasured');
});
