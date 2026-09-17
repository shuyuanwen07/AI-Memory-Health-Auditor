import { useState } from 'react';
import { api } from '../services/api';
import type { TargetMemoryTrace as Trace } from '../types/domain';

function pretty(value: string) { return value.replaceAll('_', ' ').toLowerCase(); }

export function TargetMemoryTrace({ runId }: { runId: string }) {
  const [trace, setTrace] = useState<Trace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const load = async () => { setLoading(true); setError(''); try { setTrace(await api.targetMemoryTrace(runId)); } catch (cause) { setError(cause instanceof Error ? cause.message : 'The target memory trace could not be loaded.'); } finally { setLoading(false); } };
  return <section className="target-memory-trace" aria-label="Target agent memory trace">
    <div className="failure-heading"><div><h2>How the target used memory</h2></div>{!trace && <button type="button" className="secondary" disabled={loading} onClick={load}>{loading ? 'Loading evidence…' : 'Inspect Memory Trace'}</button>}</div>
    {error && <p role="alert" className="alert">{error}</p>}
    {trace && <><p className="trace-note">Strategy: <b>{pretty(trace.memory_strategy)}</b> · Memory updates: <b>{pretty(trace.memory_maintenance_policy ?? 'update_aware_consolidation')}</b> · Up to <b>{trace.target_memory_capacity ?? 50}</b> records were retained.</p>
      <h3>Stored memories</h3><div className="trace-records">{trace.records.map((record, index) => <article className="trace-record" key={record.memory_id} title={`Technical memory ID: ${record.memory_id}`}><div className="row"><b>Memory record {index + 1}</b><span className={`trace-state ${record.lifecycle_state.toLowerCase()}`}>{pretty(record.lifecycle_state)}</span></div><p>{record.canonical_value}</p><small>Scope: {pretty(record.scope ?? 'episodic')} · recorded from {record.source_message_ids.length || 'no'} conversation message{record.source_message_ids.length === 1 ? '' : 's'}</small>{record.relationships.length > 0 && <p className="trace-note">Related memory changes: {record.relationships.map((relation) => pretty(relation.type)).join(', ')}</p>}</article>)}</div>
      <h3>Memory activity</h3><ul className="trace-events">{trace.events.map((event) => <li key={event.event_id}><b>{pretty(event.event_type)}</b>{Object.keys(event.details).length ? ` · ${Object.entries(event.details).map(([key, value]) => `${pretty(key)}: ${Array.isArray(value) ? value.length : String(value)}`).join('; ')}` : ''}</li>)}</ul>
      <h3>What was retrieved</h3>{trace.retrievals.length ? <div className="trace-retrievals">{trace.retrievals.map((retrieval, index) => <details key={retrieval.retrieval_id}><summary><b>Question {index + 1}</b> · {retrieval.selected_memory_ids.length ? `${retrieval.selected_memory_ids.length} relevant memory record${retrieval.selected_memory_ids.length === 1 ? '' : 's'} selected` : 'No relevant memory selected'}</summary><ul>{retrieval.ranking_evidence.map((item, ranking) => <li key={`${String(item.memory_id)}-${ranking}`}>Candidate memory {ranking + 1} — {item.selected ? 'used' : 'not used'}; {String(item.reason ?? 'no reason')}</li>)}</ul><small>Technical test ID: {retrieval.test_id}</small></details>)}</div> : <p className="empty">No retrieval decisions were recorded.</p>}</>}
  </section>;
}
