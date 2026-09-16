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
    <div className="failure-heading"><div><h2>Target Agent Memory Trace</h2><p>Post-audit evidence of what the controlled target independently stored, updated and retrieved. This is separate from the reviewer-confirmed ground truth.</p></div>{!trace && <button type="button" className="secondary" disabled={loading} onClick={load}>{loading ? 'Loading evidence…' : 'Inspect Memory Trace'}</button>}</div>
    {error && <p role="alert" className="alert">{error}</p>}
    {trace && <><p className="trace-note">Strategy: <b>{pretty(trace.memory_strategy)}</b> · Values are shown only after the audit completed. Evaluator-only expected behaviour is not included here.</p>
      <h3>Stored Memory Lifecycle</h3><div className="trace-records">{trace.records.map((record) => <article className="trace-record" key={record.memory_id}><div className="row"><b>{record.memory_id}</b><span className={`trace-state ${record.lifecycle_state.toLowerCase()}`}>{pretty(record.lifecycle_state)}</span></div><p>{record.canonical_value}</p><small>Write {record.write_order} · Sources: {record.source_message_ids.join(', ') || 'none'}</small>{record.relationships.length > 0 && <ul>{record.relationships.map((relation) => <li key={relation.relationship_id ?? `${relation.type}-${relation.target_memory_id}`}>{relation.type} → {relation.target_memory_id}</li>)}</ul>}</article>)}</div>
      <h3>Lifecycle Events</h3><ul className="trace-events">{trace.events.map((event) => <li key={event.event_id}><b>{pretty(event.event_type)}</b>{event.memory_id ? ` · ${event.memory_id}` : ''}{Object.keys(event.details).length ? ` · ${Object.entries(event.details).map(([key, value]) => `${pretty(key)}: ${Array.isArray(value) ? value.join(', ') : String(value)}`).join('; ')}` : ''}</li>)}</ul>
      <h3>Retrieval Decisions</h3>{trace.retrievals.length ? <div className="trace-retrievals">{trace.retrievals.map((retrieval) => <details key={retrieval.retrieval_id}><summary><b>{retrieval.test_id}</b> · selected {retrieval.selected_memory_ids.join(', ') || 'no relevant memory'}</summary><ul>{retrieval.ranking_evidence.map((item, index) => <li key={`${String(item.memory_id)}-${index}`}>{String(item.memory_id)} — {item.selected ? 'selected' : 'not selected'}; {String(item.reason ?? 'no reason')}</li>)}</ul></details>)}</div> : <p className="empty">No retrieval decisions were recorded.</p>}</>}
  </section>;
}
