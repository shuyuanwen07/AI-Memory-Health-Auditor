import { useEffect, useState } from 'react';
import { api } from '../services/api';
import { UIButton } from './ui';

type Option = { value: string; label: string };
const familyPreferences = [
  { matches: (id: string) => /^openai\/gpt-5\.6(?:-|$)/i.test(id), prefers: ['openai/gpt-5.6', 'openai/gpt-5.6-pro'] },
  { matches: (id: string) => /^openai\/gpt-6(?:\.|-|$)/i.test(id), prefers: ['openai/gpt-6.1-sol', 'openai/gpt-6-astra', 'openai/gpt-6-sol'] },
  { matches: (id: string) => /^anthropic\/claude-opus-/i.test(id), prefers: ['anthropic/claude-opus-5.5'] },
  { matches: (id: string) => /^google\/gemini-/i.test(id), prefers: [] },
];

export function chooseVerifiedComparisonModels(options: Option[]): string[] {
  return familyPreferences.flatMap(family => {
    const candidates = options.filter(item => family.matches(item.value));
    if (!candidates.length) return [];
    const preferred = family.prefers.map(id => candidates.find(item => item.value === id)).find(Boolean);
    return [(preferred ?? candidates[0]).value];
  });
}

export function CurrentModelPreset({ disabled, onSelect }: { disabled: boolean; onSelect: (models: string) => void }) {
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    api.openRouterModels().then(options => { if (active) setModels(chooseVerifiedComparisonModels(options)); })
      .catch(() => { if (active) setModels([]); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  return <div className="actions"><UIButton disabled={disabled || loading || models.length === 0}
      onClick={() => onSelect(models.join('\n'))}>Use one verified model from each family</UIButton>
    <small>{loading ? 'Loading verified models…' : models.length ? 'Includes one available GPT‑5.6, GPT‑6, Opus and Gemini model where available.' : 'Run the model availability check to use this shortcut.'}</small></div>;
}
