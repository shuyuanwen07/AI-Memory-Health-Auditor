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
  EVALUATED: 'Evaluated',
  COMPLETED: 'Completed',
  FAILED: 'Failed',
};

const providerLabels: Record<AuditRun['provider'], string> = {
  rule_based: 'Rule-based baseline',
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
  const [selectedReport, setSelectedReport] = useState<AuditResult | null>(null);
  const [reportError, setReportError] = useState('');
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
  const openReport = async (runId: string) => {
    setReportError('');
    try { setSelectedReport(await api.results(runId)); }
    catch (cause) { setSelectedReport(null); setReportError(cause instanceof Error ? cause.message : 'The completed report could not be loaded.'); }
  };
  const removed = () => { setSelectedReport(null); setReportError(''); loadHistory(); };
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
  return <section><h1>Audit History</h1><p>Review the configuration, lifecycle status, completion time and post-audit evidence of each controlled audit.</p>
    <p className="data-retention-note">Local data controls export or permanently erase every audit record derived from the selected authorised conversation.</p>
    {loadState === 'loading' ? <p className="empty" role="status">Loading audit history…</p> : loadState === 'error' ? <div className="empty" role="alert"><p>Audit history could not be loaded. Check that the API service is available and try again.</p><button type="button" className="secondary" onClick={loadHistory}>Try again</button></div> : items.length ? <>
      <div className="history-filters" aria-label="Audit history filters">
        <label>Search runs or models<input aria-label="Search audit history" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Run ID, conversation ID or model" /></label>
        <label>Status<select aria-label="Filter by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">All statuses</option>{[...new Set(items.map((run) => run.status))].map((status) => <option key={status} value={status}>{formatStatus(status)}</option>)}</select></label>
        <label>Target provider<select aria-label="Filter by target provider" value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)}><option value="all">All providers</option>{[...new Set(items.map((run) => run.provider))].map((provider) => <option key={provider} value={provider}>{providerLabels[provider]}</option>)}</select></label>
        <label>Memory strategy<select aria-label="Filter by memory strategy" value={strategyFilter} onChange={(event) => setStrategyFilter(event.target.value)}><option value="all">All strategies</option>{[...new Set(items.map((run) => run.memory_strategy))].map((strategy) => <option key={strategy} value={strategy}>{strategy.replaceAll('_', ' ')}</option>)}</select></label>
        {filtersActive && <button type="button" className="secondary history-filter-reset" onClick={clearFilters}>Clear filters</button>}
      </div>
      <p className="history-count" role="status">Showing {filteredItems.length} of {items.length} audit run{items.length === 1 ? '' : 's'}.</p>
      {filteredItems.length ? <div className="history-table-scroll"><table aria-label="Audit history"><thead><tr><th>Run</th><th>Target AI</th><th>Frozen configuration</th><th>Status & recovery</th><th>Created</th><th>Completed</th><th>Evidence</th><th>Local data</th></tr></thead><tbody>{filteredItems.map((run) => <tr key={run.run_id}><td><b>{run.run_id}</b><br /><small>{run.conversation_id}</small></td><td>{providerLabels[run.provider]}<br /><small>{run.model}</small></td><td><ReproducibilityDetails run={run} /></td><td><RunRecoveryControls run={run} onRecovered={(updated) => setItems((current) => current.map((item) => item.run_id === updated.run_id ? updated : item))} /></td><td>{formatDate(run.created_at)}</td><td>{formatDate(run.completed_at)}</td><td>{run.status === 'COMPLETED' ? <><button className="secondary" type="button" onClick={() => openReport(run.run_id)}>Open report & trace</button><a className="text-link" href={`/audits/${run.run_id}`}>Open permanent report</a></> : <small>Available after completion</small>}</td><td><ConversationDataControls conversationId={run.conversation_id} onDeleted={removed} /></td></tr>)}</tbody></table></div> : <div className="empty"><b>No matching audit runs</b><p>Try clearing a filter or searching by a different run, conversation or model identifier.</p></div>}
    </> : <div className="empty"><b>No audits yet</b><p>Create and run an audit to retain a traceable record here.</p></div>}
    {reportError && <p className="alert" role="alert">{reportError}</p>}{selectedReport && <details className="history-report" open><summary>Completed report: {selectedReport.run_id}</summary><ResultDashboard result={selectedReport} /><TargetMemoryTrace runId={selectedReport.run_id} /></details>}</section>;
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
  return <section><p className="eyebrow">SAVED AUDIT REPORT</p><h1>Memory Health Report</h1><p>Report ID: {result.run_id}</p><ResultDashboard result={result} /><TargetMemoryTrace runId={result.run_id} /></section>;
}

