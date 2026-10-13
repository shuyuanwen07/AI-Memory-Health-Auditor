import { useState } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, test, expect, beforeEach } from 'vitest';
import { ModelPicker } from './ModelPicker';
import { api } from '../services/api';

vi.mock('../services/api', () => ({ api: {
  openRouterModels: vi.fn(), openRouterModelChecks: vi.fn(), checkOpenRouterModel: vi.fn(), ollamaModels: vi.fn(),
} }));
const verified = { value: 'anthropic/claude-opus-5.5', label: 'Claude Opus 5.5', status: 'available' as const, checked_at: '2026-10-12T00:00:00Z' };
const unchecked = { value: 'openai/gpt-6-astra', label: 'GPT-6 Astra', status: 'not_checked' as const, checked_at: null };
const unavailable = { value: 'openai/gpt-5.6', label: 'GPT-5.6', status: 'unavailable' as const, checked_at: '2026-10-12T00:00:00Z' };
beforeEach(() => vi.resetAllMocks());

test('keeps the configured model and labels catalog availability states', async () => {
  vi.mocked(api.openRouterModelChecks).mockResolvedValue([verified, unchecked, unavailable]);
  const changed = vi.fn();
  render(<ModelPicker label="Test generation model" provider="openrouter" value="openai/gpt-5.6" onChange={changed} />);
  expect(await screen.findByText('3 catalog models · availability is checked separately')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('combobox', { name: 'Test generation model' }));
  const listbox = await screen.findByRole('listbox');
  expect(within(listbox).getByRole('option', { name: /Claude Opus 5\.5.*recently checked/ })).toBeInTheDocument();
  expect(within(listbox).getByRole('option', { name: /GPT-6 Astra.*not checked/ })).toBeInTheDocument();
  expect(within(listbox).getByRole('option', { name: /GPT-5\.6.*last check failed/ })).toBeInTheDocument();
  expect(changed).not.toHaveBeenCalled();
});

test('checks only selected catalog models sequentially and shows the new status', async () => {
  vi.mocked(api.openRouterModelChecks).mockResolvedValue([unchecked, unavailable]);
  vi.mocked(api.checkOpenRouterModel).mockResolvedValue({ model: unchecked.value, status: 'available', checked_at: '2026-10-12T00:00:00Z' });
  const user = userEvent.setup();
  render(<ModelPicker label="Models" provider="openrouter" value={`${unchecked.value}\n${unavailable.value}`} multiple onChange={vi.fn()} />);
  await screen.findByText('2 catalog models · availability is checked separately');
  await user.click(screen.getByRole('button', { name: 'Check selected model availability' }));
  await waitFor(() => expect(api.checkOpenRouterModel).toHaveBeenCalledTimes(2));
  expect(api.checkOpenRouterModel).toHaveBeenNthCalledWith(1, unchecked.value);
  expect(api.checkOpenRouterModel).toHaveBeenNthCalledWith(2, unavailable.value);
  await waitFor(() => expect(screen.getByText(/Selected model status: GPT-6 Astra — recently checked · GPT-5\.6 — recently checked/)).toBeInTheDocument());
  await user.click(screen.getByRole('combobox', { name: 'Models' }));
  const listbox = await screen.findByRole('listbox');
  expect(within(listbox).getByRole('option', { name: /GPT-6 Astra.*recently checked/ })).toBeInTheDocument();
  expect(within(listbox).getByRole('option', { name: /GPT-5\.6.*recently checked/ })).toBeInTheDocument();
});

test('multiple configured selections remain visible with their individual check status', async () => {
  vi.mocked(api.openRouterModelChecks).mockResolvedValue([verified, unchecked]);
  const changed = vi.fn();
  render(<ModelPicker label="Targets" provider="openrouter" value={`${verified.value}\n${unchecked.value}`} multiple onChange={changed} />);
  expect(await screen.findByText(/Selected model status: Claude Opus 5\.5 — recently checked · GPT-6 Astra — not checked/)).toBeInTheDocument();
  expect(changed).not.toHaveBeenCalled();
});

test('catalog failure offers retry while preserving the configured selection', async () => {
  vi.mocked(api.openRouterModelChecks).mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValueOnce([verified]);
  const changed = vi.fn();
  render(<ModelPicker label="Evaluator" provider="openrouter" value="openai/gpt-5.6" onChange={changed} />);
  expect(await screen.findByText(/Your configured model remains selectable/)).toBeInTheDocument();
  expect(changed).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Retry catalog' }));
  await waitFor(() => expect(api.openRouterModelChecks).toHaveBeenCalledTimes(2));
  expect(await screen.findByText('1 catalog model · availability is checked separately')).toBeInTheDocument();
  expect(changed).not.toHaveBeenCalled();
});

test('local models preserve configured choices when Ollama list is unavailable', async () => {
  vi.mocked(api.ollamaModels).mockRejectedValue(new Error('Unavailable'));
  render(<ModelPicker label="Local models" provider="ollama" value="" defaultModel="qwen3:1.7b" multiple onChange={vi.fn()} />);
  await screen.findByRole('status');
  await userEvent.click(screen.getByRole('combobox', { name: 'Local models' }));
  await userEvent.click(await screen.findByText('qwen3:1.7b (configured model)'));
  expect(screen.getByRole('combobox', { name: 'Local models' })).toBeInTheDocument();
});

test('a fixed rules identity remains user-friendly and disabled', () => {
  render(<ModelPicker label="Baseline identity" provider="rule_based" value="rule-based-target-ai" disabled onChange={vi.fn()} />);
  expect(screen.getByRole('combobox', { name: 'Baseline identity' })).toBeDisabled();
});
