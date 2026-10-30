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
  const names=['weak_first_hit','strong_rule_based','scope_aware','temporal_importance'];
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

it('shows reviewed answers and failures outside the candidate list without presenting a zero recall',()=>{
  const data={a:{source_run_id:'AUD',conditions:[{run_id:'R',label:'Fixed templates',response_level:{true_negatives:3,false_positives:0,true_positives:0,false_negatives:1,unresolved_or_single_reviewer_labels:0},failure_discovery_rate:{status:'measured',discovered_distinct_failures:0,known_distinct_failures:3},discovery_mapping:{status:'frozen',entries:[{human_passed:false,defect_ids:[]}]}}]},b:null,bHuman:{},c:null,analysis:null,errors:[]};
  render(<DynamicA data={data as never}/>);
  expect(screen.getByText('3 passed · 1 failed')).toBeInTheDocument();
  expect(screen.getByText(/0 of 3 candidate patterns matched · 1 failed answer outside the candidate list/)).toBeInTheDocument();
  expect(screen.getByText(/No matches does not measure detection accuracy/)).toBeInTheDocument();
});

it('aggregates only completed scenarios in the selected campaign and retains pending reviews',()=>{
  const condition=(mode:string,completed:number,reviewed:number,passed:number,failed:number,status='COMPLETED')=>({suite_mode:mode,status,completed_answers:completed,response_level:{independently_labelled_responses:reviewed,true_negatives:passed,false_positives:0,true_positives:failed,false_negatives:0}});
  const modes=['direct_ground_truth','fixed_template','contextual_indirect'];
  const scenario=(id:string,complete:boolean)=>({id,result:{comparison_id:id,source_run_id:`AUD-${id}`,conditions:modes.map(mode=>condition(mode,4,3,2,1,complete?'COMPLETED':'TESTS_GENERATED'))}});
  const data={a:null,campaign:{id:'campaign',planned:4,scenarios:[scenario('first',true),scenario('second',true),scenario('third',false)]},b:null,bHuman:{},c:null,analysis:null,errors:[]};
  render(<DynamicA data={data as never}/>);
  expect(screen.getByText('2/4 scenarios complete · 3 registered · campaign')).toBeInTheDocument();
  expect(screen.getAllByText('4 passed · 2 failed')).toHaveLength(3);
  expect(screen.getAllByText('Independent human agreement · 2 answers awaiting independent human agreement · 2 completed scenarios')).toHaveLength(3);
  expect(screen.getByText('In progress · 9 reviewed answers')).toBeInTheDocument();
});

it('shows a single human reference without presenting it as two-human agreement',()=>{
  const modes=['direct_ground_truth','fixed_template','contextual_indirect'];
  const conditions=modes.map((mode,i)=>({run_id:String(i),suite_mode:mode,status:'COMPLETED',completed_answers:4,response_level:{independently_labelled_responses:0,true_negatives:0,false_positives:0,true_positives:0,false_negatives:0}}));
  const singleReviews=Object.fromEntries(conditions.map(c=>[c.run_id,{passed:2,decided:4,reviewed:4,unresolved:0}]));
  const data={a:null,campaign:{id:'single',planned:1,scenarios:[{id:'case',result:{comparison_id:'C',source_run_id:'R',conditions},singleReviews}]},b:null,bHuman:{},c:null,analysis:null,errors:[]};
  render(<DynamicA data={data as never}/>);
  expect(screen.getAllByText('2 passed · 2 failed')).toHaveLength(3);
  expect(screen.getAllByText('Single human reference · 4 answers awaiting independent human agreement · 1 completed scenarios')).toHaveLength(3);
});

it('loads only the newest explicit campaign and refreshes as a scenario completes',async()=>{
  const group=(campaign:string,scenario:string,comparison:string,date:string)=>({experiment_id:comparison,conversation_id:scenario,status:'CREATED',created_at:date,test_suite_metadata:{study_role:'audit_method_comparison',diagnostic_source_run_id:`AUD-${scenario}`,method_comparison_id:comparison,method_campaign_id:campaign,method_scenario_id:scenario,method_campaign_planned_scenarios:2}});
  const groups=[group('new','one','C1','2026-10-30'),group('new','one','C1','2026-10-30'),group('new','two','C2','2026-10-29'),group('old','other','C3','2026-10-28')];
  mocks.experimentGroups.mockResolvedValue(groups);mocks.listBenchmarkPlans.mockResolvedValue([]);mocks.listBenchmarkAnalyses.mockResolvedValue([]);
  let secondComplete=false;
  mocks.methodComparisonResults.mockImplementation(async (source:string,id:string)=>({comparison_id:id,source_run_id:source,conditions:['direct_ground_truth','fixed_template','contextual_indirect'].map(suite_mode=>({suite_mode,status:id==='C2'&&!secondComplete?'CREATED':'COMPLETED',completed_answers:1,response_level:{independently_labelled_responses:1,true_negatives:1,false_positives:0,true_positives:0,false_negatives:0}}))}));
  render(<Page/>);
  expect(await screen.findByText('1/2 scenarios complete · 2 registered · new')).toBeInTheDocument();
  expect(mocks.methodComparisonResults).not.toHaveBeenCalledWith('AUD-other','C3');
  secondComplete=true;fireEvent.click(screen.getByRole('button',{name:'Update'}));
  expect(await screen.findByText('2/2 scenarios complete · 2 registered · new')).toBeInTheDocument();
  expect(screen.getAllByText('2 passed · 0 failed')).toHaveLength(3);
});
