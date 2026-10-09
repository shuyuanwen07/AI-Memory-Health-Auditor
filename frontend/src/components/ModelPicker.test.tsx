import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, test, expect } from 'vitest';
import { ModelPicker } from './ModelPicker';
import { api } from '../services/api';
vi.mock('../services/api', () => ({ api: { openRouterModels: vi.fn(), ollamaModels: vi.fn() } }));
test('loads named models and submits their exact model IDs', async () => {
  vi.mocked(api.openRouterModels).mockResolvedValue([{ value: 'qwen/example', label: 'Qwen Example (qwen/example)' }]);
  const changed = vi.fn();
  render(<ModelPicker label="Test generation model" provider="openrouter" value="google/default" onChange={changed} />);
  const user = userEvent.setup();
  await waitFor(() => expect(api.openRouterModels).toHaveBeenCalled());
  await user.click(screen.getByRole('combobox', { name: 'Test generation model' }));
  await user.click(await screen.findByText('Qwen Example (qwen/example)'));
  expect(changed).toHaveBeenCalledWith('qwen/example');
});
test('multiple choices preserve the comparison payload format', async () => {
  vi.mocked(api.openRouterModels).mockResolvedValue([{ value: 'qwen/example', label: 'Qwen Example' }]);
  const changed = vi.fn();
  render(<ModelPicker label="Targets" provider="openrouter" value="google/default" multiple onChange={changed} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole('combobox', { name: 'Targets' }));
  await user.click(await screen.findByText('Qwen Example'));
  expect(changed).toHaveBeenCalledWith('google/default\nqwen/example');
});
test('failed catalog preserves selection and offers a retry', async () => {
  vi.mocked(api.openRouterModels).mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValueOnce([{value: 'google/default', label: 'Default'}]);
  render(<ModelPicker label="Evaluator" provider="openrouter" value="google/default" onChange={vi.fn()} />);
  expect(await screen.findByRole('status')).toHaveTextContent('Configured models remain selectable');
  await userEvent.click(screen.getByRole('button', { name: 'Retry model list' }));
  await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
});

test('empty model selection identifies the affected field and tells users how to proceed', async () => {
  vi.mocked(api.ollamaModels).mockResolvedValue([{ value: 'qwen3:1.7b', label: 'qwen3:1.7b' }]);
  render(<ModelPicker label="Local target models" provider="ollama" value="" multiple onChange={vi.fn()} />);
  expect(screen.getByRole('combobox', { name: 'Local target models' })).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByText('Select at least one model, or deselect this service above.')).toBeInTheDocument();
  await waitFor(() => expect(api.ollamaModels).toHaveBeenCalled());
});

test('clearing selected models does not remove the configured default from the dropdown', async () => {
  vi.mocked(api.ollamaModels).mockRejectedValue(new Error('Local model service unavailable'));
  const changed = vi.fn();
  render(<ModelPicker label="Local models" provider="ollama" value="" defaultModel="qwen3:1.7b" multiple onChange={changed} />);
  await screen.findByRole('status');
  await userEvent.click(screen.getByRole('combobox', { name: 'Local models' }));
  await userEvent.click(await screen.findByText('qwen3:1.7b (configured model)'));
  expect(changed).toHaveBeenCalledWith('qwen3:1.7b');
});

test('a removed non-default model remains available for reselection when catalog is unavailable', async () => {
  vi.mocked(api.ollamaModels).mockRejectedValue(new Error('Unavailable'));
  const changed = vi.fn();
  const { rerender } = render(<ModelPicker label="Local reselection" provider="ollama" value="qwen/custom" defaultModel="qwen3:1.7b" multiple onChange={changed} />);
  await screen.findByRole('status');
  rerender(<ModelPicker label="Local reselection" provider="ollama" value="" defaultModel="qwen3:1.7b" multiple onChange={changed} />);
  await userEvent.click(screen.getByRole('combobox', { name: 'Local reselection' }));
  await userEvent.click(await screen.findByText('qwen/custom (configured model)'));
  expect(changed).toHaveBeenCalledWith('qwen/custom');
});

test('clicking the remove icon allows the same installed model to be selected again', async () => {
  vi.mocked(api.ollamaModels).mockResolvedValue([{ value: 'qwen3:1.7b', label: 'qwen3:1.7b' }]);
  function Form() {
    const [value, setValue] = useState('qwen3:1.7b');
    return <label>Local models<ModelPicker label="Local models" provider="ollama" value={value} defaultModel="qwen3:1.7b" multiple onChange={setValue} /></label>;
  }
  const { container } = render(<Form />);
  const user = userEvent.setup();
  await waitFor(() => expect(container.querySelector('.ant-select-selection-item-remove')).not.toBeNull());
  await user.click(container.querySelector('.ant-select-selection-item-remove') as HTMLElement);
  await waitFor(() => expect(container.querySelector('.ant-select-selection-item')).toBeNull());
  await user.click(screen.getByRole('combobox', { name: 'Local models' }));
  await user.click(await screen.findByText('qwen3:1.7b', { selector: '.ant-select-item-option-content' }));
  await waitFor(() => expect(container.querySelector('.ant-select-selection-item')).not.toBeNull());
});
