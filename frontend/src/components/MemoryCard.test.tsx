import { act, render, screen } from '@testing-library/react'; import userEvent from '@testing-library/user-event'; import { MemoryCard } from './MemoryCard';
const memory={memory_id:'M002',conversation_id:'C1',canonical_value:'Backend now uses PostgreSQL.',status:'candidate' as const,source_message_ids:['MSG002'],relationships:[{type:'UPDATE' as const,target_memory_id:'M001'}]};
test('allows a candidate memory to be accepted',async()=>{const change=vi.fn();render(<MemoryCard memory={memory} onChange={change}/>);await userEvent.click(screen.getByRole('button',{name:'Accept'}));expect(change).toHaveBeenCalledWith({status:'confirmed'});expect(screen.getByText(/UPDATE/)).not.toBeNull();});

test('waits for saving, shows the accepted decision, and allows undo', async () => {
  let finish!: () => void;
  const change = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
  const { rerender } = render(<MemoryCard memory={memory} onChange={change} />);
  await userEvent.click(screen.getByRole('button', { name: 'Accept' }));
  expect((screen.getByRole('button', { name: 'Saving…' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByText(/accepted and ready/)).toBeNull();
  await act(async () => { finish(); });
  rerender(<MemoryCard memory={{ ...memory, status: 'confirmed' }} onChange={change} />);
  expect((screen.getByRole('button', { name: '✓ Accepted' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('status').textContent).toContain('accepted and ready');
  expect(screen.getByRole('article').classList.contains('confirmed')).toBe(true);
  await userEvent.click(screen.getByRole('button', { name: 'Undo decision' }));
  expect(change).toHaveBeenLastCalledWith({ status: 'candidate' });
  await act(async () => { finish(); });
  rerender(<MemoryCard memory={memory} onChange={change} />);
  expect((screen.getByRole('button', { name: 'Accept' }) as HTMLButtonElement).disabled).toBe(false);
  expect(screen.queryByText(/accepted and ready/)).toBeNull();
});

test('failed saving keeps the memory pending and permits retry', async () => {
  const change = vi.fn().mockRejectedValue(new Error('unavailable'));
  render(<MemoryCard memory={memory} onChange={change} />);
  await userEvent.click(screen.getByRole('button', { name: 'Accept' }));
  expect(screen.getByRole('alert').textContent).toContain('could not be saved');
  expect((screen.getByRole('button', { name: 'Accept' }) as HTMLButtonElement).disabled).toBe(false);
  expect(screen.queryByText(/accepted and ready/)).toBeNull();
});

test('edits source evidence using readable message labels while preserving API references', async () => {
  const change = vi.fn();
  render(<MemoryCard memory={memory} sourceLabels={{ MSG002: 'Message 2: Database migration', MSG003: 'Message 3: Deployment plan' }} onChange={change} />);
  expect(document.body.textContent).not.toContain('MSG002');
  expect(document.querySelector('[title*="M002"]')).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
  await userEvent.click(screen.getByRole('checkbox', { name: 'Message 3: Deployment plan' }));
  await userEvent.click(screen.getByRole('button', { name: 'Save edit' }));
  expect(change).toHaveBeenCalledWith(expect.objectContaining({ source_message_ids: ['MSG002', 'MSG003'] }));
});

test('keeps edits available when saving fails', async () => {
  const user = userEvent.setup();
  render(<MemoryCard memory={memory} onChange={vi.fn().mockRejectedValue(new Error('Cannot save this edit'))} />);
  await user.click(screen.getByRole('button', { name: 'Edit' }));
  await user.clear(screen.getByLabelText('Canonical memory'));
  await user.type(screen.getByLabelText('Canonical memory'), 'Retain my correction');
  await user.click(screen.getByRole('button', { name: 'Save edit' }));
  expect((await screen.findByRole('alert')).textContent).toContain('Cannot save this edit');
  expect((screen.getByLabelText('Canonical memory') as HTMLInputElement).value).toBe('Retain my correction');
});

test('sends an explicit empty timestamp when the user clears a recorded date', async () => {
  const change = vi.fn();
  render(<MemoryCard memory={{ ...memory, timestamp: '2026-10-01T09:00:00Z' }} onChange={change} />);
  await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
  await userEvent.clear(screen.getByLabelText('Observed timestamp (optional)'));
  await userEvent.click(screen.getByRole('button', { name: 'Save edit' }));
  expect(change).toHaveBeenCalledWith(expect.objectContaining({ timestamp: null }));
});
