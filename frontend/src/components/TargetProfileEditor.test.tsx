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
  });
});
