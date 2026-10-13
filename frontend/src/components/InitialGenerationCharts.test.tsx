import {render,screen} from '@testing-library/react';
import {InitialGenerationCharts} from './InitialGenerationCharts';
import type {GeneratorComparisonBatch} from '../types/domain';

const entry={selection:{provider:'openrouter',model:'fixed-generator'},run:null,result:null,
  quality:{saved_questions:1,accepted:1,rejected:0,pending:0,accepted_percentage:100,dimensions:{accuracy:1,freshness:0,conflict_resolution:0,appropriate_use:0},initial_candidates_measured:true},
  generation:{operation_count:2,repair_passes:1,latest_status:'saved',initial_candidates:4,initial_local_check_percentage:75,
    initial_leak_percentage:25,initial_suite_contract_valid:false}} as GeneratorComparisonBatch['entries'][number];

test('shows first-attempt checks and repair effort separately from saved acceptance',()=>{
  render(<InitialGenerationCharts entries={[entry]}/>);
  expect(screen.getByRole('img',{name:'Initial local-check pass rate by generator'})).toHaveAccessibleDescription(/75%/);
  expect(screen.getByRole('img',{name:'Initial answer-leak flags by generator'})).toHaveAccessibleDescription(/25%/);
  expect(screen.getByText('2 generation operations · 1 automatic repair passes')).toBeInTheDocument();
  expect(screen.getByText('Initial suite contract rejected')).toBeInTheDocument();
  expect(screen.getByText(/not independent validity/)).toBeInTheDocument();
});

test('old or unfinished observations remain unknown rather than becoming zero leakage',()=>{
  render(<InitialGenerationCharts entries={[{...entry,generation:undefined},{...entry,selection:{provider:'rule_based'},
    generation:{...entry.generation!,latest_status:'unfinished',initial_candidates:null,initial_local_check_percentage:null,initial_leak_percentage:null}}]}/>);
  expect(screen.getByRole('img',{name:'Initial answer-leak flags by generator'})).toHaveAccessibleDescription(/Unknown/);
  expect(screen.getByRole('img',{name:'Initial answer-leak flags by generator'})).not.toHaveAccessibleDescription(/: 0%/);
  expect(screen.getByText('Unfinished generation operation')).toBeInTheDocument();
});
