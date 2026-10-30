import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { DynamicA, DynamicBC, useDynamicStudies } from './DynamicStudies';

const mocks=vi.hoisted(()=>({experimentGroups:vi.fn(),experimentResults:vi.fn(),methodComparisonResults:vi.fn(),listBenchmarkPlans:vi.fn(),listBenchmarkAnalyses:vi.fn()}));
vi.mock('../services/api',()=>({api:mocks}));
afterEach(()=>{cleanup();vi.resetAllMocks();});
function Page(){const {data,refresh}=useDynamicStudies();return <><button onClick={refresh}>Update</button><DynamicA data={data}/><DynamicBC data={data}/></>;}
it('reads A, B and C separately and refreshes saved evidence without mixing studies',async()=>{
  const group={experiment_id:'B1',label:'B',status:'COMPLETED',created_at:'2026-10-30',test_suite_metadata:{}};
  const a={...group,experiment_id:'A1',test_suite_metadata:{study_role:'audit_method_comparison',method_comparison_id:'CMP',diagnostic_source_run_id:'AUD'}};
  mocks.experimentGroups.mockResolvedValue([a,group]);
  mocks.methodComparisonResults.mockResolvedValue({source_run_id:'AUD',conditions:[1,2,3].map(n=>({run_id:String(n),label:`method ${n}`,status:'COMPLETED',failure_discovery_rate:{discovered_distinct_failures:n,known_distinct_failures:5,status:'measured'}}))});
  const names=['weak_first_hit','strong_rule_based','strong_score_based','scope_aware'];
  mocks.experimentResults.mockResolvedValue({experiment:group,conditions:names.map((name,i)=>({condition_id:name,memory_strategy:name,provider:'openrouter',model:'gpt',completed_runs:1,planned_runs:1,tests_passed:i+1,tests_total:5,dimensions:[]}))});
  const plan=(count:number)=>[{plan_id:'P',executions:{r1:{status:'COMPLETED',dashboard_summary:{metric:'lexical_match',conditions:[{strategy:'weak_first_hit',matched:count,total:5}]}}}}];
  mocks.listBenchmarkPlans.mockResolvedValueOnce(plan(1)).mockResolvedValue(plan(4));
  mocks.listBenchmarkAnalyses.mockResolvedValue([]);
  render(<Page/>);
  expect(await screen.findByText('Latest saved A comparison')).toBeInTheDocument();
  expect(screen.getByText('B · saved four-strategy group')).toBeInTheDocument();
  expect(screen.getByText('C · r1 · lexical match')).toBeInTheDocument();
  expect(screen.getByText(/automatic lexical match, not human-validated accuracy/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Update'}));
  await waitFor(()=>expect(screen.getAllByText('4/5 · 80.0%')).toHaveLength(2));
});
