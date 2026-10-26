import { saveBlob } from '../services/download';
import { UIActionLink } from '../components/ui';
import { useUIConfirmation } from '../components/ui';
import { UIAlert, UICard } from '../components/ui';
import { UIButton, UIInput, UISelect, UIOption, UIPanel, UISummary, UITable } from '../components/ui';
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../services/api';
import { auditDisplayNames, modelDisplayName, friendlyText, memoryMaintenanceLabel, processingLabel, memoryStrategyLabel as friendlyStrategy, retrievalApproachKey, retrievalApproachLabel } from '../services/display';
import type { AuditResult, AuditRetryPlan, AuditRun, Experiment, ExperimentAnalytics, ExperimentRunReport, PairedComparison } from '../types/domain';
import { ResultDashboard } from '../components/ResultDashboard';
import { TargetMemoryTrace } from '../components/TargetMemoryTrace';
import { TestSuiteReview } from '../components/TestSuiteReview';
import type { TestCase } from '../types/domain';
import { ResearchValidation } from '../components/ResearchValidation';
import { PairedOutcomeOverview } from '../components/PairedOutcomeOverview';

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
      const matchesSearch = !query || [displayNames[run.run_id], run.model, run.memory_strategy, retrievalApproachLabel(run), providerLabels[run.provider], formatDate(run.created_at), run.reproducibility?.assessment_source_run_id ? 'Saved-answer reassessment' : 'Target audit']
        .some((value) => value.toLowerCase().includes(query));
      return matchesSearch
        && (statusFilter === 'all' || run.status === statusFilter)
        && (providerFilter === 'all' || run.provider === providerFilter)
        && (strategyFilter === 'all' || retrievalApproachKey(run) === strategyFilter);
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
        <label>Memory approach<UISelect aria-label="Filter by memory strategy" value={strategyFilter} onChange={(event) => setStrategyFilter(event.target.value)}><UIOption value="all">All approaches</UIOption>{[...new Set(items.map(retrievalApproachKey))].map((strategy) => <UIOption key={strategy} value={strategy}>{strategy === 'agent' ? 'AI retrieval Agent' : friendlyStrategy(strategy as AuditRun['memory_strategy'])}</UIOption>)}</UISelect></label>
        {filtersActive && <UIButton type="button" className="secondary history-filter-reset" onClick={clearFilters}>Clear filters</UIButton>}
      </div>
      <p className="history-count" role="status">Showing {filteredItems.length} of {items.length} audit run{items.length === 1 ? '' : 's'}.</p>
      {filteredItems.length ? <div className="audit-history-list" aria-label="Audit history">{pageItems.map((run) => <AuditHistoryCard key={run.run_id} displayName={displayNames[run.run_id]} run={run} onRecovered={(updated) => setItems((current) => current.map((item) => item.run_id === updated.run_id ? updated : item))} onDeleted={removed} />)}</div> : <div className="empty"><b>No matching audits</b><p>Try clearing a filter or searching by a different model, memory approach, or date.</p></div>}
      {filteredItems.length > pageSize && <nav aria-label="Audit history pages" className="review-toolbar"><UIButton className="secondary" disabled={activePage === 0} onClick={() => setHistoryPage(activePage - 1)}>Previous page</UIButton><span role="status">Page {activePage + 1} of {lastPage + 1} · {activePage * pageSize + 1}–{Math.min((activePage + 1) * pageSize, filteredItems.length)} of {filteredItems.length} matching audits</span><UIButton className="secondary" disabled={activePage === lastPage} onClick={() => setHistoryPage(activePage + 1)}>Next page</UIButton></nav>}
    </> : <div className="empty"><b>No audits yet</b><p>Create and run an audit to retain a traceable record here.</p></div>}
  </section>;
}

