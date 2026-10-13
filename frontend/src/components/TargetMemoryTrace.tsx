import { memoryMaintenanceLabel, memoryStrategyLabel, modelDisplayName } from '../services/display';
import { UIAlert, UICard } from './ui';
import { UIButton, UIPanel, UISummary } from './ui';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services/api';
import { retrievalExplanation } from '../services/display';
import type { TargetMemoryTrace as Trace } from '../types/domain';

const memoryStates: Record<string, [string, string]> = {
  ACTIVE: ['Current', 'Retained as a current memory. The selected strategy still decides whether to send it.'],
  SUPERSEDED: ['Replaced by newer information', 'Kept as history after an update. Newer information now applies.'],
  CONFLICTED: ['Needs clarification', 'Conflicting requirements remain unresolved. Check the original conversation before choosing one.'],
  EVICTED: ['Removed from retained memory', 'No longer retained for ordinary retrieval. The record remains visible here as audit evidence.'],
  DIAGNOSTIC_ONLY: ['Diagnostic evidence only', 'Added for a diagnostic check. This is not ordinary stored memory.'],
};
const memoryEvents: Record<string, string> = {
  INGESTED: 'Conversation received', WRITTEN: 'Memory saved', UPDATED: 'Memory updated',
  CONFLICT_RECORDED: 'Conflicting requirements found', CONTEXTUAL_OVERRIDE_RECORDED: 'Task-specific exception saved',
  MAINTENANCE_APPLIED: 'Stored memories checked', RETRIEVED: 'Memories selected for a question',
};
const memoryScopes: Record<string, string> = {
  profile: 'Personal information', preference: 'General preference',
  project_requirement: 'Project requirement', episodic: 'Conversation detail',
};
const memoryRelationships: Record<string, string> = {
  UPDATE: 'Replaces an older fact', CONFLICT: 'Conflicts with another requirement',
  CONTEXTUAL_OVERRIDE: 'Applies instead of a general preference for this task',
};

