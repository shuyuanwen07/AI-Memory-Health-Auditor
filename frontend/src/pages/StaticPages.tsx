import { saveBlob } from '../services/download';
import { UIActionLink } from '../components/ui';
import { useUIConfirmation } from '../components/ui';
import { UIAlert, UICard } from '../components/ui';
import { UIButton, UIInput, UISelect, UIOption, UIPanel, UISummary, UITable } from '../components/ui';
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../services/api';
import { auditDisplayNames, friendlyText, processingLabel } from '../services/display';
import type { AuditResult, AuditRetryPlan, AuditRun, Experiment, ExperimentAnalytics, ExperimentRunReport, PairedComparison } from '../types/domain';
import { ResultDashboard } from '../components/ResultDashboard';
import { TargetMemoryTrace } from '../components/TargetMemoryTrace';
import { TestSuiteReview } from '../components/TestSuiteReview';
import type { TestCase } from '../types/domain';
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
  openrouter: 'OpenRouter',
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
  const [historyPage, setHistoryPage] = useState(0);
  const pageSize = 20;
  useEffect(() => setHistoryPage(0), [search, statusFilter, providerFilter, strategyFilter]);
  const loadHistory = useCallback(() => {
    setLoadState('loading');
    api.audits().then((audits) => { setItems(audits); setLoadState('ready'); })
      .catch(() => { setItems([]); setLoadState('error'); });
  }, []);
  useEffect(() => { loadHistory(); }, [loadHistory]);
  const removed = () => { loadHistory(); };
  const displayNames = auditDisplayNames(items);
  const filteredItems = useMemo(() => {
    const query = search.trim().toLowerCase();
    return items.filter((run) => {
      const matchesSearch = !query || [displayNames[run.run_id], run.model, run.memory_strategy, friendlyStrategy(run.memory_strategy), providerLabels[run.provider], formatDate(run.created_at)]
        .some((value) => value.toLowerCase().includes(query));
      return matchesSearch
        && (statusFilter === 'all' || run.status === statusFilter)
        && (providerFilter === 'all' || run.provider === providerFilter)
        && (strategyFilter === 'all' || run.memory_strategy === strategyFilter);
    });
  }, [items, search, statusFilter, providerFilter, strategyFilter, displayNames]);
  const lastPage = Math.max(0, Math.ceil(filteredItems.length / pageSize) - 1);
  const activePage = Math.min(historyPage, lastPage);
  const pageItems = filteredItems.slice(activePage * pageSize, (activePage + 1) * pageSize);
  const filtersActive = Boolean(search) || statusFilter !== 'all' || providerFilter !== 'all' || strategyFilter !== 'all';
  const clearFilters = () => { setSearch(''); setStatusFilter('all'); setProviderFilter('all'); setStrategyFilter('all'); };
  return <section><h1>Audit History</h1>
    {loadState === 'loading' ? <p className="empty" role="status">Loading audit history…</p> : loadState === 'error' ? <UIAlert className="empty" role="alert"><p>Audit history could not be loaded. Check that the API service is available and try again.</p><UIButton type="button" className="secondary" onClick={loadHistory}>Try again</UIButton></UIAlert> : items.length ? <>
      <div className="history-filters" aria-label="Audit history filters">
        <label>Find an audit<UIInput aria-label="Search audit history" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Audit name, model, memory approach, or date" /></label>
        <label>Result<UISelect aria-label="Filter by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><UIOption value="all">All results</UIOption>{[...new Set(items.map((run) => run.status))].map((status) => <UIOption key={status} value={status}>{formatStatus(status)}</UIOption>)}</UISelect></label>
        <label>Model provider<UISelect aria-label="Filter by target provider" value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)}><UIOption value="all">All providers</UIOption>{[...new Set(items.map((run) => run.provider))].map((provider) => <UIOption key={provider} value={provider}>{providerLabels[provider]}</UIOption>)}</UISelect></label>
        <label>Memory approach<UISelect aria-label="Filter by memory strategy" value={strategyFilter} onChange={(event) => setStrategyFilter(event.target.value)}><UIOption value="all">All approaches</UIOption>{[...new Set(items.map((run) => run.memory_strategy))].map((strategy) => <UIOption key={strategy} value={strategy}>{strategy.replaceAll('_', ' ')}</UIOption>)}</UISelect></label>
        {filtersActive && <UIButton type="button" className="secondary history-filter-reset" onClick={clearFilters}>Clear filters</UIButton>}
      </div>
      <p className="history-count" role="status">Showing {filteredItems.length} of {items.length} audit run{items.length === 1 ? '' : 's'}.</p>
      {filteredItems.length ? <div className="audit-history-list" aria-label="Audit history">{pageItems.map((run) => <AuditHistoryCard key={run.run_id} displayName={displayNames[run.run_id]} run={run} onRecovered={(updated) => setItems((current) => current.map((item) => item.run_id === updated.run_id ? updated : item))} onDeleted={removed} />)}</div> : <div className="empty"><b>No matching audits</b><p>Try clearing a filter or searching by a different model, memory approach, or date.</p></div>}
      {filteredItems.length > pageSize && <nav aria-label="Audit history pages" className="review-toolbar"><UIButton className="secondary" disabled={activePage === 0} onClick={() => setHistoryPage(activePage - 1)}>Previous page</UIButton><span role="status">Page {activePage + 1} of {lastPage + 1} · {activePage * pageSize + 1}–{Math.min((activePage + 1) * pageSize, filteredItems.length)} of {filteredItems.length} matching audits</span><UIButton className="secondary" disabled={activePage === lastPage} onClick={() => setHistoryPage(activePage + 1)}>Next page</UIButton></nav>}
    </> : <div className="empty"><b>No audits yet</b><p>Create and run an audit to retain a traceable record here.</p></div>}
  </section>;
}

