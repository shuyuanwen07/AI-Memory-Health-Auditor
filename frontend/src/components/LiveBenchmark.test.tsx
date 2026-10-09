import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import { LiveBenchmark } from './LiveBenchmark';

const calls=vi.hoisted(()=>({validateLongMemEval:vi.fn(),runLiveBenchmark:vi.fn()}));
vi.mock('../services/api',()=>({api:calls}));
const result={model:'qwen3:1.7b',notice:'Exploratory proxies, not official scores.',conditions:[{strategy:'weak_first_hit',lexical_matches:0,total:1,percentage:0,cases:[]},{strategy:'scope_aware',lexical_matches:1,total:1,percentage:100,cases:[]}]};
beforeEach(()=>{vi.clearAllMocks();calls.validateLongMemEval.mockResolvedValue({cases:[{question:'Where now?',expected_answer:'Alice Springs',messages:[{}]}]});calls.runLiveBenchmark.mockResolvedValue(result);});
async function upload(){const input=screen.getByLabelText('Live benchmark JSON');fireEvent.change(input,{target:{files:[new File(['[{"question":"Where now?"}]'],'sample.json',{type:'application/json'})]}});await waitFor(()=>expect(screen.getByText('2 model answers requested; provider retries may add calls.')).toBeInTheDocument());}

test('counts shared native preparation once and keeps historical costs unknown',async()=>{
  const user=userEvent.setup();
  const nativeCase={case_id:'one',question:'Where now?',expected_answer:'Alice Springs',response_text:'Alice Springs',lexical_match:true,token_f1:1,message_count:1,assistant_message_count:0,stored_memory_count:1,retained_memory_count:1,retrieved_memory_ids:['r'],supplied_memory_ids:['r'],execution_metadata:{request_attempts:1,latency_ms:1},memory_preparation:{system:'mem0_oss',sdk_version:'2.2.1',native_llm_calls:2,embedding_calls:4,preparation_charged_here:true}};
  calls.runLiveBenchmark.mockResolvedValue({...result,conditions:[{strategy:'mem0_native',lexical_matches:1,total:2,percentage:50,cases:[nativeCase,{...nativeCase,case_id:'old',memory_preparation:{system:'mem0_oss'}},{...nativeCase,case_id:'partial',memory_preparation:{system:'mem0_oss',native_llm_calls:3}}]},{strategy:'mem0_generic',lexical_matches:1,total:1,percentage:100,cases:[{...nativeCase,memory_preparation:{...nativeCase.memory_preparation,preparation_charged_here:false}}]}]});
  render(<LiveBenchmark/>);await upload();await user.click(screen.getByLabelText('Live benchmark source authorisation'));await user.click(screen.getByRole('button',{name:'Run Real-Model Comparison'}));
  await screen.findByText(/Memory preparation: 5 recorded model calls · 4 recorded embedding calls · 2 preparations not measured/);
  await user.click(screen.getByRole('button',{name:'Inspect Mem0 original answers and supply evidence'}));
  expect(screen.getAllByText(/preparation calls not measured/)).toHaveLength(2);
});

test('requires validated source and consent before actual model calls',async()=>{
  const user=userEvent.setup();render(<LiveBenchmark/>);
  expect(screen.getByRole('button',{name:'Run Real-Model Comparison'})).toBeDisabled();
  await upload();expect(calls.runLiveBenchmark).not.toHaveBeenCalled();
  await user.click(screen.getByLabelText('Live benchmark source authorisation'));
  await user.click(screen.getByRole('button',{name:'Run Real-Model Comparison'}));
  await screen.findByText('Real-model comparison completed');
  expect(calls.runLiveBenchmark).toHaveBeenCalledWith(expect.objectContaining({provider:'ollama',model:'qwen3:1.7b',source_authorised:true,strategies:['weak_first_hit','scope_aware']}),expect.any(AbortSignal));
  expect(screen.getByText('Scope-aware · 1/1 lexical matches')).toBeInTheDocument();
  expect(screen.getByText(/Word matches are an initial check/)).toBeInTheDocument();
});

test('invalid source cannot start model calls',async()=>{
  calls.validateLongMemEval.mockRejectedValue(new Error('History dates do not align.'));render(<LiveBenchmark/>);
  fireEvent.change(screen.getByLabelText('Live benchmark JSON'),{target:{files:[new File(['[]'],'bad.json',{type:'application/json'})]}});
  await screen.findByText('History dates do not align.');expect(screen.getByRole('button',{name:'Run Real-Model Comparison'})).toBeDisabled();
  expect(calls.runLiveBenchmark).not.toHaveBeenCalled();
});

test('cancels pending execution and ignores a late response',async()=>{
  let resolve:(value:unknown)=>void=()=>{};calls.runLiveBenchmark.mockImplementation(()=>new Promise(r=>{resolve=r;}));
  const user=userEvent.setup();render(<LiveBenchmark/>);await upload();await user.click(screen.getByLabelText('Live benchmark source authorisation'));await user.click(screen.getByRole('button',{name:'Run Real-Model Comparison'}));
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
  render(<LiveBenchmark/>);await upload();
  await user.click(screen.getByLabelText('Include native Mem0 comparison'));
  expect(screen.getByText('3 model answers requested; provider retries may add calls.')).toBeInTheDocument();
  await user.click(screen.getByLabelText('Live benchmark source authorisation'));
  await user.click(screen.getByRole('button',{name:'Run Real-Model Comparison'}));
  await screen.findByText('Real-model comparison completed');
  expect(calls.runLiveBenchmark).toHaveBeenCalledWith(expect.objectContaining({include_mem0:true}),expect.any(AbortSignal));
  await user.click(screen.getByRole('button',{name:'Inspect Scope-aware answers and supply evidence'}));
  expect(screen.queryByText(/Mem0 OSS/)).not.toBeInTheDocument();
});


test('requires one controlled reference for three native repair conditions',async()=>{
  const user=userEvent.setup();render(<LiveBenchmark/>);await upload();
  await user.click(screen.getByLabelText('Include native Mem0 comparison'));
  expect(screen.getByLabelText('Compare native generic and directed repairs')).toBeDisabled();
});
