import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import type { AuditResult, AuditRun, Experiment, ExperimentAnalytics, ExperimentRunReport, PairedComparison } from '../types/domain';
import { ResultDashboard } from '../components/ResultDashboard';
import { TargetMemoryTrace } from '../components/TargetMemoryTrace';
import { ResearchValidation } from '../components/ResearchValidation';

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
  const loadHistory = useCallback(() => {
    setLoadState('loading');
    api.audits()
      .then((audits) => { setItems(audits); setLoadState('ready'); })
      .catch(() => { setItems([]); setLoadState('error'); });
  }, []);

  useEffect(() => { loadHistory(); }, [loadHistory]);
  const openReport = async (runId: string) => { setReportError(''); try { setSelectedReport(await api.results(runId)); } catch (cause) { setSelectedReport(null); setReportError(cause instanceof Error ? cause.message : 'The completed report could not be loaded.'); } };

  return <section><h1>Audit History</h1><p>Review the configuration, lifecycle status, completion time and post-audit evidence of each controlled audit.</p>{loadState === 'loading' ? <p className="empty" role="status">Loading audit history…</p> : loadState === 'error' ? <div className="empty" role="alert"><p>Audit history could not be loaded. Check that the API service is available and try again.</p><button type="button" className="secondary" onClick={loadHistory}>Try again</button></div> : items.length ? <table aria-label="Audit history"><thead><tr><th>Run</th><th>Target AI</th><th>Audit settings</th><th>Status</th><th>Created</th><th>Completed</th><th>Evidence</th></tr></thead><tbody>{items.map((run) => <tr key={run.run_id}><td><b>{run.run_id}</b></td><td>{providerLabels[run.provider]}<br /><small>{run.model}</small></td><td>{run.target_configuration === 'strong' ? 'Strong Memory' : 'Weak Memory'}<br /><small>{run.test_budget} test budget · temperature {run.temperature} · seed {run.random_seed}</small></td><td>{formatStatus(run.status)}</td><td>{formatDate(run.created_at)}</td><td>{formatDate(run.completed_at)}</td><td>{run.status === 'COMPLETED' ? <button className="secondary" type="button" onClick={() => openReport(run.run_id)}>Open report & trace</button> : <small>Available after completion</small>}</td></tr>)}</tbody></table> : <div className="empty"><b>No audits yet</b><p>Create and run an audit to retain a traceable record here.</p></div>}{reportError && <p className="alert" role="alert">{reportError}</p>}{selectedReport && <details className="history-report" open><summary>Completed report: {selectedReport.run_id}</summary><ResultDashboard result={selectedReport} /><TargetMemoryTrace runId={selectedReport.run_id} /></details>}</section>;
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

  return <section><h1>Experiments</h1><p>Each experiment freezes one shared test suite, so every model and memory strategy is compared fairly.</p>{loadState === 'loading' ? <p className="empty" role="status">Loading experiment groups…</p> : loadState === 'error' ? <div className="empty" role="alert"><p>Experiment groups could not be loaded. Check that the API service is available and try again.</p><button type="button" className="secondary" onClick={loadExperiments}>Try again</button></div> : items.length ? items.map((item) => <ExperimentHistoryCard key={item.experiment_id} experiment={item} report={analytics[item.experiment_id]} exporting={exportingId === item.experiment_id} onDownload={download} />) : <div className="empty"><b>No experiments yet</b><p>Start a multi-model or multi-strategy audit to create a controlled comparison group.</p></div>}<ResearchValidation /></section>;
}

function percentage(value: number | null | undefined) { return value === null || value === undefined ? 'Not tested' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`; }

function ExperimentHistoryCard({ experiment, report, exporting, onDownload }: { experiment: Experiment; report?: ExperimentAnalytics; exporting: boolean; onDownload: (experiment: Experiment) => void }) {
  const complete = report?.runs.filter((item) => item.run.status === 'COMPLETED').length ?? 0;
  const failed = report?.runs.filter((item) => item.run.status === 'FAILED').length ?? 0;
  return <article className="experiment"><div className="experiment-heading"><div><h2>{experiment.label}</h2><p className="experiment-summary">{experiment.status === 'COMPLETED' ? 'All conditions completed on the same frozen suite.' : 'This comparison remains reproducible because its test suite is frozen.'}</p></div><button className="secondary export-button" type="button" disabled={exporting} onClick={() => onDownload(experiment)}>{exporting ? 'Preparing CSV…' : 'Download group CSV'}</button></div><div className="experiment-scores"><span><small>Shared tests</small><b>{experiment.test_suite_metadata.test_count || '—'}</b></span><span><small>Conditions complete</small><b>{complete} / {report?.runs.length ?? 0}</b></span></div>{failed > 0 && <p className="experiment-alert"><b>{failed} failed condition{failed === 1 ? '' : 's'} require attention.</b> Completed conditions are retained for comparison.</p>}<p><small>Suite: seed {experiment.test_suite_configuration.random_seed} · {experiment.test_suite_configuration.test_budget} test budget · {experiment.test_suite_configuration.prompt_template_version}</small></p>{report && <><ConditionTable report={report} /><RunReports runs={report.runs} /><PairedSignals comparisons={report.paired_comparisons} /></>}</article>;
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
