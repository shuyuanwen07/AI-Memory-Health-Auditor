import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import { LiveBenchmark } from './LiveBenchmark';

const calls=vi.hoisted(()=>({validateLongMemEval:vi.fn(),runLiveBenchmark:vi.fn()}));
vi.mock('../services/api',()=>({api:calls}));
const result={model:'qwen3:1.7b',notice:'Exploratory proxies, not official scores.',dataset_provenance:{dataset_version:'fixture-v1',license:'synthetic fixture',citation:'Synthetic unit-test fixture'},source_fingerprint_sha256:'a'.repeat(64),adapter_version:'fixture-adapter-v1',adapter_fingerprint_sha256:'b'.repeat(64),compatibility_limitations:['Contract fixture only'],conditions:[{strategy:'weak_first_hit',lexical_matches:0,total:1,percentage:0,cases:[]},{strategy:'strong_rule_based',lexical_matches:1,total:1,percentage:100,cases:[]}]};
beforeEach(()=>{vi.clearAllMocks();calls.validateLongMemEval.mockResolvedValue({cases:[{question:'Where now?',expected_answer:'Alice Springs',messages:[{}]}]});calls.runLiveBenchmark.mockResolvedValue(result);});
async function upload(user:ReturnType<typeof userEvent.setup>){fireEvent.change(screen.getByLabelText('Dataset version'),{target:{value:'fixture-v1'}});fireEvent.change(screen.getByLabelText('Dataset licence'),{target:{value:'synthetic fixture'}});fireEvent.change(screen.getByLabelText('Dataset citation'),{target:{value:'Synthetic unit-test fixture'}});const input=screen.getByLabelText('Live benchmark JSON');fireEvent.change(input,{target:{files:[new File(['[{"question":"Where now?"}]'],'sample.json',{type:'application/json'})]}});await user.click(screen.getByLabelText('Live benchmark source authorisation'));await waitFor(()=>expect(screen.getByText('2 model answers requested; provider retries may add calls.')).toBeInTheDocument());}

test('counts shared native preparation once and keeps historical costs unknown',async()=>{
  const user=userEvent.setup();
  const nativeCase={case_id:'one',question:'Where now?',expected_answer:'Alice Springs',response_text:'Alice Springs',lexical_match:true,token_f1:1,message_count:1,assistant_message_count:0,stored_memory_count:1,retained_memory_count:1,retrieved_memory_ids:['r'],supplied_memory_ids:['r'],execution_metadata:{request_attempts:1,latency_ms:1},memory_preparation:{system:'mem0_oss',sdk_version:'2.2.1',native_llm_calls:2,embedding_calls:4,preparation_charged_here:true}};
  calls.runLiveBenchmark.mockResolvedValue({...result,conditions:[{strategy:'mem0_native',lexical_matches:1,total:2,percentage:50,cases:[nativeCase,{...nativeCase,case_id:'old',memory_preparation:{system:'mem0_oss'}},{...nativeCase,case_id:'partial',memory_preparation:{system:'mem0_oss',native_llm_calls:3}}]},{strategy:'mem0_generic',lexical_matches:1,total:1,percentage:100,cases:[{...nativeCase,memory_preparation:{...nativeCase.memory_preparation,preparation_charged_here:false}}]}]});
  render(<LiveBenchmark/>);await upload(user);await user.click(screen.getByLabelText('Live benchmark model-run authorisation'));await user.click(screen.getByRole('button',{name:'Run Real-Model Comparison'}));
  await screen.findByText(/Memory preparation: 5 recorded model calls · 4 recorded embedding calls · 2 preparations not measured/);
  await user.click(screen.getByRole('button',{name:'Inspect Mem0 original answers and supply evidence'}));
  expect(screen.getAllByText(/preparation calls not measured/)).toHaveLength(2);
});

test('requires validated source and consent before actual model calls',async()=>{
  const user=userEvent.setup();render(<LiveBenchmark/>);
  expect(screen.getByText(/Experiment C defaults to Weak first-hit and Strong rule-based/)).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Run Real-Model Comparison'})).toBeDisabled();
  await upload(user);expect(calls.runLiveBenchmark).not.toHaveBeenCalled();
  await user.click(screen.getByLabelText('Live benchmark model-run authorisation'));
  await user.click(screen.getByRole('button',{name:'Run Real-Model Comparison'}));
  await screen.findByText('Real-model comparison completed');
  expect(calls.runLiveBenchmark).toHaveBeenCalledWith(expect.objectContaining({provider:'ollama',model:'qwen3:1.7b',source_authorised:true,strategies:['weak_first_hit','strong_rule_based'],dataset_provenance:{dataset_version:'fixture-v1',license:'synthetic fixture',citation:'Synthetic unit-test fixture'}}),expect.any(AbortSignal));
  expect(screen.getByText('Strong rule-based · 1/1 lexical matches')).toBeInTheDocument();
  expect(screen.getByRole('img', {name: /Weak first-hit 0\/1 lexical matches, 0%; Strong rule-based 1\/1 lexical matches, 100%/})).toBeInTheDocument();
  expect(screen.getByText(/Word matches are an initial check/)).toBeInTheDocument();
});

