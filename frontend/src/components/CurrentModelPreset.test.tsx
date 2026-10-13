import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, test, expect } from 'vitest';
import { CurrentModelPreset, chooseVerifiedComparisonModels } from './CurrentModelPreset';
import { api } from '../services/api';

vi.mock('../services/api', () => ({ api: { openRouterModels: vi.fn() } }));
const available = [
  { value: 'openai/gpt-5.6', label: 'GPT-5.6' },
  { value: 'openai/gpt-6.1-sol', label: 'GPT-6.1 Sol' },
  { value: 'openai/gpt-6-astra', label: 'GPT-6 Astra' },
  { value: 'anthropic/claude-opus-5.5', label: 'Claude Opus 5.5' },
  { value: 'google/gemini-3.1-flash', label: 'Gemini 3.1 Flash' },
];

test('preset waits for verified availability and chooses no failed or unchecked model', async () => {
  vi.mocked(api.openRouterModels).mockResolvedValue(available);
  expect(chooseVerifiedComparisonModels(available)).toEqual([
    'openai/gpt-5.6', 'openai/gpt-6.1-sol', 'anthropic/claude-opus-5.5', 'google/gemini-3.1-flash',
  ]);
  const select = vi.fn();
  render(<CurrentModelPreset disabled={false} onSelect={select} />);
  expect(select).not.toHaveBeenCalled();
  await userEvent.click(await screen.findByRole('button', { name: 'Use one verified model from each family' }));
  expect(select).toHaveBeenCalledWith('openai/gpt-5.6\nopenai/gpt-6.1-sol\nanthropic/claude-opus-5.5\ngoogle/gemini-3.1-flash');
  expect(screen.getByText(/where available/)).toBeInTheDocument();
});

test('no available models disables the shortcut', async () => {
  vi.mocked(api.openRouterModels).mockResolvedValue([]);
  render(<CurrentModelPreset disabled={false} onSelect={vi.fn()} />);
  expect(await screen.findByRole('button', { name: 'Use one verified model from each family' })).toBeDisabled();
  expect(screen.getByText(/Run the model availability check/)).toBeInTheDocument();
});
