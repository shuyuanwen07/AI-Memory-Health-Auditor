import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ComponentProps } from 'react';
import { ConversationStep } from './ConversationStep';

function renderStep(overrides: Partial<ComponentProps<typeof ConversationStep>> = {}) {
  const props = {
    text: 'A conversation', consent: false, sourceOrigin: 'unknown' as const, busy: false,
    onTextChange: vi.fn(), onConsentChange: vi.fn(), onSourceOriginChange: vi.fn(), onImport: vi.fn(), onImportError: vi.fn(), onClearDraft: vi.fn(), onContinue: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<ConversationStep {...props} />) };
}

test('retains original offset provenance when importing an exported UTC message',async()=>{
  const user=userEvent.setup();
  const {props}=renderStep({consent:true});
  const message={message_id:'offset',role:'user',content:'I prefer Python.',timestamp:'2026-01-01T03:00:00Z',original_timestamp:'2026-01-01T14:00:00+11:00'};
  await user.upload(screen.getByLabelText('Or upload conversation JSON'),new File([JSON.stringify({messages:[message]})],'offset.json',{type:'application/json'}));
  await waitFor(()=>expect(props.onImport).toHaveBeenCalledWith([message],'[user] I prefer Python.'));
});

test('rejects conflicting original timestamps without replacing the draft',async()=>{
  const user=userEvent.setup();
  const {props}=renderStep({consent:true});
  const message={role:'user',content:'I prefer Python.',timestamp:'2026-01-01T03:00:00Z',original_timestamp:'2026-01-01T15:00:00+11:00'};
  await user.upload(screen.getByLabelText('Or upload conversation JSON'),new File([JSON.stringify({messages:[message]})],'conflict.json',{type:'application/json'}));
  await waitFor(()=>expect(props.onImportError).toHaveBeenCalled());
  expect(props.onImport).not.toHaveBeenCalled();
});

test('requires authorisation before continuing', async () => {
  const user = userEvent.setup();
  const { container, props } = renderStep();
  expect((screen.getByRole('button', { name: 'Continue to Ground Truth' }) as HTMLButtonElement).disabled).toBe(true);
  expect(container.querySelector('input[type="file"]')).toBeDisabled();
  await user.click(screen.getByLabelText(/I confirm that I am authorised to use this conversation data/));
  expect(props.onConsentChange).toHaveBeenCalledWith(true);
});

test('lets the operator record synthetic source origin separately from research eligibility', async () => {
  const user = userEvent.setup();
  const { props } = renderStep({consent:true});
  await user.click(screen.getByRole('combobox', { name: 'Conversation source origin' }));
  await user.click(await screen.findByRole('option', { name: 'Synthetic test data' }));
  expect(props.onSourceOriginChange).toHaveBeenCalledWith('synthetic');
  expect(screen.getByText(/does not create human labels or confirm research eligibility/i)).toBeInTheDocument();
});

test('imports valid JSON conversation messages without discarding IDs or timestamps', async () => {
  const user = userEvent.setup();
  const { props } = renderStep({consent:true});
  const file = new File([JSON.stringify({ messages: [{ message_id: 'source-101', role: 'user', content: 'I prefer Python.', timestamp: '2026-01-01T00:00:00Z' }] })], 'conversation.json', { type: 'application/json' });
  await user.upload(screen.getByLabelText('Or upload conversation JSON'), file);
  await waitFor(() => expect(props.onImport).toHaveBeenCalledWith([{ message_id: 'source-101', role: 'user', content: 'I prefer Python.', timestamp: '2026-01-01T00:00:00Z' }], '[user] I prefer Python.'));
  expect(props.onImportError).toHaveBeenCalledWith('');
  expect(screen.getByText('1 message imported successfully.')).not.toBeNull();
});

test('reports invalid JSON uploads without replacing the conversation', async () => {
  const user = userEvent.setup();
  const { props } = renderStep({consent:true});
  await user.upload(screen.getByLabelText('Or upload conversation JSON'), new File(['{}'], 'invalid.json', { type: 'application/json' }));
  await waitFor(() => expect(props.onImportError).toHaveBeenCalledWith(expect.stringContaining('messages array')));
  expect(props.onImport).not.toHaveBeenCalled();
  expect(screen.getByText('Import was not completed. Your pasted conversation has not been changed.')).not.toBeNull();
});

