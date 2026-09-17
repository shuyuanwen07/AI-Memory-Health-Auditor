import { FormEvent, useMemo, useState } from 'react';
import type { Memory, MemoryReviewPatch, MemoryStatus } from '../types/domain';
import { MemoryCard } from './MemoryCard';

type Props = {
  memories: Memory[];
  busy: boolean;
  onChange: (memory: Memory, patch: MemoryReviewPatch) => void;
  onAddMemory: (canonicalValue: string) => void;
  onConfirm: () => void;
};

export function GroundTruthReview({ memories, busy, onChange, onAddMemory, onConfirm }: Props) {
  const [adding, setAdding] = useState(false);
  const [newMemory, setNewMemory] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | MemoryStatus>('all');
  const accepted = memories.filter((memory) => memory.status === 'confirmed').length;
  const edited = memories.filter((memory) => memory.status === 'edited').length;
  const rejected = memories.filter((memory) => memory.status === 'rejected').length;
  const candidates = memories.filter((memory) => memory.status === 'candidate').length;
  const visibleMemories = statusFilter === 'all' ? memories : memories.filter((memory) => memory.status === statusFilter);
  const memoryLabels = useMemo(() => Object.fromEntries(memories.map((memory) => [memory.memory_id, memory.canonical_value])), [memories]);
  const submitAddition = (event: FormEvent) => {
    event.preventDefault();
    if (!newMemory.trim()) return;
    onAddMemory(newMemory.trim());
    setNewMemory('');
    setAdding(false);
  };

  return <section aria-labelledby="ground-truth-title">
    <h1 id="ground-truth-title">Review Extracted Memories</h1>
    <div className="summary" role="status" aria-label="Memory review summary">
      <span>Extracted {memories.length}</span><span>To review {candidates}</span><span>Accepted {accepted}</span><span>Edited {edited}</span><span>Rejected {rejected}</span>
    </div>
    {memories.length > 0 && <div className="review-toolbar"><label htmlFor="memory-status-filter">Show memories<select id="memory-status-filter" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as 'all' | MemoryStatus)}><option value="all">All statuses ({memories.length})</option><option value="candidate">To review ({candidates})</option><option value="confirmed">Accepted ({accepted})</option><option value="edited">Edited ({edited})</option><option value="rejected">Rejected ({rejected})</option></select></label><p role="status">Showing {visibleMemories.length} of {memories.length} memories.</p></div>}
    {memories.length === 0 ? <p className="empty">No candidate memories were found. Add a memory to continue.</p> : visibleMemories.length === 0 ? <p className="empty">No memories match this status. Choose another filter or add a missing memory.</p> : <div className="memory-grid">{visibleMemories.map((memory, index) => <MemoryCard key={memory.memory_id} memory={memory} position={index + 1} memoryLabels={memoryLabels} onChange={(patch) => onChange(memory, patch)} />)}</div>}
    {adding ? <form className="add-memory" onSubmit={submitAddition}>
      <label htmlFor="missing-memory">Missing memory<input id="missing-memory" value={newMemory} onChange={(event) => setNewMemory(event.target.value)} placeholder="Describe a fact the audit should retain" autoFocus /></label>
      <button type="submit" disabled={busy || !newMemory.trim()}>Add Memory</button>
      <button type="button" className="secondary" onClick={() => { setAdding(false); setNewMemory(''); }}>Cancel</button>
    </form> : <button className="secondary" onClick={() => setAdding(true)} disabled={busy}>Add Missing Memory</button>}
    <button disabled={busy || !memories.some((memory) => memory.status === 'confirmed' || memory.status === 'edited')} onClick={onConfirm}>Confirm Ground Truth & Continue</button>
  </section>;
}