function friendlyStrategy(strategy: AuditRun['memory_strategy']) {
  return strategy.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function friendlyExperimentLabel(label: string) {
  return friendlyText(label)
    .replace(/\s+\d{4}-\d{2}-\d{2}T[\d:.]+Z$/, '')
    .replace(/(?:SYN-C|STUDY-)0*(\d+)/gi, (_match, number: string) => `Scenario ${Number(number)}`)
    .replace(/:\s*(Scenario \d+)/, ' · $1')
    .replace(/held_out/g, 'Validation').replace(/diagnostic/g, 'Diagnosis');
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

function AuditHistoryCard({ run, displayName, onRecovered, onDeleted }: {
  run: AuditRun;
  displayName: string;
  onRecovered: (run: AuditRun) => void;
  onDeleted: () => void;
}) {
  const completed = run.status === 'COMPLETED';
  return <UICard className="audit-history-card">
    <div className="audit-history-card-main">
      <div className="audit-history-card-meta"><span>{providerLabels[run.provider]}</span><span>{completed ? `Completed ${shortDate(run.completed_at)}` : `Started ${shortDate(run.created_at)}`}</span></div>
      <h2>{displayName} · {friendlyStrategy(run.memory_strategy)}</h2>
      <p>{run.model} · Test budget: up to {run.test_budget} questions</p>
      <ReproducibilityDetails run={run} />
    </div>
    <div className="audit-history-card-actions">
      <RunRecoveryControls run={run} onRecovered={onRecovered} />
      {completed ? <UIActionLink className="secondary audit-view-report" href={`/audits/${run.run_id}`}>View report</UIActionLink> : run.status === 'CANCELLED' ? <CancelledRunEvidence runId={run.run_id} /> : <small>Results are available after completion.</small>}
    </div>
    <UIPanel className="audit-technical-details"><UISummary>Dates and saved data</UISummary><dl><div><dt>Created</dt><dd>{formatDate(run.created_at)}</dd></div><div><dt>Completed</dt><dd>{formatDate(run.completed_at)}</dd></div></dl><ConversationDataControls conversationId={run.conversation_id} onDeleted={onDeleted} /></UIPanel>
  </UICard>;
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
  if (state === 'error' || !result) return <section><h1>Memory Health Report</h1><UIAlert className="empty" role="alert"><b>Report unavailable</b><p>This audit may not be complete, may have been deleted with its authorised conversation, or the API is unavailable.</p><a className="text-link" href="/history">Return to Audit History</a></UIAlert></section>;
  return <section><p className="eyebrow">SAVED AUDIT REPORT</p><h1>Memory Health Report</h1><UIActionLink className="secondary comparison-report-link" href={`/compare?before=${encodeURIComponent(result.run_id)}`}>Compare before & after →</UIActionLink><ResultDashboard result={result} /><TargetMemoryTrace runId={result.run_id} /></section>;
}

function ReproducibilityDetails({ run }: { run: AuditRun }) {
  const retryPolicy = run.reproducibility?.target_retry_policy;
  const seed = run.reproducibility?.seed_control;
  return <UIPanel className="reproducibility-details"><UISummary>Memory settings · {friendlyStrategy(run.memory_strategy)}</UISummary><ul><li>Test budget: up to {run.test_budget} questions · temperature {run.temperature} · seed {run.random_seed}</li>{seed && <li>Seed control: target {seed.target?.replaceAll('_', ' ') ?? 'not declared'} · pipeline {seed.pipeline?.replaceAll('_', ' ') ?? 'not declared'} · evaluator {seed.evaluator?.replaceAll('_', ' ') ?? 'not declared'}</li>}<li>Test preparation: {processingLabel(run.pipeline_provider)}{run.pipeline_provider !== 'rule_based' && ` · ${run.pipeline_model}`}</li><li>Assessment: {processingLabel(run.evaluator_provider)}{run.evaluator_provider !== 'rule_based' && ` · ${run.evaluator_model}`}</li><li>Target system: {run.target_system_adapter === "external-http" ? "Independent target service (internal memory unobserved)" : "Model with configurable memory"}</li>{run.target_memory_profile&&<><li>Configuration: {run.target_memory_profile.label} · version {run.target_memory_profile.version}</li><li>Context budget: {run.target_memory_profile.max_retrieved_records} memories / {run.target_memory_profile.context_character_budget} characters</li><li>Project isolation: {run.target_memory_profile.isolate_project_scope?"On":"Off"} · current-state priority: {run.target_memory_profile.prefer_current_state?"On":"Off"}</li>{run.target_memory_profile.additional_instructions&&<li>Additional target instructions: {run.target_memory_profile.additional_instructions}</li>}</>}{run.reproducibility?.study_role&&<li>Experiment purpose: {run.reproducibility.study_role.replaceAll("_"," ")} · {run.reproducibility.validation_split?.replaceAll("_"," ")}</li>}<li>Memory maintenance: {(run.memory_maintenance_policy ?? 'update_aware_consolidation').replaceAll('_', ' ')}</li>{run.target_memory_capacity && <li>Target memory capacity: {run.target_memory_capacity} records</li>}<li>Memory preparation: {processingLabel(run.target_memory_writer)}</li>{retryPolicy && <li>Recovery: up to {retryPolicy.max_attempts} attempts · {retryPolicy.timeout_seconds}s timeout</li>}</ul></UIPanel>;
}

const recoveryStageLabels: Record<NonNullable<AuditRetryPlan['next_stage']>, string> = { generate_tests: 'generate the shared tests', execute_tests: 'execute unanswered tests', evaluate_responses: 'evaluate pending responses' };

function RunRecoveryControls({ run, onRecovered }: { run: AuditRun; onRecovered: (updated: AuditRun) => void }) {
  const [plan, setPlan] = useState<AuditRetryPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [preparedTests, setPreparedTests] = useState<TestCase[] | null>(null);
  const inspectTests = async () => { setBusy(true); setMessage(''); try { setPreparedTests((await api.testReview(run.run_id)).tests); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'Prepared tests could not be loaded.'); } finally { setBusy(false); } };
  const updatePreparedTest = async (test: TestCase, decision?: 'accepted' | 'rejected') => { setBusy(true); setMessage(''); try { const updated = decision ? await api.reviewTest(run.run_id, test.test_id, decision) : await api.regenerateTest(run.run_id, test.test_id); setPreparedTests((items) => items?.map((item) => item.test_id === updated.test_id ? updated : item) ?? null); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The prepared test could not be updated.'); } finally { setBusy(false); } };
  const inspect = async () => { setBusy(true); setMessage(''); try { setPlan(await api.retryPlan(run.run_id)); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The recovery plan could not be loaded.'); } finally { setBusy(false); } };
  const retry = async () => { setBusy(true); setMessage(''); try { const updated = await api.retry(run.run_id); onRecovered(updated); setPlan(null); setMessage(updated.status === 'COMPLETED' ? 'Recovery completed. The report is now available.' : `Recovery stopped at ${formatStatus(updated.status)}.`); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The audit could not be resumed.'); } finally { setBusy(false); } };
  if (run.status === 'COMPLETED') return <div className="recovery-controls"><span className="status-complete">Completed</span>{message && <small className="success-message" role="status">{message}</small>}</div>;
  if (run.status === 'CANCELLED') return <div className="recovery-controls"><b>{formatStatus(run.status)}</b><small>This run is terminal and cannot be resumed.</small></div>;
  return <div className="recovery-controls"><b>{formatStatus(run.status)}</b>{!plan ? <UIButton type="button" className="secondary" disabled={busy} onClick={inspect}>{busy ? 'Checking…' : 'View recovery plan'}</UIButton> : plan.retryable && plan.next_stage ? <><small>{plan.pending > 0 ? `${plan.pending} item${plan.pending === 1 ? '' : 's'} pending; recovery will ${recoveryStageLabels[plan.next_stage]}.` : `Recovery will ${recoveryStageLabels[plan.next_stage]}.`}</small><UIButton type="button" disabled={busy} onClick={retry}>{busy ? 'Resuming…' : 'Resume audit'}</UIButton></> : <small>No recovery is required for this run.</small>}{plan?.next_stage === 'execute_tests' && <UIButton type="button" className="secondary" disabled={busy} onClick={inspectTests}>Review prepared tests</UIButton>}{preparedTests && plan?.next_stage === 'execute_tests' && <TestSuiteReview tests={preparedTests} busy={busy} onReview={(test, decision) => updatePreparedTest(test, decision)} onRegenerate={(test) => updatePreparedTest(test)} />}{message && <small className={message.startsWith('Recovery completed') ? 'success-message' : 'alert-message'} role="status">{message}</small>}</div>;
}

function ConversationDataControls({ conversationId, onDeleted }: { conversationId: string; onDeleted: () => void }) {
  const [confirmationOpen, setConfirmationOpen] = useState(false); const [confirmation, setConfirmation] = useState(''); const [busy, setBusy] = useState(false); const [message, setMessage] = useState('');
  const download = async () => { setBusy(true); setMessage(''); try { const blob = await api.downloadConversationExport(conversationId); saveBlob(blob, 'memory-health-data-export.json'); setMessage('The authorised data export is ready; your browser was asked to save it.'); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The export could not be created.'); } finally { setBusy(false); } };
  const erase = async () => { setBusy(true); setMessage(''); try { const receipt = await api.deleteConversation(conversationId, conversationId); setMessage(`Deleted this conversation and its ${receipt.deleted_audit_runs} audit records.`); onDeleted(); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The local data could not be deleted.'); } finally { setBusy(false); } };
  return <div className="conversation-data-controls"><UIButton type="button" className="secondary" disabled={busy} onClick={download}>Export JSON</UIButton><UIButton type="button" className="ghost" disabled={busy} onClick={() => { setConfirmationOpen(!confirmationOpen); setMessage(''); }}>Delete data</UIButton>{confirmationOpen && <div className="delete-confirmation"><label>Enter <b>DELETE</b> to permanently delete this conversation and all of its audit data.<UIInput aria-label="Confirm deletion of saved conversation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label><UIButton type="button" className="danger" disabled={busy || confirmation !== 'DELETE'} onClick={erase}>Permanently delete local data</UIButton></div>}{message && <small className={message.startsWith('The authorised') ? 'success-message' : 'alert-message'}>{message}</small>}</div>;
}

export function Experiments() {
  const { confirm, dialog } = useUIConfirmation();
  const [items, setItems] = useState<Experiment[]>([]);
  const [analytics, setAnalytics] = useState<Record<string, ExperimentAnalytics>>({});
  const [reportErrors, setReportErrors] = useState<Record<string, boolean>>({});
  const [reportRetry, setReportRetry] = useState(0);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [exportingId, setExportingId] = useState<string | null>(null);
  const [experimentPage, setExperimentPage] = useState(0);
  const experimentPageSize = 3;
  const lastExperimentPage = Math.max(0, Math.ceil(items.length / experimentPageSize) - 1);
  const activeExperimentPage = Math.min(experimentPage, lastExperimentPage);
  const visibleExperiments = items.slice(activeExperimentPage * experimentPageSize, (activeExperimentPage + 1) * experimentPageSize);
  const [actionMessage, setActionMessage] = useState('');
  const loadExperiments = useCallback(() => {
    setLoadState('loading');
    api.experimentGroups()
      .then(async (groups) => {
        const orderedGroups = [...groups].sort((left, right) => scenarioNumber(left.label) - scenarioNumber(right.label));
        setItems(orderedGroups);
        setAnalytics({});
        setReportErrors({});
        setLoadState('ready');
      })
      .catch(() => { setItems([]); setAnalytics({}); setLoadState('error'); });
  }, []);

  useEffect(() => { loadExperiments(); }, [loadExperiments]);

  useEffect(() => {
    let cancelled = false;
    const pending = items.slice(activeExperimentPage * experimentPageSize, (activeExperimentPage + 1) * experimentPageSize)
      .filter(item => !analytics[item.experiment_id]);
    if (!pending.length) return;
    setReportErrors(current => ({...current, ...Object.fromEntries(pending.map(item => [item.experiment_id, false]))}));
    void Promise.allSettled(pending.map(item => api.experimentResults(item.experiment_id))).then(results => {
      if (cancelled) return;
      const reports: Record<string, ExperimentAnalytics> = {};
      const errors: Record<string, boolean> = {};
      results.forEach((result, i) => {
        const id = pending[i].experiment_id;
        if (result.status === 'fulfilled') reports[id] = result.value;
        else errors[id] = true;
      });
      setAnalytics(current => ({...current, ...reports}));
      setReportErrors(current => ({...current, ...errors}));
    });
    return () => { cancelled = true; };
    // Loaded reports are cached; retries and page changes request only missing summaries.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, activeExperimentPage, reportRetry]);

  const download = async (experiment: Experiment) => {
    setExportingId(experiment.experiment_id); setActionMessage('');
    try {
      const blob = await api.downloadExperimentCsv(experiment.experiment_id);
      saveBlob(blob, 'experiment-results.csv');
      setActionMessage('The download is ready; your browser was asked to save it.');
    } catch (cause) { setActionMessage(cause instanceof Error ? cause.message : 'The experiment CSV could not be created.'); }
    finally { setExportingId(null); }
  };

  const downloadBundle = async (experiment: Experiment) => {
    setExportingId(experiment.experiment_id); setActionMessage('');
    try {
      const blob = await api.downloadExperimentBundle(experiment.experiment_id);
      saveBlob(blob, 'experiment-research-data.json');
      setActionMessage('The download is ready; your browser was asked to save it.');
    } catch (cause) { setActionMessage(cause instanceof Error ? cause.message : 'The reproducibility bundle could not be created.'); }
    finally { setExportingId(null); }
  };

  const downloadArtifact = async (experiment: Experiment) => {
    setExportingId(experiment.experiment_id); setActionMessage('');
    try {
      const blob = await api.downloadExperimentArtifact(experiment.experiment_id);
      saveBlob(blob, 'experiment-research-artifact.zip');
      setActionMessage('The download is ready; your browser was asked to save it.');
    } catch (cause) { setActionMessage(cause instanceof Error ? cause.message : 'The frozen experiment artifact could not be created.'); }
    finally { setExportingId(null); }
  };

  const cancelExperiment = async (experiment: Experiment) => {
    if (!await confirm(`Cancel every unfinished condition in ${experiment.label}? Completed results and retained evidence will remain available.`)) return;
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

  return <section>{dialog}<h1>Compare memory strategies & models</h1><p className="experiment-page-intro">See how different settings perform on the same questions. Start with the result summary, then inspect which answers changed.</p>{actionMessage && <p className={(actionMessage.startsWith('The unfinished') || actionMessage.startsWith('The download')) ? 'success-message' : 'alert-message'} role="status">{actionMessage}</p>}{loadState === 'loading' ? <p className="empty" role="status">Loading experiment groups…</p> : loadState === 'error' ? <UIAlert className="empty" role="alert"><p>Experiment groups could not be loaded. Check that the API service is available and try again.</p><UIButton type="button" className="secondary" onClick={loadExperiments}>Try again</UIButton></UIAlert> : items.length ? visibleExperiments.map((item) => <ExperimentHistoryCard key={item.experiment_id} experiment={item} report={analytics[item.experiment_id]} reportError={reportErrors[item.experiment_id]} onRetryReport={() => setReportRetry(current => current + 1)} exporting={exportingId === item.experiment_id} onDownload={download} onDownloadBundle={downloadBundle} onDownloadArtifact={downloadArtifact} onCancel={cancelExperiment} />) : <div className="empty"><b>No experiments yet</b><p>Start a multi-model or multi-strategy audit to create a controlled comparison group.</p></div>}{items.length > experimentPageSize && <nav className="history-pagination" aria-label="Experiment pages"><UIButton type="button" className="secondary" disabled={activeExperimentPage === 0} onClick={() => setExperimentPage(activeExperimentPage - 1)}>Previous experiments</UIButton><span>Page {activeExperimentPage + 1} of {lastExperimentPage + 1} · {items.length} experiment groups</span><UIButton type="button" className="secondary" disabled={activeExperimentPage >= lastExperimentPage} onClick={() => setExperimentPage(activeExperimentPage + 1)}>Next experiments</UIButton></nav>}<UIPanel className="experiment-history-detail"><UISummary>Research tools · benchmarks and reviewer checks</UISummary><p>Use these tools to validate assessment quality and prepare research experiments.</p><ResearchValidation /></UIPanel></section>;
}

function percentage(value: number | null | undefined) { return value === null || value === undefined ? 'Not tested' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`; }

function strategyExplanation(strategy: AuditRun['memory_strategy']) {
  const descriptions: Record<AuditRun['memory_strategy'], string> = {
    no_memory: 'Answers without stored memories.',
    full_context: 'Uses all available conversation context.',
    weak_first_hit: 'Uses the first matching memory.',
    strong_rule_based: 'Selects memories using predefined rules.',
    strong_score_based: 'Ranks memories by relevance and other scoring signals.',
    scope_aware: 'Selects memories for the relevant project or context.',
    temporal_importance: 'Considers relevance, time and importance when selecting memories.',
  };
  return descriptions[strategy] ?? 'Controls which memories the model receives.';
}

function ExperimentOutcome({ report }: { report: ExperimentAnalytics }) {
  const completed = report.conditions.filter(condition => condition.completed_runs > 0 && condition.tests_total > 0);
  const pair = report.conditions.length === 2 && report.paired_comparisons.length === 1 ? report.paired_comparisons[0] : undefined;
  const settingName = (runId: string, fallback: string) => {
    const run = report.runs.find(item => item.run.run_id === runId)?.run;
    if (!run) return friendlyText(fallback);
    const multipleModels = new Set(report.runs.map(item => item.run.model)).size > 1;
    return `${multipleModels ? `${run.model} · ` : ''}${friendlyStrategy(run.memory_strategy)}`;
  };
  const pending = report.runs.some(({ run }) => !['COMPLETED', 'FAILED', 'CANCELLED'].includes(run.status));
  let headline = pending ? 'Comparison in progress' : 'Results are ready to review';
  let explanation = 'Compare passed questions below. Scores describe these tests, rather than overall model reliability.';
  if (!completed.length) {
    headline = 'No scored results yet';
    explanation = 'A score appears after a run completes. Completed runs are different from passed questions.';
  } else if (pair && pair.shared_tests > 0 && !pending) {
    const left = pair.both_passed + pair.reference_only_passed;
    const right = pair.both_passed + pair.candidate_only_passed;
    headline = left === right ? 'Same overall pass rate on shared questions' : 'Different pass rates on shared questions';
    explanation = `${settingName(pair.reference_run_id, pair.reference_label)} passed ${left} of ${pair.shared_tests}; ${settingName(pair.candidate_run_id, pair.candidate_label)} passed ${right} of ${pair.shared_tests}. ${left === right ? 'Equal totals can still contain different correct answers.' : 'Check the changed answers before deciding which setting to use.'}`;
  } else if (completed.length > 1 && !report.paired_comparisons.some(item => item.shared_tests > 0)) {
    headline = 'Results available · no shared-question comparison';
    explanation = 'These results are not paired on identical questions. Read each score separately; they do not establish a fair ranking.';
  }
  return <div className="experiment-outcome" role="status">
    <p className="eyebrow">RESULT AT A GLANCE</p><h3>{headline}</h3><p>{explanation}</p>
    {pair && pair.shared_tests > 0 && <div className="experiment-outcome-counts">
      <span><b>{pair.both_passed}</b> both answered correctly</span>
      <span><b>{pair.both_failed}</b> both failed</span>
      <span><b>{pair.reference_only_passed + pair.candidate_only_passed}</b> answered correctly by only one setting</span>
    </div>}
    <small>Automated assessments of this test set. A small set or one run is not enough to establish general superiority.</small>
  </div>;
}

function ExperimentHistoryCard({ experiment, report, reportError, onRetryReport, exporting, onDownload, onDownloadBundle, onDownloadArtifact, onCancel }: { experiment: Experiment; report?: ExperimentAnalytics; reportError?: boolean; onRetryReport: () => void; exporting: boolean; onDownload: (experiment: Experiment) => void; onDownloadBundle: (experiment: Experiment) => void; onDownloadArtifact: (experiment: Experiment) => void; onCancel: (experiment: Experiment) => void }) {
  const complete = report?.runs.filter((item) => item.run.status === 'COMPLETED').length ?? 0;
  const failed = report?.runs.filter((item) => item.run.status === 'FAILED').length ?? 0;
  const visualRuns = report?.runs.flatMap(({ run, result }) => result ? [{
    label: `${run.model} · ${friendlyStrategy(run.memory_strategy)}`,
    groupLabel: report.conditions.find((condition) => condition.run_ids.includes(run.run_id))?.label ?? `${run.provider} · ${run.model} · ${run.memory_strategy}`,
    result,
  }] : []) ?? [];
  const models = [...new Set(report?.runs.map(({ run }) => run.model) ?? [])];
  const canCancel = !['COMPLETED', 'FAILED', 'CANCELLED'].includes(experiment.status);
  return <UICard className="experiment">
    <div className="experiment-heading"><div><p className="eyebrow">SAME QUESTIONS · DIFFERENT SETTINGS</p><h2>{friendlyExperimentLabel(experiment.label)}</h2><p className="experiment-date">{shortDate(experiment.created_at)}</p></div>
      {canCancel && <UIButton className="ghost" type="button" disabled={exporting} onClick={() => onCancel(experiment)}>{exporting ? 'Cancelling…' : 'Cancel unfinished conditions'}</UIButton>}
    </div>
    <div className="experiment-scores"><span><small>Questions in the shared test set</small><b>{experiment.test_suite_metadata.test_count ?? '—'}</b></span><span><small>Runs completed · not questions passed</small><b>{report ? `${complete} / ${report.runs.length}` : reportError ? 'Not available' : 'Loading…'}</b></span></div>
    {reportError && <UIAlert role="alert"><p>This result summary could not be loaded. Other experiment results remain available.</p><UIButton type="button" className="secondary" onClick={onRetryReport}>Retry result summary</UIButton></UIAlert>}
    <p className="experiment-purpose">{models.length === 1 ? `Model: ${models[0]}. Compare how different memory settings affect its answers; the model is not retrained.` : models.length > 1 ? `Models: ${models.join(', ')}. This experiment compares model and memory settings on one shared test set.` : 'The same test set is used across the experiment settings.'}</p>
    {failed > 0 && <p className="experiment-alert"><b>{failed} run{failed === 1 ? '' : 's'} could not finish.</b> This is a run error, not an incorrect answer. Completed results remain available.</p>}
    {report && <><ExperimentOutcome report={report} />
      <div className="experiment-setting-cards" aria-label="Results by setting">{report.conditions.map(condition => <div className="experiment-setting-card" key={condition.condition_id}>
        <h3>{friendlyStrategy(condition.memory_strategy)}</h3><p className="experiment-model-name">{condition.model}</p><p>{strategyExplanation(condition.memory_strategy)}</p>
        <b className="experiment-pass-count">{condition.tests_total ? `${condition.tests_passed} of ${condition.tests_total} answers passed` : 'No scored answers yet'}</b>
        <span>{condition.completed_runs} of {condition.planned_runs} runs complete</span>
      </div>)}</div>
      {visualRuns.length > 1 && <Suspense fallback={<p className="chart-loading" role="status">Loading comparison charts…</p>}><p className="experiment-chart-explanation">The overall chart averages the tested ability scores. It can differ from the fraction of answers passed above when abilities have different numbers of questions.</p><ComparisonVisualizations runs={visualRuns} /></Suspense>}
      <RunReports runs={report.runs} />
      <UIPanel className="experiment-history-detail"><UISummary>Detailed scores, runtime & statistics</UISummary><ConditionTable report={report} /><PairedSignals comparisons={report.paired_comparisons} /></UIPanel>
    </>}
    <UIPanel className="experiment-history-detail"><UISummary>Export results & experiment settings</UISummary>
      <p>Download a results table, a record for reproducing this experiment, or the fixed test materials.</p>
      <div className="experiment-export-actions"><UIButton className="secondary" disabled={exporting} onClick={() => onDownload(experiment)}>{exporting ? 'Preparing export…' : 'Results table (CSV)'}</UIButton><UIButton className="secondary" disabled={exporting} onClick={() => onDownloadBundle(experiment)}>Reproduction package</UIButton><UIButton className="secondary" disabled={exporting} onClick={() => onDownloadArtifact(experiment)}>Fixed test materials</UIButton></div>
      <p><small>Requested question limit: {experiment.test_suite_configuration.test_budget} · Questions generated: {experiment.test_suite_metadata.test_count} · Random seed: {experiment.test_suite_configuration.random_seed}</small></p>
    </UIPanel>
  </UICard>;
}

function ConditionTable({ report }: { report: ExperimentAnalytics }) {
  return <div className="comparison-scroll experiment-history-table"><UITable><thead><tr><th>Model & memory setting</th><th>Runs completed</th><th>Average pass rate</th><th>Variation across runs</th><th>Answers passed</th><th>Detected problems</th><th>Runtime</th></tr></thead><tbody>{report.conditions.map((condition) => <tr key={condition.condition_id}><th scope="row">{friendlyText(condition.label)}</th><td>{condition.completed_runs} / {condition.planned_runs}</td><td><b>{percentage(condition.overall_mean)}</b></td><td>{percentage(condition.overall_standard_deviation)}</td><td>{condition.tests_passed} / {condition.tests_total}</td><td>{condition.failure_count}</td><td>{condition.mean_latency_ms === null ? '—' : `${Math.round(condition.mean_latency_ms)} ms avg`} · {condition.total_tokens === null ? 'tokens —' : `${condition.total_tokens.toLocaleString()} tokens`}</td></tr>)}</tbody></UITable></div>;
}

function CancelledRunEvidence({ runId }: { runId: string }) {
  const [evidence, setEvidence] = useState<Awaited<ReturnType<typeof api.cancelledEvidence>> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const load = async () => { setLoading(true); setError(''); try { setEvidence(await api.cancelledEvidence(runId)); } catch (cause) { setError(cause instanceof Error ? cause.message : 'Retained cancellation evidence could not be loaded.'); } finally { setLoading(false); } };
  return <div className="cancelled-evidence"><p className="empty">This condition was cancelled before evaluation. Any completed target responses and safe memory trace are retained.</p>{!evidence && <UIButton type="button" className="secondary" disabled={loading} onClick={load}>{loading ? 'Loading retained evidence…' : 'Inspect retained evidence'}</UIButton>}{error && <UIAlert role="alert" className="alert-message">{error}</UIAlert>}{evidence && <><p><b>{evidence.completed_responses.length}</b> target response{evidence.completed_responses.length === 1 ? '' : 's'} completed before cancellation.</p>{evidence.completed_responses.length ? <ul className="experiment-failures">{evidence.completed_responses.map((response, index) => <li key={response.response_id}><b>Response {index + 1}</b>: {response.response_text}</li>)}</ul> : <p className="empty">No target response completed before cancellation.</p>}<TargetMemoryTrace runId={runId} /></>}</div>;
}

function RunReports({ runs }: { runs: ExperimentRunReport[] }) {
  return <UIPanel className="experiment-history-detail"><UISummary>Inspect answers & detected problems</UISummary>{runs.map(({ run, result }) => <UIPanel className="run-report" key={run.run_id}><UISummary><b>{providerLabels[run.provider]} · {friendlyStrategy(run.memory_strategy)}</b> — {formatStatus(run.status)}{result && ` · ${percentage(result.overall_score)}`}</UISummary>{result ? <><p>{result.tests_passed} / {result.tests_total} tests passed. {result.failures.length} detected failure{result.failures.length === 1 ? '' : 's'}.</p>{result.failures.length ? <ul className="experiment-failures">{result.failures.map((failure) => <li key={failure.failure_id}><b>{failure.test.dimension.replaceAll('_', ' ')}</b>: {friendlyText(failure.evaluation.reason)}<span><b>Question:</b> {failure.test.prompt}</span><span><b>Expected:</b> {failure.test.expected_behavior}</span><span><b>AI answer:</b> {failure.response.response_text || 'No answer text returned.'}</span></li>)}</ul> : <p className="empty">No failures were detected for this run.</p>}<UIActionLink className="secondary" href={`/audits/${run.run_id}`}>Open full report & memory evidence</UIActionLink></> : run.status === 'CANCELLED' ? <CancelledRunEvidence runId={run.run_id} /> : <p className="empty">Results are not available until this run completes.</p>}</UIPanel>)}</UIPanel>;
}

function PairedSignals({ comparisons }: { comparisons: PairedComparison[] }) {
  if (!comparisons.length) return <p className="repeat-note">Paired comparison signals will appear after at least two conditions complete.</p>;
  return <UIPanel className="experiment-history-detail"><UISummary>Paired comparison signals</UISummary><p>Each row aligns the exact frozen tests answered by two completed runs. A positive delta favours the candidate condition. The 95% interval is a deterministic bootstrap estimate; the p-value is a two-sided exact sign test over discordant tests.</p><div className="comparison-scroll"><UITable><thead><tr><th>Candidate vs reference</th><th>Shared tests</th><th>Candidate-only passes</th><th>Reference-only passes</th><th>Delta</th><th>95% interval</th><th>p-value</th></tr></thead><tbody>{comparisons.map((pair) => <tr key={`${pair.reference_run_id}:${pair.candidate_run_id}`}><th scope="row">{friendlyText(pair.candidate_label)} vs {friendlyText(pair.reference_label)}</th><td>{pair.shared_tests}</td><td>{pair.candidate_only_passed}</td><td>{pair.reference_only_passed}</td><td><b>{pair.candidate_delta_percentage_points === null ? 'Not available' : `${pair.candidate_delta_percentage_points > 0 ? '+' : ''}${pair.candidate_delta_percentage_points.toFixed(1)} pp`}</b></td><td>{pair.candidate_delta_confidence_interval_low === null || pair.candidate_delta_confidence_interval_high === null ? 'Not available' : `${pair.candidate_delta_confidence_interval_low.toFixed(1)} to ${pair.candidate_delta_confidence_interval_high.toFixed(1)} pp`}</td><td>{pair.two_sided_sign_test_p_value === null ? 'Not available' : pair.two_sided_sign_test_p_value.toFixed(4)}</td></tr>)}</tbody></UITable></div></UIPanel>;
}

export function About() {
  return <section><h1>About AI Memory Health Auditor</h1><p>AI Memory Health Auditor evaluates memory behaviour in configurable or independently hosted conversational AI systems over time.</p><p>It separates the underlying language model from the memory policy being tested, then measures Accuracy, Freshness, Conflict Resolution and Appropriate Use with traceable evidence where the target exposes it. External systems may leave internal memory decisions unobserved.</p><p>Controlled experiment groups freeze one test suite before comparing models or strategies. Rule-based components provide a reproducible local baseline; optional provider connectors can be configured on the backend.</p></section>;
}
