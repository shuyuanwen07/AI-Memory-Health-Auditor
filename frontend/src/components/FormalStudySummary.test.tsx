import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {test,expect,vi,beforeEach} from 'vitest';
import {FormalStudySummary} from './FormalStudySummary';
import type {FormalMatrixCreateResponse,FormalStudySummary as Summary} from '../types/domain';
const {load,save}=vi.hoisted(()=>({load:vi.fn(),save:vi.fn()}));
vi.mock('../services/download',()=>({saveBlob:save}));vi.mock('../services/api',()=>({api:{formalStudySummary:load}}));
const plan={scenarios:[{run_ids:['private-anchor']}]} as FormalMatrixCreateResponse;
const report={version:'fixture',primary_outcome:'freshness',analysis_plan_recorded:false,planned_histories:5,repetitions_per_condition:3,notice:'Automated engineering fixture only.',conditions:[{condition_index:1,provider:'rule_based',model:'hidden-cloud-placeholder',memory_strategy:'scope_aware',planned_runs:15,completed_runs:3,measured_runs:3,invalid_evidence_runs:0,uncertain_runs:0,measured_histories:1,missing_histories:4,mean_percent:75,standard_deviation:null,interval_low:null,interval_high:null,overall_memory_health:{mean_percent:50,standard_deviation:null,interval_low:null,interval_high:null,measured_histories:1,missing_histories:4,repeat_variability:{complete_repeat_histories:1,mean_within_history_repeat_standard_deviation:12.3,notice:'Fixture variation.'}},dimension_summaries:[{dimension:'accuracy',mean_percent:0,standard_deviation:null,interval_low:null,interval_high:null,planned_runs:15,completed_runs:3,measured_runs:3,invalid_evidence_runs:0,uncertain_runs:0,measured_histories:1,missing_histories:4}]}],comparisons:[],overall_memory_health_comparisons:[{reference_condition:1,candidate_condition:2,paired_histories:1,missing_pairs:4,mean_percent:10,standard_deviation:null,interval_low:null,interval_high:null}],dimension_comparisons:[{dimension:'accuracy',reference_condition:1,candidate_condition:2,paired_histories:1,missing_pairs:4,mean_percent:10,standard_deviation:null,interval_low:null,interval_high:null}]} as Summary;
beforeEach(()=>{load.mockReset();save.mockReset();});
test('shows histories rather than repeats, missing coverage and an accessible vertical chart',async()=>{
 load.mockResolvedValue(report);const user=userEvent.setup();render(<FormalStudySummary matrix={plan}/>);
 await user.click(screen.getByRole('button',{name:'Refresh across-scene results'}));
 expect(await screen.findByText('Incomplete scene coverage')).toBeInTheDocument();
 expect(screen.getByRole('img',{name:/Setting 1: 75%, 1 of 5 scenes measured/})).toBeInTheDocument();
 expect(screen.getByText('Overall Memory Health · four-dimension macro-average')).toBeInTheDocument();
 expect(screen.getByText('12.3 pp')).toBeInTheDocument();
 expect(screen.getAllByText('accuracy')).toHaveLength(2);
 expect(screen.getByText('Paired differences by dimension')).toBeInTheDocument();
 expect(screen.getByText(/Local rule-based baseline/)).toBeInTheDocument();
 expect(screen.queryByText('private-anchor')).not.toBeInTheDocument();
 expect(screen.queryByText(/hidden-cloud-placeholder/)).not.toBeInTheDocument();
 expect(load).toHaveBeenCalledWith('private-anchor');
});
test('no saved plan or active execution prevents fetching',()=>{
 const {rerender}=render(<FormalStudySummary matrix={null}/>);
 expect(screen.getByRole('button',{name:'Refresh across-scene results'})).toBeDisabled();
 rerender(<FormalStudySummary matrix={plan} executionBusy/>);
 expect(screen.getByRole('button',{name:'Refresh across-scene results'})).toBeDisabled();expect(load).not.toHaveBeenCalled();
});
test('a late response from another plan cannot replace the selected study',async()=>{
 let resolve!:(value:Summary)=>void;load.mockReturnValue(new Promise<Summary>(r=>resolve=r));
 const user=userEvent.setup();const {rerender}=render(<FormalStudySummary matrix={plan}/>);
 await user.click(screen.getByRole('button',{name:'Refresh across-scene results'}));
 rerender(<FormalStudySummary matrix={{...plan,scenarios:[{...plan.scenarios[0],run_ids:['different-private-anchor']}]}}/>);
 resolve(report);await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh across-scene results'})).toBeEnabled());
 expect(screen.queryByText('Incomplete scene coverage')).not.toBeInTheDocument();
});


test('exports the current evidence-bound summary and removes export after plan changes',async()=>{
 const bound={...report,provenance:{dataset_fingerprint_sha256:'a'.repeat(64),frozen_plan_sha256:'b'.repeat(64),evidence_sha256:'c'.repeat(64),analysis_runtime_source_sha256:'d'.repeat(64),notice:'Checksums do not prove independent authorship.'},receipt_sha256:'e'.repeat(64)};
 load.mockResolvedValue(bound);const user=userEvent.setup();const {rerender}=render(<FormalStudySummary matrix={plan}/>);
 await user.click(screen.getByRole('button',{name:'Refresh across-scene results'}));
 await user.click(await screen.findByRole('button',{name:'Download scene comparison'}));
 expect(save).toHaveBeenCalledWith(expect.any(Blob),'scene-comparison-evidence.json');
 const blob=save.mock.calls[0][0];const reader=new FileReader();
 const json=await new Promise<string>((resolve)=>{reader.onload=()=>resolve(String(reader.result));reader.readAsText(blob);});
 expect(JSON.parse(json)).toEqual(bound);
 rerender(<FormalStudySummary matrix={{...plan,scenarios:[{...plan.scenarios[0],run_ids:['replacement']}]}}/>);
 expect(screen.queryByRole('button',{name:'Download scene comparison'})).not.toBeInTheDocument();
});