function ReproducibilityDetails({ run }: { run: AuditRun }) {
  const retryPolicy = run.reproducibility?.target_retry_policy;
  const seed = run.reproducibility?.seed_control;
  return <details className="reproducibility-details"><summary>{run.target_configuration === 'strong' ? 'Strong Memory' : 'Weak Memory'} · {run.memory_strategy.replaceAll('_', ' ')}</summary><ul><li>{run.test_budget} tests · temperature {run.temperature} · seed {run.random_seed}</li>{seed && <li>Seed control: target {seed.target?.replaceAll('_', ' ') ?? 'not declared'} · pipeline {seed.pipeline?.replaceAll('_', ' ') ?? 'not declared'} · evaluator {seed.evaluator?.replaceAll('_', ' ') ?? 'not declared'}</li>}<li>Suite: {run.prompt_template_version}</li><li>Pipeline: {run.pipeline_provider} / {run.pipeline_model}</li><li>Evaluator: {run.evaluator_provider} / {run.evaluator_model}</li><li>Memory maintenance: {(run.memory_maintenance_policy ?? 'update_aware_consolidation').replaceAll('_', ' ')}</li>{run.target_memory_capacity && <li>Target memory capacity: {run.target_memory_capacity} records</li>}<li>Writer: {run.target_memory_writer ?? 'rule_based'}{run.target_memory_writer_version ? ` (${run.target_memory_writer_version})` : ''}</li>{retryPolicy && <li>Recovery: up to {retryPolicy.max_attempts} attempts · {retryPolicy.timeout_seconds}s timeout</li>}{run.reproducibility?.configuration_fingerprint && <li className="fingerprint">Configuration fingerprint: <code>{run.reproducibility.configuration_fingerprint}</code></li>}</ul></details>;
}

const recoveryStageLabels: Record<NonNullable<AuditRetryPlan['next_stage']>, string> = { generate_tests: 'generate the shared tests', execute_tests: 'execute unanswered tests', evaluate_responses: 'evaluate pending responses' };

