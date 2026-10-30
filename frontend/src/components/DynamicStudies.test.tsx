import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { DynamicA, DynamicBC, useDynamicStudies } from './DynamicStudies';

const mocks=vi.hoisted(()=>({experimentGroups:vi.fn(),experimentResults:vi.fn(),methodComparisonResults:vi.fn(),evaluationReview:vi.fn(),listBenchmarkPlans:vi.fn(),listBenchmarkAnalyses:vi.fn()}));
vi.mock('../services/api',()=>({api:mocks}));
afterEach(()=>{cleanup();vi.resetAllMocks();});
function Page(){const {data,refresh}=useDynamicStudies();return <><button onClick={refresh}>Update</button><DynamicA data={data}/><DynamicBC data={data}/></>;}
it('reads A, B and C separately and refreshes saved evidence without mixing studies',async()=>{
  const group={experiment_id:'B1',label:'B',status:'COMPLETED',created_at:'2026-10-30',test_suite_metadata:{}};
  const a={...group,experiment_id:'A1',test_suite_metadata:{study_role:'audit_method_comparison',method_comparison_id:'CMP',diagnostic_source_run_id:'AUD'}};
  mocks.experimentGroups.mockResolvedValue([a,group]);
  mocks.methodComparisonResults.mockResolvedValue({source_run_id:'AUD',conditions:[1,2,3].map(n=>({run_id:String(n),label:`method ${n}`,status:'COMPLETED',failure_discovery_rate:{discovered_distinct_failures:n,known_distinct_failures:5,status:'measured'}}))});
  const names=['weak_first_hit','strong_rule_based','strong_score_based','scope_aware'];
  mocks.experimentResults.mockResolvedValue({experiment:group,conditions:names.map((name,i)=>({condition_id:name,memory_strategy:name,provider:'openrouter',model:'gpt',completed_runs:1,planned_runs:1,run_ids:[name],tests_passed:i+1,tests_total:5,dimensions:[]}))});
  const review=(reviewer_label:string,human_passed:boolean)=>({reviewer_label,review_role:'independent',human_passed,updated_at:'2026-10-30',review_id:reviewer_label});
  mocks.evaluationReview.mockResolvedValue([{human_reviews:[review('one',true),review('two',true)]},{human_reviews:[review('one',true),review('two',false)]}]);
  const plan=(count:number)=>[{plan_id:'P',executions:{r1:{status:'COMPLETED',dashboard_summary:{metric:'lexical_match',conditions:[{strategy:'weak_first_hit',matched:count,total:5}]}}}}];
  mocks.listBenchmarkPlans.mockResolvedValueOnce(plan(1)).mockResolvedValue(plan(4));
  mocks.listBenchmarkAnalyses.mockResolvedValue([]);
  render(<Page/>);
  expect(await screen.findByText('Latest saved A comparison')).toBeInTheDocument();
  expect(screen.getByText('B · saved four-strategy group')).toBeInTheDocument();
  expect(screen.getByText('Independent human-review consensus')).toBeInTheDocument();
  expect(screen.getAllByText('2 reviewed by at least two · 1 disagreements excluded')).toHaveLength(4);
  expect(screen.getByText('C · r1 · lexical match')).toBeInTheDocument();
  expect(screen.getByText(/lexical match is automatic/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Update'}));
  await waitFor(()=>expect(screen.getAllByText('4/5 · 80.0%')).toHaveLength(2));
});

it('keeps C human disagreements unresolved and separate from lexical results',()=>{
  const rows=[{strategy:'weak_first_hit',case_id:'one',verdict:'pass'},{strategy:'weak_first_hit',case_id:'two',verdict:'fail'}];
  const changed=[rows[0],{...rows[1],verdict:'pass'}];
  const data={a:null,b:null,bHuman:{},analysis:null,errors:[],c:{plan_id:'P',executions:{r1:{status:'COMPLETED',dashboard_summary:{metric:'lexical_match',conditions:[{strategy:'weak_first_hit',matched:2,total:2,case_ids:['one','two']}]},human_reviews:[{review_id:'H',reviewers:[{reviewer:'one',judgments:rows},{reviewer:'two',judgments:changed}]}]}}}};
  render(<DynamicBC data={data as never}/>);
  expect(screen.getByText('2/2 · 100.0%')).toBeInTheDocument();
  expect(screen.getByText('1/1 · 100.0%')).toBeInTheDocument();
  expect(screen.getByText('1/2 agreed pass or fail; remaining cases unresolved or unreviewed')).toBeInTheDocument();
});
