import { FormEvent, useState } from 'react';
import type { Memory, MemoryRelationship, MemoryReviewPatch, MemoryStatus, RelationshipType } from '../types/domain';

type Props = {
  memory: Memory;
  memoryLabels?: Record<string, string>;
  onChange: (patch: MemoryReviewPatch) => void;
};

export function MemoryCard({ memory, memoryLabels = {}, onChange }: Props) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(memory.canonical_value);
  const [sourceIds, setSourceIds] = useState(memory.source_message_ids.join(', '));
  const [timestamp, setTimestamp] = useState(memory.timestamp ?? '');
  const [relationships, setRelationships] = useState<MemoryRelationship[]>(memory.relationships);
  const [relationshipType, setRelationshipType] = useState<RelationshipType>('UPDATE');
  const [relationshipTarget, setRelationshipTarget] = useState('');
  const submitEdit = (event: FormEvent) => {
    event.preventDefault();
    if (!value.trim()) return;
    onChange({
      status: 'edited', canonical_value: value.trim(),
      source_message_ids: sourceIds.split(',').map((item) => item.trim()).filter(Boolean),
      timestamp: timestamp.trim() || undefined, relationships,
    });
    setEditing(false);
  };
  const addRelationship = () => {
    if (!relationshipTarget || relationships.some((item) => item.type === relationshipType && item.target_memory_id === relationshipTarget)) return;
    setRelationships((current) => [...current, { type: relationshipType, target_memory_id: relationshipTarget }]);
    setRelationshipTarget('');
  };
  const resetEdit = () => { setValue(memory.canonical_value); setSourceIds(memory.source_message_ids.join(', ')); setTimestamp(memory.timestamp ?? ''); setRelationships(memory.relationships); setEditing(false); };
  const relationshipTargets = Object.entries(memoryLabels).filter(([id]) => id !== memory.memory_id);
  return <article className={`memory-card ${memory.status}`} aria-label={`Memory ${memory.memory_id}`}>
    <div className="row"><strong>{memory.memory_id}</strong><span className="pill">{memory.status}</span></div>
    {editing ? <form onSubmit={submitEdit} className="memory-edit">
      <label htmlFor={`memory-${memory.memory_id}`}>Canonical memory<input id={`memory-${memory.memory_id}`} value={value} onChange={(event) => setValue(event.target.value)} autoFocus /></label>
      <label htmlFor={`evidence-${memory.memory_id}`}>Source evidence IDs<input id={`evidence-${memory.memory_id}`} value={sourceIds} onChange={(event) => setSourceIds(event.target.value)} placeholder="MSG001, MSG004" /><small>Use IDs from the authorised conversation; leave empty for a researcher-added memory.</small></label>
      <label htmlFor={`timestamp-${memory.memory_id}`}>Observed timestamp (optional)<input id={`timestamp-${memory.memory_id}`} value={timestamp} onChange={(event) => setTimestamp(event.target.value)} placeholder="2026-01-01T12:00:00Z" /></label>
      <fieldset className="relationship-editor"><legend>Relationships</legend>{relationships.length === 0 ? <p className="input-help">No relationship evidence recorded.</p> : <ul>{relationships.map((relationship) => <li key={`${relationship.type}-${relationship.target_memory_id}`}><span>{relationship.type.replace('_', ' ')} → {memoryLabels[relationship.target_memory_id] ?? relationship.target_memory_id}</span><button type="button" className="ghost" onClick={() => setRelationships((current) => current.filter((item) => item !== relationship))}>Remove</button></li>)}</ul>}<div><select aria-label={`Relationship type for ${memory.memory_id}`} value={relationshipType} onChange={(event) => setRelationshipType(event.target.value as RelationshipType)}><option value="UPDATE">UPDATE</option><option value="CONFLICT">CONFLICT</option><option value="CONTEXTUAL_OVERRIDE">CONTEXTUAL OVERRIDE</option></select><select aria-label={`Relationship target for ${memory.memory_id}`} value={relationshipTarget} onChange={(event) => setRelationshipTarget(event.target.value)}><option value="">Choose another memory</option>{relationshipTargets.map(([id, label]) => <option key={id} value={id}>{id}: {label}</option>)}</select><button type="button" className="secondary" disabled={!relationshipTarget} onClick={addRelationship}>Add relationship</button></div></fieldset>
      <button type="submit" disabled={!value.trim()}>Save edit</button>
      <button type="button" className="secondary" onClick={resetEdit}>Cancel</button>
    </form> : <p>{memory.canonical_value}</p>}
    <small>Source evidence: {memory.source_message_ids.join(', ') || 'Added during review'} · {memory.timestamp ? new Date(memory.timestamp).toLocaleString() : 'No source timestamp'}</small>
    {memory.relationships.length > 0 && <div className="relationship" aria-label="Memory relationships"><strong>Relationship evidence</strong>{memory.relationships.map((relationship) => <span key={`${relationship.type}-${relationship.target_memory_id}`}><em>{memoryLabels[relationship.target_memory_id] ?? relationship.target_memory_id}</em> → <b>{relationship.type.replace('_', ' ')}</b> → <em>{memory.canonical_value}</em></span>)}</div>}
    {!editing && <div className="actions"><button onClick={() => onChange({ status: 'confirmed' })}>Accept</button><button className="secondary" onClick={() => setEditing(true)}>Edit</button><button className="ghost" onClick={() => onChange({ status: 'rejected' })}>Reject</button></div>}
  </article>;
}
