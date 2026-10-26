import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { LiveBenchmark } from './LiveBenchmark';
import { UIProvider } from './ui';
const calls=vi.hoisted(()=>({validateLongMemEval:vi.fn(),runLiveBenchmark:vi.fn()}));
vi.mock('../services/api',()=>({api:calls}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
beforeEach(()=>{calls.validateLongMemEval.mockResolvedValue({cases:[{question:'Fixture question?',expected_answer:'Fixture reference',messages:[]}]});calls.runLiveBenchmark.mockResolvedValue({model:'fixture-model',notice:'Contract fixture only.',dataset_provenance:{dataset_version:'fixture-v1',license:'synthetic fixture',citation:'Synthetic unit-test fixture'},source_fingerprint_sha256:'a'.repeat(64),adapter_version:'fixture-adapter-v1',adapter_fingerprint_sha256:'b'.repeat(64),compatibility_limitations:['Contract fixture only'],conditions:[]});});
async function prepare(user:ReturnType<typeof userEvent.setup>){
  await user.type(screen.getByLabelText('Dataset version'),'fixture-v1');
  await user.type(screen.getByLabelText('Dataset licence'),'synthetic fixture');
  await user.type(screen.getByLabelText('Dataset citation'),'Synthetic unit-test fixture');
  fireEvent.change(screen.getByLabelText('Live benchmark JSON'),{target:{files:[new File(['[]'],'fixture.json',{type:'application/json'})]}});
  await user.click(screen.getByLabelText('Live benchmark source authorisation'));
  await screen.findByText('2 model answers requested; provider retries may add calls.');
  await user.click(screen.getByLabelText('Live benchmark model-run authorisation'));
}
test('sends the audit default answer budget and removes stale scores when the budget changes',async()=>{
  const user=userEvent.setup();render(<UIProvider><LiveBenchmark/></UIProvider>);await prepare(user);
  await user.click(screen.getByRole('button',{name:'Run Real-Model Comparison'}));
  await screen.findByText('Real-model comparison completed');
  expect(calls.runLiveBenchmark).toHaveBeenCalledWith(expect.objectContaining({temperature:0,random_seed:42,target_memory_capacity:50,target_memory_profile:expect.objectContaining({output_token_limit:2048,context_character_budget:16000})}),expect.any(AbortSignal));
  await user.click(screen.getByRole('button',{name:'Memory & answer settings'}));
  const budget=await screen.findByRole('spinbutton',{name:'Answer length limit'});
  await user.clear(budget);await user.type(budget,'256');await user.tab();
  await waitFor(()=>expect(screen.queryByText('Real-model comparison completed')).not.toBeInTheDocument());
  await user.click(screen.getByRole('button',{name:'Run Real-Model Comparison'}));
  await screen.findByText('Real-model comparison completed');
  expect(calls.runLiveBenchmark.mock.calls[calls.runLiveBenchmark.mock.calls.length - 1]?.[0].target_memory_profile.output_token_limit).toBe(256);
});
test('changing provider requires source authorisation again',async()=>{
  const user=userEvent.setup();render(<UIProvider><LiveBenchmark/></UIProvider>);await prepare(user);
  await user.click(screen.getByRole('combobox',{name:'Live benchmark provider'}));
  await user.click(await screen.findByText('Local Qwen (Ollama)'));
  await waitFor(()=>expect(screen.getByLabelText('Live benchmark model-run authorisation')).not.toBeChecked());
  expect(screen.getByRole('button',{name:'Run Real-Model Comparison'})).toBeDisabled();
  expect(calls.runLiveBenchmark).not.toHaveBeenCalled();
});
