import {render,screen} from '@testing-library/react';
import {GeneratorUsageCharts} from './GeneratorUsageCharts';
import type {GeneratorComparisonBatch,GeneratorUsage} from '../types/domain';

const usage:GeneratorUsage={recorded_invocations:3,receipt_count:2,unfinished_operations:false,
  timed_invocations:2,observed_elapsed_ms:500,request_attempts:3,failed_http_attempts:1,
  cost_reported_invocations:2,observed_cost_credits:0.03,complete_cost_coverage:false,
  token_reported_invocations:2,observed_total_tokens:30,scope:'fixture'};
const entry:GeneratorComparisonBatch['entries'][number]={selection:{provider:'openrouter',model:'google/gemini-2.5-flash-lite'},
  run:null,result:null,usage,quality:{saved_questions:0,accepted:0,rejected:0,pending:0,
    accepted_percentage:null,dimensions:{accuracy:0,freshness:0,conflict_resolution:0,appropriate_use:0},initial_candidates_measured:false}};

test('shows generation effort separately with coverage and unknown rules usage',()=>{
  render(<GeneratorUsageCharts entries={[{...entry,selection:{provider:'rule_based'},usage:null},entry]}/>);
  expect(screen.getByRole('img',{name:'Recorded generation time by generator'})).toHaveAccessibleDescription(/0.5 s; 2\/3 timed · 1 failed/);
  expect(screen.getByRole('img',{name:'Reported generation credits by generator'})).toHaveAccessibleDescription(/0.03 credits; 2\/3 reported · partial/);
  expect(screen.getByRole('img',{name:'Recorded HTTP attempts by generator'})).toHaveAccessibleDescription(/3 calls; 2\/3 receipts · 1 failed/);
  expect(screen.getByRole('img',{name:'Reported generation tokens by generator'})).toHaveAccessibleDescription(/Not recorded; No receipts/);
  expect(screen.getByText(/not a full invoice/)).toBeInTheDocument();
});

test('measured zero remains zero and unfinished work is explicit',()=>{
  render(<GeneratorUsageCharts entries={[{...entry,usage:{...usage,observed_cost_credits:0,observed_total_tokens:0,unfinished_operations:true}}]}/>);
  expect(screen.getByRole('img',{name:'Reported generation credits by generator'})).toHaveAccessibleDescription(/0 credits/);
  expect(screen.getByRole('img',{name:'Reported generation tokens by generator'})).toHaveAccessibleDescription(/0 tokens/);
  expect(screen.getByRole('img',{name:'Recorded generation time by generator'})).toHaveAccessibleDescription(/unfinished/);
});