function RunRecoveryControls({ run, onRecovered }: { run: AuditRun; onRecovered: (updated: AuditRun) => void }) {
  const [plan, setPlan] = useState<AuditRetryPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const inspect = async () => { setBusy(true); setMessage(''); try { setPlan(await api.retryPlan(run.run_id)); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The recovery plan could not be loaded.'); } finally { setBusy(false); } };
  const retry = async () => { setBusy(true); setMessage(''); try { const updated = await api.retry(run.run_id); onRecovered(updated); setPlan(null); setMessage(updated.status === 'COMPLETED' ? 'Recovery completed. The report is now available.' : `Recovery stopped at ${formatStatus(updated.status)}.`); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The audit could not be resumed.'); } finally { setBusy(false); } };
  if (run.status === 'COMPLETED') return <div className="recovery-controls"><span className="status-complete">Completed</span>{message && <small className="success-message" role="status">{message}</small>}</div>;
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
  const loadExperiments = useCallback(() => {
    setLoadState('loading');
    api.experimentGroups()
      .then(async (groups) => {
        const reports = await Promise.all(groups.map((group) => api.experimentResults(group.experiment_id)));
        setItems(groups);
        setAnalytics(Object.fromEntries(reports.map((report) => [report.experiment.experiment_id, report])));
        setLoadState('ready');
      })
      .catch(() => { setItems([]); setAnalytics({}); setLoadState('error'); });
  }, []);

  useEffect(() => { loadExperiments(); }, [loadExperiments]);

  const download = async (experiment: Experiment) => {
    setExportingId(experiment.experiment_id);
    try {
      const blob = await api.downloadExperimentCsv(experiment.experiment_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `experiment-${experiment.experiment_id}-results.csv`; link.click();
      URL.revokeObjectURL(url);
    } finally { setExportingId(null); }
  };

  const downloadBundle = async (experiment: Experiment) => {
    setExportingId(experiment.experiment_id);
    try {
      const blob = await api.downloadExperimentBundle(experiment.experiment_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `experiment-${experiment.experiment_id}-reproducibility-bundle.json`; link.click();
      URL.revokeObjectURL(url);
    } finally { setExportingId(null); }
  };

  return <section><h1>Experiments</h1><p>Each experiment freezes one shared test suite, so every model and memory strategy is compared fairly.</p>{loadState === 'loading' ? <p className="empty" role="status">Loading experiment groups…</p> : loadState === 'error' ? <div className="empty" role="alert"><p>Experiment groups could not be loaded. Check that the API service is available and try again.</p><button type="button" className="secondary" onClick={loadExperiments}>Try again</button></div> : items.length ? items.map((item) => <ExperimentHistoryCard key={item.experiment_id} experiment={item} report={analytics[item.experiment_id]} exporting={exportingId === item.experiment_id} onDownload={download} onDownloadBundle={downloadBundle} />) : <div className="empty"><b>No experiments yet</b><p>Start a multi-model or multi-strategy audit to create a controlled comparison group.</p></div>}<ResearchValidation /></section>;
}

function percentage(value: number | null | undefined) { return value === null || value === undefined ? 'Not tested' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`; }

function ExperimentHistoryCard({ experiment, report, exporting, onDownload, onDownloadBundle }: { experiment: Experiment; report?: ExperimentAnalytics; exporting: boolean; onDownload: (experiment: Experiment) => void; onDownloadBundle: (experiment: Experiment) => void }) {
  const complete = report?.runs.filter((item) => item.run.status === 'COMPLETED').length ?? 0;
  const failed = report?.runs.filter((item) => item.run.status === 'FAILED').length ?? 0;
  const visualRuns = report?.runs.flatMap(({ run, result }) => result ? [{
    label: run.run_id,
    groupLabel: report.conditions.find((condition) => condition.run_ids.includes(run.run_id))?.label ?? `${run.provider} · ${run.memory_strategy}`,
    result,
  }] : []) ?? [];
  return <article className="experiment"><div className="experiment-heading"><div><h2>{experiment.label}</h2><p className="experiment-summary">{experiment.status === 'COMPLETED' ? 'All conditions completed on the same frozen suite.' : 'This comparison remains reproducible because its test suite is frozen.'}</p></div><div><button className="secondary export-button" type="button" disabled={exporting} onClick={() => onDownload(experiment)}>{exporting ? 'Preparing export…' : 'Download group CSV'}</button><button className="secondary export-button" type="button" disabled={exporting} onClick={() => onDownloadBundle(experiment)}>{exporting ? 'Preparing export…' : 'Download reproducibility bundle'}</button></div></div><div className="experiment-scores"><span><small>Shared tests</small><b>{experiment.test_suite_metadata.test_count || '—'}</b></span><span><small>Conditions complete</small><b>{complete} / {report?.runs.length ?? 0}</b></span></div>{failed > 0 && <p className="experiment-alert"><b>{failed} failed condition{failed === 1 ? '' : 's'} require attention.</b> Completed conditions are retained for comparison.</p>}<p><small>Suite: seed {experiment.test_suite_configuration.random_seed} · {experiment.test_suite_configuration.test_budget} test budget · {experiment.test_suite_configuration.prompt_template_version}</small></p>{report && <>{visualRuns.length > 1 && <Suspense fallback={<p className="chart-loading" role="status">Loading visual comparison charts…</p>}><ComparisonVisualizations runs={visualRuns} /></Suspense>}<ConditionTable report={report} /><RunReports runs={report.runs} /><PairedSignals comparisons={report.paired_comparisons} /></>}</article>;
}

function ConditionTable({ report }: { report: ExperimentAnalytics }) {
  return <div className="comparison-scroll experiment-history-table"><table><thead><tr><th>Condition</th><th>Completed</th><th>Overall mean</th><th>Variation</th><th>Tests passed</th><th>Failures</th></tr></thead><tbody>{report.conditions.map((condition) => <tr key={condition.condition_id}><th scope="row">{condition.label}</th><td>{condition.completed_runs} / {condition.planned_runs}</td><td><b>{percentage(condition.overall_mean)}</b></td><td>{percentage(condition.overall_standard_deviation)}</td><td>{condition.tests_passed} / {condition.tests_total}</td><td>{condition.failure_count}</td></tr>)}</tbody></table></div>;
}

function RunReports({ runs }: { runs: ExperimentRunReport[] }) {
  return <details className="experiment-history-detail"><summary>Condition reports and detected failures</summary>{runs.map(({ run, result }) => <details className="run-report" key={run.run_id}><summary><b>{providerLabels[run.provider]} · {run.memory_strategy.replaceAll('_', ' ')}</b> — {formatStatus(run.status)}{result && ` · ${percentage(result.overall_score)}`}</summary>{result ? <><p>{result.tests_passed} / {result.tests_total} tests passed. {result.failures.length} detected failure{result.failures.length === 1 ? '' : 's'}.</p>{result.failures.length ? <ul className="experiment-failures">{result.failures.map((failure) => <li key={failure.failure_id}><b>{failure.test.dimension.replaceAll('_', ' ')}</b>: {failure.evaluation.reason}<span>Test: {failure.test.prompt}</span></li>)}</ul> : <p className="empty">No failures were detected for this run.</p>}</> : <p className="empty">Results are not available until this run completes.</p>}</details>)}</details>;
}

function PairedSignals({ comparisons }: { comparisons: PairedComparison[] }) {
  if (!comparisons.length) return <p className="repeat-note">Paired comparison signals will appear after at least two conditions complete.</p>;
  return <details className="experiment-history-detail"><summary>Paired comparison signals</summary><p>Each row aligns the exact frozen tests answered by two completed runs. A positive delta favours the candidate condition. The 95% interval is a deterministic bootstrap estimate; the p-value is a two-sided exact sign test over discordant tests.</p><div className="comparison-scroll"><table><thead><tr><th>Candidate vs reference</th><th>Shared tests</th><th>Candidate-only passes</th><th>Reference-only passes</th><th>Delta</th><th>95% interval</th><th>p-value</th></tr></thead><tbody>{comparisons.map((pair) => <tr key={`${pair.reference_run_id}:${pair.candidate_run_id}`}><th scope="row">{pair.candidate_label} vs {pair.reference_label}</th><td>{pair.shared_tests}</td><td>{pair.candidate_only_passed}</td><td>{pair.reference_only_passed}</td><td><b>{pair.candidate_delta_percentage_points === null ? 'Not available' : `${pair.candidate_delta_percentage_points > 0 ? '+' : ''}${pair.candidate_delta_percentage_points.toFixed(1)} pp`}</b></td><td>{pair.candidate_delta_confidence_interval_low === null || pair.candidate_delta_confidence_interval_high === null ? 'Not available' : `${pair.candidate_delta_confidence_interval_low.toFixed(1)} to ${pair.candidate_delta_confidence_interval_high.toFixed(1)} pp`}</td><td>{pair.two_sided_sign_test_p_value === null ? 'Not available' : pair.two_sided_sign_test_p_value.toFixed(4)}</td></tr>)}</tbody></table></div></details>;
}

export function About() {
  return <section><h1>About AI Memory Health Auditor</h1><p>AI Memory Health Auditor evaluates how reliably a controlled conversational AI remembers and uses information over time.</p><p>It separates the underlying language model from the memory policy being tested, then measures Accuracy, Freshness, Conflict Resolution and Appropriate Use with traceable evidence.</p><p>Controlled experiment groups freeze one test suite before comparing models or strategies. Rule-based components provide a reproducible local baseline; optional provider connectors can be configured on the backend.</p></section>;
}
