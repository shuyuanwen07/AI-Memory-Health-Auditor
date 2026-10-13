import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach,expect,test,vi} from 'vitest';
import {FrozenThresholdCheck} from './FrozenThresholdCheck';
import type {FormalMatrixCreateResponse,AcceptanceCheckReport} from '../types/domain';
const {check,savedCheck,list,restorePlan}=vi.hoisted(()=>({check:vi.fn(),savedCheck:vi.fn(),list:vi.fn(),restorePlan:vi.fn()}));
vi.mock('../services/api',()=>({api:{restoreFormalPlan:restorePlan,savedFormalRuns:list,checkFrozenThresholds:check,checkReviewedSavedThresholds:savedCheck}}));
const matrix={scenarios:[{run_ids:['internal-secret-run']}],acceptance_protocol:{}} as FormalMatrixCreateResponse;
const report={all_thresholds_met:false,notice:'Supplied evidence does not certify independence.',measures:[{key:'recall',label:'Failure recall',direction:'minimum',threshold_percent:66.7,numerator:2,denominator:3,observed_percent:200/3,status:'threshold_not_met',definition:'Complete reference failures',reason:'Raw counts used.'},{key:'fpr',label:'False-positive rate',direction:'maximum',threshold_percent:10,numerator:0,denominator:0,observed_percent:null,status:'insufficient_evidence',definition:'Reference passes',reason:'Missing denominator.'}]} as AcceptanceCheckReport;
beforeEach(()=>{check.mockReset();savedCheck.mockReset();list.mockResolvedValue({items:[],total:0,offset:0,limit:25});});
test('reads saved thresholds and shows unmet and missing evidence without exposing internal ids',async()=>{
  check.mockResolvedValue(report);const user=userEvent.setup();render(<FrozenThresholdCheck matrix={matrix} dataset={{version:1}} predictions={{version:1}} />);
  await user.click(screen.getByRole('button',{name:'Check frozen thresholds'}));
  expect(await screen.findByText('Does not meet')).toBeInTheDocument();
  expect(screen.getByText('Insufficient evidence')).toBeInTheDocument();
  expect(screen.getByRole('img',{name:/Failure recall: 66.7%; threshold not met/})).toBeInTheDocument();
  expect(screen.getByText('Not measured · 0/0 cases · maximum 10%')).toBeInTheDocument();
  expect(check).toHaveBeenCalledWith({dataset:{version:1},predictions:{version:1},frozen_run_id:'internal-secret-run'});
  expect(screen.queryByText('internal-secret-run')).not.toBeInTheDocument();
});
test('without a saved plan the action is disabled with an explanation',async()=>{
  render(<FrozenThresholdCheck matrix={null} dataset={{}} predictions={{}} />);
  expect(screen.getByRole('button',{name:'Check frozen thresholds'})).toBeDisabled();
  expect(await screen.findByText('No frozen experiments saved yet. Create a reviewed experiment first.')).toBeInTheDocument();
});
test('changed evidence clears results and ignores a late server response',async()=>{
  let resolve!:(value:AcceptanceCheckReport)=>void;check.mockReturnValue(new Promise<AcceptanceCheckReport>(r=>resolve=r));
  const source={version:1};const user=userEvent.setup();const {rerender}=render(<FrozenThresholdCheck matrix={matrix} dataset={source} predictions={{version:1}} />);
  await user.click(screen.getByRole('button',{name:'Check frozen thresholds'}));
  rerender(<FrozenThresholdCheck matrix={matrix} dataset={source} predictions={{version:2}} />);
  resolve(report);await waitFor(()=>expect(screen.getByRole('button',{name:'Check frozen thresholds'})).toBeEnabled());
  expect(screen.queryByText('Does not meet')).not.toBeInTheDocument();
});

