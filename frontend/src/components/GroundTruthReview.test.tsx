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
  await user.selectOptions(screen.getByLabelText('Show memories'), 'confirmed');
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
