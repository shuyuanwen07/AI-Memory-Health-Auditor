import { UICard, UIAlert } from './ui';
import { UITable, UISelect, UIOption, UIInput, UITextArea, UIButton, UICheckbox } from './ui';
import { friendlyText } from '../services/display';
import { useState, useEffect, type ChangeEvent, type FormEvent } from 'react';
import { api } from '../services/api';
import { LiveBenchmark } from './LiveBenchmark';
import { BenchmarkSemanticReview } from './BenchmarkSemanticReview';
import type {
  AnnotationImportReport, BenchmarkFamily, BenchmarkRunResponse, BenchmarkValidationResponse,
  BinaryClassificationMetrics, MemoryStrategy, PilotAgreementMetrics, PilotReadinessReport,
  ResearchValidityReport, FormalMatrixCreateResponse, TargetProvider,
} from '../types/domain';

type JsonObject = Record<string, unknown>;
type JsonPayload = JsonObject | JsonObject[];

const benchmarkCopy: Record<BenchmarkFamily, { label: string; detail: string }> = {
  longmemeval: { label: 'LongMemEval', detail: 'Long-horizon memory questions, including information updates and multi-session reasoning.' },
  locomo: { label: 'LoCoMo', detail: 'Local LoCoMo-compatible conversational-memory cases supplied by your research team.' },
  beam: { label: 'BEAM', detail: 'Local BEAM-compatible memory cases supplied by your research team.' },
};