function friendlyExperimentLabel(label: string) {
  return friendlyText(label)
    .replace(/\s+\d{4}-\d{2}-\d{2}T[\d:.]+Z$/, '')
    .replace(/^Memory strategy comparison\s*·\s*custom(?:\s*·)?$/i, 'Memory strategy comparison')
    .replace(/(?:SYN-C|STUDY-)0*(\d+)/gi, (_match, number: string) => `Scenario ${Number(number)}`)
    .replace(/:\s*(Scenario \d+)/, ' · $1')
    .replace(/held_out/g, 'Validation').replace(/diagnostic/g, 'Diagnosis')
    .replace(/\s*[·:—-]+\s*$/, '').trim();
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
      <h2>{displayName} · {retrievalApproachLabel(run)}</h2>
      <p>{modelDisplayName(run.model)} · Test budget: up to {run.test_budget} questions</p>
      {run.reproducibility?.assessment_source_run_id && <p><b>Saved-answer reassessment</b> · No new target call. <a href={`/audits/${run.reproducibility.assessment_source_run_id}`}>View original assessment</a></p>}
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
  return <AuditReportSession key={runId} runId={runId}/>;
}
function AuditReportSession({runId}: {runId:string}) {
  const [refresh, setRefresh] = useState(0);
  const [result, setResult] = useState<AuditResult | null>(null);
  const [run, setRun] = useState<AuditRun | null>(null);
  const [settingsState, setSettingsState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  useEffect(() => {
    if (!runId) { setState('error'); return; }
    setState('loading');
    let active = true;
    api.getAudit(runId).then((saved) => {
      if (!active) return;
      if (saved.run_id !== runId) { setSettingsState('error'); return; }
      setRun(saved); setSettingsState('ready');
    }).catch(() => { if (active) setSettingsState('error'); });
    api.results(runId).then((loaded) => { if(active){setResult(loaded);setState('ready');} })
      .catch(() => { if(active){setResult(null);setState('error');} });
    return () => { active = false; };
  }, [runId, refresh]);
  if (state === 'loading') return <section><h1>Memory Health Report</h1><p className="empty" role="status">Loading the saved audit report…</p></section>;
  if(state==='error'&&settingsState==='ready'&&run?.status&&run.status!=='COMPLETED')return <section><p className="eyebrow">SAVED AUDIT PROGRESS</p><h1>Audit progress</h1><p>The final report is available after assessment completes. Inspect saved progress before resuming; recovery continues the unfinished stage.</p><p><b>{modelDisplayName(run.model)}</b> · {providerLabels[run.provider]} · {retrievalApproachLabel(run)}</p><RunRecoveryControls run={run} onRecovered={updated=>{setRun(updated);if(updated.status==='COMPLETED')setRefresh(value=>value+1);}}/><a className="text-link" href="/history">Return to Audit History</a></section>;
  if (state === 'error' || !result) return <section><h1>Memory Health Report</h1><UIAlert className="empty" role="alert"><b>Report unavailable</b><p>This audit may not be complete, may have been deleted with its authorised conversation, or the API is unavailable.</p><a className="text-link" href="/history">Return to Audit History</a></UIAlert></section>;
  return <section><p className="eyebrow">SAVED AUDIT REPORT</p><h1>Memory Health Report</h1><UIActionLink className="secondary comparison-report-link" href={`/compare?before=${encodeURIComponent(result.run_id)}`}>Compare before & after →</UIActionLink><section aria-label="Saved audit configuration">{run && settingsState === 'ready' ? <><p><b>{modelDisplayName(run.model)}</b> · {providerLabels[run.provider]} · {retrievalApproachLabel(run)}</p><p className="trace-note">Question generation: {savedProcessingLabel(run.pipeline_provider)}{run.pipeline_provider && run.pipeline_provider !== 'rule_based' && ` · ${modelDisplayName(run.pipeline_model)}`} · Semantic duplicate review: {savedProcessingLabel(run.semantic_review_provider ?? run.pipeline_provider)}{(run.semantic_review_provider ?? run.pipeline_provider) !== 'rule_based' && ` · ${modelDisplayName(run.semantic_review_model ?? run.pipeline_model)}`} · Memory retrieval: {run.retrieval_mode === 'agent' ? `AI retrieval Agent · ${run.retrieval_provider ?? 'model service not recorded'}${run.retrieval_model ? ` · ${modelDisplayName(run.retrieval_model)}` : ''}` : 'fixed policy'} · Answer assessment: {savedProcessingLabel(run.evaluator_provider)}{run.evaluator_provider && run.evaluator_provider !== 'rule_based' && ` · ${modelDisplayName(run.evaluator_model)}`}</p><ReproducibilityDetails run={run}/></> : <p role={settingsState === 'error' ? 'note' : 'status'}>{settingsState === 'error' ? 'Saved model and assessment settings are unavailable. The saved results remain below; check Audit History before interpreting the configuration.' : 'Loading saved model and assessment settings…'}</p>}</section><ResultDashboard result={result} run={run ?? undefined} /><TargetMemoryTrace runId={result.run_id} /></section>;
}

function savedProcessingLabel(provider?: string) {
  if (!provider) return 'Not recorded';
  if (provider === 'rule_based') return processingLabel(provider);
  const label = providerLabels[provider as AuditRun['provider']];
  return label ? `AI-assisted processing · ${label}` : processingLabel(provider);
}

function ReproducibilityDetails({ run }: { run: AuditRun }) {
  const retryPolicy = run.reproducibility?.target_retry_policy;
  const seed = run.reproducibility?.seed_control;
  return <UIPanel className="reproducibility-details"><UISummary>Memory settings · {retrievalApproachLabel(run)}</UISummary><ul><li>Test budget: up to {run.test_budget} questions · temperature {run.temperature} · seed {run.random_seed}</li>{seed && <li>Seed control: target {seed.target?.replaceAll('_', ' ') ?? 'not declared'} · pipeline {seed.pipeline?.replaceAll('_', ' ') ?? 'not declared'} · semantic review {seed.semantic_review?.replaceAll('_', ' ') ?? 'not declared'} · evaluator {seed.evaluator?.replaceAll('_', ' ') ?? 'not declared'}</li>}<li>Test generation: {savedProcessingLabel(run.pipeline_provider)}{run.pipeline_provider && run.pipeline_provider !== 'rule_based' && ` · ${run.pipeline_model}`}</li><li>Semantic duplicate review: {savedProcessingLabel(run.semantic_review_provider ?? run.pipeline_provider)}{(run.semantic_review_provider ?? run.pipeline_provider) !== 'rule_based' && ` · ${run.semantic_review_model ?? run.pipeline_model}`}</li><li>Memory retrieval: {run.retrieval_mode === 'agent' ? `AI retrieval Agent · ${run.retrieval_provider ?? 'model service not recorded'}${run.retrieval_model ? ` · ${run.retrieval_model}` : ''}` : 'Fixed retrieval policy'}</li><li>Answer assessment: {savedProcessingLabel(run.evaluator_provider)}{run.evaluator_provider && run.evaluator_provider !== 'rule_based' && ` · ${run.evaluator_model}`}</li><li>Target system: {run.target_system_adapter === "external-http" ? "Independent target service (internal memory unobserved)" : run.target_system_adapter === "controlled-memory" ? "Model with configurable memory" : "Not recorded"}</li>{run.target_memory_profile&&<><li>Configuration: {run.target_memory_profile.label} · version {run.target_memory_profile.version}</li><li>Context budget: {run.target_memory_profile.max_retrieved_records} memories / {run.target_memory_profile.context_character_budget} characters</li><li>Event identity analysis: {run.target_memory_profile.identity_analysis === "evidence_links" ? `On · separate ${run.target_memory_profile.identity_analysis_output_token_limit ?? 4096}-token analysis budget` : "Off"}</li><li>Configured final reasoning request: {run.target_memory_profile.reasoning_effort ?? "Not recorded"}</li><li>Configured identity reasoning request: {run.target_memory_profile.identity_analysis_reasoning_effort ?? "Not recorded"}. Actual reasoning effort is not reported.</li><li>Project isolation: {run.target_memory_profile.isolate_project_scope?"On":"Off"} · current-state priority: {run.target_memory_profile.prefer_current_state?"On":"Off"}</li>{run.target_memory_profile.additional_instructions&&<li>Additional target instructions: {run.target_memory_profile.additional_instructions}</li>}</>}{run.reproducibility?.study_role&&<li>Experiment purpose: {run.reproducibility.study_role.replaceAll("_"," ")} · {run.reproducibility.validation_split?.replaceAll("_"," ")}</li>}<li>Memory maintenance: {memoryMaintenanceLabel(run.memory_maintenance_policy)}</li>{<li>Target memory capacity: {run.target_memory_capacity == null ? 'Not recorded' : `${run.target_memory_capacity} records`}</li>}<li>Memory preparation: {run.target_memory_writer ? processingLabel(run.target_memory_writer) : 'Not recorded'}</li>{retryPolicy && <li>Recovery: up to {retryPolicy.max_attempts} attempts · {retryPolicy.timeout_seconds}s timeout</li>}</ul></UIPanel>;
}

const recoveryStageLabels: Record<NonNullable<AuditRetryPlan['next_stage']>, string> = { generate_tests: 'generate the shared tests', execute_tests: 'execute unanswered tests', evaluate_responses: 'evaluate pending responses' };

function RunRecoveryControls({ run, onRecovered }: { run: AuditRun; onRecovered: (updated: AuditRun) => void }) {
  const [plan, setPlan] = useState<AuditRetryPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [isResuming,setIsResuming]=useState(false);
  const [message, setMessage] = useState('');
  const [preparedTests, setPreparedTests] = useState<TestCase[] | null>(null);
  const inspectTests = async () => { setBusy(true); setMessage(''); try { setPreparedTests((await api.testReview(run.run_id)).tests); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'Prepared tests could not be loaded.'); } finally { setBusy(false); } };
  const updatePreparedTest = async (test: TestCase, decision?: 'accepted' | 'rejected', note?:string) => { setBusy(true); setMessage(''); try { const updated = decision ? await (note?api.reviewTest(run.run_id,test.test_id,decision,note):api.reviewTest(run.run_id,test.test_id,decision)) : await api.regenerateTest(run.run_id, test.test_id); setPreparedTests((items) => items?.map((item) => item.test_id === updated.test_id ? updated : item) ?? null); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The prepared test could not be updated.'); } finally { setBusy(false); } };
  const inspect = async () => { setBusy(true); setMessage(''); try { const next = await api.retryPlan(run.run_id); setPlan(next); if (next.status && next.status !== run.status) { onRecovered({...run, status: next.status, completed_at: next.completed_at ?? run.completed_at}); if (next.status === 'COMPLETED') setMessage('Background work completed. The report is now available.'); } } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The recovery plan could not be loaded.'); } finally { setBusy(false); } };
  const retry = async () => { setIsResuming(true);setBusy(true); setMessage(''); try { const updated = await api.retry(run.run_id); onRecovered(updated); setPlan(null); setMessage(updated.status === 'COMPLETED' ? 'Recovery completed. The report is now available.' : updated.status === 'TESTS_EXECUTED' ? 'Saved progress: answers are saved. View the recovery plan to finish their assessment.' : updated.status === 'TESTS_GENERATED' ? 'Saved progress: questions are ready. View the recovery plan to review them before testing.' : `The audit needs attention at ${formatStatus(updated.status)}. Check its recovery plan before continuing.`); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The audit could not be resumed.'); } finally { setIsResuming(false);setBusy(false); } };
  const needsQuestionReview=plan?.next_stage==='execute_tests'&&preparedTests!==null&&(!preparedTests.length||preparedTests.some(test=>test.quality_status!=='accepted'));
  if (run.status === 'COMPLETED') return <div className="recovery-controls"><span className="status-complete">Completed</span>{message && <small className="success-message" role="status">{message}</small>}</div>;
  if (run.status === 'CANCELLED') return <div className="recovery-controls"><b>{formatStatus(run.status)}</b><small>This run is terminal and cannot be resumed.</small></div>;
  return <div className="recovery-controls"><b>{formatStatus(run.status)}</b>{!plan ? <UIButton type="button" className="secondary" disabled={busy} onClick={inspect}>{busy ? 'Checking…' : 'View recovery plan'}</UIButton> : plan.busy ? <><small role="status">Work is still running in the background. Saved progress can be checked without sending another model request.</small><UIButton type="button" className="secondary" disabled={busy} onClick={inspect}>Check progress again</UIButton></> : plan.resume_blocked_reason ? <><small role="alert">{plan.resume_blocked_reason}</small><a className="text-link" href="/new-audit">Start a new audit</a><UIButton type="button" className="secondary" disabled={busy} onClick={inspect}>Check compatibility again</UIButton></> : plan.retryable && plan.next_stage ? <><small>{plan.pending > 0 ? `${plan.pending} item${plan.pending === 1 ? '' : 's'} pending; recovery will ${recoveryStageLabels[plan.next_stage]}.` : `Recovery will ${recoveryStageLabels[plan.next_stage]}.`}</small><UIButton type="button" disabled={busy||needsQuestionReview} onClick={retry}>{isResuming ? 'Resuming…' : 'Resume audit'}</UIButton></> : <small>No recovery is required for this run.</small>}{plan?.next_stage === 'execute_tests' && !plan.busy && !plan.resume_blocked_reason && <UIButton type="button" className="secondary" disabled={busy} onClick={inspectTests}>Review prepared tests</UIButton>}{needsQuestionReview&&<small role="note">Accept the prepared questions before resuming unanswered tests.</small>}{preparedTests && plan?.next_stage === 'execute_tests' && !plan.resume_blocked_reason && <TestSuiteReview tests={preparedTests} busy={busy || Boolean(plan.busy)} onReview={(test, decision, note) => updatePreparedTest(test, decision, note)} onRegenerate={(test) => updatePreparedTest(test)} />}{message && <small className={(message.startsWith('Recovery completed') || message.startsWith('Background work completed') || message.startsWith('Saved progress:')) ? 'success-message' : 'alert-message'} role="status">{message}</small>}</div>;
}

function ConversationDataControls({ conversationId, onDeleted }: { conversationId: string; onDeleted: () => void }) {
  const [confirmationOpen, setConfirmationOpen] = useState(false); const [confirmation, setConfirmation] = useState(''); const [busy, setBusy] = useState(false); const [message, setMessage] = useState('');
  const download = async () => { setBusy(true); setMessage(''); try { const blob = await api.downloadConversationExport(conversationId); saveBlob(blob, 'memory-health-data-export.json'); setMessage('The authorised data export is ready; your browser was asked to save it.'); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The export could not be created.'); } finally { setBusy(false); } };
  const erase = async () => { setBusy(true); setMessage(''); try { const receipt = await api.deleteConversation(conversationId, conversationId); setMessage(`Deleted this conversation and its ${receipt.deleted_audit_runs} audit records.`); onDeleted(); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The local data could not be deleted.'); } finally { setBusy(false); } };
  return <div className="conversation-data-controls"><UIButton type="button" className="secondary" disabled={busy} onClick={download}>Export JSON</UIButton><UIButton type="button" className="ghost" disabled={busy} onClick={() => { setConfirmationOpen(!confirmationOpen); setMessage(''); }}>Delete data</UIButton>{confirmationOpen && <div className="delete-confirmation"><label>Enter <b>DELETE</b> to permanently delete this conversation and all of its audit data.<UIInput aria-label="Confirm deletion of saved conversation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label><UIButton type="button" className="danger" disabled={busy || confirmation !== 'DELETE'} onClick={erase}>Permanently delete local data</UIButton></div>}{message && <small className={message.startsWith('The authorised') ? 'success-message' : 'alert-message'}>{message}</small>}</div>;
}

export function Experiments() {
  const { experimentId } = useParams();
  const loadRevision = useRef(0);
  const { confirm, dialog } = useUIConfirmation();
  const [items, setItems] = useState<Experiment[]>([]);
  const [analytics, setAnalytics] = useState<Record<string, ExperimentAnalytics>>({});
  const [reportErrors, setReportErrors] = useState<Record<string, boolean>>({});
  const [reportRetry, setReportRetry] = useState(0);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [exportingId, setExportingId] = useState<string | null>(null);
  const [experimentPage, setExperimentPage] = useState(0);
  const experimentPageSize = 3;
  const scopedItems = experimentId ? items.filter(item => item.experiment_id === experimentId) : items;
  const lastExperimentPage = Math.max(0, Math.ceil(scopedItems.length / experimentPageSize) - 1);
  const activeExperimentPage = Math.min(experimentPage, lastExperimentPage);
  const visibleExperiments = scopedItems.slice(activeExperimentPage * experimentPageSize, (activeExperimentPage + 1) * experimentPageSize);
  const [actionMessage, setActionMessage] = useState('');
  const loadExperiments = useCallback(() => {
    const revision = ++loadRevision.current;
    setLoadState('loading');
    api.experimentGroups()
      .then(async (groups) => {
        if (revision !== loadRevision.current) return;
        const orderedGroups = [...groups].sort((left, right) => scenarioNumber(left.label) - scenarioNumber(right.label));
        setItems(orderedGroups);
        setAnalytics({});
        setReportErrors({});
        setLoadState('ready');
      })
      .catch(() => { if (revision !== loadRevision.current) return; setItems([]); setAnalytics({}); setLoadState('error'); });
  }, []);

  useEffect(() => { loadExperiments(); return () => { loadRevision.current++; }; }, [loadExperiments]);

  useEffect(() => {
    let cancelled = false;
    const pending = (experimentId ? items.filter(item => item.experiment_id === experimentId) : items).slice(activeExperimentPage * experimentPageSize, (activeExperimentPage + 1) * experimentPageSize)
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
  }, [items, experimentId, activeExperimentPage, reportRetry]);

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

  return <section>{dialog}<h1>Compare memory strategies & models</h1>{experimentId && <p><a href="/experiments">All experiment groups</a></p>}<p className="experiment-page-intro">See how different settings perform on the same questions. Start with the result summary, then inspect which answers changed.</p>{actionMessage && <p className={(actionMessage.startsWith('The unfinished') || actionMessage.startsWith('The download')) ? 'success-message' : 'alert-message'} role="status">{actionMessage}</p>}{loadState === 'loading' ? <p className="empty" role="status">Loading experiment groups…</p> : loadState === 'error' ? <UIAlert className="empty" role="alert"><p>Experiment groups could not be loaded. Check that the API service is available and try again.</p><UIButton type="button" className="secondary" onClick={loadExperiments}>Try again</UIButton></UIAlert> : scopedItems.length ? visibleExperiments.map((item) => <ExperimentHistoryCard key={item.experiment_id} experiment={item} report={analytics[item.experiment_id]} reportError={reportErrors[item.experiment_id]} onRetryReport={() => setReportRetry(current => current + 1)} exporting={exportingId === item.experiment_id} onDownload={download} onDownloadBundle={downloadBundle} onDownloadArtifact={downloadArtifact} onCancel={cancelExperiment} />) : experimentId ? <div className="empty" role="status"><b>Experiment group not found</b><p>This saved group is not available. Open all experiment groups to choose another comparison.</p></div> : <div className="empty"><b>No experiments yet</b><p>Start a multi-model or multi-strategy audit to create a controlled comparison group.</p></div>}{scopedItems.length > experimentPageSize && <nav className="history-pagination" aria-label="Experiment pages"><UIButton type="button" className="secondary" disabled={activeExperimentPage === 0} onClick={() => setExperimentPage(activeExperimentPage - 1)}>Previous experiments</UIButton><span>Page {activeExperimentPage + 1} of {lastExperimentPage + 1} · {scopedItems.length} experiment groups</span><UIButton type="button" className="secondary" disabled={activeExperimentPage >= lastExperimentPage} onClick={() => setExperimentPage(activeExperimentPage + 1)}>Next experiments</UIButton></nav>}<UIPanel className="experiment-history-detail"><UISummary>Research tools · benchmarks and reviewer checks</UISummary><p>Use these tools to validate assessment quality and prepare research experiments.</p><ResearchValidation /></UIPanel></section>;
}

function percentage(value: number | null | undefined) { return value === null || value === undefined ? 'Not tested' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`; }

function strategyExplanation(strategy: AuditRun['memory_strategy']) {
  const descriptions: Record<AuditRun['memory_strategy'], string> = {
    no_memory: 'Answers without stored memories.',
    full_context: 'Replays retained current facts and unresolved conflicts. Replaced historical facts may be excluded; check the saved model input.',
    weak_first_hit: 'Uses the first matching memory.',
    strong_rule_based: 'Selects memories using predefined rules.',
    strong_score_based: 'Ranks memories by relevance and other scoring signals.',
    scope_aware: 'Selects memories for the relevant project or context.',
    temporal_importance: 'Considers relevance, time and importance when selecting memories.',
  };
  return descriptions[strategy] ?? 'Controls which memories the model receives.';
}

function retrievalExplanationForRun(run: AuditRun | undefined, strategy: AuditRun['memory_strategy']) {
  return run?.retrieval_mode === 'agent'
    ? 'The AI retrieval Agent selects memories from the target system’s private store using the meaning of the question.'
    : strategyExplanation(strategy);
}

export function experimentSettingName(run: AuditRun) {
  const methods:Record<string,string>={rules:'Rule tests + rule review',model_generation:'Model tests + rule review',hybrid:'Model tests + hybrid review'};
  const method=methods[run.reproducibility?.auditor_method??''];
  const profile=run.target_memory_profile?.label;
  return [retrievalApproachLabel(run),method,profile&&profile!=='Original configuration'?profile:null].filter(Boolean).join(' · ');
}

function experimentRunName(report: ExperimentAnalytics, runId: string, fallback: string) {
    const run = report.runs.find(item => item.run.run_id === runId)?.run;
    if (!run) return friendlyText(fallback);
    const multipleModels = new Set(report.runs.map(item => item.run.model)).size > 1;
    return `${multipleModels ? `${modelDisplayName(run.model)} · ` : ''}${experimentSettingName(run)}`;
}

function ExperimentOutcome({ report }: { report: ExperimentAnalytics }) {
  const completed = report.conditions.filter(condition => condition.completed_runs > 0 && condition.tests_total > 0);
  const pair = report.conditions.length === 2 && report.paired_comparisons.length === 1 ? report.paired_comparisons[0] : undefined;
  const settingName = (runId:string,fallback:string)=>experimentRunName(report,runId,fallback);
  const pending = report.runs.some(({ run }) => !['COMPLETED', 'FAILED', 'CANCELLED'].includes(run.status));
  let headline = pending ? (report.conditions.length === 1 ? 'Audit in progress' : 'Comparison in progress') : 'Results are ready to review';
  let explanation = `${report.conditions.length === 1 ? 'Review the passed and failed answers below.' : 'Compare passed questions below.'} Scores describe these tests, rather than overall model reliability.`;
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
    explanation = 'No shared questions have comparable, decided assessments. Read each score separately; they do not establish a fair ranking.';
  }
  return <div className="experiment-outcome" role="status">
    <p className="eyebrow">RESULT AT A GLANCE</p><h3>{headline}</h3><p>{explanation}</p>
    {pair && pair.shared_tests > 0 && <div className="experiment-outcome-counts">
      <span><b>{pair.both_passed}</b> both answered correctly</span>
      <span><b>{pair.both_failed}</b> both failed</span>
      <span><b>{pair.reference_only_passed + pair.candidate_only_passed}</b> answered correctly by only one setting</span>
    </div>}
    {report.paired_comparisons.some(item => (item.excluded_uncertain_count ?? 0) > 0) && <small>Answers awaiting assessment are excluded from paired changes; inspect the comparison details for counts.</small>}
    {report.paired_comparisons.some(item => (item.excluded_assessment_count ?? 0) > 0) && <small>Shared answers scored under different or incompletely recorded review standards are excluded from paired changes. Scores from different review methods do not establish memory improvement.</small>}
    <small>Automated assessments of this test set. A small set or one run is not enough to establish general superiority.</small>
  </div>;
}

export function experimentChartRuns(report: ExperimentAnalytics) {
  return report.runs.flatMap(({run, result}) => {
    if (!result) return [];
    const condition = report.conditions.find(item => item.run_ids.includes(run.run_id));
    const representative = condition
      ? report.runs.find(item => condition.run_ids.includes(item.run.run_id))?.run ?? run
      : run;
    const name = friendlyText(`${modelDisplayName(representative.model)} · ${experimentSettingName(representative)}`);
    return [{label: name, groupLabel: name,
      groupKey: condition?.condition_id ?? `unverified-run:${run.run_id}`, result}];
  });
}

function ExperimentHistoryCard({ experiment, report, reportError, onRetryReport, exporting, onDownload, onDownloadBundle, onDownloadArtifact, onCancel }: { experiment: Experiment; report?: ExperimentAnalytics; reportError?: boolean; onRetryReport: () => void; exporting: boolean; onDownload: (experiment: Experiment) => void; onDownloadBundle: (experiment: Experiment) => void; onDownloadArtifact: (experiment: Experiment) => void; onCancel: (experiment: Experiment) => void }) {
  const complete = report?.runs.filter((item) => item.run.status === 'COMPLETED').length ?? 0;
  const failed = report?.runs.filter((item) => item.run.status === 'FAILED').length ?? 0;
  const visualRuns = report ? experimentChartRuns(report) : [];
  const models = [...new Set(report?.runs.map(({ run }) => run.model) ?? [])];
  const canCancel = !['COMPLETED', 'FAILED', 'CANCELLED'].includes(experiment.status);
  return <UICard className="experiment">
    <div className="experiment-heading"><div><p className="eyebrow">{(report?.conditions?.length ?? 0) > 1 ? 'SAME QUESTIONS · DIFFERENT SETTINGS' : report?.conditions?.length === 1 ? 'ONE SETTING · SAVED RESULTS' : 'SAVED EXPERIMENT'}</p><h2>{report?.conditions?.length === 1 ? friendlyExperimentLabel(experiment.label).replace(/^Memory strategy comparison/, 'Audit result') : friendlyExperimentLabel(experiment.label)}</h2><p className="experiment-date">{shortDate(experiment.created_at)}</p></div>
      {canCancel && <UIButton className="ghost" type="button" disabled={exporting} onClick={() => onCancel(experiment)}>{exporting ? 'Cancelling…' : 'Cancel unfinished conditions'}</UIButton>}
    </div>
    <div className="experiment-scores"><span><small>{report?.conditions?.length === 1 ? 'Questions in this audit' : 'Questions in the shared test set'}</small><b>{experiment.test_suite_metadata.test_count ?? '—'}</b></span><span><small>Runs completed · not questions passed</small><b>{report ? `${complete} / ${report.runs.length}` : reportError ? 'Not available' : 'Loading…'}</b></span></div>
    {reportError && <UIAlert role="alert"><p>This result summary could not be loaded. Other experiment results remain available.</p><UIButton type="button" className="secondary" onClick={onRetryReport}>Retry result summary</UIButton></UIAlert>}
    <p className="experiment-purpose">{report?.conditions?.length === 1 ? `Model: ${modelDisplayName(models[0] ?? '')}. Results for one saved memory setting; no model retraining.` : models.length ? `${models.length === 1 ? 'Model' : 'Models'}: ${models.map(modelDisplayName).join(', ')} · ${report?.conditions.length ?? 0} saved settings on the shared questions.` : 'Loading the saved comparison settings…'}</p>
    {failed > 0 && <p className="experiment-alert"><b>{failed} run{failed === 1 ? '' : 's'} could not finish.</b> This is a run error, not an incorrect answer. Completed results remain available.</p>}
    {report && <><ExperimentOutcome report={report} />
      {report.conditions.length>2&&<PairedOutcomeOverview comparisons={report.paired_comparisons} labelForRun={(id,fallback)=>experimentRunName(report,id,fallback)}/>}
      {<UIPanel className="experiment-history-detail"><UISummary>Settings & answer counts</UISummary><div className="experiment-setting-cards" aria-label="Results by setting">{report.conditions.map(condition => <div className="experiment-setting-card" key={condition.condition_id}>
        <h3>{report.runs.find(item=>condition.run_ids.includes(item.run.run_id)) ? experimentSettingName(report.runs.find(item=>condition.run_ids.includes(item.run.run_id))!.run) : friendlyStrategy(condition.memory_strategy)}</h3><p className="experiment-model-name">{modelDisplayName(condition.model)}</p><p>{retrievalExplanationForRun(report.runs.find(item=>condition.run_ids.includes(item.run.run_id))?.run, condition.memory_strategy)}</p>
        <b className="experiment-pass-count">{condition.tests_total ? `${condition.tests_passed} of ${condition.tests_total} answers passed` : 'No scored answers yet'}</b>
        <span>{condition.completed_runs} of {condition.planned_runs} runs complete</span>
      </div>)}</div></UIPanel>}
      {visualRuns.length > 0 && <Suspense fallback={<p className="chart-loading" role="status">Loading result charts…</p>}><ComparisonVisualizations runs={visualRuns} compact singleSetting={report.conditions.length === 1} /></Suspense>}
      <RunReports runs={report.runs} />
      <UIPanel className="experiment-history-detail"><UISummary>Detailed scores, runtime & statistics</UISummary><ConditionTable report={report} /><PairedSignals comparisons={report.paired_comparisons} /></UIPanel>
    </>}
    <UIPanel className="experiment-history-detail"><UISummary>Export results & experiment settings</UISummary>
      <p>Download a results table, a record for reproducing this experiment, or the fixed test materials.</p>
      <div className="experiment-export-actions"><UIButton className="secondary" disabled={exporting} onClick={() => onDownload(experiment)}>{exporting ? 'Preparing export…' : 'Results table (CSV)'}</UIButton><UIButton className="secondary" disabled={exporting || !report} onClick={() => report && saveBlob(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }), `experiment-${experiment.experiment_id}-results.json`)}>Answer report (JSON)</UIButton><UIButton className="secondary" disabled={exporting} onClick={() => onDownloadBundle(experiment)}>Reproduction package</UIButton><UIButton className="secondary" disabled={exporting} onClick={() => onDownloadArtifact(experiment)}>Fixed test materials</UIButton></div>
      <p><small>Requested question limit: {experiment.test_suite_configuration.test_budget} · Questions generated: {experiment.test_suite_metadata.test_count} · Random seed: {experiment.test_suite_configuration.random_seed}</small></p>
    </UIPanel>
  </UICard>;
}

function ConditionTable({ report }: { report: ExperimentAnalytics }) {
  return <><p>Each run gives its tested dimensions equal weight; these scores are then averaged across runs. This differs from the fraction of answers passed. Untested dimensions and uncertain answers are excluded.</p><div className="comparison-scroll experiment-history-table"><UITable><thead><tr><th>Model & memory setting</th><th>Runs completed</th><th>Tested ability average</th><th>Variation across runs</th><th>Answers passed</th><th>Detected problems</th><th>Runtime</th></tr></thead><tbody>{report.conditions.map((condition) => <tr key={condition.condition_id}><th scope="row">{friendlyText(condition.label)}</th><td>{condition.completed_runs} / {condition.planned_runs}</td><td><b>{percentage(condition.overall_mean)}</b></td><td>{condition.overall_standard_deviation === null ? 'Not measured' : percentage(condition.overall_standard_deviation)}</td><td>{condition.tests_passed} / {condition.tests_total}</td><td>{condition.failure_count}</td><td>{condition.mean_latency_ms === null ? '—' : `${Math.round(condition.mean_latency_ms)} ms avg`} · {condition.total_tokens === null ? 'tokens —' : `${condition.total_tokens.toLocaleString()} tokens`}</td></tr>)}</tbody></UITable></div></>;
}

function CancelledRunEvidence({ runId }: { runId: string }) {
  const [evidence, setEvidence] = useState<Awaited<ReturnType<typeof api.cancelledEvidence>> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const load = async () => { setLoading(true); setError(''); try { setEvidence(await api.cancelledEvidence(runId)); } catch (cause) { setError(cause instanceof Error ? cause.message : 'Retained cancellation evidence could not be loaded.'); } finally { setLoading(false); } };
  return <div className="cancelled-evidence"><p className="empty">This condition was cancelled before evaluation. Any completed target responses and safe memory trace are retained.</p>{!evidence && <UIButton type="button" className="secondary" disabled={loading} onClick={load}>{loading ? 'Loading retained evidence…' : 'Inspect retained evidence'}</UIButton>}{error && <UIAlert role="alert" className="alert-message">{error}</UIAlert>}{evidence && <><p><b>{evidence.completed_responses.length}</b> target response{evidence.completed_responses.length === 1 ? '' : 's'} completed before cancellation.</p>{evidence.completed_responses.length ? <ul className="experiment-failures">{evidence.completed_responses.map((response, index) => <li key={response.response_id}><b>Response {index + 1}</b>: {response.response_text}</li>)}</ul> : <p className="empty">No target response completed before cancellation.</p>}<TargetMemoryTrace runId={runId} /></>}</div>;
}

function RunReports({ runs }: { runs: ExperimentRunReport[] }) {
  return <UIPanel className="experiment-history-detail"><UISummary>Inspect answers & detected problems</UISummary>{runs.map(({ run, result, answers = [] }) => <UIPanel className="run-report" key={run.run_id}><UISummary><b>{providerLabels[run.provider]} · {experimentSettingName(run)}</b> — {formatStatus(run.status)}{result && ` · ${percentage(result.overall_score)}`}</UISummary>{result ? <><p>{result.tests_passed} / {result.tests_total} tests passed. {result.failures.length} detected failure{result.failures.length === 1 ? '' : 's'}.{(result.uncertain_count ?? 0) > 0 && ` ${result.uncertain_count} ${result.uncertain_count === 1 ? 'answer still awaits' : 'answers still await'} review.`}</p>{result.failures.length ? <ul className="experiment-failures">{result.failures.map((failure) => <li key={failure.failure_id}><b>{failure.test.dimension.replaceAll('_', ' ')}</b>: {friendlyText(failure.evaluation.reason)}<span><b>Question:</b> {failure.test.prompt}</span><span><b>Expected:</b> {failure.test.expected_behavior}</span><span><b>AI answer:</b> {failure.response.response_text || 'No answer text returned.'}</span></li>)}</ul> : <p className="empty">No failures were detected among decided answers.</p>}{answers.length > 0 && <section role="region" aria-label="Saved answers"><h3>Saved answers</h3><ul className="experiment-answers">{answers.map((answer) => {
        const outcomeLabel = answer.outcome === 'pass' ? 'Passed' : answer.outcome === 'fail' ? 'Failed' : answer.outcome === 'uncertain' ? 'Awaiting assessment' : 'Unassessed';
        return <li key={`${answer.test_id}:${answer.response_id}`} aria-label={`${outcomeLabel} answer for ${answer.test_id}`}>
          <b>{outcomeLabel}</b><span><b>Dimension:</b> {answer.dimension.replaceAll('_', ' ')}</span>
          <span><b>Question:</b> {answer.prompt}</span><span><b>Expected behaviour:</b> {answer.expected_behavior}</span>
          <span><b>Answer:</b> {answer.answer || 'No answer text returned.'}</span>
          {answer.observed_category && <span><b>Observed category:</b> {answer.observed_category.replaceAll('_', ' ')}</span>}
          {answer.evaluation_reason && <span><b>Assessment:</b> {friendlyText(answer.evaluation_reason)}</span>}
          <details><summary>Source evidence</summary>{answer.source_evidence.length ? <ul>{answer.source_evidence.map((evidence) => <li key={evidence.memory_id}><b>{evidence.canonical_value}</b><span>Source message IDs: {evidence.source_message_ids.length ? evidence.source_message_ids.join(', ') : 'None recorded'}</span></li>)}</ul> : <p>No linked source memory evidence.</p>}{answer.supporting_memory_ids.length > 0 && <p>Supporting memory IDs: {answer.supporting_memory_ids.join(', ')}</p>}</details>
          {answer.source_statements.length > 0 && <details><summary>Source statements</summary><ul>{answer.source_statements.map((statement, index) => <li key={`${statement.timestamp}:${index}`}><b>{statement.role}</b> · {formatDate(statement.timestamp)}<span>{statement.content}</span></li>)}</ul></details>}
        </li>;
      })}</ul></section>}<UIActionLink className="secondary" href={`/audits/${run.run_id}`}>Open full report & memory evidence</UIActionLink></> : run.status === 'CANCELLED' ? <CancelledRunEvidence runId={run.run_id} /> : <p className="empty">Results are not available until this run completes.</p>}</UIPanel>)}</UIPanel>;
}

function PairedSignals({ comparisons }: { comparisons: PairedComparison[] }) {
  if (!comparisons.length) return <p className="repeat-note">Paired comparison signals will appear after at least two conditions complete.</p>;
  return <UIPanel className="experiment-history-detail"><UISummary>Paired comparison signals</UISummary><p>Each row aligns the exact frozen tests answered by two completed runs. A positive delta favours the candidate condition. The 95% interval resamples the observed questions and needs at least two paired answers. A zero-width interval does not prove certainty. The p-value is a two-sided exact sign test over changed outcomes; neither statistic replaces independent scenarios and repeated runs.</p><div className="comparison-scroll"><UITable><thead><tr><th>Candidate vs reference</th><th>Shared questions</th><th>Comparable decided questions</th><th>Awaiting assessment</th><th>Different or unknown review standards</th><th>Candidate-only passes</th><th>Reference-only passes</th><th>Delta</th><th>95% interval</th><th>p-value</th></tr></thead><tbody>{comparisons.map((pair) => <tr key={`${pair.reference_run_id}:${pair.candidate_run_id}`}><th scope="row">{friendlyText(pair.candidate_label)} vs {friendlyText(pair.reference_label)}</th><td>{pair.shared_question_count ?? 'Not recorded'}</td><td>{pair.shared_tests}</td><td>{pair.excluded_uncertain_count ?? 0}</td><td>{pair.excluded_assessment_count ?? 0}</td><td>{pair.candidate_only_passed}</td><td>{pair.reference_only_passed}</td><td><b>{pair.candidate_delta_percentage_points === null ? 'Not available' : `${pair.candidate_delta_percentage_points > 0 ? '+' : ''}${pair.candidate_delta_percentage_points.toFixed(1)} pp`}</b></td><td>{pair.candidate_delta_confidence_interval_low === null || pair.candidate_delta_confidence_interval_high === null ? pair.shared_tests === 1 ? 'Not estimable from one question' : 'Not available' : `${pair.candidate_delta_confidence_interval_low.toFixed(1)} to ${pair.candidate_delta_confidence_interval_high.toFixed(1)} pp`}</td><td>{pair.two_sided_sign_test_p_value === null ? 'Not available' : pair.two_sided_sign_test_p_value.toFixed(4)}</td></tr>)}</tbody></UITable></div></UIPanel>;
}

export function About() {
  return <section><h1>About AI Memory Health Auditor</h1>
    <p>Test how an AI uses remembered facts. Choose a model and memory strategy, review the facts and questions, then inspect the answers and supporting evidence.</p>
    <p>Four abilities: Accuracy, Freshness, Conflict Resolution and Appropriate Use. Compare models or memory strategies on the same saved questions.</p>
    <p>Changing a memory strategy changes the context supplied to the model; it does not train the model. Scores describe the tested setup. Independent human evaluation is needed to establish how reliable the auditor is.</p>
  </section>;
}
