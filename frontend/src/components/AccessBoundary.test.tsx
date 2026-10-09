import { act, cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { AccessBoundary } from './AccessBoundary';
import { api } from '../services/api';
import { SESSION_ENDED } from '../services/access';
import type { AccessStatus } from '../services/access';
vi.mock('../services/api',()=>({api:{accessStatus:vi.fn(),signIn:vi.fn(),signOut:vi.fn()}}));
const locked:AccessStatus={mode:'protected',requires_sign_in:true,authenticated:false,expires_at:null,expires_in_seconds:null,csrf_token:null};
const unlocked:AccessStatus={...locked,authenticated:true,csrf_token:'test-csrf'};
beforeEach(()=>{vi.clearAllMocks();sessionStorage.clear();localStorage.clear();});
afterEach(()=>cleanup());
function workspace(){return render(<AccessBoundary>{signOut=><><p>Private audit evidence</p>{signOut&&<button onClick={()=>void signOut()}>Sign out</button>}</>}</AccessBoundary>);}
it('keeps private content unmounted until the server accepts the password',async()=>{
  vi.mocked(api.accessStatus).mockResolvedValue(locked);vi.mocked(api.signIn).mockResolvedValue(unlocked);
  workspace();expect(await screen.findByText('Sign in to your workspace')).toBeTruthy();expect(screen.queryByText('Private audit evidence')).toBeNull();
  await userEvent.type(screen.getByLabelText('Workspace password'),'synthetic-test-password-only');await userEvent.click(screen.getByRole('button',{name:/^Sign in$/}));
  expect(await screen.findByText('Private audit evidence')).toBeTruthy();expect(api.signIn).toHaveBeenCalledWith('synthetic-test-password-only');
});
it('clears private drafts and unmounts evidence when the session ends',async()=>{
  vi.mocked(api.accessStatus).mockResolvedValue(unlocked);workspace();await screen.findByText('Private audit evidence');
  sessionStorage.setItem('mha-new-audit-draft-v1','private conversation');sessionStorage.setItem('unrelated-setting','keep');
  act(()=>window.dispatchEvent(new Event(SESSION_ENDED)));
  expect(await screen.findByText('Sign in to your workspace')).toBeTruthy();expect(screen.queryByText('Private audit evidence')).toBeNull();
  expect(sessionStorage.getItem('mha-new-audit-draft-v1')).toBeNull();expect(sessionStorage.getItem('unrelated-setting')).toBe('keep');
});
it('waits for server revocation before confirming sign out',async()=>{
  vi.mocked(api.accessStatus).mockResolvedValue(unlocked);vi.mocked(api.signOut).mockResolvedValue({signed_out:true});workspace();await screen.findByText('Private audit evidence');
  await userEvent.click(screen.getByRole('button',{name:'Sign out'}));expect(await screen.findByText('Sign in to your workspace')).toBeTruthy();expect(api.signOut).toHaveBeenCalledTimes(1);
});
it('keeps evidence hidden when access cannot be checked',async()=>{
  vi.mocked(api.accessStatus).mockRejectedValue(new Error('Connection interrupted'));workspace();
  expect(await screen.findByText('Connection interrupted')).toBeTruthy();expect(screen.queryByText('Private audit evidence')).toBeNull();expect(screen.getByRole('button',{name:'Retry connection'})).toBeTruthy();
});

it('does not restore private evidence from a stale access check after session expiry',async()=>{
  let resolve!:(value:AccessStatus)=>void;
  vi.mocked(api.accessStatus).mockReturnValue(new Promise<AccessStatus>(done=>{resolve=done;}));workspace();
  act(()=>window.dispatchEvent(new Event(SESSION_ENDED)));
  await act(async()=>{resolve(unlocked);});
  expect(screen.queryByText('Private audit evidence')).toBeNull();
});
