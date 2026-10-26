import '@testing-library/jest-dom/vitest';
import { render,screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe,it,expect,vi } from 'vitest';
import { TargetProfileEditor,defaultTargetProfile } from './TargetProfileEditor';
describe('frozen target configuration editor',()=>{
  it('edits instructions and scope as target settings without a reference-answer input',async()=>{
    const user=userEvent.setup();const changed=vi.fn();
    render(<TargetProfileEditor value={defaultTargetProfile} onChange={changed}/>);
    await user.click(screen.getByRole('switch',{name:'Keep projects separate'}));
    expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({isolate_project_scope:true}));
    await user.type(screen.getByRole('textbox',{name:'Additional target instructions'}),'A');
    expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({additional_instructions:'A'}));
    expect(screen.queryByRole('textbox',{name:/expected answer/i})).toBeNull();
  });
  it('locks all configuration inputs while a run is being prepared',()=>{
    render(<TargetProfileEditor value={defaultTargetProfile} onChange={vi.fn()} disabled/>);
    expect(screen.getByRole('textbox',{name:'Configuration name'})).toBeDisabled();
    expect(screen.getByRole('switch',{name:'Prefer current facts'})).toBeDisabled();
    expect(screen.getByRole('switch',{name:'Check event identity'})).toBeDisabled();
  });
  it('opts into identity analysis explicitly and displays its separate budget',async()=>{
    const user=userEvent.setup();const changed=vi.fn();
    const {rerender}=render(<TargetProfileEditor value={defaultTargetProfile} onChange={changed}/>);
    expect(screen.queryByRole('spinbutton',{name:'Identity analysis output limit'})).toBeNull();
    await user.click(screen.getByRole('switch',{name:'Check event identity'}));
    const profile=changed.mock.calls.at(-1)![0];
    expect(profile.identity_analysis).toBe('evidence_links');
    rerender(<TargetProfileEditor value={profile} onChange={changed}/>);
    expect(screen.getByRole('spinbutton',{name:'Identity analysis output limit'})).toHaveValue('4096');
    expect(profile.output_token_limit).toBe(defaultTargetProfile.output_token_limit);
  });
  it('requires explicit continuation opt in and resets it when identity analysis is toggled',async()=>{
    const user=userEvent.setup();const changed=vi.fn();
    const {rerender}=render(<TargetProfileEditor value={defaultTargetProfile} onChange={changed}/>);
    expect(defaultTargetProfile.identity_analysis_failure_policy).toBe('fail_closed');
    expect(screen.queryByRole('combobox',{name:'If identity suggestions are unavailable'})).toBeNull();
    const profile={...defaultTargetProfile,identity_analysis:'evidence_links' as const};
    rerender(<TargetProfileEditor value={profile} onChange={changed}/>);
    expect(screen.getByText('Stop and show the error')).toBeInTheDocument();
    await user.click(screen.getByRole('combobox',{name:'If identity suggestions are unavailable'}));
    await user.click(screen.getByRole('option',{name:'Continue without identity suggestions'}));
    expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({identity_analysis_failure_policy:'continue_without_advisory'}));
    const optedIn=changed.mock.calls.at(-1)![0];
    rerender(<TargetProfileEditor value={optedIn} onChange={changed}/>);
    await user.click(screen.getByRole('switch',{name:'Check event identity'}));
    expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({identity_analysis:'off',identity_analysis_failure_policy:'fail_closed'}));
    expect(screen.getByText(/verifiable OpenRouter identity reply/)).toBeInTheDocument();
  });
});

it.each(['low','medium'] as const)('preserves hidden optional %s target reasoning choice when editing ordinary profile fields',async effort=>{
  const changed=vi.fn();const user=userEvent.setup();
  render(<TargetProfileEditor value={{...defaultTargetProfile,reasoning_effort:effort,identity_analysis_reasoning_effort:'low'}} onChange={changed}/>);
  await user.type(screen.getByRole('textbox',{name:'Configuration name'}),'A');
  expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({reasoning_effort:effort,identity_analysis_reasoning_effort:'low',output_token_limit:2048}));
  expect(screen.queryByRole('combobox',{name:/reasoning effort/i})).toBeNull();
});

it('keeps legacy retention by default and saves explicit source coverage without changing budgets',async()=>{
  const changed=vi.fn();const user=userEvent.setup();
  render(<TargetProfileEditor value={defaultTargetProfile} onChange={changed}/>);
  expect(screen.getByText('Prefer recent facts within each importance level')).toBeInTheDocument();
  await user.click(screen.getByRole('combobox',{name:'When memory fills up'}));
  await user.click(screen.getByRole('option',{name:'Balance coverage across messages'}));
  expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({retention_policy:'source_coverage',max_retrieved_records:50,context_character_budget:16000,output_token_limit:2048}));
  expect(screen.getByText(/does not guarantee complete recall/)).toBeInTheDocument();
});
