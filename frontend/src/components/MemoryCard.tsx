import { FormEvent, useState } from 'react';
import type { Memory } from '../types/domain';

type Props = {
  memory: Memory;
  memoryLabels?: Record<string, string>;
  onChange: (status: Memory['status'], text?: string) => void;
};

export function MemoryCard({ memory, memoryLabels = {}, onChange }: Props) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(memory.canonical_value);
  const submitEdit = (event: FormEvent) => {
    event.preventDefault();
    if (!value.trim()) return;
    onChange('edited', value.trim());
    setEditing(false);
  };
  return <article className={`memory-card ${memory.status}`} aria-label={`Memory ${memory.memory_id}`}>
    <div className="row"><strong>{memory.memory_id}</strong><span className="pill">{memory.status}</span></div>
    {editing ? <form onSubmit={submitEdit} className="memory-edit">
      <label htmlFor={`memory-${memory.memory_id}`}>Canonical memory<input id={`memory-${memory.memory_id}`} value={value} onChange={(event) => setValue(event.target.value)} autoFocus /></label>
      <button type="submit" disabled={!value.trim()}>Save edit</button>
      <button type="button" className="secondary" onClick={() => { setValue(memory.canonical_value); setEditing(false); }}>Cancel</button>
    </form> : <p>{memory.canonical_value}</p>}
    <small>Source evidence: {memory.source_message_ids.join(', ') || 'Added during review'} · {memory.timestamp ? new Date(memory.timestamp).toLocaleString() : 'No source timestamp'}</small>
    {memory.relationships.length > 0 && <div className="relationship" aria-label="Memory relationships"><strong>Relationship evidence</strong>{memory.relationships.map((relationship) => <span key={`${relationship.type}-${relationship.target_memory_id}`}><em>{memoryLabels[relationship.target_memory_id] ?? relationship.target_memory_id}</em> → <b>{relationship.type.replace('_', ' ')}</b> → <em>{memory.canonical_value}</em></span>)}</div>}
    {!editing && <div className="actions"><button onClick={() => onChange('confirmed')}>Accept</button><button className="secondary" onClick={() => setEditing(true)}>Edit</button><button className="ghost" onClick={() => onChange('rejected')}>Reject</button></div>}
  </article>;
}
