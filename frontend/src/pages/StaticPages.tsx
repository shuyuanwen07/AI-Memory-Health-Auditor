import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../services/api';
import type { AuditResult, AuditRetryPlan, AuditRun, Experiment, ExperimentAnalytics, ExperimentRunReport, PairedComparison } from '../types/domain';
import { ResultDashboard } from '../components/ResultDashboard';
import { TargetMemoryTrace } from '../components/TargetMemoryTrace';
import { ResearchValidation } from '../components/ResearchValidation';

const ComparisonVisualizations = lazy(() => import('../components/ResultVisualizations').then((module) => ({ default: module.ComparisonVisualizations })));

const statusLabels: Record<string, string> = {
  CREATED: 'Created',
  MEMORY_EXTRACTED: 'Memory extracted',
  GROUND_TRUTH_CONFIRMED: 'Ground truth confirmed',
  TESTS_GENERATED: 'Tests generated',
  TESTS_EXECUTED: 'Tests executed',
  COMPLETED: 'Completed',
  FAILED: 'Failed',
  CANCELLED: 'Cancelled',
};

const providerLabels: Record<AuditRun['provider'], string> = {
  rule_based: 'Rule-based baseline',
  ollama: 'Local Ollama',
  openai: 'OpenAI',
  deepseek: 'DeepSeek',
  gemini: 'Google Gemini',
};

function formatDate(value?: string) {
  if (!value) return 'Not completed';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unavailable' : date.toLocaleString();
}

function formatStatus(status: string) {
  return statusLabels[status] ?? status.replaceAll('_', ' ').toLowerCase();
}

export function History() {
  const [items, setItems] = useState<AuditRun[]>([]);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [providerFilter, setProviderFilter] = useState('all');
  const [strategyFilter, setStrategyFilter] = useState('all');
  const loadHistory = useCallback(() => {
    setLoadState('loading');
    api.audits().then((audits) => { setItems(audits); setLoadState('ready'); })
      .catch(() => { setItems([]); setLoadState('error'); });
  }, []);
  useEffect(() => { loadHistory(); }, [loadHistory]);
  const removed = () => { loadHistory(); };
  const filteredItems = useMemo(() => {
    const query = search.trim().toLowerCase();
    return items.filter((run) => {
      const matchesSearch = !query || [run.run_id, run.conversation_id, run.model, run.pipeline_model, run.evaluator_model]
        .some((value) => value.toLowerCase().includes(query));
      return matchesSearch
        && (statusFilter === 'all' || run.status === statusFilter)
        && (providerFilter === 'all' || run.provider === providerFilter)
        && (strategyFilter === 'all' || run.memory_strategy === strategyFilter);
    });
  }, [items, search, statusFilter, providerFilter, strategyFilter]);
  const filtersActive = Boolean(search) || statusFilter !== 'all' || providerFilter !== 'all' || strategyFilter !== 'all';
  const clearFilters = () => { setSearch(''); setStatusFilter('all'); setProviderFilter('all'); setStrategyFilter('all'); };
  return <section><h1>Audit History</h1>
    {loadState === 'loading' ? <p className="empty" role="status">Loading audit history…</p> : loadState === 'error' ? <div className="empty" role="alert"><p>Audit history could not be loaded. Check that the API service is available and try again.</p><button type="button" className="secondary" onClick={loadHistory}>Try again</button></div> : items.length ? <>
      <div className="history-filters" aria-label="Audit history filters">
        <label>Find an audit<input aria-label="Search audit history" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Model, strategy, or technical ID" /></label>
        <label>Result<select aria-label="Filter by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">All results</option>{[...new Set(items.map((run) => run.status))].map((status) => <option key={status} value={status}>{formatStatus(status)}</option>)}</select></label>
        <label>Model provider<select aria-label="Filter by target provider" value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)}><option value="all">All providers</option>{[...new Set(items.map((run) => run.provider))].map((provider) => <option key={provider} value={provider}>{providerLabels[provider]}</option>)}</select></label>
        <label>Memory approach<select aria-label="Filter by memory strategy" value={strategyFilter} onChange={(event) => setStrategyFilter(event.target.value)}><option value="all">All approaches</option>{[...new Set(items.map((run) => run.memory_strategy))].map((strategy) => <option key={strategy} value={strategy}>{strategy.replaceAll('_', ' ')}</option>)}</select></label>
        {filtersActive && <button type="button" className="secondary history-filter-reset" onClick={clearFilters}>Clear filters</button>}
      </div>
      <p className="history-count" role="status">Showing {filteredItems.length} of {items.length} audit run{items.length === 1 ? '' : 's'}.</p>
      {filteredItems.length ? <div className="audit-history-list" aria-label="Audit history">{filteredItems.map((run) => <AuditHistoryCard key={run.run_id} run={run} onRecovered={(updated) => setItems((current) => current.map((item) => item.run_id === updated.run_id ? updated : item))} onDeleted={removed} />)}</div> : <div className="empty"><b>No matching audits</b><p>Try clearing a filter or searching by a different model, strategy, or technical ID.</p></div>}
    </> : <div className="empty"><b>No audits yet</b><p>Create and run an audit to retain a traceable record here.</p></div>}
  </section>;
}