test('restored replacement plan cannot submit the old experiment selection',async()=>{
  check.mockResolvedValue(report);const user=userEvent.setup();const source={};const machine={};
  const {rerender}=render(<FrozenThresholdCheck matrix={matrix} dataset={source} predictions={machine} />);
  const replacement={...matrix,scenarios:[{...matrix.scenarios[0],run_ids:['new-reference-run']}]};
  rerender(<FrozenThresholdCheck matrix={replacement} dataset={source} predictions={machine} />);
  await user.click(screen.getByRole('button',{name:'Check frozen thresholds'}));
  await waitFor(()=>expect(check).toHaveBeenCalledWith({dataset:source,predictions:machine,frozen_run_id:'new-reference-run'}));
});

test('numerical success cannot imply saved-result success when answer binding is incomplete',async()=>{
  check.mockResolvedValue({...report,all_thresholds_met:true,saved_result_thresholds_met:false,saved_evidence_binding:{status:'incomplete',reference_cases:4,matched:2,missing:1,mismatched:1,ambiguous:0,notice:'Independent labels remain unverified.'}});
  const user=userEvent.setup();render(<FrozenThresholdCheck matrix={matrix} dataset={{}} predictions={{}} />);
  await user.click(screen.getByRole('button',{name:'Check frozen thresholds'}));
  expect(await screen.findByText('Saved evidence incomplete')).toBeInTheDocument();
  expect(screen.getByText('2/4 matched · 1 missing · 1 mismatched · 0 ambiguous')).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Supplied numerical thresholds met; saved-result acceptance is not established.');
});

test('verified evidence and numerical success still retain independent-evaluation limits',async()=>{
  check.mockResolvedValue({...report,all_thresholds_met:true,saved_result_thresholds_met:true,saved_evidence_binding:{status:'verified',reference_cases:4,matched:4,missing:0,mismatched:0,ambiguous:0,notice:'Independent labels remain unverified.'}});
  const user=userEvent.setup();render(<FrozenThresholdCheck matrix={matrix} dataset={{}} predictions={{}} />);
  await user.click(screen.getByRole('button',{name:'Check frozen thresholds'}));
  expect(await screen.findByText('Saved answers verified')).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Independent evidence is still required.');
});

test('checks actual saved-answer labels without files and keeps incomplete review coverage visible',async()=>{
  savedCheck.mockResolvedValue({...report,review_coverage:{expected_tests:4,saved_answers:4,resolved_labels:2,missing_labels:2,ambiguous_tests:0,independently_adjudicated:0,failure_categories_missing:0}});
  const user=userEvent.setup();render(<FrozenThresholdCheck matrix={matrix} dataset={null} predictions={null} />);
  expect(screen.getByRole('button',{name:'Check frozen thresholds'})).toBeDisabled();
  await user.click(screen.getByRole('button',{name:'Check reviewed saved answers'}));
  expect(await screen.findByText('2/4 resolved · 2 missing · 0 ambiguous')).toBeInTheDocument();
  expect(savedCheck).toHaveBeenCalledWith('internal-secret-run');expect(check).not.toHaveBeenCalled();
});

test('refreshing actual labels clears the previous decision while the request is pending',async()=>{
  savedCheck.mockResolvedValueOnce({...report,review_coverage:{expected_tests:4,saved_answers:4,resolved_labels:4,missing_labels:0,ambiguous_tests:0,independently_adjudicated:0,failure_categories_missing:0}});
  const user=userEvent.setup();render(<FrozenThresholdCheck matrix={matrix} dataset={null} predictions={null} />);
  await user.click(screen.getByRole('button',{name:'Check reviewed saved answers'}));
  expect(await screen.findByText('4/4 resolved · 0 missing · 0 ambiguous')).toBeInTheDocument();
  let resolve!:(value:unknown)=>void;savedCheck.mockReturnValueOnce(new Promise(r=>resolve=r));
  await user.click(screen.getByRole('button',{name:'Check reviewed saved answers'}));
  expect(screen.queryByText('4/4 resolved · 0 missing · 0 ambiguous')).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Checking saved reviews…'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Check frozen thresholds'})).toBeDisabled();
  resolve(report);await waitFor(()=>expect(screen.getByRole('button',{name:'Check reviewed saved answers'})).toBeEnabled());
});

