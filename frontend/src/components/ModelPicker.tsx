import { useEffect, useId, useState } from 'react';
import { Select } from 'antd';
import { api } from '../services/api';
import { UIButton } from './ui';
import type { TargetProvider } from '../types/domain';

type Option = { value: string; label: string };
export function ModelPicker({ provider, value, onChange, multiple = false, disabled = false, label, defaultModel }: {
  provider: TargetProvider; value: string; onChange: (value: string) => void;
  multiple?: boolean; disabled?: boolean; label: string; defaultModel?: string;
}) {
  const helpId = useId();
  const [options, setOptions] = useState<Option[]>([]);
  const [loading, setLoading] = useState(false);
  const [failure, setFailure] = useState('');
  const [retry, setRetry] = useState(0);
  const [search, setSearch] = useState('');
  const [knownModels, setKnownModels] = useState<string[]>([]);
  useEffect(() => {
    setKnownModels([]); setSearch('');
  }, [provider]);
  useEffect(() => {
    const current = value.split(/\r?\n/).map(id => id.trim()).filter(Boolean);
    setKnownModels(previous => [...new Set([...previous, ...current])]);
  }, [provider, value]);
  useEffect(() => {
    let active = true;
    setOptions([]); setFailure('');
    if (provider !== 'openrouter' && provider !== 'ollama') { setLoading(false); return; }
    setLoading(true);
    (provider === 'ollama' ? api.ollamaModels() : api.openRouterModels()).then(items => { if (active) setOptions(items); })
      .catch((error: unknown) => { if (active) setFailure(error instanceof Error ? error.message : 'Model list could not be loaded.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [provider, retry]);
  const selected = [...new Set(value.split(/\r?\n/).map(item => item.trim()).filter(Boolean))];
  const missing = !disabled && selected.length === 0;
  const configured = [...new Set([...knownModels, ...selected, ...(defaultModel?.trim() ? [defaultModel.trim()] : [])])];
  const choices = [...configured.filter(id => !options.some(option => option.value === id))
    .map(id => ({ value: id, label: `${id} (configured model)` })), ...options];
  return <div>
    <Select aria-label={label} aria-invalid={missing} aria-describedby={missing ? helpId : undefined} status={missing ? 'error' : undefined} className="ui-select" style={{ width: '100%' }}
      showSearch optionFilterProp="label" searchValue={search} onSearch={setSearch}
      onOpenChange={() => setSearch('')} onDeselect={() => setSearch('')} loading={loading} disabled={disabled}
      mode={multiple ? 'multiple' : undefined} maxCount={multiple ? 8 : undefined}
      value={multiple ? selected : selected[0]} options={choices}
      onChange={(next: string | string[]) => { setSearch(''); onChange(Array.isArray(next) ? next.join('\n') : next); }}
      placeholder="Search available models" notFoundContent={loading ? 'Loading models…' : failure ? 'Model list unavailable — retry below' : options.length === 0 ? 'No models returned by this service' : 'No matching models'} />
    {missing && <small id={helpId} style={{ color: '#b43f45' }}>Select at least one model{multiple ? ', or deselect this service above' : ''}.</small>}
    {(failure || (!loading && options.length === 0 && (provider === 'ollama' || provider === 'openrouter'))) && <small role="status">{failure || (provider === 'ollama' ? 'No installed local models were returned. Check that a model is installed in Ollama.' : 'No text models were returned by OpenRouter.')} Configured models remain selectable; availability has not been verified. <UIButton className="text-button" onClick={() => setRetry(count => count + 1)}>Retry model list</UIButton></small>}
  </div>;
}
