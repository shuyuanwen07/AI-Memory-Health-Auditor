import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ComponentProps } from 'react';
import { ConversationStep } from './ConversationStep';

function renderStep(overrides: Partial<ComponentProps<typeof ConversationStep>> = {}) {
  const props = {
    text: 'A conversation', consent: false, busy: false,
    onTextChange: vi.fn(), onConsentChange: vi.fn(), onImport: vi.fn(), onImportError: vi.fn(), onContinue: vi.fn(),
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

test('imports valid JSON conversation messages', async () => {
  const user = userEvent.setup();
  const { props } = renderStep();
  const file = new File([JSON.stringify({ messages: [{ role: 'user', content: 'I prefer Python.' }] })], 'conversation.json', { type: 'application/json' });
  await user.upload(screen.getByLabelText('Or upload conversation JSON'), file);
  await waitFor(() => expect(props.onImport).toHaveBeenCalledWith('[user] I prefer Python.'));
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

test('does not treat whitespace-only input as a conversation', () => {
  renderStep({ text: '   \n  ', consent: true });
  expect(screen.getByText('Add at least one non-empty message to continue.')).not.toBeNull();
  expect((screen.getByRole('button', { name: 'Continue to Ground Truth' }) as HTMLButtonElement).disabled).toBe(true);
});