test('rejects a JSON upload over the client-side safety limit before parsing it', async () => {
  const user = userEvent.setup();
  const { props } = renderStep({consent:true});
  const oversized = new File(['x'.repeat(1_000_001)], 'oversized.json', { type: 'application/json' });
  await user.upload(screen.getByLabelText('Or upload conversation JSON'), oversized);
  await waitFor(() => expect(props.onImportError).toHaveBeenCalledWith(expect.stringContaining('larger than 1 MB')));
  expect(props.onImport).not.toHaveBeenCalled();
});

test('does not read an uploaded conversation before consent', () => {
  const { container } = renderStep();
  const file = new File(['{}'], 'private.json', { type: 'application/json' });
  const read = vi.spyOn(file, 'text');
  const input=container.querySelector('input[type="file"]');
  expect(input).toBeDisabled();
  fireEvent.change(input!, { target: { files: [file] } });
  expect(read).not.toHaveBeenCalled();
});

test('does not treat whitespace-only input as a conversation', () => {
  renderStep({ text: '   \n  ', consent: true });
  expect(screen.getByText('Add at least one non-empty message to continue.')).not.toBeNull();
  expect((screen.getByRole('button', { name: 'Continue to Ground Truth' }) as HTMLButtonElement).disabled).toBe(true);
});

test('allows a local browser draft to be cleared explicitly', async () => {
  const user = userEvent.setup();
  const { props } = renderStep();
  await user.click(screen.getByRole('button', { name: 'Clear local draft' }));
  expect(props.onClearDraft).toHaveBeenCalledTimes(1);
});

test.each(['edit','clear','unmount'])('discards a late file read after %s', async (action) => {
  const user = userEvent.setup();
  const view = renderStep({consent:true});
  let resolveRead!:(value:string)=>void;
  const file = new File(['pending'], 'slow.json', {type:'application/json'});
  Object.defineProperty(file,'text',{value:()=>new Promise<string>(resolve=>{resolveRead=resolve;})});
  await user.upload(screen.getByLabelText('Or upload conversation JSON'), file);
  expect(screen.getByRole('button',{name:'Continue to Ground Truth'})).toBeDisabled();
  if (action === 'edit') await user.type(screen.getByLabelText('Authorised conversation text'),'New text');
  else if (action === 'clear') await user.click(screen.getByRole('button',{name:'Clear local draft'}));
  else view.unmount();
  await act(async()=>resolveRead(JSON.stringify({messages:[{role:'user',content:'Stale imported fact'}]})));
  expect(view.props.onImport).not.toHaveBeenCalled();
  expect(view.props.onImportError).not.toHaveBeenCalled();
});

test('discards a pending file read when source authorisation is revoked', async () => {
  const user = userEvent.setup();
  const view = renderStep({consent:true});
  let resolveRead!:(value:string)=>void;
  const file = new File(['pending'], 'slow.json', {type:'application/json'});
  Object.defineProperty(file,'text',{value:()=>new Promise<string>(resolve=>{resolveRead=resolve;})});
  await user.upload(screen.getByLabelText('Or upload conversation JSON'), file);
  await user.click(screen.getByLabelText(/I confirm that I am authorised to use this conversation data/));
  expect(view.props.onConsentChange).toHaveBeenCalledWith(false);
  view.rerender(<ConversationStep {...view.props} consent={false}/>);
  await act(async()=>resolveRead(JSON.stringify({messages:[{role:'user',content:'Revoked imported fact'}]})));
  expect(view.props.onImport).not.toHaveBeenCalled();
  expect(view.props.onImportError).not.toHaveBeenCalled();
});

test('only the latest selected file can replace the conversation', async () => {
  const user = userEvent.setup();
  const {props} = renderStep({consent:true});
  let resolveRead!:(value:string)=>void;
  const oldFile = new File(['pending'], 'old.json', {type:'application/json'});
  Object.defineProperty(oldFile,'text',{value:()=>new Promise<string>(resolve=>{resolveRead=resolve;})});
  const input = screen.getByLabelText('Or upload conversation JSON');
  await user.upload(input,oldFile);
  await user.upload(screen.getByLabelText('Or upload conversation JSON'),new File([JSON.stringify({messages:[{role:'user',content:'Current imported fact'}]})],'new.json',{type:'application/json'}));
  await waitFor(()=>expect(props.onImport).toHaveBeenCalledTimes(1));
  await act(async()=>resolveRead(JSON.stringify({messages:[{role:'user',content:'Stale imported fact'}]})));
  expect(props.onImport).toHaveBeenCalledTimes(1);
  expect(props.onImport).toHaveBeenLastCalledWith([{role:'user',content:'Current imported fact',message_id:undefined,timestamp:undefined}],'[user] Current imported fact');
});