const storedRun={run_id:'server-private-id',provider:'ollama',model:'qwen3:1.7b',memory_strategy:'scope_aware',created_at:'2026-10-12T00:00:00Z',status:'COMPLETED',has_frozen_criteria:true};

test('restores server experiments with no browser plan or uploaded files',async()=>{
  list.mockResolvedValue({items:[storedRun],total:1,offset:0,limit:25});savedCheck.mockResolvedValue(report);
  const user=userEvent.setup();render(<FrozenThresholdCheck matrix={null} dataset={null} predictions={null} />);
  await waitFor(()=>expect(screen.getByRole('button',{name:'Check reviewed saved answers'})).toBeEnabled());
  await user.click(screen.getByRole('button',{name:'Check reviewed saved answers'}));
  expect(savedCheck).toHaveBeenCalledWith('server-private-id');
  expect(screen.queryByText('server-private-id')).not.toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Review these answers'})).toHaveAttribute('href','/audits/server-private-id');
});

test('loading errors can be retried and legacy criteria stay unavailable',async()=>{
  list.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({items:[{...storedRun,has_frozen_criteria:false}],total:1,offset:0,limit:25});
  const user=userEvent.setup();render(<FrozenThresholdCheck matrix={null} dataset={null} predictions={null} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Saved experiments could not be loaded. Try again.');
  await user.click(screen.getByRole('button',{name:'Refresh saved experiments'}));
  await waitFor(()=>expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  expect(screen.getByRole('button',{name:'Check reviewed saved answers'})).toBeDisabled();
  expect(screen.getByText(/criteria unavailable/)).toBeInTheDocument();
});

test('server pagination replaces the active selection and clamps a shrinking list',async()=>{
  list.mockResolvedValueOnce({items:[storedRun],total:26,offset:0,limit:25})
    .mockResolvedValueOnce({items:[{...storedRun,run_id:'second-page-id'}],total:26,offset:25,limit:25})
    .mockResolvedValueOnce({items:[],total:1,offset:25,limit:25})
    .mockResolvedValue({items:[storedRun],total:1,offset:0,limit:25});savedCheck.mockResolvedValue(report);
  const user=userEvent.setup();render(<FrozenThresholdCheck matrix={null} dataset={null} predictions={null} />);
  await user.click(await screen.findByRole('button',{name:'Next saved experiments'}));
  await waitFor(()=>expect(list).toHaveBeenCalledWith(25));
  await user.click(screen.getByRole('button',{name:'Check reviewed saved answers'}));
  expect(savedCheck).toHaveBeenCalledWith('second-page-id');
  await user.click(screen.getByRole('button',{name:'Refresh saved experiments'}));
  await waitFor(()=>expect(list.mock.calls.at(-1)?.[0]).toBe(0));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Check reviewed saved answers'})).toBeEnabled());
});

test('same-model records created together still have distinct friendly choices',async()=>{
  list.mockResolvedValue({items:[storedRun,{...storedRun,run_id:'other-private-id'}],total:2,offset:0,limit:25});savedCheck.mockResolvedValue(report);
  const user=userEvent.setup();render(<FrozenThresholdCheck matrix={null} dataset={null} predictions={null} />);
  await waitFor(()=>expect(screen.getByRole('combobox',{name:'Threshold reference experiment'})).toBeEnabled());
  await user.click(screen.getByRole('combobox',{name:'Threshold reference experiment'}));
  await user.click(await screen.findByRole('option',{name:/Saved run 2/}));
  await user.click(screen.getByRole('button',{name:'Check reviewed saved answers'}));
  expect(savedCheck).toHaveBeenCalledWith('other-private-id');
  expect(screen.queryByText('other-private-id')).not.toBeInTheDocument();
});


test('rule executor is named as a baseline even when stored model metadata names a cloud model',async()=>{
  list.mockResolvedValue({items:[{...storedRun,provider:'rule_based',model:'cloud-model-placeholder'}],total:1,offset:0,limit:25});
  render(<FrozenThresholdCheck matrix={null} dataset={null} predictions={null} />);
  expect(await screen.findByText(/Local rule-based baseline/)).toBeInTheDocument();
  expect(screen.queryByText(/cloud-model-placeholder/)).not.toBeInTheDocument();
});


test('restores a complete plan explicitly without scoring or model calls',async()=>{
  list.mockResolvedValue({items:[storedRun],total:1,offset:0,limit:25});restorePlan.mockResolvedValue(matrix);const restored=vi.fn();
  const user=userEvent.setup();render(<FrozenThresholdCheck matrix={null} dataset={null} predictions={null} onRestore={restored} />);
  await waitFor(()=>expect(screen.getByRole('button',{name:'Restore execution plan'})).toBeEnabled());
  await user.click(screen.getByRole('button',{name:'Restore execution plan'}));
  await waitFor(()=>expect(restored).toHaveBeenCalledWith(matrix));
  expect(restorePlan).toHaveBeenCalledWith(storedRun.run_id);expect(check).not.toHaveBeenCalled();expect(savedCheck).not.toHaveBeenCalled();
});

test('rejected recovery preserves the current plan and explains the failure',async()=>{
  list.mockResolvedValue({items:[storedRun],total:1,offset:0,limit:25});restorePlan.mockRejectedValue(new Error('Some conditions in the saved plan are missing.'));const restored=vi.fn();
  const user=userEvent.setup();render(<FrozenThresholdCheck matrix={null} dataset={null} predictions={null} onRestore={restored} />);
  await waitFor(()=>expect(screen.getByRole('button',{name:'Restore execution plan'})).toBeEnabled());
  await user.click(screen.getByRole('button',{name:'Restore execution plan'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Some conditions in the saved plan are missing.');expect(restored).not.toHaveBeenCalled();
});


test('execution in progress prevents switching to a different saved plan',async()=>{
  list.mockResolvedValue({items:[storedRun],total:1,offset:0,limit:25});const restored=vi.fn();
  render(<FrozenThresholdCheck matrix={null} dataset={null} predictions={null} onRestore={restored} executionBusy />);
  await waitFor(()=>expect(screen.getByRole('combobox',{name:'Threshold reference experiment'})).toBeEnabled());
  expect(screen.getByRole('button',{name:'Restore execution plan'})).toBeDisabled();
});


test('cached repeated runs retain condition identity and select the exact round',async()=>{
  const repeated={...matrix,condition_count:2,repetition_count:3,scenarios:[{...matrix.scenarios[0],run_ids:['round1a','round1b','round2a','round2b','round3a','round3b']}]};
  savedCheck.mockResolvedValue(report);const user=userEvent.setup();
  render(<FrozenThresholdCheck matrix={repeated} dataset={null} predictions={null} />);
  await waitFor(()=>expect(screen.getByRole('combobox',{name:'Threshold reference experiment'})).toBeEnabled());
  await user.click(screen.getByRole('combobox',{name:'Threshold reference experiment'}));
  await user.click(await screen.findByRole('option',{name:'Scenario 1 · condition 2 · run 3 of 3'}));
  await user.click(screen.getByRole('button',{name:'Check reviewed saved answers'}));
  expect(savedCheck).toHaveBeenCalledWith('round3b');
  expect(screen.queryByText('round3b')).not.toBeInTheDocument();
});

test('server restored repeat position is shown with its strategy',async()=>{
  list.mockResolvedValue({items:[{...storedRun,repetition_index:2,repetition_count:3}],total:1,offset:0,limit:25});
  render(<FrozenThresholdCheck matrix={null} dataset={null} predictions={null} />);
  expect(await screen.findByText(/run 2 of 3/)).toBeInTheDocument();
});