function isObject(value: unknown): value is JsonObject { return typeof value === 'object' && value !== null && !Array.isArray(value); }
function asJsonPayload(value: unknown): JsonPayload | null { return isObject(value) || (Array.isArray(value) && value.every(isObject)) ? value : null; }
async function parseJsonFile(file: File): Promise<unknown> { try { return JSON.parse(await file.text()); } catch { throw new Error(`“${file.name}” is not valid JSON.`); } }
function displayMetric(value: number | null) { return value === null ? 'Not measured' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`; }
function displayKappa(value: number | null) { return value === null ? 'Not measured' : value.toFixed(2); }
function humanise(value: string) { return value.replaceAll('_', ' '); }
function releaseLabel(version: string) { return /^[a-f0-9]{32,}$/i.test(version) || version.length > 48 ? 'Evidence-bound dataset release' : `Dataset version ${version}`; }

function MetricCard({ title, metrics }: { title: string; metrics: BinaryClassificationMetrics }) {
  return <UICard className="validity-card"><h3>{title}</h3><div className="validity-values"><span><small>Precision</small><b>{displayMetric(metrics.precision)}</b></span><span><small>Recall</small><b>{displayMetric(metrics.recall)}</b></span><span><small>F1</small><b>{displayMetric(metrics.f1)}</b></span><span><small>Cohen’s κ</small><b>{displayKappa(metrics.cohens_kappa)}</b></span></div><p><small>{metrics.labelled_cases} labelled cases · Accuracy {displayMetric(metrics.accuracy)} · False-positive rate {displayMetric(metrics.false_positive_rate)}</small></p></UICard>;
}

function DatasetReport({ report }: { report: AnnotationImportReport }) {
  return <div className="research-report" role="status"><h3>Annotation dataset validated</h3><p>{releaseLabel(report.dataset_version)} · {humanise(report.validation_status)}</p><div className="research-counts"><span>{report.conversations} conversations</span><span>{report.gold_memories} gold memories</span><span>{report.gold_relationships} relationships</span><span>{report.gold_tests} tests</span><span>{report.gold_evaluations} evaluations</span></div></div>;
}

function BenchmarkPreview({ family, report }: { family: BenchmarkFamily; report: BenchmarkValidationResponse }) {
  return <div className="research-report" role="status"><h3>{benchmarkCopy[family].label}-compatible input validated</h3><p><b>{report.report.cases_imported}</b> cases · {report.report.source_format}</p><p>{friendlyText(report.report.notice)}</p>{report.report.dimension_hints.length > 0 && <p><small>Dimension hints: {report.report.dimension_hints.join(', ')}</small></p>}</div>;
}

function BenchmarkRunReport({ family, run }: { family: BenchmarkFamily; run: BenchmarkRunResponse }) {
  const score = run.overall_percentage === null ? 'Not measured' : `${run.overall_percentage.toFixed(1)}%`;
  const f1 = run.mean_token_f1 == null ? 'Not measured' : `${(run.mean_token_f1 * 100).toFixed(1)}%`;
  const latency = run.mean_latency_ms == null ? 'Not measured' : `${run.mean_latency_ms.toFixed(1)} ms`;
  return <div className="research-report benchmark-run-report" role="status"><h3>{benchmarkCopy[family].label} local baseline completed</h3><p><b>{score}</b> · {run.tests_passed} / {run.tests_total} cases passed · strategy <b>{humanise(run.metadata.memory_strategy)}</b></p><div className="research-counts"><span>Mean token F1: {f1}</span><span>Mean case latency: {latency}</span></div><div className="comparison-scroll"><UITable><thead><tr><th>Case</th><th>Dimension</th><th>Outcome</th><th>Token F1</th><th>Latency</th><th>Retrieved records</th></tr></thead><tbody>{run.cases.map((item, index) => <tr key={item.case_id}><th scope="row">Case {index + 1}</th><td>{item.dimension ? humanise(item.dimension) : 'Not mapped'}</td><td>{item.passed ? 'Pass' : 'Fail'}</td><td>{item.token_f1 == null ? '—' : `${(item.token_f1 * 100).toFixed(1)}%`}</td><td>{item.latency_ms == null ? '—' : `${item.latency_ms.toFixed(1)} ms`}</td><td>{item.retrieved_memory_ids.length ? `${item.retrieved_memory_ids.length} record${item.retrieved_memory_ids.length === 1 ? '' : 's'}` : 'None'}</td></tr>)}</tbody></UITable></div><p><small>{friendlyText(run.metadata.notice)}</small></p></div>;
}

function pilotMetricRow(metric: PilotAgreementMetrics) {
  return <tr key={metric.task ?? 'overall'}><th scope="row">{metric.task ? humanise(metric.task) : 'Overall'}</th><td>{metric.annotator_a_labelled} / {metric.declared_items}</td><td>{metric.annotator_b_labelled} / {metric.declared_items}</td><td>{metric.paired_items} / {metric.declared_items}</td><td>{metric.disagreement_count}</td><td>{metric.unresolved_disagreements}</td><td>{displayMetric(metric.percent_agreement)}</td><td>{displayKappa(metric.cohens_kappa)}</td></tr>;
}

function PilotReport({ report }: { report: PilotReadinessReport }) {
  const dryRun = report.annotation_mode === 'ai_assisted_synthetic_dry_run';
  return <div className={`pilot-report ${report.ready_for_formal_evaluation ? 'pilot-ready' : 'pilot-not-ready'}`} role="status"><h3>{dryRun ? 'Synthetic calibration dry run — not eligible for formal evaluation' : report.ready_for_formal_evaluation ? 'Ready for formal evaluation' : 'Pilot needs resolution before formal evaluation'}</h3><p>{releaseLabel(report.dataset_version)} · {dryRun ? 'simulated reviewer labels' : `${report.overall.paired_items} of ${report.overall.declared_items} items labelled by both reviewers`}</p><div className="research-counts"><span>{report.overall.paired_items} paired labels</span><span>{report.overall.disagreement_count} disagreements</span><span>{report.overall.unresolved_disagreements} unresolved</span><span>Overall κ {displayKappa(report.overall.cohens_kappa)}</span></div><div className="comparison-scroll"><UITable><thead><tr><th>Task</th><th>Annotator A coverage</th><th>Annotator B coverage</th><th>Paired coverage</th><th>Disagreements</th><th>Unresolved</th><th>Agreement</th><th>Cohen’s κ</th></tr></thead><tbody>{report.by_task.map(pilotMetricRow)}{pilotMetricRow(report.overall)}</tbody></UITable></div>{report.blocking_reasons.length > 0 ? <div className="pilot-blockers"><b>Formal-evaluation blockers</b><ul>{report.blocking_reasons.map((reason) => <li key={reason}>{humanise(friendlyText(reason))}</li>)}</ul></div> : <p className="pilot-success">Coverage, adjudication and the declared agreement thresholds are satisfied.</p>}</div>;
}

/** Research files are request-scoped and never added to audit history. */
export function ResearchValidation() {
  const [dataset, setDataset] = useState<JsonObject | null>(null);
  const [predictions, setPredictions] = useState<JsonObject | null>(null);
  const [datasetFile, setDatasetFile] = useState('No file selected');
  const [predictionFile, setPredictionFile] = useState('No file selected');
  const [datasetReport, setDatasetReport] = useState<AnnotationImportReport | null>(null);
  const [validityReport, setValidityReport] = useState<ResearchValidityReport | null>(null);
  const [validityBusy, setValidityBusy] = useState(false);
  const [benchmarkFamily, setBenchmarkFamily] = useState<BenchmarkFamily>('longmemeval');
  const [benchmark, setBenchmark] = useState<JsonPayload | null>(null);
  const [benchmarkFile, setBenchmarkFile] = useState('No file selected');
  const [benchmarkPreview, setBenchmarkPreview] = useState<BenchmarkValidationResponse | null>(null);
  const [benchmarkRun, setBenchmarkRun] = useState<BenchmarkRunResponse | null>(null);
  const [benchmarkStrategy, setBenchmarkStrategy] = useState<MemoryStrategy>('strong_rule_based');
  const [benchmarkAuthorised, setBenchmarkAuthorised] = useState(false);
  const [benchmarkBusy, setBenchmarkBusy] = useState(false);
  const [pilotPackage, setPilotPackage] = useState<JsonObject | null>(null);
  const [pilotFile, setPilotFile] = useState('No file selected');
  const [pilotReport, setPilotReport] = useState<PilotReadinessReport | null>(null);
  const [pilotBusy, setPilotBusy] = useState(false);
  const [matrixBusy, setMatrixBusy] = useState(false);
  const [matrixRunning, setMatrixRunning] = useState(false);
  const [matrix, setMatrix] = useState<FormalMatrixCreateResponse | null>(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem('mha-formal-matrix-plan') || 'null');
      if (saved && typeof saved.dataset_id === 'string' && typeof saved.total_audit_runs === 'number'
          && Array.isArray(saved.scenarios) && saved.scenarios.length > 0
          && saved.scenarios.every((scenario: {run_ids?: unknown}) => Array.isArray(scenario.run_ids)
            && scenario.run_ids.length > 0 && scenario.run_ids.every((id: unknown) => typeof id === 'string'))) return saved;
    } catch { /* A malformed local plan must not prevent the research page loading. */ }
    return null;
  });
  const [matrixCompleted, setMatrixCompleted] = useState<number | null>(null);
  useEffect(() => {
    if (matrix) {
      try { sessionStorage.setItem('mha-formal-matrix-plan', JSON.stringify(matrix)); }
      catch { setError('This browser could not save the experiment plan. Keep this page open; the audit records remain available in Experiments.'); }
    }
  }, [matrix]);
  const [matrixProvider, setMatrixProvider] = useState<TargetProvider>('openrouter');
  const [matrixModel, setMatrixModel] = useState('google/gemini-2.5-flash-lite');
  const matrixModels = matrixModel.split(/[,\n]/).map(value => value.trim()).filter(Boolean);
  const [selectedStrategies, setSelectedStrategies] = useState<MemoryStrategy[]>(['no_memory', 'full_context', 'weak_first_hit', 'strong_rule_based', 'strong_score_based', 'scope_aware', 'temporal_importance']);
  const conditionCount = matrixModels.length * selectedStrategies.length;
  const validModels = matrixModels.length > 0 && new Set(matrixModels).size === matrixModels.length && matrixModels.every(value => value.length <= 100);
  const [syntheticConfirmed, setSyntheticConfirmed] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const importObject = (setter: (value: JsonObject) => void, fileSetter: (value: string) => void, reset: () => void, kind: string) => async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; if (!file) return;
    try { const parsed = await parseJsonFile(file); if (!isObject(parsed)) throw new Error(`The ${kind} must be a JSON object.`); setter(parsed); fileSetter(file.name); reset(); setError(''); }
    catch (reason) { setError(reason instanceof Error ? reason.message : `The ${kind} could not be read.`); }
  };
  const importDataset = importObject(setDataset, setDatasetFile, () => { setDatasetReport(null); setValidityReport(null); }, 'annotation dataset');
  const importPredictions = importObject(setPredictions, setPredictionFile, () => setValidityReport(null), 'prediction set');
  const importPilot = importObject(setPilotPackage, setPilotFile, () => setPilotReport(null), 'pilot package');
  const importBenchmark = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; if (!file) return;
    try { const parsed = asJsonPayload(await parseJsonFile(file)); if (!parsed) throw new Error('The benchmark file must contain a JSON object or array of objects.'); setBenchmark(parsed); setBenchmarkFile(file.name); setBenchmarkPreview(null); setBenchmarkRun(null); setBenchmarkAuthorised(false); setError(''); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'The benchmark file could not be read.'); }
  };
  const validateResearch = async (event: FormEvent) => {
    event.preventDefault(); if (!dataset) return;
    setValidityBusy(true); setError(''); setMessage('');
    try { const annotation = await api.validateAnnotationDataset(dataset); const validity = predictions ? await api.researchValidity(dataset, predictions) : null; setDatasetReport(annotation); setValidityReport(validity); setMessage(predictions ? 'Research labels and predictions were validated.' : 'Annotation dataset validated. Add predictions to calculate Auditor validity metrics.'); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Research validation could not be completed.'); }
    finally { setValidityBusy(false); }
  };
  const validateBenchmark = async () => {
    if (!benchmark) return;
    setBenchmarkBusy(true); setError('');
    try { setBenchmarkPreview(await api.validateBenchmark(benchmarkFamily, benchmark)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'The benchmark file could not be validated.'); }
    finally { setBenchmarkBusy(false); }
  };
  const runBenchmark = async (event: FormEvent) => {
    event.preventDefault(); if (!benchmark || !benchmarkAuthorised) { setError('Select a permitted benchmark file and confirm that you may process it before running.'); return; }
    setBenchmarkBusy(true); setError('');
    try { setBenchmarkRun(await api.runBenchmark(benchmarkFamily, benchmark, benchmarkFile, benchmarkStrategy)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'The local benchmark baseline could not be completed.'); }
    finally { setBenchmarkBusy(false); }
  };
  const analysePilot = async (event: FormEvent) => {
    event.preventDefault(); if (!pilotPackage) return;
    setPilotBusy(true); setError('');
    try { setPilotReport(await api.analysePilot(pilotPackage)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'The pilot package could not be analysed.'); }
    finally { setPilotBusy(false); }
  };
  const toggleStrategy = (strategy: MemoryStrategy) => setSelectedStrategies((current) => current.includes(strategy) ? current.filter((item) => item !== strategy) : [...current, strategy]);
  const createMatrix = async (event: FormEvent) => {
    event.preventDefault();
    if (!dataset || !pilotPackage || !syntheticConfirmed) { setError('Upload the matching frozen dataset and ready pilot package, then confirm that the source is synthetic.'); return; }
    if (!pilotReport?.ready_for_formal_evaluation) { setError('Analyse the matching double-annotation package and resolve all formal-evaluation blockers before creating a matrix.'); return; }
    if (!validModels || conditionCount < 2 || conditionCount > 8) { setError('Choose distinct model names and memory strategies to create 2–8 comparison conditions.'); return; }
    setMatrixBusy(true); setError(''); setMessage(''); setMatrixCompleted(null);
    try {
      const labels: Record<MemoryStrategy, string> = { no_memory: 'No memory', full_context: 'Full context', weak_first_hit: 'Weak first-hit', strong_rule_based: 'Strong rule-based', strong_score_based: 'Strong score-based', scope_aware: 'Scope-aware retrieval', temporal_importance: 'Temporal & importance' };
      setMatrix(await api.createFormalSyntheticMatrix({ dataset, pilot: pilotPackage, synthetic_data_confirmation: true, label_prefix: 'Synthetic Pilot v2', random_seed: 42, conditions: matrixModels.flatMap(model => selectedStrategies.map((memory_strategy) => ({ label: matrixModels.length > 1 ? `${model.slice(0, 65)} · ${labels[memory_strategy]}` : labels[memory_strategy], memory_strategy, provider: matrixProvider, model, temperature: 0 }))) }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The formal synthetic matrix could not be created.'); }
    finally { setMatrixBusy(false); }
  };
  const runMatrix = async () => {
    if (!matrix) return;
    setMatrixRunning(true); setError(''); setMessage(''); setMatrixCompleted(0);
    const runIds = matrix.scenarios.flatMap((scenario) => scenario.run_ids);
    try {
      let completed = 0;
      for (const runId of runIds) {
        let state = await api.getAudit(runId);
        if (state.status === 'CANCELLED') throw new Error('A condition was cancelled. Its saved answers are preserved; this matrix cannot be reported as complete.');
        if (state.status === 'FAILED') { await api.retry(runId); state = await api.getAudit(runId); }
        if (state.status === 'TESTS_GENERATED') { await api.execute(runId); state = await api.getAudit(runId); }
        if (state.status === 'TESTS_EXECUTED') { await api.evaluate(runId); state = await api.getAudit(runId); }
        if (state.status !== 'COMPLETED') throw new Error('A condition has not completed. Inspect its saved report, then continue this matrix.');
        completed += 1;
        setMatrixCompleted(completed);
      }
      setMessage(`Completed ${runIds.length} controlled synthetic audit runs. Open Experiments to compare the frozen suites and export figures.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The matrix stopped before completion. Completed runs remain available in Experiments.'); }
    finally { setMatrixRunning(false); }
  };

  return <section className="research-validation" aria-labelledby="research-validation-title">
    <h2 id="research-validation-title">Research Workspace</h2><p>Run permitted local benchmark files, check double-annotation readiness and validate Auditor outputs. Research uploads are request-scoped, except an explicitly authorised synthetic formal matrix that you choose to materialise as audit records.</p>
    <LiveBenchmark />
    <BenchmarkSemanticReview />
    <section className="research-workspace" aria-labelledby="benchmark-workspace-title"><h3 id="benchmark-workspace-title">Local Benchmark Workspace</h3><p>Use this deterministic policy baseline to compare memory strategies on a local, permitted source. It is not an official score for any external benchmark.</p>
      <form className="benchmark-run-controls" onSubmit={runBenchmark}><div className="benchmark-controls-grid"><label>Benchmark family<UISelect aria-label="Benchmark family" value={benchmarkFamily} onChange={(event) => { setBenchmarkFamily(event.target.value as BenchmarkFamily); setBenchmarkPreview(null); setBenchmarkRun(null); }}><UIOption value="longmemeval">LongMemEval</UIOption><UIOption value="locomo">LoCoMo</UIOption><UIOption value="beam">BEAM</UIOption></UISelect><small>{benchmarkCopy[benchmarkFamily].detail}</small></label><label>Local benchmark JSON<UIInput aria-label="Local benchmark JSON" type="file" accept="application/json,.json" onChange={importBenchmark} /><small>{benchmarkFile}</small></label><label>Memory strategy<UISelect aria-label="Benchmark memory strategy" value={benchmarkStrategy} onChange={(event) => setBenchmarkStrategy(event.target.value as MemoryStrategy)}><UIOption value="no_memory">No memory</UIOption><UIOption value="full_context">Full context</UIOption><UIOption value="weak_first_hit">Weak first-hit</UIOption><UIOption value="strong_rule_based">Strong rule-based</UIOption><UIOption value="strong_score_based">Strong score-based</UIOption><UIOption value="scope_aware">Scope-aware retrieval</UIOption><UIOption value="temporal_importance">Temporal &amp; importance</UIOption></UISelect><small>Runs use seed 42 and isolated in-memory records.</small></label></div><UICheckbox aria-label="Benchmark source authorisation" checked={benchmarkAuthorised} onChange={(event) => setBenchmarkAuthorised(event.target.checked)} className="consent">I confirm that I am authorised to process this local source and comply with its licence, citation and privacy terms.</UICheckbox><div className="research-actions"><UIButton type="button" className="secondary" disabled={benchmarkBusy || !benchmark} onClick={validateBenchmark}>{benchmarkBusy ? 'Working…' : 'Validate Benchmark Input'}</UIButton><UIButton type="submit" disabled={benchmarkBusy || !benchmark || !benchmarkAuthorised}>{benchmarkBusy ? 'Running local baseline…' : 'Run Local Baseline'}</UIButton></div></form>{benchmarkPreview && <BenchmarkPreview family={benchmarkFamily} report={benchmarkPreview} />}{benchmarkRun && <BenchmarkRunReport family={benchmarkFamily} run={benchmarkRun} />}
    </section>
    <section className="research-workspace" aria-labelledby="pilot-workspace-title"><h3 id="pilot-workspace-title">Double-Annotation Pilot</h3><p>Upload one de-identified package containing two independent label sets and adjudications. The analysis shows coverage, disagreement resolution, Cohen’s κ and formal-study readiness.</p><form onSubmit={analysePilot}><label className="pilot-upload">Pilot package JSON<UIInput aria-label="Pilot package JSON" type="file" accept="application/json,.json" onChange={importPilot} /><small>{pilotFile}</small></label><UIButton type="submit" disabled={pilotBusy || !pilotPackage}>{pilotBusy ? 'Analysing pilot…' : 'Analyse Pilot Package'}</UIButton></form>{pilotReport && <PilotReport report={pilotReport} />}</section>
    <section className="research-workspace" aria-labelledby="validity-workspace-title"><h3 id="validity-workspace-title">Auditor Validity Checks</h3><p>Validate a frozen human-label dataset, then optionally compare it against prediction data. These metrics evaluate the Auditor, not a benchmark target.</p><form onSubmit={validateResearch}><div className="research-upload-grid"><label>Annotation dataset JSON<UIInput aria-label="Annotation dataset JSON" type="file" accept="application/json,.json" onChange={importDataset} /><small>{datasetFile}</small></label><label>Prediction set JSON<UIInput aria-label="Prediction set JSON" type="file" accept="application/json,.json" onChange={importPredictions} /><small>{predictionFile}</small></label></div><UIButton type="submit" disabled={validityBusy || !dataset}>{validityBusy ? 'Validating research files…' : 'Validate Research Files'}</UIButton></form>{message && <p className="research-message" role="status">{message}</p>}{datasetReport && <DatasetReport report={datasetReport} />}{validityReport && <div className="validity-report"><h3>Auditor validity metrics</h3><p>Scores compare submitted, decided predictions with their matching reference labels. Missing and uncertain judgments are excluded, so coverage must be reported alongside accuracy. Memory and relationship recall assumes the imported candidate inventory is complete.</p>{[ ["Question assessments", validityReport.test_assessment_coverage], ["Answer judgments", validityReport.evaluator_coverage] ].map(([label, raw]) => { const coverage = raw as import("../types/domain").PredictionCoverage | undefined; return coverage ? <p key={String(label)}>{String(label)}: {coverage.decided} / {coverage.expected} decided · {coverage.missing} missing · {coverage.abstained} uncertain</p> : null; })}<div className="validity-grid"><MetricCard title="Memory Extraction" metrics={validityReport.extraction} /><MetricCard title="Relationship Classification" metrics={validityReport.relationship} /><MetricCard title="Test Validity" metrics={validityReport.test_validity} /><MetricCard title="Behaviour Evaluator" metrics={validityReport.evaluator} /></div></div>}</section>
    {error && <UIAlert className="alert" role="alert">{error}</UIAlert>}
    <section className="research-workspace" aria-labelledby="formal-matrix-title">
      <h3 id="formal-matrix-title">Formal Synthetic Pilot Matrix</h3>
      <p>Create one frozen comparison group per synthetic scenario. Every model and selected strategy receives the same human-labelled test suite. Select one strategy with several models to compare models, or one model with several strategies to compare memory policy.</p>
      <form onSubmit={createMatrix}>
        <div className="benchmark-controls-grid">
          <label>Target runtime<UISelect aria-label="Formal matrix target runtime" value={matrixProvider} onChange={(event) => { const provider = event.target.value as TargetProvider; setMatrixProvider(provider); setMatrixModel(provider === 'openrouter' ? 'google/gemini-2.5-flash-lite' : provider === 'ollama' ? 'qwen3:1.7b' : 'rule-based-target-ai'); }}><UIOption value="openrouter">OpenRouter</UIOption><UIOption value="ollama">Local Ollama</UIOption><UIOption value="rule_based">Deterministic rule-based baseline</UIOption></UISelect></label>
          <label>Target models<UITextArea aria-label="Formal matrix target model" value={matrixModel} onChange={(event) => setMatrixModel(event.target.value)} required rows={3} /><small>Enter one deployed model name per line. Models share the selected service; local models must already be installed.</small></label>
          <fieldset><legend>Memory strategies</legend>{(['no_memory', 'full_context', 'weak_first_hit', 'strong_rule_based', 'strong_score_based', 'scope_aware', 'temporal_importance'] as MemoryStrategy[]).map((strategy) => <UICheckbox checked={selectedStrategies.includes(strategy)} onChange={() => toggleStrategy(strategy)} key={strategy} className="consent">{humanise(strategy)}</UICheckbox>)}</fieldset>
        </div>
        <p role="status">{conditionCount} conditions per scenario · {matrixModels.length} models × {selectedStrategies.length} strategies. Choose 2–8 conditions.</p>
        {!validModels && <p role="alert">Use distinct, non-empty model names of at most 100 characters.</p>}
        <UICheckbox aria-label="Synthetic data confirmation" checked={syntheticConfirmed} onChange={(event) => setSyntheticConfirmed(event.target.checked)} className="consent">I confirm that this is authorised synthetic data and may be materialised as operational audit records.</UICheckbox>
        <UIButton type="submit" disabled={matrixBusy || matrixRunning || !dataset || !pilotPackage || !pilotReport?.ready_for_formal_evaluation || !syntheticConfirmed || !validModels || conditionCount < 2 || conditionCount > 8}>{matrixBusy ? 'Creating frozen matrix…' : 'Create Formal Matrix'}</UIButton>
      </form>
      {matrix && <div className="research-report" role="status"><h3>Formal synthetic matrix created</h3><p><b>{matrix.scenario_count}</b> scenarios × <b>{matrix.condition_count}</b> conditions = <b>{matrix.total_audit_runs}</b> runs.</p><p>Saved plan for dataset {matrix.dataset_id} · version {matrix.dataset_version}. Source files and human labels are not stored in this browser plan.</p><p role="status">{matrixCompleted === null ? 'Continue to verify saved progress.' : `${matrixCompleted} / ${matrix.total_audit_runs} conditions verified complete.`}</p><UIButton type="button" disabled={matrixRunning} onClick={runMatrix}>{matrixRunning ? 'Running conditions…' : `Run ${matrix.total_audit_runs} Conditions`}</UIButton></div>}
    </section>
  </section>;
}
