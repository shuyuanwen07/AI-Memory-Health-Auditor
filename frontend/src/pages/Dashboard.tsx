import { useEffect, useState } from 'react';
import { UIAlert, UIActionLink, UIButton, UICard } from '../components/ui';
import { api } from '../services/api';
import { auditDisplayNames, memoryStrategyLabel, modelDisplayName } from '../services/display';
import type { AuditRun } from '../types/domain';

const stageNames: Record<string, string> = {
  CREATED: 'Setup saved', MEMORY_EXTRACTED: 'Memories ready to review',
  GROUND_TRUTH_CONFIRMED: 'Ready to prepare questions', TESTS_GENERATED: 'Questions ready',
  TESTS_EXECUTED: 'Answers ready to assess', COMPLETED: 'Report ready',
  FAILED: 'Run interrupted', CANCELLED: 'Cancelled',
};

export function Dashboard() {
  const [runs, setRuns] = useState<AuditRun[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let current = true;
    setState('loading');
    api.audits().then(items => { if (current) { setRuns(items); setState('ready'); } })
      .catch(() => { if (current) setState('error'); });
    return () => { current = false; };
  }, [refresh]);
  const completed = runs.filter(run => run.status === 'COMPLETED').length;
  const interrupted = runs.filter(run => run.status === 'FAILED').length;
  const unfinished = runs.filter(run => !['COMPLETED', 'FAILED', 'CANCELLED'].includes(run.status)).length;
  const names = auditDisplayNames(runs);
  const recent = [...runs].sort((a, b) => b.created_at.localeCompare(a.created_at) || b.run_id.localeCompare(a.run_id)).slice(0, 5);
  return <section className="workspace-dashboard">
    <div className="dashboard-heading"><div><h1>Memory audit workspace</h1><p>Check how an AI uses remembered facts, inspect the evidence, and compare results.</p></div><UIActionLink href="/new-audit">Start a new audit</UIActionLink></div>
    {state === 'loading' ? <p role="status">Loading workspace progress…</p> : state === 'error' ? <UIAlert><p>Workspace progress could not be loaded. Your saved audits have not been changed.</p><UIButton className="secondary" onClick={() => setRefresh(value => value + 1)}>Try again</UIButton></UIAlert> : <>
      <div className="dashboard-metrics" aria-label="Saved audit progress">
        <UICard><span>Reports ready</span><b>{completed}</b><small>Completed assessments, including saved-answer reassessments.</small></UICard>
        <UICard><span>Unfinished audits</span><b>{unfinished}</b><small>Saved stages that have not reached a completed report.</small></UICard>
        <UICard><span>Interrupted runs</span><b>{interrupted}</b><small>Run errors, separate from answers that failed a test.</small></UICard>
      </div>
      <p className="dashboard-count-note">These are workflow counts, not a measure of model accuracy. Cancelled runs are listed in History.</p>
      {!runs.length ? <UICard><h2>Start with a conversation</h2><p>Upload conversation data, confirm the extracted facts, then run the audit. Your saved results will appear here.</p></UICard> : <UICard><div className="dashboard-heading"><h2>Recent activity</h2><UIButton className="secondary" onClick={() => setRefresh(value => value + 1)}>Refresh progress</UIButton></div><p className="trace-note">Model names below belong to saved audits. Saving a setup does not run its model. Benchmark studies are shown separately in <a href="/experiments">Experiments</a>.</p><ul className="dashboard-recent">{recent.map(run => <li key={run.run_id}><div><h3>{names[run.run_id]} · {modelDisplayName(run.model)}</h3><p>{memoryStrategyLabel(run.memory_strategy)} · {stageNames[run.status] ?? 'Check saved progress'}</p><small>Saved on <time dateTime={run.created_at}>{run.created_at.slice(0, 10)}</time></small>{run.reproducibility?.assessment_source_run_id && <small>Saved-answer reassessment · No new target call.</small>}</div><UIActionLink className="secondary" href={run.status === 'COMPLETED' ? `/audits/${run.run_id}` : '/history'}>{run.status === 'COMPLETED' ? `View ${names[run.run_id]} report` : `Find ${names[run.run_id]} in History`}</UIActionLink></li>)}</ul><UIActionLink className="secondary" href="/history">View all audit history</UIActionLink></UICard>}
    </>}
    <div className="dashboard-next" aria-label="Ways to inspect results">
      <UICard><h2>Compare results</h2><p>Compare the same questions before and after a memory change, or inspect different models and settings.</p><UIActionLink className="secondary" href="/experiments">Open experiments</UIActionLink></UICard>
      <UICard><h2>Check the auditor</h2><p>Review answers independently and see how automated assessments agree with human decisions.</p><UIActionLink className="secondary" href="/quality">Review auditor reliability</UIActionLink></UICard>
    </div>
  </section>;
}