function friendlyStrategy(strategy: AuditRun['memory_strategy']) {
  return strategy.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function friendlyExperimentLabel(label: string) {
  return label
    .replace(/SYN-C0*(\d+)/gi, (_match, number: string) => `Scenario ${Number(number)}`)
    .replace(/:\s*(Scenario \d+)/, ' · $1');
}

function scenarioNumber(label: string) {
  const match = label.match(/(?:SYN-C0*|Scenario\s+)(\d+)/i);
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER;
}

function shortDate(value?: string) {
  if (!value) return 'Not completed yet';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Date unavailable';
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function AuditHistoryCard({ run, onRecovered, onDeleted }: {
  run: AuditRun;
  onRecovered: (run: AuditRun) => void;
  onDeleted: () => void;
}) {
  const completed = run.status === 'COMPLETED';
  return <article className="audit-history-card">
    <div className="audit-history-card-main">
      <div className="audit-history-card-meta"><span>{providerLabels[run.provider]}</span><span>{completed ? `Completed ${shortDate(run.completed_at)}` : `Started ${shortDate(run.created_at)}`}</span></div>
      <h2>{friendlyStrategy(run.memory_strategy)} memory audit</h2>
      <p>{run.model} · {run.test_budget} behavioural tests</p>
      <ReproducibilityDetails run={run} />
    </div>
    <div className="audit-history-card-actions">
      <RunRecoveryControls run={run} onRecovered={onRecovered} />
      {completed ? <a className="secondary audit-view-report" href={`/audits/${run.run_id}`}>View report</a> : <small>Results are available after completion.</small>}
    </div>
    <details className="audit-technical-details"><summary>Technical details and local data</summary><dl><div><dt>Audit ID</dt><dd><code>{run.run_id}</code></dd></div><div><dt>Conversation ID</dt><dd><code>{run.conversation_id}</code></dd></div><div><dt>Created</dt><dd>{formatDate(run.created_at)}</dd></div><div><dt>Completed</dt><dd>{formatDate(run.completed_at)}</dd></div></dl><ConversationDataControls conversationId={run.conversation_id} onDeleted={onDeleted} /></details>
  </article>;
}

/** Stable, shareable report route; it reads results again after a browser refresh. */
export function AuditReportPage() {
  const { runId = '' } = useParams();
  const [result, setResult] = useState<AuditResult | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  useEffect(() => {
    if (!runId) { setState('error'); return; }
    setState('loading');
    api.results(runId).then((loaded) => { setResult(loaded); setState('ready'); })
      .catch(() => { setResult(null); setState('error'); });
  }, [runId]);
  if (state === 'loading') return <section><h1>Memory Health Report</h1><p className="empty" role="status">Loading the saved audit report…</p></section>;
  if (state === 'error' || !result) return <section><h1>Memory Health Report</h1><div className="empty" role="alert"><b>Report unavailable</b><p>This audit may not be complete, may have been deleted with its authorised conversation, or the API is unavailable.</p><a className="text-link" href="/history">Return to Audit History</a></div></section>;
  return <section><p className="eyebrow">SAVED AUDIT REPORT</p><h1>Memory Health Report</h1><ResultDashboard result={result} /><details className="audit-technical-details"><summary>Technical report details</summary><p><code>{result.run_id}</code></p></details><TargetMemoryTrace runId={result.run_id} /></section>;
}

function ReproducibilityDetails({ run }: { run: AuditRun }) {
  const retryPolicy = run.reproducibility?.target_retry_policy;
  const seed = run.reproducibility?.seed_control;
  return <details className="reproducibility-details"><summary>{run.target_configuration === 'strong' ? 'Strong Memory' : 'Weak Memory'} · {run.memory_strategy.replaceAll('_', ' ')}</summary><ul><li>{run.test_budget} tests · temperature {run.temperature} · seed {run.random_seed}</li>{seed && <li>Seed control: target {seed.target?.replaceAll('_', ' ') ?? 'not declared'} · pipeline {seed.pipeline?.replaceAll('_', ' ') ?? 'not declared'} · evaluator {seed.evaluator?.replaceAll('_', ' ') ?? 'not declared'}</li>}<li>Suite: {run.prompt_template_version}</li><li>Pipeline: {run.pipeline_provider} / {run.pipeline_model}</li><li>Evaluator: {run.evaluator_provider} / {run.evaluator_model}</li><li>Target system: {run.target_system_adapter ?? 'controlled-memory'}{run.target_system_adapter_version ? ` (${run.target_system_adapter_version})` : ''}</li><li>Memory maintenance: {(run.memory_maintenance_policy ?? 'update_aware_consolidation').replaceAll('_', ' ')}</li>{run.target_memory_capacity && <li>Target memory capacity: {run.target_memory_capacity} records</li>}<li>Writer: {run.target_memory_writer ?? 'rule_based'}{run.target_memory_writer_version ? ` (${run.target_memory_writer_version})` : ''}</li>{retryPolicy && <li>Recovery: up to {retryPolicy.max_attempts} attempts · {retryPolicy.timeout_seconds}s timeout</li>}{run.reproducibility?.configuration_fingerprint && <li className="fingerprint">Configuration fingerprint: <code>{run.reproducibility.configuration_fingerprint}</code></li>}</ul></details>;
}

const recoveryStageLabels: Record<NonNullable<AuditRetryPlan['next_stage']>, string> = { generate_tests: 'generate the shared tests', execute_tests: 'execute unanswered tests', evaluate_responses: 'evaluate pending responses' };

function RunRecoveryControls({ run, onRecovered }: { run: AuditRun; onRecovered: (updated: AuditRun) => void }) {
  const [plan, setPlan] = useState<AuditRetryPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const inspect = async () => { setBusy(true); setMessage(''); try { setPlan(await api.retryPlan(run.run_id)); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The recovery plan could not be loaded.'); } finally { setBusy(false); } };
  const retry = async () => { setBusy(true); setMessage(''); try { const updated = await api.retry(run.run_id); onRecovered(updated); setPlan(null); setMessage(updated.status === 'COMPLETED' ? 'Recovery completed. The report is now available.' : `Recovery stopped at ${formatStatus(updated.status)}.`); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The audit could not be resumed.'); } finally { setBusy(false); } };
  if (run.status === 'COMPLETED') return <div className="recovery-controls"><span className="status-complete">Completed</span>{message && <small className="success-message" role="status">{message}</small>}</div>;
  if (run.status === 'CANCELLED') return <div className="recovery-controls"><b>{formatStatus(run.status)}</b><small>This run is terminal and cannot be resumed.</small></div>;
  return <div className="recovery-controls"><b>{formatStatus(run.status)}</b>{!plan ? <button type="button" className="secondary" disabled={busy} onClick={inspect}>{busy ? 'Checking…' : 'View recovery plan'}</button> : plan.retryable && plan.next_stage ? <><small>{plan.pending > 0 ? `${plan.pending} item${plan.pending === 1 ? '' : 's'} pending; recovery will ${recoveryStageLabels[plan.next_stage]}.` : `Recovery will ${recoveryStageLabels[plan.next_stage]}.`}</small><button type="button" disabled={busy} onClick={retry}>{busy ? 'Resuming…' : 'Resume audit'}</button></> : <small>No recovery is required for this run.</small>}{message && <small className={message.startsWith('Recovery completed') ? 'success-message' : 'alert-message'} role="status">{message}</small>}</div>;
}

function ConversationDataControls({ conversationId, onDeleted }: { conversationId: string; onDeleted: () => void }) {
  const [confirmationOpen, setConfirmationOpen] = useState(false); const [confirmation, setConfirmation] = useState(''); const [busy, setBusy] = useState(false); const [message, setMessage] = useState('');
  const download = async () => { setBusy(true); setMessage(''); try { const blob = await api.downloadConversationExport(conversationId); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `memory-health-${conversationId}-export.json`; link.click(); URL.revokeObjectURL(url); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The export could not be created.'); } finally { setBusy(false); } };
  const erase = async () => { setBusy(true); setMessage(''); try { const receipt = await api.deleteConversation(conversationId, confirmation); setMessage(receipt.message); onDeleted(); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The local data could not be deleted.'); } finally { setBusy(false); } };
  return <div className="conversation-data-controls"><button type="button" className="secondary" disabled={busy} onClick={download}>Export JSON</button><button type="button" className="ghost" disabled={busy} onClick={() => { setConfirmationOpen(!confirmationOpen); setMessage(''); }}>Delete data</button>{confirmationOpen && <div className="delete-confirmation"><label>Enter <b>{conversationId}</b> to permanently delete this conversation and all of its audit data.<input aria-label={`Confirm deletion of ${conversationId}`} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label><button type="button" className="danger" disabled={busy || confirmation !== conversationId} onClick={erase}>Permanently delete local data</button></div>}{message && <small className={message.startsWith('The authorised') ? 'success-message' : 'alert-message'}>{message}</small>}</div>;
}

export function Experiments() {
  const [items, setItems] = useState<Experiment[]>([]);
  const [analytics, setAnalytics] = useState<Record<string, ExperimentAnalytics>>({});
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [exportingId, setExportingId] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState('');
  const loadExperiments = useCallback(() => {
    setLoadState('loading');
    api.experimentGroups()
      .then(async (groups) => {
        const orderedGroups = [...groups].sort((left, right) => scenarioNumber(left.label) - scenarioNumber(right.label));
        const reports = await Promise.all(orderedGroups.map((group) => api.experimentResults(group.experiment_id)));
        setItems(orderedGroups);
        setAnalytics(Object.fromEntries(reports.map((report) => [report.experiment.experiment_id, report])));
        setLoadState('ready');
      })
      .catch(() => { setItems([]); setAnalytics({}); setLoadState('error'); });
  }, []);

  useEffect(() => { loadExperiments(); }, [loadExperiments]);

  const download = async (experiment: Experiment) => {
    setExportingId(experiment.experiment_id); setActionMessage('');
    try {
      const blob = await api.downloadExperimentCsv(experiment.experiment_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `experiment-${experiment.experiment_id}-results.csv`; link.click();
      URL.revokeObjectURL(url);
    } catch (cause) { setActionMessage(cause instanceof Error ? cause.message : 'The experiment CSV could not be created.'); }
    finally { setExportingId(null); }
  };

  const downloadBundle = async (experiment: Experiment) => {
    setExportingId(experiment.experiment_id); setActionMessage('');
    try {
      const blob = await api.downloadExperimentBundle(experiment.experiment_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `experiment-${experiment.experiment_id}-reproducibility-bundle.json`; link.click();
      URL.revokeObjectURL(url);
    } catch (cause) { setActionMessage(cause instanceof Error ? cause.message : 'The reproducibility bundle could not be created.'); }
    finally { setExportingId(null); }
  };

  const downloadArtifact = async (experiment: Experiment) => {
    setExportingId(experiment.experiment_id); setActionMessage('');
    try {
      const blob = await api.downloadExperimentArtifact(experiment.experiment_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `experiment-${experiment.experiment_id}-artifact.zip`; link.click();
      URL.revokeObjectURL(url);
    } catch (cause) { setActionMessage(cause instanceof Error ? cause.message : 'The frozen experiment artifact could not be created.'); }
    finally { setExportingId(null); }
  };

  const cancelExperiment = async (experiment: Experiment) => {
    if (!window.confirm(`Cancel every unfinished condition in ${experiment.label}? Completed results and retained evidence will remain available.`)) return;
    setExportingId(experiment.experiment_id); setActionMessage('');
    try {
      const updated = await api.cancelExperiment(experiment.experiment_id);
      const report = await api.experimentResults(experiment.experiment_id);
      setItems((current) => current.map((item) => item.experiment_id === updated.experiment_id ? updated : item));
      setAnalytics((current) => ({ ...current, [updated.experiment_id]: report }));
      setActionMessage('The unfinished conditions were cancelled. Completed results remain available.');
    } catch (cause) { setActionMessage(cause instanceof Error ? cause.message : 'The experiment could not be cancelled.'); }
    finally { setExportingId(null); }
  };

  return <section><h1>Experiments</h1>{actionMessage && <p className={actionMessage.startsWith('The unfinished') ? 'success-message' : 'alert-message'} role="status">{actionMessage}</p>}{loadState === 'loading' ? <p className="empty" role="status">Loading experiment groups…</p> : loadState === 'error' ? <div className="empty" role="alert"><p>Experiment groups could not be loaded. Check that the API service is available and try again.</p><button type="button" className="secondary" onClick={loadExperiments}>Try again</button></div> : items.length ? items.map((item) => <ExperimentHistoryCard key={item.experiment_id} experiment={item} report={analytics[item.experiment_id]} exporting={exportingId === item.experiment_id} onDownload={download} onDownloadBundle={downloadBundle} onDownloadArtifact={downloadArtifact} onCancel={cancelExperiment} />) : <div className="empty"><b>No experiments yet</b><p>Start a multi-model or multi-strategy audit to create a controlled comparison group.</p></div>}<ResearchValidation /></section>;
}

function percentage(value: number | null | undefined) { return value === null || value === undefined ? 'Not tested' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`; }

function ExperimentHistoryCard({ experiment, report, exporting, onDownload, onDownloadBundle, onDownloadArtifact, onCancel }: { experiment: Experiment; report?: ExperimentAnalytics; exporting: boolean; onDownload: (experiment: Experiment) => void; onDownloadBundle: (experiment: Experiment) => void; onDownloadArtifact: (experiment: Experiment) => void; onCancel: (experiment: Experiment) => void }) {
  const complete = report?.runs.filter((item) => item.run.status === 'COMPLETED').length ?? 0;
  const failed = report?.runs.filter((item) => item.run.status === 'FAILED').length ?? 0;
  const visualRuns = report?.runs.flatMap(({ run, result }) => result ? [{
    label: `${providerLabels[run.provider]} · ${friendlyStrategy(run.memory_strategy)}`,
    groupLabel: report.conditions.find((condition) => condition.run_ids.includes(run.run_id))?.label ?? `${run.provider} · ${run.memory_strategy}`,
    result,
  }] : []) ?? [];
  const canCancel = !['COMPLETED', 'FAILED', 'CANCELLED'].includes(experiment.status);
  return <article className="experiment"><div className="experiment-heading"><div><h2>{friendlyExperimentLabel(experiment.label)}</h2></div><div><button className="secondary export-button" type="button" disabled={exporting} onClick={() => onDownload(experiment)}>{exporting ? 'Preparing export…' : 'Download group CSV'}</button><button className="secondary export-button" type="button" disabled={exporting} onClick={() => onDownloadBundle(experiment)}>{exporting ? 'Preparing export…' : 'Download reproducibility bundle'}</button><button className="secondary export-button" type="button" disabled={exporting} onClick={() => onDownloadArtifact(experiment)}>{exporting ? 'Preparing export…' : 'Download frozen artifact'}</button>{canCancel && <button className="ghost" type="button" disabled={exporting} onClick={() => onCancel(experiment)}>{exporting ? 'Cancelling…' : 'Cancel unfinished conditions'}</button>}</div></div><div className="experiment-scores"><span><small>Shared tests</small><b>{experiment.test_suite_metadata.test_count || '—'}</b></span><span><small>Conditions complete</small><b>{complete} / {report?.runs.length ?? 0}</b></span></div>{failed > 0 && <p className="experiment-alert"><b>{failed} failed condition{failed === 1 ? '' : 's'} require attention.</b> Completed conditions are retained for comparison.</p>}<p><small>Suite: seed {experiment.test_suite_configuration.random_seed} · {experiment.test_suite_configuration.test_budget} test budget · {experiment.test_suite_configuration.prompt_template_version}</small></p>{report && <>{visualRuns.length > 1 && <Suspense fallback={<p className="chart-loading" role="status">Loading visual comparison charts…</p>}><ComparisonVisualizations runs={visualRuns} /></Suspense>}<ConditionTable report={report} /><RunReports runs={report.runs} /><PairedSignals comparisons={report.paired_comparisons} /></>}<details className="audit-technical-details"><summary>Technical experiment ID</summary><code>{experiment.experiment_id}</code></details></article>;
}

function ConditionTable({ report }: { report: ExperimentAnalytics }) {
  return <div className="comparison-scroll experiment-history-table"><table><thead><tr><th>Condition</th><th>Completed</th><th>Overall mean</th><th>Variation</th><th>Tests passed</th><th>Failures</th></tr></thead><tbody>{report.conditions.map((condition) => <tr key={condition.condition_id}><th scope="row">{condition.label}</th><td>{condition.completed_runs} / {condition.planned_runs}</td><td><b>{percentage(condition.overall_mean)}</b></td><td>{percentage(condition.overall_standard_deviation)}</td><td>{condition.tests_passed} / {condition.tests_total}</td><td>{condition.failure_count}</td></tr>)}</tbody></table></div>;
}

function CancelledRunEvidence({ runId }: { runId: string }) {
  const [evidence, setEvidence] = useState<Awaited<ReturnType<typeof api.cancelledEvidence>> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const load = async () => { setLoading(true); setError(''); try { setEvidence(await api.cancelledEvidence(runId)); } catch (cause) { setError(cause instanceof Error ? cause.message : 'Retained cancellation evidence could not be loaded.'); } finally { setLoading(false); } };
  return <div className="cancelled-evidence"><p className="empty">This condition was cancelled before evaluation. Any completed target responses and safe memory trace are retained.</p>{!evidence && <button type="button" className="secondary" disabled={loading} onClick={load}>{loading ? 'Loading retained evidence…' : 'Inspect retained evidence'}</button>}{error && <p role="alert" className="alert-message">{error}</p>}{evidence && <><p><b>{evidence.completed_responses.length}</b> target response{evidence.completed_responses.length === 1 ? '' : 's'} completed before cancellation.</p>{evidence.completed_responses.length ? <ul className="experiment-failures">{evidence.completed_responses.map((response, index) => <li key={response.response_id}><b>Response {index + 1}</b>: {response.response_text}<small title={`Technical test ID: ${response.test_id}`}>Technical ID available on hover</small></li>)}</ul> : <p className="empty">No target response completed before cancellation.</p>}<TargetMemoryTrace runId={runId} /></>}</div>;
}

function RunReports({ runs }: { runs: ExperimentRunReport[] }) {
  return <details className="experiment-history-detail"><summary>Condition reports and detected failures</summary>{runs.map(({ run, result }) => <details className="run-report" key={run.run_id}><summary><b>{providerLabels[run.provider]} · {run.memory_strategy.replaceAll('_', ' ')}</b> — {formatStatus(run.status)}{result && ` · ${percentage(result.overall_score)}`}</summary>{result ? <><p>{result.tests_passed} / {result.tests_total} tests passed. {result.failures.length} detected failure{result.failures.length === 1 ? '' : 's'}.</p>{result.failures.length ? <ul className="experiment-failures">{result.failures.map((failure) => <li key={failure.failure_id}><b>{failure.test.dimension.replaceAll('_', ' ')}</b>: {failure.evaluation.reason}<span>Test: {failure.test.prompt}</span></li>)}</ul> : <p className="empty">No failures were detected for this run.</p>}</> : run.status === 'CANCELLED' ? <CancelledRunEvidence runId={run.run_id} /> : <p className="empty">Results are not available until this run completes.</p>}</details>)}</details>;
}

function PairedSignals({ comparisons }: { comparisons: PairedComparison[] }) {
  if (!comparisons.length) return <p className="repeat-note">Paired comparison signals will appear after at least two conditions complete.</p>;
  return <details className="experiment-history-detail"><summary>Paired comparison signals</summary><p>Each row aligns the exact frozen tests answered by two completed runs. A positive delta favours the candidate condition. The 95% interval is a deterministic bootstrap estimate; the p-value is a two-sided exact sign test over discordant tests.</p><div className="comparison-scroll"><table><thead><tr><th>Candidate vs reference</th><th>Shared tests</th><th>Candidate-only passes</th><th>Reference-only passes</th><th>Delta</th><th>95% interval</th><th>p-value</th></tr></thead><tbody>{comparisons.map((pair) => <tr key={`${pair.reference_run_id}:${pair.candidate_run_id}`}><th scope="row">{pair.candidate_label} vs {pair.reference_label}</th><td>{pair.shared_tests}</td><td>{pair.candidate_only_passed}</td><td>{pair.reference_only_passed}</td><td><b>{pair.candidate_delta_percentage_points === null ? 'Not available' : `${pair.candidate_delta_percentage_points > 0 ? '+' : ''}${pair.candidate_delta_percentage_points.toFixed(1)} pp`}</b></td><td>{pair.candidate_delta_confidence_interval_low === null || pair.candidate_delta_confidence_interval_high === null ? 'Not available' : `${pair.candidate_delta_confidence_interval_low.toFixed(1)} to ${pair.candidate_delta_confidence_interval_high.toFixed(1)} pp`}</td><td>{pair.two_sided_sign_test_p_value === null ? 'Not available' : pair.two_sided_sign_test_p_value.toFixed(4)}</td></tr>)}</tbody></table></div></details>;
}

export function About() {
  return <section><h1>About AI Memory Health Auditor</h1><p>AI Memory Health Auditor evaluates how reliably a controlled conversational AI remembers and uses information over time.</p><p>It separates the underlying language model from the memory policy being tested, then measures Accuracy, Freshness, Conflict Resolution and Appropriate Use with traceable evidence.</p><p>Controlled experiment groups freeze one test suite before comparing models or strategies. Rule-based components provide a reproducible local baseline; optional provider connectors can be configured on the backend.</p></section>;
}
