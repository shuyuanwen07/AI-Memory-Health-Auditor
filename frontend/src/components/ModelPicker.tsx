import { useEffect, useId, useRef, useState } from 'react';
import { Progress, Select } from 'antd';
import { api } from '../services/api';
import { modelDisplayName } from '../services/display';
import { UIButton } from './ui';
import type { ModelAvailabilityOption, TargetProvider } from '../types/domain';

type Option = { value: string; label: string };
export function ModelPicker({ provider, value, onChange, multiple = false, disabled = false, label, defaultModel }: {
  provider: TargetProvider; value: string; onChange: (value: string) => void;
  multiple?: boolean; disabled?: boolean; label: string; defaultModel?: string;
}) {
  const helpId = useId();
  const [options, setOptions] = useState<Option[]>([]);
  const [candidates, setCandidates] = useState<ModelAvailabilityOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(false);
  const [failure, setFailure] = useState('');
  const [checkFailure, setCheckFailure] = useState('');
  const [retry, setRetry] = useState(0);
  const [search, setSearch] = useState('');
  const [knownModels, setKnownModels] = useState<string[]>([]);
  const [checkProgress, setCheckProgress] = useState({ completed: 0, total: 0, current: '' });
  const stopChecks = useRef(false);
  useEffect(() => {
    setKnownModels([]); setSearch('');
  }, [provider]);
  useEffect(() => {
    if (provider === 'ollama') {
      const current = value.split(/\r?\n/).map(id => id.trim()).filter(Boolean);
      setKnownModels(previous => [...new Set([...previous, ...current])]);
    }
  }, [provider, value]);
  useEffect(() => {
    let active = true;
    stopChecks.current = true;
    setChecking(false); setCandidates([]); setOptions([]); setFailure(''); setCheckFailure('');
    if (provider !== 'openrouter' && provider !== 'ollama') { setLoading(false); return; }
    setLoading(true);
    const load = provider === 'ollama'
      ? api.ollamaModels().then(items => { if (active) setOptions(items); })
      : api.openRouterModelChecks().then(items => {
        if (active) {
          setCandidates(items);
          setOptions(items.map(({ value, label }) => ({ value, label })));
        }
      });
    load.catch(() => { if (active) {
      setFailure(provider === 'ollama'
        ? 'The local model list could not be loaded. Check that Ollama is running, then retry.'
        : 'The cloud model list could not be loaded. Your configured model remains selectable; check the connection to browse the catalog.');
    } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; stopChecks.current = true; };
  }, [provider, retry]);

  const selected = [...new Set(value.split(/\r?\n/).map(item => item.trim()).filter(Boolean))];
  const shownSelection = selected;
  const missing = !disabled && shownSelection.length === 0;
  const configured = [...new Set([...knownModels, ...selected, ...(defaultModel?.trim() ? [defaultModel.trim()] : [])])];
  const statusLabel = (status: ModelAvailabilityOption['status']) => ({
    available: 'recently checked', unavailable: 'last check failed', checking: 'check in progress', not_checked: 'not checked',
  }[status]);
  const cloudOptions = candidates.map(item => ({ value: item.value, label: `${item.label} · ${statusLabel(item.status)}` }));
  const cloudIds = new Set(cloudOptions.map(item => item.value));
  const choices = provider === 'openrouter' ? [
    ...cloudOptions,
    ...configured.filter(id => !cloudIds.has(id)).map(id => ({
      value: id,
      label: `${modelDisplayName(id)} (configured model · not checked)`,
    })),
  ] : [
    ...configured.filter(id => !options.some(option => option.value === id))
      .map(id => ({ value: id, label: id === 'rule-based-target-ai' ? modelDisplayName(id) : `${modelDisplayName(id)} (configured model)` })),
    ...options,
  ];
  const checkableSelection = selected.filter(id => candidates.some(item => item.value === id));
  const runChecks = async () => {
    if (checking || provider !== 'openrouter' || checkableSelection.length === 0) return;
    stopChecks.current = false; setChecking(true); setFailure(''); setCheckFailure('');
    setCheckProgress({ completed: 0, total: checkableSelection.length, current: '' });
    for (let index = 0; index < checkableSelection.length; index += 1) {
      if (stopChecks.current) break;
      const model = checkableSelection[index];
      const candidate = candidates.find(item => item.value === model);
      setCheckProgress({ completed: index, total: checkableSelection.length, current: candidate?.label ?? model });
      try {
        const result = await api.checkOpenRouterModel(model);
        if (stopChecks.current) break;
        setCandidates(previous => previous.map(item => item.value === model
          ? { ...item, status: result.status, checked_at: result.checked_at, reason: result.reason } : item));
      } catch {
        if (stopChecks.current) break;
        setCheckFailure('The selected model could not be checked. It remains selectable; the actual request will confirm access.');
      }
      setCheckProgress({ completed: index + 1, total: checkableSelection.length, current: '' });
    }
    if (!stopChecks.current) setChecking(false);
  };
  const stop = () => { stopChecks.current = true; setChecking(false); setCheckProgress(previous => ({ ...previous, current: '' })); };
  const failed = candidates.filter(item => item.status === 'unavailable');
  const selectedAvailability = selected.map(id => candidates.find(item => item.value === id)).filter((item): item is ModelAvailabilityOption => Boolean(item));
  return <div>
    <Select aria-label={label} aria-invalid={missing} aria-describedby={missing ? helpId : undefined} status={missing ? 'error' : undefined} className="ui-select" style={{ width: '100%' }}
      showSearch optionFilterProp="label" searchValue={search} onSearch={setSearch}
      onOpenChange={() => setSearch('')} onDeselect={() => setSearch('')} loading={loading} disabled={disabled}
      optionRender={option => <span>{(option.data as Option).label}</span>}
      mode={multiple ? 'multiple' : undefined} maxCount={multiple ? 8 : undefined}
      value={multiple ? shownSelection : shownSelection[0]} options={choices} virtual={false}
      onChange={(next: string | string[]) => { setSearch(''); onChange(Array.isArray(next) ? next.join('\n') : next); }}
      placeholder="Search models" notFoundContent={loading ? 'Loading model catalog…' : failure ? 'The model catalog could not be loaded' : choices.length === 0 ? 'No models are listed yet' : 'No matching models'} />
    {missing && <small id={helpId} style={{ color: '#b43f45' }}>Select a model{multiple ? ', or deselect this service above' : ''}.</small>}
    {provider === 'openrouter' && <div className="model-availability" aria-live="polite">
      {loading && <small role="status">Loading model catalog…</small>}
      {!loading && <small>{candidates.length} catalog {candidates.length === 1 ? 'model' : 'models'} · availability is checked separately</small>}
      {selectedAvailability.length > 0 && <small>Selected model status: {selectedAvailability.map(item => `${item.label} — ${statusLabel(item.status)}`).join(' · ')}</small>}
      {checking && <>
        <Progress aria-label="Model availability check progress" percent={checkProgress.total ? Math.round(checkProgress.completed / checkProgress.total * 100) : 100}
          format={() => `${checkProgress.completed} of ${checkProgress.total}`} size="small" />
        {checkProgress.current && <small role="status">Checking {checkProgress.current}…</small>}
        <UIButton className="text-button" onClick={stop}>Stop after this check</UIButton>
      </>}
      {!checking && <UIButton className="text-button" disabled={disabled || loading || checkableSelection.length === 0}
        onClick={() => void runChecks()}>{selectedAvailability.some(item => item.status === 'available') ? 'Recheck selected model' : 'Check selected model availability'}</UIButton>}
      {selected.length > 0 && checkableSelection.length === 0 && <small>The configured model is not in the current catalog. It remains selected; its access will be confirmed when you use it.</small>}
      {checkFailure && <small role="status">{checkFailure}</small>}
      {failure && <small role="status">{failure} <UIButton className="text-button" onClick={() => setRetry(count => count + 1)}>Retry catalog</UIButton></small>}
      {!loading && candidates.length === 0 && !failure && <small>No catalog models were returned. A configured model can still be used.</small>}
      {failed.length > 0 && <details><summary>Unavailable models ({failed.length})</summary>
        <ul>{failed.map(item => <li key={item.value}>{item.label}{item.reason ? ` · ${item.reason}` : ''}</li>)}</ul>
      </details>}
      <small>Availability checks reflect a recent request and do not guarantee long-term service access.</small>
    </div>}
    {provider === 'ollama' && (failure || (!loading && options.length === 0)) && <small role="status">{failure || 'No installed local models were returned. Check that a model is installed in Ollama.'} <UIButton className="text-button" onClick={() => setRetry(count => count + 1)}>Retry model list</UIButton></small>}
  </div>;
}
