import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TestSuiteReview, hasDuplicateQuestions } from './TestSuiteReview';
import type { TestCase } from '../types/domain';

test('source-scope warning is readable and does not claim sources were checked', () => {
  const test: TestCase = {test_id:'scope', run_id:'run', dimension:'accuracy', prompt:'Which fact?',
    expected_behavior:'Recorded fact', supporting_memory_ids:['M1'], generator_version:'preview',
    quality_status:'pending', grounding_status:'grounded',
    validation_notes:'source-scope-review-v1: Original source messages are missing; review them.'};
  render(<TestSuiteReview tests={[test]} busy={false} onReview={vi.fn()} onRegenerate={vi.fn()} />);
  expect(screen.getByText(/Source evidence needs review/)).toHaveTextContent('Original source messages are missing');
  expect(screen.queryByText(/source-scope-review-v1/)).toBeNull();
});

test('grounding metadata does not claim that source meaning was checked', () => {
  const test: TestCase = {test_id:'grounded', run_id:'run', dimension:'accuracy', prompt:'Which fact?',
    expected_behavior:'Recorded fact', supporting_memory_ids:['M1'], generator_version:'preview',
    quality_status:'accepted', grounding_status:'grounded', validation_notes:'Evidence identifiers available.'};
  render(<TestSuiteReview tests={[test]} busy={false} onReview={vi.fn()} onRegenerate={vi.fn()} />);
  expect(screen.getByText(/Evidence references recorded/)).toBeInTheDocument();
  expect(screen.queryByText(/Source evidence checked/)).toBeNull();
});