test('invalid source cannot start model calls',async()=>{
  calls.validateLongMemEval.mockRejectedValue(new Error('History dates do not align.'));const user=userEvent.setup();render(<LiveBenchmark/>);
  fireEvent.change(screen.getByLabelText('Dataset version'),{target:{value:'fixture-v1'}});fireEvent.change(screen.getByLabelText('Dataset licence'),{target:{value:'synthetic fixture'}});fireEvent.change(screen.getByLabelText('Dataset citation'),{target:{value:'Synthetic unit-test fixture'}});
  fireEvent.change(screen.getByLabelText('Live benchmark JSON'),{target:{files:[new File(['[]'],'bad.json',{type:'application/json'})]}});
  expect(calls.validateLongMemEval).not.toHaveBeenCalled();await user.click(screen.getByLabelText('Live benchmark source authorisation'));
  await screen.findByText('History dates do not align.');expect(screen.getByRole('button',{name:'Run Real-Model Comparison'})).toBeDisabled();
  expect(calls.runLiveBenchmark).not.toHaveBeenCalled();
});

test('requires dataset version, licence and citation before source authorisation',async()=>{
  render(<LiveBenchmark/>);
  const input=screen.getByLabelText('Live benchmark JSON');
  fireEvent.change(input,{target:{files:[new File(['[]'],'sample.json',{type:'application/json'})]}});
  expect(screen.getByLabelText('Live benchmark source authorisation')).toBeDisabled();
  expect(screen.getByRole('button',{name:'Run Real-Model Comparison'})).toBeDisabled();
  expect(calls.runLiveBenchmark).not.toHaveBeenCalled();
  expect(calls.validateLongMemEval).not.toHaveBeenCalled();
});

test('ignores a late benchmark read and validation after source authorisation is revoked',async()=>{
  const user=userEvent.setup();render(<LiveBenchmark/>);
  fireEvent.change(screen.getByLabelText('Dataset version'),{target:{value:'fixture-v1'}});
  fireEvent.change(screen.getByLabelText('Dataset licence'),{target:{value:'synthetic fixture'}});
  fireEvent.change(screen.getByLabelText('Dataset citation'),{target:{value:'Synthetic unit-test fixture'}});
  let resolveRead!:(value:string)=>void;
  const file=new File(['pending'],'slow.json',{type:'application/json'});
  Object.defineProperty(file,'text',{value:()=>new Promise<string>(resolve=>{resolveRead=resolve;})});
  fireEvent.change(screen.getByLabelText('Live benchmark JSON'),{target:{files:[file]}});
  await user.click(screen.getByLabelText('Live benchmark source authorisation'));
  await user.click(screen.getByLabelText('Live benchmark source authorisation'));
  await act(async()=>resolveRead('[{"question":"stale"}]'));
  expect(calls.validateLongMemEval).not.toHaveBeenCalled();
  expect(screen.queryByText(/Review 1 imported questions/)).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Run Real-Model Comparison'})).toBeDisabled();
});

test('cancels pending execution and ignores a late response',async()=>{
  let resolve:(value:unknown)=>void=()=>{};calls.runLiveBenchmark.mockImplementation(()=>new Promise(r=>{resolve=r;}));
  const user=userEvent.setup();render(<LiveBenchmark/>);await upload(user);await user.click(screen.getByLabelText('Live benchmark model-run authorisation'));await user.click(screen.getByRole('button',{name:'Run Real-Model Comparison'}));
  await user.click(await screen.findByRole('button',{name:'Cancel comparison'}));
  expect(calls.runLiveBenchmark.mock.calls[0][1].aborted).toBe(true);
  resolve(result);await waitFor(()=>expect(screen.queryByText('Real-model comparison completed')).not.toBeInTheDocument());
  expect(screen.getByText(/Comparison cancelled/)).toBeInTheDocument();
});


test('includes native condition only when selected and keeps controlled preparation unlabelled',async()=>{
  const user=userEvent.setup();
  const baseCase={case_id:'one',question:'Where now?',expected_answer:'Alice Springs',response_text:'Alice Springs',lexical_match:true,
    token_f1:1,message_count:1,assistant_message_count:0,stored_memory_count:1,retained_memory_count:1,retrieved_memory_ids:['r'],
    supplied_memory_ids:['r'],execution_metadata:{request_attempts:1,latency_ms:1},memory_preparation:{}};
  calls.runLiveBenchmark.mockResolvedValue({...result,conditions:[{...result.conditions[1],cases:[baseCase]}]});
  render(<LiveBenchmark/>);await upload(user);
  await user.click(screen.getByLabelText('Include native Mem0 comparison'));
  expect(screen.getByText('3 model answers requested; provider retries may add calls.')).toBeInTheDocument();
  await user.click(screen.getByLabelText('Live benchmark model-run authorisation'));
  await user.click(screen.getByRole('button',{name:'Run Real-Model Comparison'}));
  await screen.findByText('Real-model comparison completed');
  expect(calls.runLiveBenchmark).toHaveBeenCalledWith(expect.objectContaining({include_mem0:true}),expect.any(AbortSignal));
  await user.click(screen.getByRole('button',{name:'Inspect Strong rule-based answers and supply evidence'}));
  expect(screen.queryByText(/Mem0 OSS/)).not.toBeInTheDocument();
});


test('requires one controlled reference for three native repair conditions',async()=>{
  const user=userEvent.setup();render(<LiveBenchmark/>);await upload(user);
  await user.click(screen.getByLabelText('Include native Mem0 comparison'));
  expect(screen.getByLabelText('Compare native generic and directed repairs')).toBeDisabled();
});
