import { selectUIOption, selectedUILabel } from './ui/testHelpers';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EvaluationReview } from './EvaluationReview';

const apiMocks = vi.hoisted(() => ({
  auditSourceHistory: vi.fn(), evaluationReview: vi.fn(), blindEvaluationReview: vi.fn(), evaluationCalibration: vi.fn(), reviewEvaluation: vi.fn(),
}));
vi.mock('../services/api', () => ({ api: apiMocks }));

const item = {
  test: { test_id: 'T1', run_id: 'RUN1', dimension: 'freshness', prompt: 'Which database applies now?', expected_behavior: 'PostgreSQL', supporting_memory_ids: ['M1'], generator_version: 'v1' },
  response: { response_id: 'R1', test_id: 'T1', run_id: 'RUN1', response_text: 'MySQL', model: 'local', temperature: 0, created_at: '2026-01-01T00:00:00Z' },
  automated: { evaluation_id: 'E1', test_id: 'T1', response_id: 'R1', passed: false, failure_type: 'freshness', reason: 'Expected PostgreSQL.', evidence_memory_ids: ['M1'], evaluator: 'rule-based-v4' },
  human_reviews: [], human_review: null,
};

test.each([
  {names:['Reviewer A',' reviewer a '], count:undefined},
  {names:['Straße','STRASSE'], count:1},
])('does not enable adjudication for reviewer aliases', async ({names, count}) => {
  const reviews=names.map((reviewer_label,index)=>({review_id:`h${index}`,evaluation_id:'E1',human_passed:true,reviewer_label,review_role:'independent',based_on_review_ids:[],created_at:'2026-01-01T00:00:00Z',updated_at:'2026-01-01T00:00:00Z'}));
  apiMocks.evaluationReview.mockResolvedValue([{...item,human_reviews:reviews,independent_reviewer_count:count}]);
  const user=userEvent.setup(); render(<EvaluationReview runId="RUN1" exposedToAutomatedResults />);
  await user.click(screen.getByRole('button',{name:'Review Evaluations'}));
  await screen.findByText('Automated: Fail');
  await selectUIOption(user,'Evaluation review role','Adjudication');
  await user.click(screen.getByRole('button',{name:'Review Evaluations'}));
  await screen.findByText('Automated: Fail');
  await user.type(screen.getByRole('textbox',{name:'Reviewer pseudonym'}),'Final reviewer');
  expect(screen.getByRole('button',{name:'Adjudicate: Pass'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Adjudicate: Fail'})).toBeDisabled();
});

beforeEach(() => {
  apiMocks.auditSourceHistory.mockResolvedValue([]);
  apiMocks.evaluationReview.mockResolvedValue([item]);
  apiMocks.blindEvaluationReview.mockResolvedValue([{...item, test:{test_id:item.test.test_id,prompt:item.test.prompt,expected_behavior:item.test.expected_behavior}, response:{response_text:item.response.response_text}, automated:{evaluation_id:"E1"}}]);
  apiMocks.evaluationCalibration.mockResolvedValue({ human_reviewed_count: 0, agreement_percentage: null, failure_precision: null, failure_recall: null, failure_f1: null, independent_review_count: 0, independently_reviewed_evaluation_count: 0, independent_consensus_count: 0, independent_conflict_count: 0, independent_pair_kappa: null });
  apiMocks.reviewEvaluation.mockResolvedValue({});
});

test('keeps automated verdict and summaries hidden in independent blind review mode', async () => {
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" />);
  await user.click(screen.getByRole('button', { name: 'Review Evaluations' }));
  await waitFor(() => expect(screen.getByText('Blind independent label')).toBeTruthy());
  expect(screen.getByText('Reference behaviour:')).toBeTruthy();
  expect(screen.getByText(/PostgreSQL/, { selector: '.review-reference small' })).toBeTruthy();
  expect(screen.queryByText('Expected PostgreSQL.')).toBeNull();
  expect(screen.queryByText('Automated: Fail')).toBeNull();
  expect(screen.queryByText(/automated agreement/)).toBeNull();
  await selectUIOption(user, 'Evaluation review role', 'Reference label');
  await user.click(screen.getByRole('button', {name:'Review Evaluations'}));
  expect(await screen.findByText('Automated: Fail')).toBeTruthy();
  expect(screen.getByText('Expected PostgreSQL.')).toBeTruthy();
});

test('uses the reviewer-selected failure dimension rather than the automated class', async () => {
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" />);
  await user.click(screen.getByRole('button', { name: 'Review Evaluations' }));
  await waitFor(() => expect(screen.getByText('Blind independent label')).toBeTruthy());
  await user.type(screen.getByRole('textbox', {name:'Reviewer pseudonym'}), 'reviewer-A');
  await selectUIOption(user, 'Failure dimension 1', 'Appropriate Use');
  await user.click(screen.getByRole('button', { name: 'Record Fail label' }));
  await waitFor(() => expect(apiMocks.reviewEvaluation).toHaveBeenCalledWith('RUN1', 'E1', expect.objectContaining({ human_failure_type: 'appropriate_use', review_role: 'independent' })));
});

test('shows recorded judge requests only outside blind mode and leaves historical cost unknown', async () => {
  apiMocks.evaluationReview.mockResolvedValue([{...item, automated:{...item.automated, judge_execution:{request_attempts:2,failed_http_attempts:1,elapsed_ms:1200,reported_total_tokens:null}}}]);
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" />);
  await user.click(screen.getByRole('button', {name:'Review Evaluations'}));
  expect(await screen.findByText('Blind independent label')).toBeTruthy();
  expect(screen.queryByText(/Assessment requests:/)).toBeNull();
  await selectUIOption(user, 'Evaluation review role', 'Reference label');
  await user.click(screen.getByRole('button', {name:'Review Evaluations'}));
  expect(await screen.findByText(/Assessment requests: 2/)).toBeTruthy();
  expect(screen.getByText(/failed HTTP attempts: 1/).textContent).toContain('reported tokens: Unknown');
  apiMocks.evaluationReview.mockResolvedValue([{...item, automated:{...item.automated,evaluator:'llm-judge-openrouter-v4'}}]);
  await selectUIOption(user, 'Evaluation review role', 'Adjudication');
  await user.click(screen.getByRole('button', {name:'Review Evaluations'}));
  expect(await screen.findByText('Assessment request evidence was not recorded for this result. Costs remain unknown.')).toBeTruthy();
});

test('confirms a saved blind label without revealing the automated verdict', async () => {
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" />);
  await user.click(screen.getByRole('button', { name: 'Review Evaluations' }));
  await waitFor(() => expect(screen.getByText('Blind independent label')).toBeTruthy());
  await user.type(screen.getByRole('textbox', {name:'Reviewer pseudonym'}), 'reviewer-A');
  await selectUIOption(user, 'Failure dimension 1', 'Freshness');
  await user.click(screen.getByRole('button', { name: 'Record Fail label' }));
  expect((await screen.findByRole('status')).textContent).toContain('Your independent label was saved: Fail. It is recorded as calibration evidence.');
  expect(screen.queryByText('Automated: Fail')).toBeNull();
  expect(screen.getByText(/Saved for this reviewer in this session: 1 of 1/)).toBeTruthy();
  await user.clear(screen.getByRole('textbox', {name:'Reviewer pseudonym'}));
  await user.type(screen.getByRole('textbox', {name:'Reviewer pseudonym'}), 'reviewer-B');
  expect(screen.getByText(/Saved for this reviewer in this session: 0 of 1/)).toBeTruthy();
});

test('explains an empty review batch without inventing completed reviews', async () => {
  apiMocks.blindEvaluationReview.mockResolvedValueOnce([]);
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" independentOnly />);
  await user.click(screen.getByRole('button', {name: 'Review Evaluations'}));
  expect(await screen.findByText(/There are no assessed answers to review/)).toBeTruthy();
  expect(screen.queryByText(/Saved for this reviewer/)).toBeNull();
  expect(screen.queryByRole('button', {name: 'Record Pass label'})).toBeNull();
});

test('cannot collect an independent label on a report that exposed automated results', async () => {
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" exposedToAutomatedResults />);
  expect(screen.getByText('This report has shown the automated results.')).toBeTruthy();
  expect(screen.getByRole('link', {name: 'separate blind review page'})).toHaveAttribute('href', '/blind-review/RUN1');
  await user.click(screen.getByRole('button', {name: 'Review Evaluations'}));
  await screen.findByText('Automated: Fail');
  expect(apiMocks.blindEvaluationReview).not.toHaveBeenCalled();
  await user.type(screen.getByRole('textbox', {name: 'Reviewer pseudonym'}), 'report-reader');
  await user.click(screen.getByRole('button', {name: 'Record Pass label'}));
  await waitFor(() => expect(apiMocks.reviewEvaluation).toHaveBeenCalledWith('RUN1', 'E1', expect.objectContaining({review_role: 'reference'})));
  expect(screen.queryByText('Blind independent label')).toBeNull();
});

test('requires an explicit independent failure class without exposing the test dimension as a heading', async () => {
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" />);
  await user.click(screen.getByRole('button', { name: 'Review Evaluations' }));
  await screen.findByText('Blind independent label');
  expect(screen.getByRole('button', { name: 'Record Fail label' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Record Pass label' })).toBeDisabled();
  expect(screen.queryByText('Freshness', { selector: '.evaluation-review-card .row b' })).toBeNull();
  await user.type(screen.getByRole('textbox', {name:'Reviewer pseudonym'}), 'reviewer-A');
  await selectUIOption(user, 'Failure dimension 1', 'Accuracy');
  expect(screen.getByRole('button', { name: 'Record Fail label' })).toBeEnabled();
});


test('discards previous answers and reviewer decisions when switching audit records', async () => {
  const user=userEvent.setup();
  const view=render(<EvaluationReview runId="RUN1"/>);
  await user.click(screen.getByRole('button',{name:'Review Evaluations'}));
  await screen.findByText('Blind independent label');
  await user.type(screen.getByRole('textbox',{name:'Reviewer pseudonym'}),'reviewer-A');
  await user.type(screen.getByRole('textbox',{name:'Calibration note 1'}),'First audit only');
  view.rerender(<EvaluationReview runId="RUN2"/>);
  expect(screen.queryByText('Blind independent label')).toBeNull();
  expect(screen.getByRole('button',{name:'Review Evaluations'})).toBeEnabled();
  await user.click(screen.getByRole('button',{name:'Review Evaluations'}));
  await screen.findByText('Blind independent label');
  expect(screen.getByRole('textbox',{name:'Reviewer pseudonym'})).toHaveValue('');
  expect(screen.getByRole('textbox',{name:'Calibration note 1'})).toHaveValue('');
  expect(apiMocks.blindEvaluationReview).toHaveBeenLastCalledWith('RUN2');
});


test('reference review displays complete original evidence once for passing and failing answers', async () => {
  apiMocks.auditSourceHistory.mockResolvedValue([
    {role:'USER',content:'We used MySQL before.',timestamp:'2026-01-01T00:00:00Z'},
    {role:'ASSISTANT',content:'We now use PostgreSQL.',timestamp:'2026-01-02T00:00:00Z'},
  ]);
  apiMocks.evaluationReview.mockResolvedValue([item,{...item,
    automated:{...item.automated,evaluation_id:'E2',passed:true},
    test:{...item.test,test_id:'T2'},response:{...item.response,response_text:'PostgreSQL'}}]);
  render(<EvaluationReview runId="RUN1" exposedToAutomatedResults />);
  const user = userEvent.setup();
  await user.click(screen.getByRole('button',{name:'Review Evaluations'}));
  expect(await screen.findByText('Automated: Pass')).toBeInTheDocument();
  await user.click(screen.getByText('Read the complete original conversation · 2 messages'));
  expect(screen.getByText('We used MySQL before.',{exact:false})).toBeInTheDocument();
  expect(screen.getAllByText('We now use PostgreSQL.',{exact:false})).toHaveLength(1);
  expect(screen.getByText('User:')).toBeInTheDocument();
  expect(screen.getByText('Assistant:')).toBeInTheDocument();
  expect(screen.getByText(/This is source evidence, not the context sent/)).toBeInTheDocument();
  expect(apiMocks.reviewEvaluation).not.toHaveBeenCalled();
});

test('blind review uses its supplied source without fetching automated review evidence', async () => {
  apiMocks.blindEvaluationReview.mockResolvedValue([{...item,
    test:{test_id:'T1',prompt:'Current database?',expected_behavior:'PostgreSQL'},
    response:{response_text:'MySQL'},automated:{evaluation_id:'E1'},
    source_statements:[{role:'user',content:'We now use PostgreSQL.',timestamp:'2026-01-02T00:00:00Z'}]}]);
  render(<EvaluationReview runId="RUN1" independentOnly />);
  const user = userEvent.setup();
  await user.click(screen.getByRole('button',{name:'Review Evaluations'}));
  await user.click(await screen.findByText('Read the complete original conversation · 1 message'));
  expect(screen.getByText('We now use PostgreSQL.',{exact:false})).toBeInTheDocument();
  expect(apiMocks.auditSourceHistory).not.toHaveBeenCalled();
  expect(apiMocks.evaluationReview).not.toHaveBeenCalled();
  expect(apiMocks.evaluationCalibration).not.toHaveBeenCalled();
  expect(screen.queryByText('Expected PostgreSQL.')).toBeNull();
});

test.each(['changed version', 'new reviewer'])('refreshes %s before retrying a final decision', async (change) => {
  const reviews=['A','B'].map((reviewer,index)=>({review_id:`h${index}`,evaluation_id:'E1',human_passed:true,reviewer_label:reviewer,review_role:'independent',based_on_review_ids:[],created_at:'2026-01-01T00:00:00Z',updated_at:'2026-01-01T00:00:00Z'}));
  apiMocks.evaluationReview.mockResolvedValue([{...item,human_reviews:reviews}]);
  apiMocks.reviewEvaluation.mockRejectedValueOnce(new Error(change === 'new reviewer'
    ? 'The independent review set changed or is incomplete. Refresh the review evidence and consider every independent label before submitting your final decision.'
    : 'An independent review changed while this page was open. Refresh the review evidence, check the updated labels, then submit your final decision again.'));
  const user=userEvent.setup();
  render(<EvaluationReview runId="RUN1" exposedToAutomatedResults />);
  await user.click(screen.getByRole('button',{name:'Review Evaluations'}));
  await screen.findByText('Automated: Fail');
  await selectUIOption(user,'Evaluation review role','Adjudication');
  await user.click(screen.getByRole('button',{name:'Review Evaluations'}));
  await screen.findByText('Automated: Fail');
  await user.type(screen.getByRole('textbox',{name:'Reviewer pseudonym'}),'Final reviewer');
  await user.click(screen.getByRole('button',{name:'Adjudicate: Pass'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Refresh the review evidence');
  expect(screen.queryByText(/Your adjudication label was saved/)).toBeNull();
  expect(apiMocks.reviewEvaluation).toHaveBeenLastCalledWith('RUN1','E1',expect.objectContaining({based_on_review_versions:{h0:'2026-01-01T00:00:00Z',h1:'2026-01-01T00:00:00Z'}}));
  const refreshed = change === 'new reviewer'
    ? [...reviews, {...reviews[0], review_id:'h2', reviewer_label:'D', human_passed:false, updated_at:'2026-01-02T00:00:00Z'}]
    : [{...reviews[0],human_passed:false,updated_at:'2026-01-02T00:00:00Z'},reviews[1]];
  apiMocks.evaluationReview.mockResolvedValue([{...item,human_reviews:refreshed}]);
  await user.click(screen.getByRole('button',{name:'Refresh review evidence'}));
  await screen.findByText(change === 'new reviewer' ? 'Independent reviewer: Fail · Category not recorded · D' : 'Independent reviewer: Fail · Category not recorded · A');
  await user.click(screen.getByRole('button',{name:'Adjudicate: Fail'}));
  expect((await screen.findByRole('status')).textContent).toContain('Your adjudication label was saved: Fail');
  expect(apiMocks.reviewEvaluation).toHaveBeenLastCalledWith('RUN1','E1',expect.objectContaining({human_passed:false,
    based_on_review_ids:refreshed.map(review=>review.review_id),
    based_on_review_versions:Object.fromEntries(refreshed.map(review=>[review.review_id,review.updated_at]))}));
});


test('cannot return to independent review after automated evidence was revealed in this session', async () => {
  const user=userEvent.setup();
  render(<EvaluationReview runId="RUN1" />);
  await user.click(screen.getByRole('button',{name:'Review Evaluations'}));
  await screen.findByText('Blind independent label');
  await selectUIOption(user,'Evaluation review role','Reference label');
  await user.click(screen.getByRole('button',{name:'Review Evaluations'}));
  await screen.findByText('Automated: Fail');
  expect(screen.getByText('This report has shown the automated results.')).toBeTruthy();
  await user.click(screen.getByRole('combobox',{name:'Evaluation review role'}));
  const independent=screen.getByRole('option',{name:'Independent reviewer'});
  expect(independent).toHaveAttribute('aria-disabled','true');
  await user.click(independent);
  expect(selectedUILabel('Evaluation review role')).toContain('Reference label');
  expect(apiMocks.reviewEvaluation).not.toHaveBeenCalled();
});


test('locks the submitted reviewer, category and note while a label is being saved', async () => {
  let resolveSave!:(value:object)=>void;
  apiMocks.reviewEvaluation.mockReturnValueOnce(new Promise(resolve=>{resolveSave=resolve;}));
  const user=userEvent.setup();
  render(<EvaluationReview runId="RUN1" independentOnly/>);
  await user.click(screen.getByRole('button',{name:'Review Evaluations'}));
  await screen.findByText('Blind independent label');
  await user.type(screen.getByRole('textbox',{name:'Reviewer pseudonym'}),'reviewer-A');
  await selectUIOption(user,'Failure dimension 1','Freshness');
  await user.type(screen.getByRole('textbox',{name:'Calibration note 1'}),'The answer uses the old fact.');
  await user.click(screen.getByRole('button',{name:'Record Fail label'}));
  await waitFor(()=>expect(apiMocks.reviewEvaluation).toHaveBeenCalled());
  expect(screen.getByRole('textbox',{name:'Reviewer pseudonym'})).toBeDisabled();
  expect(screen.getByRole('combobox',{name:'Failure dimension 1'})).toBeDisabled();
  expect(screen.getByRole('textbox',{name:'Calibration note 1'})).toBeDisabled();
  expect(apiMocks.reviewEvaluation).toHaveBeenLastCalledWith('RUN1','E1',expect.objectContaining({human_failure_type:'freshness',note:'The answer uses the old fact.',reviewer_label:'reviewer-A'}));
  resolveSave({});
  await screen.findByText(/Your independent label was saved/);
  await waitFor(()=>expect(screen.getByRole('textbox',{name:'Calibration note 1'})).not.toBeDisabled());
});

 test('does not call local rule assessment missing model evidence', async () => {
  const user = userEvent.setup(); render(<EvaluationReview runId="RUN1" exposedToAutomatedResults />);
  await user.click(screen.getByRole('button', {name:'Review Evaluations'}));
  expect(await screen.findByText('Rule-based assessment runs locally; no assessment model request was made.')).toBeTruthy();
  expect(screen.queryByText(/Costs remain unknown/)).toBeNull();
});

test('distinguishes pass-fail agreement from failure-category disagreement',async()=>{
  apiMocks.evaluationCalibration.mockResolvedValue({human_reviewed_count:0,agreement_percentage:null,failure_precision:null,failure_recall:null,failure_f1:null,independent_review_count:2,independently_reviewed_evaluation_count:1,independent_consensus_count:1,independent_conflict_count:0,independent_pair_kappa:null,independent_failure_category_compared_count:1,independent_failure_category_agreement_count:0,independent_failure_category_conflict_count:1,independent_failure_category_missing_count:0});
  apiMocks.evaluationReview.mockResolvedValue([{...item,human_reviews:[{review_id:'A',human_passed:false,human_failure_type:'accuracy',reviewer_label:'A',review_role:'independent'},{review_id:'B',human_passed:false,human_failure_type:'freshness',reviewer_label:'B',review_role:'independent'}]}]);
  render(<EvaluationReview runId="RUN1" exposedToAutomatedResults/>);const user=userEvent.setup();
  await user.click(screen.getByRole('button',{name:'Review Evaluations'}));
  expect(await screen.findByText(/Failure-category agreement: 0\/1/)).toHaveTextContent('1 category disagreements');
  expect(screen.getByText(/Independent reviewer: Fail · Accuracy · A/)).toBeInTheDocument();
  expect(screen.getByText(/Independent reviewer: Fail · Freshness · B/)).toBeInTheDocument();
});


test('does not invent category agreement when independent failure categories are missing',async()=>{
  apiMocks.evaluationCalibration.mockResolvedValue({human_reviewed_count:0,agreement_percentage:null,failure_precision:null,failure_recall:null,failure_f1:null,independent_review_count:2,independently_reviewed_evaluation_count:1,independent_consensus_count:1,independent_conflict_count:0,independent_pair_kappa:null,independent_failure_category_compared_count:0,independent_failure_category_agreement_count:0,independent_failure_category_conflict_count:0,independent_failure_category_missing_count:1});
  render(<EvaluationReview runId="RUN1" exposedToAutomatedResults/>);const user=userEvent.setup();
  await user.click(screen.getByRole('button',{name:'Review Evaluations'}));
  expect(await screen.findByText(/Failure-category agreement: Not measured/)).toHaveTextContent('1 groups missing categories');
});
