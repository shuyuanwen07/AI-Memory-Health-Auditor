import type { MemoryReviewConcern } from '../services/memoryReviewConcerns';
import { UICard, UIAlert } from './ui';
import { UIInput, UIButton, UISelect, UIOption, UICheckbox } from './ui';
import { FormEvent, useState } from 'react';
import { relationshipLabel, relationshipEvidenceLabel } from '../services/display';
import type { Memory, MemoryRelationship, MemoryReviewPatch, MemoryStatus, RelationshipType } from '../types/domain';
import { Select } from 'antd';

type Props = {
  memory: Memory;
  memoryLabels?: Record<string, string>;
  memorySourceIds?: Record<string, string[]>;
  onChange: (patch: MemoryReviewPatch) => void | Promise<void>;
  busy?: boolean;
  position?: number;
  sourceLabels?: Record<string, string>;
  concerns?: MemoryReviewConcern[];
};

export function MemoryCard({ memory, memoryLabels = {}, memorySourceIds = {}, sourceLabels = {}, concerns = [], onChange, position, busy = false }: Props) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const updateDecision = async (status: MemoryStatus) => {
    setSaving(true); setError('');
    try { await onChange({ status }); }
    catch { setError('This decision could not be saved. Please try again.'); }
    finally { setSaving(false); }
  };
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(memory.canonical_value);
  const [sourceIds, setSourceIds] = useState(memory.source_message_ids);
  const [timestamp, setTimestamp] = useState(memory.timestamp ?? '');
  const [relationships, setRelationships] = useState<MemoryRelationship[]>(memory.relationships);
  const [relationshipType, setRelationshipType] = useState<RelationshipType>('UPDATE');
  const [relationshipTarget, setRelationshipTarget] = useState('');
  const [relationshipEvidenceIds, setRelationshipEvidenceIds] = useState<string[]>([]);
  const submitEdit = async (event: FormEvent) => {
    event.preventDefault();
    if (!value.trim() || busy || saving) return;
    if (timestamp.trim() && Number.isNaN(Date.parse(timestamp))) {
      setError('Enter a valid date and time, or leave the timestamp empty.');
      return;
    }
    setSaving(true); setError('');
    try {
      await onChange({status: 'edited', canonical_value: value.trim(), source_message_ids: sourceIds,
        timestamp: timestamp.trim() || null, relationships});
      setEditing(false);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The edit could not be saved. Your changes are still here.'); }
    finally { setSaving(false); }
  };
  const addRelationship = () => {
    if (!relationshipTarget || !relationshipEvidenceIds.length || relationships.some((item) => item.type === relationshipType && item.target_memory_id === relationshipTarget)) return;
    setRelationships((current) => [...current, { type: relationshipType, target_memory_id: relationshipTarget, evidence_message_ids: relationshipEvidenceIds }]);
    setRelationshipTarget('');
    setRelationshipEvidenceIds([]);
  };
  const resetEdit = () => { setValue(memory.canonical_value); setSourceIds(memory.source_message_ids); setTimestamp(memory.timestamp ?? ''); setRelationships(memory.relationships); setRelationshipEvidenceIds([]); setEditing(false); };
  const relationshipTargets = Object.entries(memoryLabels).filter(([id]) => id !== memory.memory_id);
  const sources = { ...Object.fromEntries(memory.source_message_ids.map((id, index) => [id, `Source message ${index + 1}`])), ...sourceLabels };
  const relationshipEvidenceOptions = [...new Set([...sourceIds, ...(memorySourceIds[relationshipTarget] ?? [])])]
    .map(id => [id, sources[id] ?? 'Source message'] as const);
  const accepted = memory.status === 'confirmed' || memory.status === 'edited';
  const stateLabel = memory.status === 'candidate' ? 'Needs review' : memory.status === 'rejected' ? 'Excluded' : memory.status === 'edited' ? '✓ Edited & accepted' : '✓ Accepted';
  return <UICard className={`memory-card ${memory.status}`} aria-busy={saving} aria-label={`Memory ${position ?? ''}`.trim()}>
    <div className="row"><strong>Memory{position ? ` ${position}` : ''}</strong><span className={`review-state ${memory.status}`}>{stateLabel}</span></div>
    {accepted && <p className="review-decision-note accepted" role="status">✓ This memory is accepted and ready to use as reference evidence.</p>}
    {memory.status === 'rejected' && <p className="review-decision-note rejected" role="status">This memory is excluded from the reference evidence.</p>}
    {error && <UIAlert className="alert" role="alert">{error}</UIAlert>}
    {concerns.length>0 && <div aria-label="Source wording checks"><p>Possible differences from the original wording · these checks do not decide correctness.</p>{concerns.map(concern=><UIAlert role="note" key={concern.title}><b>{concern.title}</b><p>{concern.detail}</p>{concern.sources.map(source=><blockquote key={source.message_id} style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{source.content}</blockquote>)}</UIAlert>)}</div>}
    {editing ? <form onSubmit={submitEdit} className="memory-edit">
      <label htmlFor={`memory-${position ?? 1}`}>Canonical memory<UIInput id={`memory-${position ?? 1}`} value={value} onChange={(event) => setValue(event.target.value)} autoFocus /></label>
      <fieldset><legend>Source messages</legend>{Object.entries(sources).map(([id, label]) => <UICheckbox checked={sourceIds.includes(id)} onChange={event => setSourceIds(current => event.target.checked ? [...current, id] : current.filter(value => value !== id))} className="check" key={id}>{label}</UICheckbox>)}<small>Select the conversation messages supporting this memory. Leave unchecked for a memory added during review.</small></fieldset>
      <label htmlFor={`timestamp-${position ?? 1}`}>Observed timestamp (optional)<UIInput id={`timestamp-${position ?? 1}`} value={timestamp} onChange={(event) => setTimestamp(event.target.value)} placeholder="2026-01-01T12:00:00Z" /></label>
      <fieldset className="relationship-editor"><legend>Relationships</legend>{relationships.length === 0 ? <p className="input-help">No relationship evidence recorded.</p> : <ul>{relationships.map((relationship) => <li key={`${relationship.type}-${relationship.target_memory_id}`}><span>{relationshipLabel(relationship.type)} → {memoryLabels[relationship.target_memory_id] ?? 'Related memory'}</span><UIButton type="button" className="ghost" onClick={() => setRelationships((current) => current.filter((item) => item !== relationship))}>Remove</UIButton></li>)}</ul>}<div><UISelect aria-label={`Relationship type for ${position ?? 1}`} value={relationshipType} onChange={(event) => setRelationshipType(event.target.value as RelationshipType)}><UIOption value="UPDATE">Update an older fact</UIOption><UIOption value="CONFLICT">Conflicting requirements</UIOption><UIOption value="CONTEXTUAL_OVERRIDE">Task-specific exception</UIOption></UISelect><UISelect aria-label={`Relationship target for ${position ?? 1}`} value={relationshipTarget} onChange={(event) => {setRelationshipTarget(event.target.value);setRelationshipEvidenceIds([]);}}><UIOption value="">Choose another memory</UIOption>{relationshipTargets.map(([id, label]) => <UIOption key={id} value={id}>{label}</UIOption>)}</UISelect><Select mode="multiple" virtual={false} aria-label={`Relationship source messages for ${position ?? 1}`} value={relationshipEvidenceIds} onChange={setRelationshipEvidenceIds} placeholder="Choose supporting source messages" options={relationshipEvidenceOptions.map(([id, label]) => ({value:id,label}))} /><UIButton type="button" className="secondary" disabled={!relationshipTarget || !relationshipEvidenceIds.length} onClick={addRelationship}>Add relationship</UIButton></div></fieldset>
      <UIButton type="submit" disabled={busy || saving || !value.trim()}>{saving ? 'Saving…' : 'Save edit'}</UIButton>
      <UIButton type="button" className="secondary" onClick={resetEdit}>Cancel</UIButton>
    </form> : <p>{memory.canonical_value}</p>}
    <small>Source evidence: {memory.source_message_ids.map(id => sources[id]).join(', ') || 'Added during review'} · {memory.timestamp ? new Date(memory.timestamp).toLocaleString() : 'No source timestamp'}</small>
    {memory.confidence != null && <small>Model-estimated extraction confidence: {Math.round(memory.confidence * 100)}%. Check the original wording before accepting.</small>}
    {memory.relationships.length > 0 && <div className="relationship" aria-label="Memory relationships"><strong>Relationship evidence</strong>{memory.relationships.map((relationship) => <span key={`${relationship.type}-${relationship.target_memory_id}`}><em>{memoryLabels[relationship.target_memory_id] ?? 'Related memory'}</em> → <b>{relationshipEvidenceLabel(relationship.type)}</b> → <em>{memory.canonical_value}</em><small>Supporting messages: {relationship.evidence_message_ids?.map(id => sources[id] ?? 'Source message').join(', ') || 'Not recorded; review this link manually'}</small></span>)}</div>}
    {!editing && <div className="actions review-decision-actions"><UIButton type="button" className={accepted ? 'review-accepted-button' : ''} disabled={busy || saving || accepted} onClick={() => updateDecision('confirmed')}>{saving ? 'Saving…' : accepted ? '✓ Accepted' : 'Accept'}</UIButton><UIButton type="button" className="secondary" disabled={busy || saving} onClick={() => setEditing(true)}>Edit</UIButton>{memory.status === 'candidate' ? <UIButton type="button" className="ghost" disabled={busy || saving} onClick={() => updateDecision('rejected')}>Reject</UIButton> : <UIButton type="button" className="secondary" disabled={busy || saving} onClick={() => updateDecision('candidate')}>Undo decision</UIButton>}</div>}
  </UICard>;
}
