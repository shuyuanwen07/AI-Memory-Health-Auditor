import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Card } from 'antd';
import { api } from '../services/api';
import { memoryStrategyLabel, modelDisplayName } from '../services/display';
import type { Experiment, ExperimentAnalytics } from '../types/domain';

/** Compare only conditions recorded within the same experiment; never merge unrelated suites. */
export function LiveExperimentResults() {
  const [groups, setGroups] = useState<Experiment[]>([]);
  const [selected, setSelected] = useState('');
  const [report, setReport] = useState<ExperimentAnalytics | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const request = useRef(0);
  const refresh = useCallback(() => setRevision(n => n + 1), []);

  useEffect(() => {
    const onFocus = () => { if (document.visibilityState === 'visible') refresh(); };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onFocus);
    return () => { window.removeEventListener('focus', onFocus); document.removeEventListener('visibilitychange', onFocus); };
  }, [refresh]);

  useEffect(() => {
    const current = ++request.current;
    setLoading(true); setError('');
    void api.experimentGroups().then(items => {
      if (current !== request.current) return;
      const completed = items.filter(x => x.status === 'COMPLETED').sort((a,b) => (b.completed_at ?? b.created_at).localeCompare(a.completed_at ?? a.created_at));
      setGroups(completed);
      setSelected(previous => completed.some(x => x.experiment_id === previous) ? previous : completed[0]?.experiment_id ?? '');
      setLoading(false);
    }).catch(() => { if (current === request.current) { setError('Could not load experiments. Please retry.'); setLoading(false); } });
    return () => { request.current++; };
  }, [revision]);

  useEffect(() => {
    let active = true;
    setReport(null);
    if (!selected) return;
    void api.experimentResults(selected).then(result => { if (active) setReport(result); })
      .catch(() => { if (active) setError('Could not load this experiment. Please retry.'); });
    return () => { active = false; };
  }, [selected, revision]);

  return <section aria-label="Live completed experiment results" className="dashboard-section">
    <Card title="New experiment results" extra={<Button aria-label="Refresh experiments" onClick={refresh} loading={loading}>Refresh</Button>}>
      {error && <p role="alert">{error}</p>}
      {!error && !loading && groups.length === 0 && <p>No completed experiment groups yet. Completed groups will appear here automatically.</p>}
      {groups.length > 0 && <>
        <label htmlFor="live-experiment">Experiment </label>
        <select id="live-experiment" value={selected} onChange={event => { setError(''); setSelected(event.target.value); }}>
          {groups.map(group => <option key={group.experiment_id} value={group.experiment_id}>{group.label} · {(group.completed_at ?? group.created_at).slice(0,10)}</option>)}
        </select>
        {report && <>
          <div role="img" aria-label="Saved experiment results by condition">
            {report.conditions.map(condition => <div key={condition.condition_id} style={{ margin: '1rem 0' }}>
              <div style={{display:'flex', justifyContent:'space-between', gap:12, flexWrap:'wrap'}}>
                <span>{condition.label} · {memoryStrategyLabel(condition.memory_strategy)} · {modelDisplayName(condition.model)}</span>
                <strong>{condition.overall_mean === null ? 'Not measured' : `${condition.overall_mean.toFixed(1)}% mean`}</strong>
              </div>
              <div style={{height:10, background:'#e8edf2', borderRadius:6, overflow:'hidden'}}><div style={{height:'100%', width:`${Math.max(0, Math.min(100, condition.overall_mean ?? 0))}%`, background:'#147e87'}} /></div>
              <small>{condition.tests_passed}/{condition.tests_total} decided passed · {condition.completed_runs}/{condition.planned_runs} runs completed · {condition.dimensions.reduce((n,d)=>n+(d.uncertain_count ?? 0),0)} uncertain</small>
            </div>)}
          </div>
          {!report.conditions.length && <p>No condition results are available for this experiment.</p>}
          <p className="compact-note">Automatic scores from this experiment only; uncertain answers are excluded from decided counts. Repeated runs are not independent cases. Research results below remain separately reviewed.</p>
          <a href={`/experiments/${encodeURIComponent(selected)}`}>View experiment evidence →</a>
        </>}
      </>}
    </Card>
  </section>;
}
