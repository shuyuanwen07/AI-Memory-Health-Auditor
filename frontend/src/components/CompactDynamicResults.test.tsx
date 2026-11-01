import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { act, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { AstraCapacitySummary, AstraPolicyReview, CompactBenchmarkResults } from './CompactExperimentResults';
const snapshot=()=>JSON.parse(readFileSync(resolve(process.cwd(),'public/reports/b-astra-four-strategy-v1.json'),'utf8'));
const strategies=['weak_first_hit','strong_rule_based','scope_aware','temporal_importance'];
const group=(id:string,date:string)=>({experiment:{experiment_id:id,label:'New policy run',created_at:date},conditions:strategies.map((memory_strategy,i)=>({condition_id:String(i),memory_strategy,model:'new-model',planned_runs:1,completed_runs:1,tests_passed:2,tests_total:4,dimensions:[{uncertain_count:1}]}))});
const live=(b:unknown)=>({b,bHuman:{}} as never);
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers();});
it('keeps incomplete capacity-comparison calls outside the answered denominator',async()=>{
 const report={format:'c-astra-capacity-development-v1',review_status:'human_confirmed',cases:2,before:{passed:0,answered:4,planned:4},after:{passed:0,answered:3,planned:4,missing:1}};
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>report})));
 render(<AstraCapacitySummary/>);
 const result=await screen.findByLabelText('Astra capacity development comparison');
 expect(result).toHaveTextContent('capacity 50, 0/4 passed; capacity 500, 0/3 passed and 1 request incomplete');
 expect(result).toHaveTextContent('separate from the benchmark plan');
});
it('does not publish a capacity comparison as human checked before confirmation',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({format:'c-astra-capacity-development-v1',review_status:'pending',cases:2,before:{passed:0,answered:4,planned:4},after:{passed:0,answered:3,planned:4,missing:1}})})));
 await act(async()=>{render(<AstraCapacitySummary/>);});
 expect(screen.queryByLabelText('Astra capacity development comparison')).not.toBeInTheDocument();
});
it('preserves the aggregate snapshot for old or source groups, then selects a genuinely newer group',async()=>{
 const report=snapshot();vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>report})));
 const page=render(<AstraPolicyReview data={live(group('old','2026-10-01T00:00:00Z'))}/>);
 expect(await screen.findByLabelText('Astra four-strategy paired review')).toBeInTheDocument();
 page.rerender(<AstraPolicyReview data={live(group(report.experiment_ids[0],'2026-12-01T00:00:00Z'))}/>);
 expect(screen.queryByLabelText('Latest saved four-strategy results')).not.toBeInTheDocument();
 page.rerender(<AstraPolicyReview data={live(group('genuinely-new','2026-12-01T00:00:00Z'))}/>);
 expect(screen.getByLabelText('Latest saved four-strategy results')).toHaveTextContent('Automatic saved assessments');
 expect(screen.getAllByText('2/4 · 50.0% · 1 unresolved')).toHaveLength(4);
 expect(screen.queryByLabelText('Astra four-strategy paired review')).not.toBeInTheDocument();
});
it('refreshes the policy snapshot on the 30-second timer',async()=>{
 vi.useFakeTimers();const first=snapshot(),next=snapshot();next.complete_paired_only.weak_first_hit.pass=4;next.complete_paired_only.weak_first_hit.fail=8;
 let calls=0;vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>++calls===1?first:next})));
 await act(async()=>{render(<AstraPolicyReview/>);});expect(screen.getAllByText('3/12 · 25.0% pass · 0 unresolved')).toHaveLength(2);
 await act(async()=>{await vi.advanceTimersByTimeAsync(30000);});expect(screen.getByText('4/12 · 33.3% pass · 0 unresolved')).toBeInTheDocument();
});
function plan(reviewed=false){
 const entry=(matched:number)=>({status:'COMPLETED',dashboard_summary:{metric:'lexical_match',conditions:[{strategy:'weak_first_hit',matched,total:2,case_ids:['one','two']}]},...(reviewed?{human_reviews:[{review_id:'H',reviewers:[{reviewer:'left',judgments:[{strategy:'weak_first_hit',case_id:'one',verdict:'pass'},{strategy:'weak_first_hit',case_id:'two',verdict:'fail'}]},{reviewer:'right',judgments:[{strategy:'weak_first_hit',case_id:'one',verdict:'pass'},{strategy:'weak_first_hit',case_id:'two',verdict:'pass'}]}]}]}:{})});
 return {plan_id:'P',created_at:'2026-11-01',protocol:{trials:[{trial_id:'r1'},{trial_id:'r2'},{trial_id:'r3'}],benchmark:{configuration:{model:'new-benchmark-model'}}},executions:{r1:entry(1),r2:entry(2),r3:{status:'FAILED'}}} as never;
}
it('combines completed C trials into one chart, retains missing trials, and updates on new plan data',()=>{
 const page=render(<CompactBenchmarkResults plan={plan()} strategies={[]}/>);
 expect(screen.getAllByLabelText('Latest saved benchmark plan results')).toHaveLength(1);expect(screen.getByText('3/4 · 75.0%')).toBeInTheDocument();
 expect(screen.getByText(/2\/3 planned trials complete/)).toHaveTextContent('1 incomplete');expect(screen.getByText(/Lexical match is not a human or official benchmark score/)).toBeInTheDocument();
 page.rerender(<CompactBenchmarkResults plan={plan(true)} strategies={[]}/>);
 expect(screen.getByText('2/2 · 100.0% · 2/4 agreed · 2 unresolved or unreviewed')).toBeInTheDocument();expect(screen.getByText(/Human-review consensus/)).toBeInTheDocument();expect(screen.queryByText('3/4 · 75.0%')).not.toBeInTheDocument();
});