test('keeps unreviewed legacy questions pending and updates feedback after acceptance', async () => {
  const test: TestCase = { test_id: 'test', run_id: 'run', dimension: 'accuracy', prompt: 'Which database is used?', expected_behavior: 'PostgreSQL', supporting_memory_ids: [], generator_version: 'preview' };
  const review = vi.fn();
  const { rerender } = render(<TestSuiteReview tests={[test]} busy={false} onReview={review} onRegenerate={vi.fn()} />);
  expect(screen.getByText('1 question still needs review')).not.toBeNull();
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('0');
  await userEvent.click(screen.getByRole('button', { name: 'Accept' }));
  expect(review).toHaveBeenCalledWith(test, 'accepted');
  rerender(<TestSuiteReview tests={[{ ...test, quality_status: 'accepted' }]} busy={false} onReview={review} onRegenerate={vi.fn()} />);
  expect(screen.getByText('Quality decisions complete')).not.toBeNull();
  expect(screen.getByRole('status').textContent).toContain('ready for testing');
  expect((screen.getByRole('button', { name: '✓ Accepted' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('1');
  rerender(<TestSuiteReview tests={[{ ...test, quality_status: 'rejected' }]} busy={false} onReview={review} onRegenerate={vi.fn()} />);
  expect(screen.queryByText('Quality decisions complete')).toBeNull();
  expect(screen.getByText('1 rejected question blocks execution')).toBeTruthy();
  expect((screen.getByRole('button', { name: 'Accept' }) as HTMLButtonElement).disabled).toBe(false);
});

test('accepts every question that has not yet been accepted with one action', async () => {
  const pending: TestCase = { test_id: 'pending', run_id: 'run', dimension: 'accuracy', prompt: 'Which database is used?', expected_behavior: 'PostgreSQL', supporting_memory_ids: [], generator_version: 'preview', quality_status: 'pending' };
  const rejected: TestCase = { ...pending, test_id: 'rejected', quality_status: 'rejected' };
  const accepted: TestCase = { ...pending, test_id: 'accepted', quality_status: 'accepted' };
  const acceptAll = vi.fn();
  render(<TestSuiteReview tests={[pending, rejected, accepted]} busy={false} onReview={vi.fn()} onRegenerate={vi.fn()} onAcceptAll={acceptAll} />);

  await userEvent.click(screen.getByRole('button', { name: 'Accept all questions' }));

  expect(acceptAll).toHaveBeenCalledWith([pending, rejected]);
});

test('flags identical questions with different answers instead of declaring the suite ready', () => {
  const test: TestCase = { test_id: 'one', run_id: 'run', dimension: 'accuracy', prompt: 'Which task?', expected_behavior: 'First policy', supporting_memory_ids: [], generator_version: 'preview', quality_status: 'accepted' };
  render(<TestSuiteReview tests={[test, {...test, test_id: 'two', prompt: 'Which task!', expected_behavior: 'Second policy'}]} busy={false} onReview={vi.fn()} onRegenerate={vi.fn()} />);
  expect(screen.getByRole('alert').textContent).toContain('same wording');
  expect(screen.queryByText('Quality decisions complete')).toBeNull();
  expect(screen.getByText('Duplicate questions need repair')).toBeTruthy();
});

test('shows formal reference questions read-only without reject or regenerate controls', () => {
  const test: TestCase = { test_id: 'one', run_id: 'run', dimension: 'accuracy', prompt: 'Which fact?', expected_behavior: 'Reviewed value', supporting_memory_ids: [], generator_version: 'synthetic-formal-matrix-v3', quality_status: 'accepted' };
  render(<TestSuiteReview tests={[test]} busy={false} onReview={vi.fn()} onRegenerate={vi.fn()} />);
  expect(screen.getByRole('heading', {name: 'Frozen reference questions'})).toBeTruthy();
  expect(screen.getByText(/review and import a new dataset version/)).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Reject'})).toBeNull();
  expect(screen.queryByRole('button', {name: 'Regenerate'})).toBeNull();
  expect(screen.queryByRole('button', {name: '✓ Accepted'})).toBeNull();
});


test('preserves Chinese questions and recognises Unicode-width duplicates',()=>{
  const test:TestCase={test_id:'one',run_id:'run',dimension:'accuracy',prompt:'用户住在哪里？',expected_behavior:'Recorded city.',supporting_memory_ids:[],generator_version:'preview',quality_status:'accepted'};
  expect(hasDuplicateQuestions([test,{...test,test_id:'two',prompt:'项目使用什么数据库？'}])).toBe(false);
  expect(hasDuplicateQuestions([test,{...test,test_id:'two',prompt:'用户住在哪里 ?'}])).toBe(true);
  expect(hasDuplicateQuestions([{...test,prompt:'ＡＢＣ？'},{...test,test_id:'two',prompt:'abc!'}])).toBe(true);
});


test('coverage follows accepted decisions and keeps unmeasured abilities visible before execution',()=>{
  const base:TestCase={test_id:'a',run_id:'run',dimension:'accuracy',prompt:'Which database?',expected_behavior:'Recorded value',supporting_memory_ids:[],generator_version:'preview',quality_status:'accepted'};
  const tests:TestCase[]=[base,{...base,test_id:'f',dimension:'freshness',prompt:'Where now?'},{...base,test_id:'c',dimension:'conflict_resolution',prompt:'Which conflicting rule?'},{...base,test_id:'u',dimension:'appropriate_use',prompt:'Which task requirement?',quality_status:'pending'}];
  const props={busy:false,onReview:vi.fn(),onRegenerate:vi.fn()};
  const view=render(<TestSuiteReview tests={tests} {...props}/>);
  let coverage=within(screen.getByRole('region',{name:'Accepted question coverage'}));
  expect(coverage.getByText(/3 of 4 abilities have accepted questions/)).toBeInTheDocument();
  expect(coverage.getByRole('img',{name:'Appropriate Use: 0 accepted questions'})).toBeInTheDocument();
  expect(coverage.getByText(/No accepted questions for: Appropriate Use/)).toBeInTheDocument();
  view.rerender(<TestSuiteReview tests={tests.map(test=>({...test,quality_status:'accepted'}))} {...props}/>);
  coverage=within(screen.getByRole('region',{name:'Accepted question coverage'}));
  expect(coverage.getByText(/4 of 4 abilities have accepted questions/)).toBeInTheDocument();
  expect(coverage.queryByText(/No accepted questions for:/)).toBeNull();
  view.rerender(<TestSuiteReview tests={tests.map(test=>({...test,quality_status:test.test_id==='u'?'rejected':'accepted'}))} {...props}/>);
  expect(screen.getByText(/No accepted questions for: Appropriate Use/)).toBeInTheDocument();
});


test('records a specific rejection reason without accepting a rejected question',async()=>{
 const candidate:TestCase={test_id:'bad',run_id:'run',dimension:'conflict_resolution',prompt:'Which language is generally preferred?',expected_behavior:'Project override.',supporting_memory_ids:[],generator_version:'preview',quality_status:'rejected'};
 const review=vi.fn();const user=userEvent.setup();render(<TestSuiteReview tests={[candidate]} busy={false} onReview={review} onRegenerate={vi.fn()}/>);
 const note='General preference alone does not ask about the project-specific override.';
 await user.type(screen.getByLabelText('Review reason for question 1'),note);
 await user.click(screen.getByRole('button',{name:'Save rejection reason'}));
 expect(review).toHaveBeenCalledWith(candidate,'rejected',note);
 expect(screen.getByText('1 rejected question blocks execution')).toBeTruthy();
});

test('keeps Experiment A human validity separate and requires a researcher pseudonym',async()=>{
 const test:TestCase={test_id:'a-human',run_id:'run',dimension:'accuracy',prompt:'Which database?',expected_behavior:'PostgreSQL',supporting_memory_ids:[],generator_version:'fixed-template-v2',quality_status:'accepted',grounding_status:'grounded'};
 const reviewHuman=vi.fn();const user=userEvent.setup();
 render(<TestSuiteReview tests={[test]} busy={false} onReview={vi.fn()} onRegenerate={vi.fn()} onHumanValidityReview={reviewHuman}/>);
 expect(screen.getByText(/Automated grounding check:/).closest('p')).toHaveTextContent('Grounded');
 expect(screen.getByText('Human validity not yet reviewed.')).toBeInTheDocument();
 const confirm=screen.getByRole('button',{name:'Confirm valid'});
 expect(confirm).toBeDisabled();
 await user.type(screen.getByRole('textbox',{name:'Human validity reviewer pseudonym'}),'Researcher R');
 await user.type(screen.getByRole('textbox',{name:'Human validity note for question 1'}),'Prompt matches the intended fact.');
 await user.click(confirm);
 expect(reviewHuman).toHaveBeenCalledWith(test,'accepted','Researcher R','Prompt matches the intended fact.');
});


test('hides embedded audit identifiers in primary question and expected-answer text',()=>{
  const test:TestCase={test_id:'T-INTERNAL',run_id:'RUN-INTERNAL',dimension:'accuracy',
    prompt:'What fact is linked to M001?',expected_behavior:'Recall Python from MABCDEF0123456789ABCDEF0123456789.',
    supporting_memory_ids:['M001'],generator_version:'fixture',quality_status:'pending'};
  render(<TestSuiteReview tests={[test]} busy={false} onReview={vi.fn()} onRegenerate={vi.fn()}/>);
  expect(screen.getByText('What fact is linked to saved record?')).toBeInTheDocument();
  expect(screen.getByText('Recall Python from saved record.')).toBeInTheDocument();
  expect(screen.queryByText(/MABCDEF|M001/)).toBeNull();
  expect(test.expected_behavior).toContain('MABCDEF');
});
