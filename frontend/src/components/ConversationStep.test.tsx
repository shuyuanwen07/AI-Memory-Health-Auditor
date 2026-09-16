import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ComponentProps } from 'react';
import { ConversationStep } from './ConversationStep';

function renderStep(overrides: Partial<ComponentProps<typeof ConversationStep>> = {}) {
  const props = {
    text: 'A conversation', consent: false, busy: false,
    onTextChange: vi.fn(), onConsentChange: vi.fn(), onImport: vi.fn(), onImportError: vi.fn(), onClearDraft: vi.fn(), onContinue: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<ConversationStep {...props} />) };
}

test('requires authorisation before continuing', async () => {
  const user = userEvent.setup();
  const { props } = renderStep();
  expect((screen.getByRole('button', { name: 'Continue to Ground Truth' }) as HTMLButtonElement).disabled).toBe(true);
  await user.click(screen.getByRole('checkbox'));
  expect(props.onConsentChange).toHaveBeenCalledWith(true);
});

test('imports valid JSON conversation messages without discarding IDs or timestamps', async () => {
  const user = userEvent.setup();
  const { props } = renderStep();
  const file = new File([JSON.stringify({ messages: [{ message_id: 'source-101', role: 'user', content: 'I prefer Python.', timestamp: '2026-01-01T00:00:00Z' }] })], 'conversation.json', { type: 'application/json' });
  await user.upload(screen.getByLabelText('Or upload conversation JSON'), file);
  await waitFor(() => expect(props.onImport).toHaveBeenCalledWith([{ message_id: 'source-101', role: 'user', content: 'I prefer Python.', timestamp: '2026-01-01T00:00:00Z' }], '[user] I prefer Python.'));
  expect(props.onImportError).toHaveBeenCalledWith('');
  expect(screen.getByText('1 message imported successfully.')).not.toBeNull();
});

test('reports invalid JSON uploads without replacing the conversation', async () => {
  const user = userEvent.setup();
  const { props } = renderStep();
  await user.upload(screen.getByLabelText('Or upload conversation JSON'), new File(['{}'], 'invalid.json', { type: 'application/json' }));
  await waitFor(() => expect(props.onImportError).toHaveBeenCalledWith(expect.stringContaining('messages array')));
  expect(props.onImport).not.toHaveBeenCalled();
  expect(screen.getByText('Import was not completed. Your pasted conversation has not been changed.')).not.toBeNull();
});

test('rejects a JSON upload over the client-side safety limit before parsing it', async () => {
  const user = userEvent.setup();
  const { props } = renderStep();
  const oversized = new File(['x'.repeat(1_000_001)], 'oversized.json', { type: 'application/json' });
  await user.upload(screen.getByLabelText('Or upload conversation JSON'), oversized);
  await waitFor(() => expect(props.onImportError).toHaveBeenCalledWith(expect.stringContaining('larger than 1 MB')));
  expect(props.onImport).not.toHaveBeenCalled();
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