export function TargetMemoryTrace({ runId }: { runId: string }) {
  return <TargetMemoryTraceSession key={runId} runId={runId}/>;
}
function TargetMemoryTraceSession({ runId }: { runId: string }) {
  const [trace, setTrace] = useState<Trace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const load = async () => { setLoading(true); setError(''); try { setTrace(await api.targetMemoryTrace(runId)); } catch (cause) { setError(cause instanceof Error ? cause.message : 'The target memory trace could not be loaded.'); } finally { setLoading(false); } };
  return <section className="target-memory-trace" aria-label="Target agent memory trace">
    <div className="failure-heading"><div><h2>Memory retrieval and model input</h2></div>{!trace && <UIButton type="button" className="secondary" disabled={loading} onClick={load}>{loading ? 'Loading evidence…' : 'Inspect Memory Trace'}</UIButton>}</div>
    {error && <UIAlert role="alert" className="alert">{error}</UIAlert>}
    {trace?.target_system_adapter==='external-http'&&<UIAlert className="alert">Independent target service: internal memory writes, retrieval decisions and actual model input are unobserved. An empty trace does not mean that no memory was used.</UIAlert>}
    {trace?.shared_answer_source_run_id&&<UIAlert role="status">This review reused the saved target answers without another model call. <Link to={`/audits/${trace.shared_answer_source_run_id}`}>View the original memory and model-input evidence</Link>.</UIAlert>}
    {trace && !trace.shared_answer_source_run_id && trace.target_system_adapter!=='external-http'&&<><p className="trace-note">Memory retrieval: <b>{trace.retrieval_mode === 'agent' ? 'AI retrieval Agent' : memoryStrategyLabel(trace.memory_strategy)}</b>{trace.retrieval_mode === 'agent' && trace.retrieval_provider && <> · {trace.retrieval_provider} · {trace.retrieval_model ? modelDisplayName(trace.retrieval_model) : 'model not recorded'}</>} · Memory updates: <b>{memoryMaintenanceLabel(trace.memory_maintenance_policy)}</b> · Configured retained-record limit: <b>{trace.target_memory_capacity ?? 'Not recorded'}</b>. Protected unresolved conflicts may exceed this limit.</p>
      <h3>Stored memories</h3><div className="trace-records">{trace.records.map((record, index) => {
        const [state, explanation] = memoryStates[record.lifecycle_state] ?? ['Status unavailable', 'This saved record has an unrecognised status. Its availability for retrieval is unknown.'];
        return <UICard className="trace-record" key={record.memory_id}><div className="row"><b>Memory record {index + 1}</b><span className={`trace-state ${record.lifecycle_state.toLowerCase()}`}>{state}</span></div><p>{record.canonical_value}</p><p className="trace-note">{explanation}</p><small>{memoryScopes[record.scope ?? 'episodic'] ?? 'Other memory category'} · recorded from {record.source_message_ids.length || 'no'} conversation message{record.source_message_ids.length === 1 ? '' : 's'}</small>{record.relationships.length > 0 && <p className="trace-note">Related memory changes: {record.relationships.map((relation) => memoryRelationships[relation.type.toUpperCase()] ?? 'Other recorded relationship').join(', ')}</p>}</UICard>;
      })}</div>
      <h3>Memory activity</h3><ul className="trace-events">{trace.events.map((event) => <li key={event.event_id}><b>{memoryEvents[event.event_type] ?? 'Other recorded memory activity'}</b> · {event.created_at ? new Date(event.created_at).toLocaleString() : 'Recorded during this audit'}</li>)}</ul>
      <h3>What was retrieved and sent</h3><p className="trace-note">Retrieved records can be filtered before sending. Sending a record does not prove that the model relied on it.</p>
      {trace.retrievals.length ? <div className="trace-retrievals">{trace.retrievals.map((retrieval, index) => <UIPanel key={retrieval.retrieval_id}>
        <UISummary><b>Retrieval {index + 1}</b> · {retrieval.selected_memory_ids.length} records retrieved · {retrieval.memory_input ? `${retrieval.memory_input.record_count} supplied to target` : 'Target input not recorded'}</UISummary>
        <p>{retrieval.final_response_id ? 'Linked to saved response' : 'No saved response for this attempt'}</p>
        <p><b>Question:</b> {retrieval.question ?? 'Question text is unavailable for this historical attempt.'}</p>
        {!retrieval.memory_input && <p className="trace-note">Actual target input is unknown for this attempt. Historical retrieval records cannot confirm what was sent.</p>}
        {retrieval.memory_input?.record_count === 0 && <UIAlert className="alert">No memory was supplied for this answer. A correct answer here does not demonstrate memory retrieval or memory use.</UIAlert>}
        <ul>{retrieval.ranking_evidence.map((item, ranking) => {
          const memoryId = String(item.memory_id);
          const recordIndex = trace.records.findIndex(record => record.memory_id === memoryId);
          const record = trace.records[recordIndex];
          const retrieved = retrieval.selected_memory_ids.includes(memoryId);
          const sentIds = retrieval.memory_input?.sent_memory_ids;
          const sent = sentIds == null ? 'sending unknown' : sentIds.includes(memoryId) ? 'supplied to target' : 'not supplied to target';
          const reason = String(item.reason ?? '');
          const agentReason = trace.retrieval_mode === 'agent' && item.candidate_sent_to_agent === true;
          return <li key={`${memoryId}-${ranking}`}><b>{record ? `Memory record ${recordIndex + 1}` : 'Related memory'}</b> — {retrieved ? 'retrieved' : 'not retrieved'}; {sent}; {agentReason ? `Agent decision: ${reason}` : retrievalExplanation(reason)}{record && <p>{record.canonical_value}</p>}</li>;
        })}</ul>
        {(retrieval.memory_input?.sent_memory_ids ?? []).filter(id => !retrieval.ranking_evidence.some(item => String(item.memory_id) === id)).map(id => {
          const recordIndex = trace.records.findIndex(record => record.memory_id === id);
          const record = trace.records[recordIndex];
          return <UICard key={id}><b>{record ? `Memory record ${recordIndex + 1}` : 'Supplemental record'} · supplied to target</b><p>{record?.canonical_value ?? 'Record text is unavailable.'}</p><small>Supplied outside ordinary retrieval ranking. Diagnostic source supplementation is an oracle probe, not a production repair.</small></UICard>;
        })}
        {retrieval.memory_input && <small>The final model input was recorded for verification.</small>}
      </UIPanel>)}</div> : <p className="empty">No retrieval decisions were recorded.</p>}</>}

  </section>;
}
