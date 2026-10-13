import {render,screen} from '@testing-library/react';
import {AssessorOperationCharts} from './AssessorOperationCharts';
import type {AssessorComparisonBatch,AssessorObservations} from '../types/domain';

const observation:AssessorObservations={expected_answers:4,bound_assessments:4,receipt_count:2,timed_answers:2,
  mean_elapsed_ms:200,request_attempts:3,failed_http_attempts:1,cost_reported_answers:2,
  observed_cost_credits:0.05,complete_cost_coverage:false,token_reported_answers:2,observed_total_tokens:50,scope:'fixture'};
const entries:AssessorComparisonBatch['entries']=[
  {selection:{evaluator_provider:'rule_based'},run:null,result:null,observations:null},
  {selection:{evaluator_provider:'openrouter',evaluator_model:'google/gemini-2.5-flash-lite'},run:null,result:null,observations:observation},
];

test('shows two units separately with explicit coverage and missing observations',()=>{
  render(<AssessorOperationCharts entries={entries}/>);
  expect(screen.getByRole('img',{name:'Average recorded review time by assessor'})).toHaveAccessibleDescription(/Rules: Not recorded; No receipts/);
  expect(screen.getByRole('img',{name:'Average recorded review time by assessor'})).toHaveAccessibleDescription(/0.2 s; 2\/4 timed/);
  expect(screen.getByRole('img',{name:'Reported OpenRouter credits by assessor'})).toHaveAccessibleDescription(/0.05 credits; 2\/4 reported · partial/);
  expect(screen.getByText(/not a full invoice/)).toBeInTheDocument();
});

test('explicit zero credits are measured rather than replaced with missing data',()=>{
  render(<AssessorOperationCharts entries={[{...entries[1],observations:{...observation,observed_cost_credits:0,
    cost_reported_answers:4,complete_cost_coverage:true}}]}/>);
  expect(screen.getByRole('img',{name:'Reported OpenRouter credits by assessor'})).toHaveAccessibleDescription(/0 credits; 4\/4 reported/);
  expect(screen.queryByText('Not recorded')).toBeNull();
});
