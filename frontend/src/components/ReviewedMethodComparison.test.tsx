import { act,render,screen,fireEvent,waitFor } from '@testing-library/react';
import { ReviewedMethodComparison,reviewedChartResult } from './ReviewedMethodComparison';
import type { AuditResult,EvaluationReviewItem } from '../types/domain';
const mocks=vi.hoisted(()=>({evaluationReview:vi.fn(),blindEvaluationReview:vi.fn(),reviewEvaluation:vi.fn()}));
vi.mock('../services/api',()=>({api:mocks}));
vi.mock('./ResultVisualizations',()=>({ComparisonVisualizations:({runs}: {runs:{result:AuditResult}[]})=><div data-testid="chart-score">{runs[0].result.dimensions[0].percentage??'Awaiting review'}</div>}));
const original:AuditResult={run_id:'r1',overall_score:null,tests_passed:0,tests_total:0,uncertain_count:1,evaluated_count:1,dimensions:[{dimension:'freshness',percentage:null,passed:0,total:0,uncertain_count:1}],failures:[]};
const item={test:{test_id:'t1',run_id:'r1',dimension:'freshness',prompt:'Which database is current?',expected_behavior:'PostgreSQL.',supporting_memory_ids:['m1'],generator_version:'v1'},response:{response_id:'a1',test_id:'t1',run_id:'r1',response_text:'PostgreSQL.',model:'Qwen',temperature:0,created_at:''},automated:{evaluation_id:'e1',test_id:'t1',response_id:'a1',passed:null,reason:'Disagreement',evidence_memory_ids:['m1'],evaluator:'hybrid'},human_review:null,human_reviews:[]} as EvaluationReviewItem;
const label={review_id:'h1',evaluation_id:'e1',human_passed:true,reviewer_label:'A',review_role:'reference' as const,based_on_review_ids:[],created_at:'',updated_at:''};
beforeEach(()=>{vi.resetAllMocks();mocks.evaluationReview.mockResolvedValue([item]);mocks.blindEvaluationReview.mockResolvedValue([{automated:{evaluation_id:'e1'},source_statements:[{content:'We now use PostgreSQL.',timestamp:''}]}]);});
test('shows unresolved answers automatically and updates and restores the chart from saved reference labels',async()=>{
  mocks.reviewEvaluation.mockImplementation(async()=>{mocks.evaluationReview.mockResolvedValue([{...item,human_review:label,human_reviews:[label]}]);return label;});
  const view=render(<ReviewedMethodComparison runs={[{label:'Hybrid review',result:original}]} />);
  expect(await screen.findByRole('heading',{name:'Unresolved answers (1)'})).toBeTruthy();
  expect(screen.getByText('We now use PostgreSQL.')).toBeTruthy();
  expect(screen.getByRole('button',{name:'Record reference pass'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Reviewer label or pseudonym'),{target:{value:'A'}});
  fireEvent.click(screen.getByRole('button',{name:'Record reference pass'}));
  await waitFor(()=>expect(screen.getByTestId('chart-score')).toHaveTextContent('100'));
  expect(mocks.reviewEvaluation).toHaveBeenCalledWith('r1','e1',expect.objectContaining({human_passed:true,review_role:'reference',reviewer_label:'A'}));
  expect(original.overall_score).toBeNull();expect(item.automated.passed).toBeNull();
  view.unmount();render(<ReviewedMethodComparison runs={[{label:'Hybrid review',result:original}]} />);
  await waitFor(()=>expect(screen.getByTestId('chart-score')).toHaveTextContent('100'));
  expect(await screen.findByText('No automated judgments are awaiting resolution. Independent review is still needed to validate assessment accuracy.')).toBeTruthy();
});
test('requires a failure category and preserves pending answers if saving fails',async()=>{
  mocks.reviewEvaluation.mockRejectedValue(new Error('Saving failed'));
  render(<ReviewedMethodComparison runs={[{label:'Hybrid review',result:original}]} />);
  await screen.findByRole('heading',{name:'Unresolved answers (1)'});
  fireEvent.change(screen.getByLabelText('Reviewer label or pseudonym'),{target:{value:'C'}});
  expect(screen.getByRole('button',{name:'Record reference fail'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Record reference pass'}));
  expect(await screen.findByText('Saving failed')).toBeTruthy();
  expect(screen.getByTestId('chart-score')).toHaveTextContent('Awaiting review');
  expect(screen.getByRole('heading',{name:'Unresolved answers (1)'})).toBeTruthy();
});
test('a persisted human Fail becomes a genuine zero score while unresolved rows stay unscored',()=>{
  const failed=reviewedChartResult(original,[{...item,human_review:{...label,human_passed:false,human_failure_type:'accuracy'}}]);
  expect(failed.dimensions[0]).toMatchObject({dimension:'freshness',percentage:0,total:1,passed:0,uncertain_count:0});
  expect(failed.overall_score).toBe(0);expect(failed.tests_total).toBe(1);
  expect(reviewedChartResult(original,[item])).toBe(original);
});


test('refreshes saved labels after returning from another page and ignores older loads',async()=>{
  render(<ReviewedMethodComparison runs={[{label:'Hybrid review',result:original}]}/>);
  await screen.findByRole('heading',{name:'Unresolved answers (1)'});
  let finishOlder!:(value:EvaluationReviewItem[])=>void;
  mocks.evaluationReview.mockReturnValueOnce(new Promise(resolve=>{finishOlder=resolve;}));
  await act(async()=>{window.dispatchEvent(new Event('focus'));});
  mocks.evaluationReview.mockResolvedValueOnce([{...item,human_review:label,human_reviews:[label]}]);
  await act(async()=>{window.dispatchEvent(new Event('focus'));});
  await waitFor(()=>expect(screen.getByTestId('chart-score')).toHaveTextContent('100'));
  await act(async()=>{finishOlder([item]);});
  expect(screen.getByTestId('chart-score')).toHaveTextContent('100');
  expect(mocks.reviewEvaluation).not.toHaveBeenCalled();
});
