import { selectUIOption } from './ui/testHelpers';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { GroundTruthReview } from './GroundTruthReview';
import type { Memory } from '../types/domain';

const candidate: Memory = { memory_id: 'M001', conversation_id: 'C001', canonical_value: 'The backend uses PostgreSQL.', status: 'candidate', source_message_ids: ['MSG002'], relationships: [] };

function renderReview(memories: Memory[] = [candidate]) {
  const props = { memories, busy: false, onChange: vi.fn(), onAddMemory: vi.fn(), onConfirm: vi.fn() };
  return { props, ...render(<GroundTruthReview {...props} />) };
}

test('keeps confirmation unavailable until a memory is accepted or edited', () => {
  renderReview();
  expect((screen.getByRole('button', { name: 'Confirm Ground Truth & Continue' }) as HTMLButtonElement).disabled).toBe(true);
});

test('adds a missing memory through an accessible inline form', async () => {
  const user = userEvent.setup();
  const { props } = renderReview();
  await user.click(screen.getByRole('button', { name: 'Add Missing Memory' }));
  await user.type(screen.getByLabelText('Missing memory'), 'The user is based in Sydney.');
  await user.click(screen.getByRole('button', { name: 'Add Memory' }));
  expect(props.onAddMemory).toHaveBeenCalledWith('The user is based in Sydney.');
});

test('requires a user source for a manually added fact and sends its identifier without displaying it',async()=>{
  const onAddMemory=vi.fn();
  render(<GroundTruthReview memories={[candidate]} sourceMessages={[{message_id:'PRIVATE-SOURCE',role:'user',content:'我在家工作。',timestamp:'2026-01-01T00:00:00Z'}]} busy={false} onChange={vi.fn()} onConfirm={vi.fn()} onAddMemory={onAddMemory}/>);
  const user=userEvent.setup();
  await user.click(screen.getByRole('button',{name:'Add Missing Memory'}));
  await user.type(screen.getByRole('textbox',{name:'Missing memory'}),'I work from home.');
  expect((screen.getByRole('button',{name:'Add Memory'}) as HTMLButtonElement).disabled).toBe(true);
  await user.click(screen.getByRole('combobox',{name:'Supporting source messages'}));
  await user.click(screen.getByRole('option',{name:'Message 1 · user: 我在家工作。'}));
  await user.click(screen.getByRole('textbox',{name:'Missing memory'}));
  await user.click(screen.getByRole('button',{name:'Add Memory'}));
  expect(onAddMemory).toHaveBeenCalledWith('I work from home.',['PRIVATE-SOURCE']);
  expect(screen.queryByText('PRIVATE-SOURCE')).toBeNull();
});

test('edits a candidate memory without using a browser prompt', async () => {
  const user = userEvent.setup();
  const { props } = renderReview();
  await user.click(screen.getByRole('button', { name: 'Edit' }));
  const field = screen.getByLabelText('Canonical memory');
  await user.clear(field);
  await user.type(field, 'The backend now uses PostgreSQL.');
  await user.click(screen.getByRole('button', { name: 'Save edit' }));
  expect(props.onChange).toHaveBeenCalledWith(candidate, expect.objectContaining({ status: 'edited', canonical_value: 'The backend now uses PostgreSQL.' }));
});

test('filters memories by their review status without changing the ground truth', async () => {
  const user = userEvent.setup();
  const accepted: Memory = { ...candidate, memory_id: 'M002', canonical_value: 'The user prefers Python.', status: 'confirmed' };
  renderReview([candidate, accepted]);
  await selectUIOption(user, 'Show memories', 'Accepted (1)');
  expect(screen.getByText('The user prefers Python.')).not.toBeNull();
  expect(screen.queryByText('The backend uses PostgreSQL.')).toBeNull();
  expect(screen.getByText('Showing 1 of 2 memories.')).not.toBeNull();
});

test('makes an update relationship readable using both memory values', () => {
  const previous: Memory = { ...candidate, canonical_value: 'The backend used MySQL.' };
  const updated: Memory = { ...candidate, memory_id: 'M002', canonical_value: 'The backend now uses PostgreSQL.', relationships: [{ type: 'UPDATE', target_memory_id: 'M001' }] };
  renderReview([previous, updated]);
  expect(screen.getAllByText(/The backend used MySQL/)).toHaveLength(2);
  expect(screen.getByText('Relationship evidence')).not.toBeNull();
});

test('does not permit confirmation while another candidate remains unreviewed', () => {
  renderReview([{ ...candidate, status: 'confirmed' }, { ...candidate, memory_id: 'M002' }]);
  expect((screen.getByRole('button', { name: 'Confirm Ground Truth & Continue' }) as HTMLButtonElement).disabled).toBe(true);
});

test('keeps a missing-memory draft available after a rejected save', async () => {
  const user = userEvent.setup();
  render(<GroundTruthReview memories={[candidate]} busy={false} onChange={vi.fn()} onConfirm={vi.fn()} onAddMemory={vi.fn().mockRejectedValue(new Error('Memory text is too long'))} />);
  await user.click(screen.getByRole('button', { name: 'Add Missing Memory' }));
  await user.type(screen.getByLabelText('Missing memory'), 'A draft to retain');
  await user.click(screen.getByRole('button', { name: 'Add Memory' }));
  expect((await screen.findByRole('alert')).textContent).toContain('Memory text is too long');
  expect((screen.getByLabelText('Missing memory') as HTMLInputElement).value).toBe('A draft to retain');
  expect((screen.getByRole('button', { name: 'Add Memory' }) as HTMLButtonElement).disabled).toBe(false);
});
