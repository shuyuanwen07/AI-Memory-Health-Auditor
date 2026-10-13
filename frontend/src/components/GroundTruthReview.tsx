import { memoryReviewConcerns } from '../services/memoryReviewConcerns';
import { UIAlert } from './ui';
import { Select } from 'antd';
import { UIProgress, UISelect, UIOption, UIInput, UIButton } from './ui';
import { FormEvent, useMemo, useState } from 'react';
import type { AgentExecution, ConversationMessage, Memory, MemoryReviewPatch, MemoryReviewReport, MemoryStatus } from '../types/domain';
import { MemoryCard } from './MemoryCard';
import { UIPanel, UISummary } from './ui';

type Props = {
  memories: Memory[];
  sourceMessages?: ConversationMessage[];
  memoryReview?: MemoryReviewReport | null;
  agentExecutions?: AgentExecution[];
  busy: boolean;
  onChange: (memory: Memory, patch: MemoryReviewPatch) => void | Promise<void>;
  onAddMemory: (canonicalValue: string, sourceMessageIds?: string[]) => void | Promise<void>;
  onConfirm: () => void;
};

export function GroundTruthReview({ memories, sourceMessages = [], memoryReview, agentExecutions = [], busy, onChange, onAddMemory, onConfirm }: Props) {
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
  const memorySourceIds = useMemo(() => Object.fromEntries(memories.map((memory) => [memory.memory_id, memory.source_message_ids])), [memories]);
  const sourceLabels = sourceMessages.length
    ? Object.fromEntries(sourceMessages.map((message, index) => [message.message_id, `Message ${index + 1} · ${message.role}: ${message.content.slice(0, 100)}${message.content.length > 100 ? '…' : ''}`]))
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
    <p className="input-help">Here, “ground truth” means the conversation-supported facts you accept or correct. These facts are the reference for checking audit answers.</p>
    {sourceMessages.length > 0 && <UIPanel className="review-source-history">
      <UISummary>Read the complete original conversation · {sourceMessages.length} {sourceMessages.length === 1 ? 'message' : 'messages'}</UISummary>
      <p>Card previews may be shortened. Check the full wording below, including qualifications and later corrections, before accepting a memory.</p>
      <ol>{sourceMessages.map((message, index) => <li key={message.message_id}>
        <b>Message {index + 1} · {message.role === 'user' ? 'User' : message.role === 'assistant' ? 'Assistant' : message.role}</b>
        <p style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{message.content}</p>
      </li>)}</ol>
    </UIPanel>}
    {memoryReview && <UIPanel className="agent-memory-review" aria-label="Independent memory review">
      <UISummary>Second source check · advisory only</UISummary>
      {memoryReview.status === 'failed' ? <UIAlert role="status">{memoryReview.notice}</UIAlert> : memoryReview.findings.length === 0
        ? <p>No additional concerns were returned. This does not prove that every relevant memory was found; check the source conversation above.</p>
        : <><p>The second review found {memoryReview.finding_count} item{memoryReview.finding_count === 1 ? '' : 's'} to check. Your decisions remain yours; nothing is accepted automatically.</p>
          <ul>{memoryReview.findings.map((finding, index) => <li key={`${finding.kind}-${index}`}>
            <strong>{finding.kind.replaceAll('_', ' ')}</strong>
            {finding.memory_ids.length > 0 && <p>Related memories: {finding.memory_ids.map(id => memoryLabels[id] ?? 'Memory').join('; ')}</p>}
            <p>{finding.reason}</p>
            <small>Source messages: {finding.evidence_message_ids.map(id => sourceLabels[id] ?? 'Source message').join(', ')} · model estimate {Math.round(finding.confidence * 100)}%, not a human label</small>
            {finding.suggested_memory && <div><p>Possible missing memory: {finding.suggested_memory}</p><UIButton className="secondary" disabled={busy} onClick={() => void onAddMemory(finding.suggested_memory!, finding.evidence_message_ids)}>Add as a candidate to review</UIButton></div>}
          </li>)}</ul>
        </>}
    </UIPanel>}
    <UIPanel className="agent-execution-history" aria-label="Processing record">
      <UISummary>How this review was prepared</UISummary>
      <p>An Agent is an AI task worker for one audit step, such as extracting memories or checking source coverage. The record below shows which service and model ran each step.</p>
      {agentExecutions.length === 0 ? <p>No model-agent calls were recorded for this extraction step. Check the selected service or retry an incomplete extraction.</p>
        : <ol>{agentExecutions.map((execution) => <li key={execution.execution_id}>
          <strong>{({memory_extraction:'Memory extraction',relationship_analysis:'Relationship check',independent_memory_review:'Second source check',coverage_planning:'Coverage plan',test_generation:'Question generation',test_review:'Question review',target_memory_retrieval:'Target memory retrieval',blind_evaluation:'Blind answer review'} as Record<string,string>)[execution.role] ?? 'Processing step'}</strong>
          <span> · {execution.status === 'completed' ? 'Completed' : execution.status === 'failed' ? 'Needs attention' : 'Not run'}</span>
          <p>Service and model: {execution.provider} · {execution.reported_model ?? execution.model} · {execution.attempt_count} request{execution.attempt_count === 1 ? '' : 's'}{execution.elapsed_ms != null ? ` · ${(execution.elapsed_ms / 1000).toFixed(1)} seconds` : ''}</p>
          {execution.error_summary && <UIAlert role="status">{execution.error_summary}</UIAlert>}
          <details><summary>Show evidence links and version</summary>
            <p>Prompt version: {execution.prompt_template_version} · Prompt fingerprint: {execution.prompt_fingerprint}</p>
            <p>Input fingerprint: {execution.input_fingerprint}</p>
            <p>Input references: {JSON.stringify(execution.input_refs)}</p>
            {execution.handoff_from && <p>Continued from an earlier processing step.</p>}
            {execution.output_data != null && <pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(execution.output_data, null, 2)}</pre>}
          </details>
        </li>)}</ol>}
    </UIPanel>
    <div className="summary" role="status" aria-label="Memory review summary">
      <span>Extracted {memories.length}</span><span>To review {candidates}</span><span>Accepted {accepted}</span><span>Edited {edited}</span><span>Rejected {rejected}</span>
    </div>
    {memories.length > 0 && <div className="review-progress"><div><b>{candidates === 0 ? 'All memories reviewed' : `${candidates} ${candidates === 1 ? 'memory still needs' : 'memories still need'} review`}</b><span>{memories.length - candidates} / {memories.length} reviewed</span></div><UIProgress aria-label="Memory review progress" max={memories.length} value={memories.length - candidates} /><p>{accepted + edited} accepted for reference evidence · {rejected} excluded</p></div>}
    {memories.length > 0 && <div className="review-toolbar"><label htmlFor="memory-status-filter">Show memories<UISelect aria-label={["Show memories"].join(' ')} id="memory-status-filter" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as 'all' | MemoryStatus)}><UIOption value="all">All statuses ({memories.length})</UIOption><UIOption value="candidate">To review ({candidates})</UIOption><UIOption value="confirmed">Accepted ({accepted})</UIOption><UIOption value="edited">Edited ({edited})</UIOption><UIOption value="rejected">Rejected ({rejected})</UIOption></UISelect></label><p role="status">Showing {visibleMemories.length} of {memories.length} memories.</p></div>}
    {memories.length === 0 ? <p className="empty">No candidate memories were found. Add a memory to continue.</p> : visibleMemories.length === 0 ? <p className="empty">No memories match this status. Choose another filter or add a missing memory.</p> : <div className="memory-grid">{visibleMemories.map(memory => <MemoryCard concerns={memoryReviewConcerns(memory,memories,sourceMessages)} key={memory.memory_id} memory={memory} busy={busy} position={memories.indexOf(memory) + 1} sourceLabels={sourceLabels} memoryLabels={memoryLabels} memorySourceIds={memorySourceIds} onChange={(patch) => onChange(memory, patch)} />)}</div>}
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
