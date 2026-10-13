import {render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {SavedAnswerReassessment} from './SavedAnswerReassessment';
const mocks=vi.hoisted(()=>({prepareReassessment:vi.fn(),evaluate:vi.fn(),retry:vi.fn(),getAudit:vi.fn()}));
vi.mock('../services/api',()=>({api:mocks}));
beforeEach(()=>{vi.clearAllMocks();mocks.prepareReassessment.mockResolvedValue({run_id:'NEW',status:'TESTS_EXECUTED'});mocks.evaluate.mockResolvedValue([]);mocks.getAudit.mockResolvedValue({run_id:'NEW',status:'COMPLETED'});});
test('prepares a separate score and links to it without calling the target',async()=>{
  render(<SavedAnswerReassessment runId="OLD" sourceId="ORIGINAL"/>);
  await userEvent.click(screen.getByRole('button',{name:'Reassess saved answers'}));
  expect(await screen.findByRole('link',{name:'View reassessment result'})).toHaveAttribute('href','/audits/NEW');
  expect(mocks.prepareReassessment).toHaveBeenCalledWith('OLD');
  expect(mocks.evaluate).toHaveBeenCalledWith('NEW');
  expect(screen.getByRole('link',{name:'View the original assessment'})).toHaveAttribute('href','/audits/ORIGINAL');
});
test('existing completed reassessment is reopened without another assessment call',async()=>{
  mocks.prepareReassessment.mockResolvedValue({run_id:'NEW',status:'COMPLETED'});
  render(<SavedAnswerReassessment runId="OLD"/>);
  await userEvent.click(screen.getByRole('button',{name:'Reassess saved answers'}));
  await screen.findByRole('link',{name:'View reassessment result'});
  expect(mocks.evaluate).not.toHaveBeenCalled();
  expect(mocks.retry).not.toHaveBeenCalled();
});
test('failed assessment keeps a recovery action instead of showing a result as complete',async()=>{
  mocks.evaluate.mockRejectedValue(new Error('Review service unavailable.'));
  render(<SavedAnswerReassessment runId="OLD"/>);
  await userEvent.click(screen.getByRole('button',{name:'Reassess saved answers'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Review service unavailable.');
  expect(screen.getByRole('link',{name:'Open Audit History'})).toBeInTheDocument();
  expect(screen.queryByRole('link',{name:'View reassessment result'})).toBeNull();
});
