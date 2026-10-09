import { UIAlert } from './ui';
import { Select } from 'antd';
import { UIProgress, UISelect, UIOption, UIInput, UIButton } from './ui';
import { FormEvent, useMemo, useState } from 'react';
import type { ConversationMessage, Memory, MemoryReviewPatch, MemoryStatus } from '../types/domain';
import { MemoryCard } from './MemoryCard';

type Props = {
  memories: Memory[];
  sourceMessages?: ConversationMessage[];
  busy: boolean;
  onChange: (memory: Memory, patch: MemoryReviewPatch) => void | Promise<void>;
  onAddMemory: (canonicalValue: string, sourceMessageIds?: string[]) => void | Promise<void>;
  onConfirm: () => void;
};

export function GroundTruthReview({ memories, sourceMessages = [], busy, onChange, onAddMemory, onConfirm }: Props) {
  const [adding, setAdding] = useState(false);
  const [newMemory, setNewMemory] = useState('');
  const [newSources, setNewSources] = useState<string[]>([]);
  const [additionError, setAdditionError] = useState('');
  const [addingBusy, setAddingBusy] = useState(false);
  const [statusFilter, setStatusFilter] = useState<'all' | MemoryStatus>('all');
  const accepted = memories.filter((memory) => memory.status === 'confirmed').length;
  const edited = memories.filter((memory) => memory.status === 'edited').length;
  const rejected = memories.filter((memory) => memory.status === 'rejected').length;
  const candidates = memories.filter((memory) => memory.status === 'candidate').length;
  const visibleMemories = statusFilter === 'all' ? memories : memories.filter((memory) => memory.status === statusFilter);
  const memoryLabels = useMemo(() => Object.fromEntries(memories.map((memory) => [memory.memory_id, memory.canonical_value])), [memories]);
  const sourceLabels = sourceMessages.length
    ? Object.fromEntries(sourceMessages.map((message, index) => [message.message_id, `Message ${index + 1} · ${message.role}: ${message.content.slice(0, 100)}`]))
    : Object.fromEntries([...new Set(memories.flatMap(memory => memory.source_message_ids))].map((id, index) => [id, `Source message ${index + 1}`]));
  const submitAddition = async (event: FormEvent) => {
    event.preventDefault();
    if (!newMemory.trim() || busy || addingBusy || (sourceMessages.length>0&&!newSources.length)) return;
    setAddingBusy(true); setAdditionError('');
    try {
      if(sourceMessages.length)await onAddMemory(newMemory.trim(),newSources);
      else await onAddMemory(newMemory.trim());
      setNewMemory(''); setNewSources([]); setAdding(false);
    } catch (cause) {
      setAdditionError(cause instanceof Error ? cause.message : 'The memory could not be added. Your text has been kept for retry.');
    } finally { setAddingBusy(false); }
  };

  return <section aria-labelledby="ground-truth-title">
    <h1 id="ground-truth-title">Review Extracted Memories</h1>
    <div className="summary" role="status" aria-label="Memory review summary">
      <span>Extracted {memories.length}</span><span>To review {candidates}</span><span>Accepted {accepted}</span><span>Edited {edited}</span><span>Rejected {rejected}</span>
    </div>
    {memories.length > 0 && <div className="review-progress"><div><b>{candidates === 0 ? 'All memories reviewed' : `${candidates} ${candidates === 1 ? 'memory still needs' : 'memories still need'} review`}</b><span>{memories.length - candidates} / {memories.length} reviewed</span></div><UIProgress aria-label="Memory review progress" max={memories.length} value={memories.length - candidates} /><p>{accepted + edited} accepted for reference evidence · {rejected} excluded</p></div>}
    {memories.length > 0 && <div className="review-toolbar"><label htmlFor="memory-status-filter">Show memories<UISelect aria-label={["Show memories"].join(' ')} id="memory-status-filter" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as 'all' | MemoryStatus)}><UIOption value="all">All statuses ({memories.length})</UIOption><UIOption value="candidate">To review ({candidates})</UIOption><UIOption value="confirmed">Accepted ({accepted})</UIOption><UIOption value="edited">Edited ({edited})</UIOption><UIOption value="rejected">Rejected ({rejected})</UIOption></UISelect></label><p role="status">Showing {visibleMemories.length} of {memories.length} memories.</p></div>}
    {memories.length === 0 ? <p className="empty">No candidate memories were found. Add a memory to continue.</p> : visibleMemories.length === 0 ? <p className="empty">No memories match this status. Choose another filter or add a missing memory.</p> : <div className="memory-grid">{visibleMemories.map(memory => <MemoryCard key={memory.memory_id} memory={memory} busy={busy} position={memories.indexOf(memory) + 1} sourceLabels={sourceLabels} memoryLabels={memoryLabels} onChange={(patch) => onChange(memory, patch)} />)}</div>}
    {adding ? <form className="add-memory" onSubmit={submitAddition}>
      <label htmlFor="missing-memory">Missing memory<UIInput id="missing-memory" value={newMemory} onChange={(event) => setNewMemory(event.target.value)} placeholder="Describe a fact the audit should retain" autoFocus /></label>
      {sourceMessages.length>0&&<label>Supporting source messages<Select mode="multiple" virtual={false} aria-label="Supporting source messages" style={{width:'100%'}} value={newSources} onChange={setNewSources} disabled={busy||addingBusy} options={sourceMessages.filter(message=>message.role==='user').map(message=>({value:message.message_id,label:sourceLabels[message.message_id]}))}/><small>Select the user statements that support this fact. Do not add facts absent from the conversation.</small></label>}
      <UIButton type="submit" disabled={busy || addingBusy || !newMemory.trim() || (sourceMessages.length>0&&!newSources.length)}>{addingBusy ? 'Adding…' : 'Add Memory'}</UIButton>
      {additionError && <UIAlert role="alert">{additionError}</UIAlert>}
      <UIButton type="button" className="secondary" disabled={busy || addingBusy} onClick={() => { setAdding(false); setNewMemory(''); setNewSources([]); setAdditionError(''); }}>Cancel</UIButton>
    </form> : <UIButton className="secondary" onClick={() => setAdding(true)} disabled={busy}>Add Missing Memory</UIButton>}
    <UIButton disabled={busy || candidates > 0 || !memories.some((memory) => memory.status === 'confirmed' || memory.status === 'edited')} onClick={onConfirm}>Confirm Ground Truth & Continue</UIButton>
  </section>;
}
