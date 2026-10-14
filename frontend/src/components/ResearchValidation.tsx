import { UICard, UIAlert } from './ui';
import {FrozenThresholdCheck} from './FrozenThresholdCheck';
import {FormalStudySummary} from './FormalStudySummary';
import { ResearchValidityChart } from './ResearchValidityChart';
import { PilotCoverageChart } from './PilotCoverageChart';
import { UITable, UISelect, UIOption, UIInput, UITextArea, UIButton, UICheckbox, UIPanel, UISummary } from './ui';
import { friendlyText, memoryStrategyLabel } from '../services/display';
import { useState, useEffect, useRef, type ChangeEvent, type FormEvent } from 'react';
import { api } from '../services/api';
import { saveBlob } from '../services/download';
import { LiveBenchmark } from './LiveBenchmark';
import { BenchmarkSemanticReview } from './BenchmarkSemanticReview';
import { BenchmarkRankingAgreement } from './BenchmarkRankingAgreement';
import type {
  AnnotationImportReport, BenchmarkFamily, BenchmarkRunResponse, BenchmarkValidationResponse,
  MemoryStrategy, PilotAgreementMetrics, PilotReadinessReport,
  ResearchValidityReport, FormalMatrixCreateResponse, TargetProvider,
} from '../types/domain';

const successCriteriaFields = [
  {key:'failure_detection_recall_min_percent',label:'Minimum failure recall (%)'},
  {key:'failure_classification_accuracy_min_percent',label:'Minimum classification accuracy (%)'},
  {key:'test_validity_min_percent',label:'Minimum test validity (%)'},
  {key:'false_positive_rate_max_percent',label:'Maximum false-positive rate (%)'},
] as const;
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


function DatasetReport({ report }: { report: AnnotationImportReport }) {
  const [receipt, setReceipt] = useState('');
  const download = () => {
    const content = JSON.stringify({schema_version:'reviewed-dataset-receipt-v1',
      dataset_id:report.dataset_id,dataset_version:report.dataset_version,
      dataset_fingerprint_sha256:report.fingerprint_sha256},null,2);
    setReceipt(content);
    saveBlob(new Blob([content],{type:'application/json'}),'dataset-review-receipt.json');
  };
  return <div className="research-report" role="status"><h3>Annotation dataset validated</h3><p>{releaseLabel(report.dataset_version)} · {humanise(report.validation_status)}</p><div className="research-counts"><span>{report.conversations} {report.conversations === 1 ? 'conversation' : 'conversations'}</span><span>{report.gold_memories} gold memories</span><span>{report.gold_relationships} relationships</span><span>{report.gold_tests} tests</span><span>{report.gold_evaluations} evaluations</span></div><p>Declared source: {friendlyText(report.data_origin || 'Not recorded')}</p><small>Format and reference checks do not verify independent human review.</small><UIButton onClick={download}>Download dataset review receipt</UIButton>
    {receipt && <><p>Review receipt prepared. If no file was saved, copy the JSON below.</p><UIPanel open><UISummary>Prepared review receipt</UISummary><UITextArea aria-label="Dataset review receipt JSON" value={receipt} readOnly rows={6}/></UIPanel></>}
  </div>;
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
  return <tr key={metric.task ?? 'overall'}><th scope="row">{metric.task ? humanise(metric.task) : 'Overall'}</th><td>{metric.annotator_a_labelled} / {metric.declared_items}</td><td>{metric.annotator_b_labelled} / {metric.declared_items}</td><td>{metric.paired_items} / {metric.declared_items}</td><td>{metric.adjudicated_items} / {metric.declared_items}</td><td>{metric.disagreement_count}</td><td>{metric.unresolved_disagreements}</td><td>{displayMetric(metric.percent_agreement)}</td><td>{displayKappa(metric.cohens_kappa)}</td></tr>;
}

function PilotReport({ report }: { report: PilotReadinessReport }) {
  const dryRun = report.annotation_mode === 'ai_assisted_synthetic_dry_run';
  const incompleteReviews = report.by_task.filter(metric => metric.declared_items === 0 || metric.paired_items < report.minimum_paired_items_per_task || metric.paired_items !== metric.declared_items).length;
  const incompleteReferences = report.by_task.filter(metric => metric.adjudicated_items !== metric.declared_items).length;
  return <div className={`pilot-report ${report.ready_for_formal_evaluation ? 'pilot-ready' : 'pilot-not-ready'}`} role="status">
    <h3>{dryRun ? 'Synthetic calibration dry run — not eligible for formal evaluation' : report.ready_for_formal_evaluation ? 'Pilot annotation checks passed' : 'Pilot needs resolution before formal evaluation'}</h3>
    <p>{releaseLabel(report.dataset_version)} · {dryRun ? 'simulated reviewer labels' : `${report.overall.paired_items} of ${report.overall.declared_items} items labelled by both reviewers`}</p>
    <div className="research-counts"><span>{report.overall.disagreement_count} original disagreements</span><span>{report.overall.unresolved_disagreements} unresolved</span><span>Overall κ {displayKappa(report.overall.cohens_kappa)}</span></div>
    {report.minimum_kappa !== null && <p><small>Required κ: {report.minimum_kappa}. Displayed agreement values are rounded; readiness uses unrounded values.</small></p>}
    <PilotCoverageChart metrics={report.by_task} />
    {report.blocking_reasons.length > 0 && <div className="pilot-blockers">
      <b>Next steps</b><ul>
        {incompleteReviews > 0 && <li>Complete both reviewers’ labels and the required sample size in {incompleteReviews} tasks.</li>}
        {incompleteReferences > 0 && <li>Complete reference decisions in {incompleteReferences} tasks.</li>}
        {report.overall.unresolved_disagreements > 0 && <li>Resolve {report.overall.unresolved_disagreements} remaining disagreements against the source.</li>}
        <li>Review the required checks below before starting formal evaluation.</li>
      </ul>
      <UIPanel><UISummary>Required checks ({report.blocking_reasons.length})</UISummary><ul>{report.blocking_reasons.map(reason => <li key={reason}>{humanise(friendlyText(reason))}</li>)}</ul></UIPanel>
    </div>}
    <UIPanel><UISummary>Exact review counts & agreement</UISummary><div className="comparison-scroll"><UITable><thead><tr><th>Task</th><th>Reviewer 1 coverage</th><th>Reviewer 2 coverage</th><th>Paired coverage</th><th>Reference decisions</th><th>Disagreements</th><th>Unresolved</th><th>Agreement</th><th>Cohen’s κ</th></tr></thead><tbody>{report.by_task.map(pilotMetricRow)}{pilotMetricRow(report.overall)}</tbody></UITable></div></UIPanel>
    {!report.blocking_reasons.length && <p className="pilot-success">Coverage, adjudication and the declared agreement thresholds are satisfied. Independent provenance still requires verification.</p>}
  </div>;
}

/** Research files are request-scoped and never added to audit history. */
export function ResearchValidation() {
  const [dataset, setDataset] = useState<JsonObject | null>(null);
  const [predictions, setPredictions] = useState<JsonObject | null>(null);
  const [datasetFile, setDatasetFile] = useState('No file selected');
  const [predictionFile, setPredictionFile] = useState('No file selected');
  const [developmentDataset,setDevelopmentDataset]=useState<JsonObject|null>(null);
  const [developmentFile,setDevelopmentFile]=useState('No file selected');
  const [checkDistinctHistories,setCheckDistinctHistories]=useState(false);
  const [freezeStudyDesign,setFreezeStudyDesign]=useState(false);
  const [samplingRule,setSamplingRule]=useState('');
  const [primaryOutcome,setPrimaryOutcome]=useState('overall_memory_health');
  const validStudyDesign=!freezeStudyDesign||(checkDistinctHistories&&!!developmentDataset&&samplingRule.trim().length>=20&&samplingRule.trim().length<=1000);
  const [datasetReport, setDatasetReport] = useState<AnnotationImportReport | null>(null);
  const [validityReport, setValidityReport] = useState<ResearchValidityReport | null>(null);
  const [validityBusy, setValidityBusy] = useState(false);
  const [benchmarkFamily, setBenchmarkFamily] = useState<BenchmarkFamily>('longmemeval');
  const [benchmark, setBenchmark] = useState<JsonPayload | null>(null);
  const [benchmarkFile, setBenchmarkFile] = useState('No file selected');
  const [pendingBenchmarkFile, setPendingBenchmarkFile] = useState<File | null>(null);
  const [benchmarkPreview, setBenchmarkPreview] = useState<BenchmarkValidationResponse | null>(null);
  const [benchmarkRun, setBenchmarkRun] = useState<BenchmarkRunResponse | null>(null);
  const [benchmarkStrategy, setBenchmarkStrategy] = useState<MemoryStrategy>('strong_rule_based');
  const [benchmarkAuthorised, setBenchmarkAuthorised] = useState(false);
  const [benchmarkBusy, setBenchmarkBusy] = useState(false);
  const [pilotPackage, setPilotPackage] = useState<JsonObject | null>(null);
  const [pilotFile, setPilotFile] = useState('No file selected');
  const [pilotReport, setPilotReport] = useState<PilotReadinessReport | null>(null);
  const [pilotBusy, setPilotBusy] = useState(false);
  const matrixOperation=useRef(false);
  const [matrixRestoring,setMatrixRestoring]=useState(false);
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
  const [repetitionsInput,setRepetitionsInput]=useState('1');
  const [matrixProvider, setMatrixProvider] = useState<TargetProvider>('openrouter');
  const [matrixModel, setMatrixModel] = useState('openai/gpt-6-luna');
  const matrixModels = matrixModel.split(/[,\n]/).map(value => value.trim()).filter(Boolean);
  const [selectedStrategies, setSelectedStrategies] = useState<MemoryStrategy[]>(['no_memory', 'full_context', 'weak_first_hit', 'strong_rule_based', 'strong_score_based', 'scope_aware', 'temporal_importance']);
  const validRepetitions=/^[1-5]$/.test(repetitionsInput)&&(!freezeStudyDesign||Number(repetitionsInput)>=3);
  const validFormalStudyConditions=!freezeStudyDesign||(matrixModels.length===1&&selectedStrategies.includes('weak_first_hit')&&selectedStrategies.includes('strong_rule_based'));
  const conditionCount = matrixModels.length * selectedStrategies.length;
  const validModels = matrixModels.length > 0 && new Set(matrixModels).size === matrixModels.length && matrixModels.every(value => value.length <= 100);
  const [criteriaInputs,setCriteriaInputs]=useState<Record<typeof successCriteriaFields[number]['key'],string>>({failure_detection_recall_min_percent:'',failure_classification_accuracy_min_percent:'',test_validity_min_percent:'',false_positive_rate_max_percent:''});
  const validSuccessCriteria=Object.values(criteriaInputs).every(value=>value.trim()!=='' && Number.isFinite(Number(value)) && Number(value)>=0 && Number(value)<=100);
  const [syntheticConfirmed, setSyntheticConfirmed] = useState(false);
  const [researchConfirmed,setResearchConfirmed]=useState(false);
  const [sourceRelease,setSourceRelease]=useState<JsonObject|null>(null);
  const [sourceReleaseFile,setSourceReleaseFile]=useState('No file selected');
  const researchSource=dataset?.data_origin==='deidentified_research';
  const sourceConfirmed=researchSource?researchConfirmed&&!!sourceRelease&&freezeStudyDesign:syntheticConfirmed;
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const [researchFilesAuthorised, setResearchFilesAuthorised] = useState(false);
  const researchFilesPermission = useRef(false);
  const researchRevision = useRef(0);
  const pilotRevision = useRef(0);
  const importRevisions = useRef<Record<string, number>>({});
  const importObject = (setter: (value: JsonObject | null) => void, fileSetter: (value: string) => void, reset: () => void, kind: string) => async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; if (!file || !researchFilesPermission.current) return;
    const revision = (importRevisions.current[kind] || 0) + 1;
    importRevisions.current[kind] = revision;
    setter(null); fileSetter(file.name); reset(); setError(''); setMessage('');
    try {
      const parsed = await parseJsonFile(file);
      if (importRevisions.current[kind] !== revision) return;
      if (!isObject(parsed)) throw new Error(`The ${kind} must be a JSON object.`);
      setter(parsed);
    } catch (reason) {
      if (importRevisions.current[kind] === revision) setError(reason instanceof Error ? reason.message : `The ${kind} could not be read.`);
    }
  };
  const resetResearch = () => { researchRevision.current++; setValidityBusy(false); setValidityReport(null); };
  const importDataset = importObject(setDataset, setDatasetFile, () => { resetResearch(); setDatasetReport(null); setResearchConfirmed(false); }, 'annotation dataset');
  const importPredictions = importObject(setPredictions, setPredictionFile, resetResearch, 'prediction set');
  const importSourceRelease=importObject(setSourceRelease,setSourceReleaseFile,()=>setResearchConfirmed(false),'source permission receipt');
  const importDevelopment=importObject(setDevelopmentDataset,setDevelopmentFile,()=>{},'development dataset');
  const importPilot = importObject(setPilotPackage, setPilotFile, () => { pilotRevision.current++; setPilotBusy(false); setPilotReport(null); }, 'pilot package');
  const updateResearchFileAuthorisation = (checked: boolean) => {
    researchFilesPermission.current = checked;
    setResearchFilesAuthorised(checked);
    if (checked) return;
    for (const kind of Object.keys(importRevisions.current)) importRevisions.current[kind]++;
    resetResearch(); pilotRevision.current++; setPilotBusy(false);
    setDataset(null); setDatasetFile('No file selected'); setDatasetReport(null);
    setPredictions(null); setPredictionFile('No file selected');
    setDevelopmentDataset(null); setDevelopmentFile('No file selected');
    setSourceRelease(null); setSourceReleaseFile('No file selected');
    setPilotPackage(null); setPilotFile('No file selected'); setPilotReport(null);
    setSyntheticConfirmed(false); setResearchConfirmed(false); setError(''); setMessage('');
  };
  const benchmarkRevision = useRef(0);
  const benchmarkImportRevision = useRef(0);
  const resetBenchmarkResults = () => {
    benchmarkRevision.current++; setBenchmarkBusy(false); setBenchmarkPreview(null); setBenchmarkRun(null);
  };
  const readBenchmarkFile = async (file: File, revision: number) => {
    try {
      const parsed = asJsonPayload(await parseJsonFile(file));
      if (benchmarkImportRevision.current !== revision) return;
      if (!parsed) throw new Error('The benchmark file must contain a JSON object or array of objects.');
      setBenchmark(parsed);
    } catch (reason) {
      if (benchmarkImportRevision.current === revision) setError(reason instanceof Error ? reason.message : 'The benchmark file could not be read.');
    }
  };
  const importBenchmark = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; if (!file) return;
    benchmarkImportRevision.current++;
    resetBenchmarkResults(); setBenchmark(null); setPendingBenchmarkFile(file); setBenchmarkFile(file.name); setBenchmarkAuthorised(false); setError('');
  };
  const updateBenchmarkAuthorisation = (checked: boolean) => {
    setBenchmarkAuthorised(checked);
    if (!checked) {
      benchmarkImportRevision.current++;
      resetBenchmarkResults(); setBenchmark(null); setError('');
      return;
    }
    if (pendingBenchmarkFile) void readBenchmarkFile(pendingBenchmarkFile, benchmarkImportRevision.current);
  };
  const validateResearch = async (event: FormEvent) => {
    event.preventDefault(); if (!dataset || !researchFilesPermission.current) return;
    const revision = ++researchRevision.current;
    setValidityBusy(true); setError(''); setMessage('');
    try {
      const annotation = await api.validateAnnotationDataset(dataset,researchFilesPermission.current);
      if (researchRevision.current !== revision) return;
      const validity = predictions ? await api.researchValidity(dataset, predictions,researchFilesPermission.current) : null;
      if (researchRevision.current !== revision) return;
      setDatasetReport(annotation); setValidityReport(validity);
      setMessage(predictions ? 'Research labels and predictions were validated.' : 'Annotation dataset validated. Add predictions to calculate Auditor validity metrics.');
    } catch (reason) {
      if (researchRevision.current === revision) setError(reason instanceof Error ? reason.message : 'Research validation could not be completed.');
    } finally { if (researchRevision.current === revision) setValidityBusy(false); }
  };
  const validateBenchmark = async () => {
    if (!benchmark || !benchmarkAuthorised) return;
    const revision = ++benchmarkRevision.current;
    setBenchmarkBusy(true); setError('');
    try {
      const report = await api.validateBenchmark(benchmarkFamily, benchmark, benchmarkAuthorised);
      if (benchmarkRevision.current === revision) setBenchmarkPreview(report);
    } catch (reason) {
      if (benchmarkRevision.current === revision) setError(reason instanceof Error ? reason.message : 'The benchmark file could not be validated.');
    } finally { if (benchmarkRevision.current === revision) setBenchmarkBusy(false); }
  };
  const runBenchmark = async (event: FormEvent) => {
    event.preventDefault(); if (!benchmark || !benchmarkAuthorised) { setError('Select a permitted benchmark file and confirm that you may process it before running.'); return; }
    const revision = ++benchmarkRevision.current;
    setBenchmarkBusy(true); setError('');
    try {
      const run = await api.runBenchmark(benchmarkFamily, benchmark, benchmarkAuthorised, benchmarkFile, benchmarkStrategy);
      if (benchmarkRevision.current === revision) setBenchmarkRun(run);
    } catch (reason) {
      if (benchmarkRevision.current === revision) setError(reason instanceof Error ? reason.message : 'The local benchmark baseline could not be completed.');
    } finally { if (benchmarkRevision.current === revision) setBenchmarkBusy(false); }
  };
  const analysePilot = async (event: FormEvent) => {
    event.preventDefault(); if (!pilotPackage || !researchFilesPermission.current) return;
    const revision = ++pilotRevision.current;
    setPilotBusy(true); setError('');
    try {
      const report = await api.analysePilot(pilotPackage,researchFilesPermission.current);
      if (pilotRevision.current === revision) setPilotReport(report);
    } catch (reason) {
      if (pilotRevision.current === revision) setError(reason instanceof Error ? reason.message : 'The pilot package could not be analysed.');
    } finally { if (pilotRevision.current === revision) setPilotBusy(false); }
  };
  const toggleStrategy = (strategy: MemoryStrategy) => setSelectedStrategies((current) => current.includes(strategy) ? current.filter((item) => item !== strategy) : [...current, strategy]);
  const matchingPilotDataset = !!datasetReport && !!pilotPackage
    && pilotPackage.dataset_id === datasetReport.dataset_id
    && pilotPackage.dataset_version === datasetReport.dataset_version
    && pilotPackage.dataset_fingerprint_sha256 === datasetReport.fingerprint_sha256;
  const createMatrix = async (event: FormEvent) => {
    event.preventDefault();
    if(matrixOperation.current) return;
    if (!dataset || !pilotPackage || !sourceConfirmed) { setError('Upload the matching frozen dataset and ready pilot package, then confirm the source permission for this matrix.'); return; }
    if (!matchingPilotDataset) {setError('Validate the dataset and use a pilot bound to that exact reviewed release before creating a matrix.'); return;}
    if (!pilotReport?.ready_for_formal_evaluation) { setError('Analyse the matching double-annotation package and resolve all formal-evaluation blockers before creating a matrix.'); return; }
    if (!validModels || conditionCount < 2 || conditionCount > 8) { setError('Choose distinct model names and memory strategies to create 2–8 comparison conditions.'); return; }
    if(freezeStudyDesign&&!validStudyDesign){setError('Provide a development dataset and a selection rule of 20–1000 characters before saving the formal analysis plan.');return;}
    if(freezeStudyDesign&&!validFormalStudyConditions){setError('A formal Experiment B needs exactly one fixed target model plus both Weak first-hit and Strong rule-based policies.');return;}
    if(freezeStudyDesign&&Number(repetitionsInput)<3){setError('Formal Experiment B requires at least three runs per policy, including local Ollama and the deterministic baseline.');return;}
    if(freezeStudyDesign&&!developmentDataset){setError('Upload the development annotation dataset before freezing formal Experiment B.');return;}
    if(checkDistinctHistories&&!developmentDataset){setError('Upload the development annotation dataset to check for reused histories.');return;}
    if (!validRepetitions) {setError('Choose a whole number of repetitions from 1 to 5 before freezing the experiment.');return;}
    if (!validSuccessCriteria) {setError('Enter all four pilot-selected success criteria as percentages from 0 to 100 before freezing the experiment.');return;}
    matrixOperation.current=true;setMatrixBusy(true); setError(''); setMessage(''); setMatrixCompleted(null);
    try {
      const requestBody={ dataset, pilot: pilotPackage, ...(freezeStudyDesign?{study_design:{sampling_rule:samplingRule.trim(),primary_outcome:primaryOutcome,analysis_unit:'source_history',incomplete_results:'report_without_imputing_scores'}}:{}), ...(checkDistinctHistories?{development_dataset:developmentDataset}:{}), repetitions:Number(repetitionsInput), success_criteria:Object.fromEntries(Object.entries(criteriaInputs).map(([key,value])=>[key,Number(value)])), synthetic_data_confirmation: !researchSource, ...(researchSource?{source_release:sourceRelease}:{}), label_prefix: researchSource?'Reviewed research release':'Synthetic Pilot v2', random_seed: 42, conditions: matrixModels.flatMap(model => selectedStrategies.map((memory_strategy) => ({ label: matrixModels.length > 1 ? `${model.slice(0, 65)} · ${memoryStrategyLabel(memory_strategy)}` : memoryStrategyLabel(memory_strategy), memory_strategy, provider: matrixProvider, model, temperature: 0 }))) };
      setMatrix(await (researchSource?api.createFormalResearchMatrix(requestBody):freezeStudyDesign?api.createFormalSyntheticMatrix(requestBody):api.createExploratorySyntheticMatrix(requestBody)));
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The formal synthetic matrix could not be created.'); }
    finally { matrixOperation.current=false;setMatrixBusy(false); }
  };
  const runMatrix = async () => {
    if (!matrix || matrixOperation.current) return;
    if (!matrix.acceptance_protocol) {setError('This saved plan has no frozen success criteria. Prepare a newly reviewed experiment before collecting formal results.');return;}
    matrixOperation.current=true;setMatrixRunning(true); setError(''); setMessage(''); setMatrixCompleted(0);
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
      setMessage(`Completed ${runIds.length} controlled audit runs. Open Experiments to compare the frozen suites and export figures.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The matrix stopped before completion. Completed runs remain available in Experiments.'); }
    finally { matrixOperation.current=false;setMatrixRunning(false); }
  };

  return <section className="research-validation" aria-labelledby="research-validation-title">
    <h2 id="research-validation-title">Research Workspace</h2>
    <UICard><h3>Evidence needed for the proposal</h3><p>The default three-method chart is a development comparison. Complete the following studies with frozen sources and independent human labels before making research claims.</p>
      <div className="comparison-scroll"><UITable><thead><tr><th>Study</th><th>Keep fixed</th><th>Evidence to collect</th><th>Where to start</th></tr></thead><tbody>
        <tr><th>A · Can the auditor find useful problems?</th><td>Same model, histories and actual call budget</td><td>Direct, rule-seeded researcher-reviewed fixed-template and contextual probes; distinct human-confirmed defects, validity, precision and recall</td><td>Open a completed audit → Prepare audit-method comparison</td></tr>
        <tr><th>B · Do memory policies differ?</th><td>Same model, reviewed questions and reader settings</td><td>Weak / Strong policies, no-memory and full-context controls, repeated results and regressions</td><td>New audit → compare memory strategies</td></tr>
        <tr><th>C · Does an external benchmark agree?</th><td>Same policies and technically compatible benchmark subset</td><td>Semantic reference labels and relative ranking; lexical matches alone are insufficient</td><td>Real-model benchmark below</td></tr>
        <tr><th>Repair value · Does the finding transfer?</th><td>Same model; repair rule frozen before new scenes</td><td>Original / generic instruction / directed policy on independently reviewed new histories; gains, regressions, budget and uncertainty</td><td>Completed audit → Prepare repair comparison → Independent validation history</td></tr>
      </tbody></UITable></div><p><a href="/quality">Review auditor reliability and begin independent blind review</a>. The dataset, pilot and formal-matrix tools below validate submitted evidence; this guide does not mark a study complete.</p>
    </UICard><p>Run permitted local benchmark files, check double-annotation readiness and validate Auditor outputs. Most research uploads are request-scoped. Creating an authorised matrix stores its source histories; saving a benchmark plan stores metadata and execution receipts.</p>
    <UICheckbox aria-label="Research file source authorisation" checked={researchFilesAuthorised} onChange={event=>updateResearchFileAuthorisation(event.target.checked)}>I am authorised to process the annotation, prediction, pilot, development and permission files. Checking allows this browser to read them; validation sends them to this Auditor server. Revoke to clear loaded files and pending previews. Saving histories or calling a model requires the separate confirmation below.</UICheckbox>
    <LiveBenchmark />
    <BenchmarkSemanticReview />
    <BenchmarkRankingAgreement />
    <section className="research-workspace" aria-labelledby="benchmark-workspace-title"><h3 id="benchmark-workspace-title">Local Benchmark Workspace</h3><p>Use this deterministic policy baseline to compare memory strategies on a local, permitted source. It is not an official score for any external benchmark.</p>
      <form className="benchmark-run-controls" onSubmit={runBenchmark}><div className="benchmark-controls-grid"><label>Benchmark family<UISelect aria-label="Benchmark family" value={benchmarkFamily} onChange={(event) => { setBenchmarkFamily(event.target.value as BenchmarkFamily); resetBenchmarkResults(); setError(''); }}><UIOption value="longmemeval">LongMemEval</UIOption><UIOption value="locomo">LoCoMo</UIOption><UIOption value="beam">BEAM</UIOption></UISelect><small>{benchmarkCopy[benchmarkFamily].detail}</small></label><label>Local benchmark JSON<UIInput aria-label="Local benchmark JSON" type="file" accept="application/json,.json" onChange={importBenchmark} /><small>{benchmarkFile}</small></label><label>Memory strategy<UISelect aria-label="Benchmark memory strategy" value={benchmarkStrategy} onChange={(event) => { setBenchmarkStrategy(event.target.value as MemoryStrategy); resetBenchmarkResults(); setError(''); }}><UIOption value="no_memory">Supply no memories</UIOption><UIOption value="full_context">Replay all retained memories</UIOption><UIOption value="weak_first_hit">First matching memory</UIOption><UIOption value="strong_rule_based">Prioritise requirements and updates</UIOption><UIOption value="strong_score_based">Rank memories by relevance</UIOption><UIOption value="scope_aware">Match the task and project</UIOption><UIOption value="temporal_importance">Consider time and importance</UIOption></UISelect><small>Runs use seed 42 and isolated in-memory records.</small></label></div><UICheckbox aria-label="Benchmark source authorisation" checked={benchmarkAuthorised} onChange={(event) => updateBenchmarkAuthorisation(event.target.checked)} className="consent">I am authorised to process this local source and comply with its licence, citation and privacy terms. Checking permits the browser to read the selected file and send it to this local Auditor for validation.</UICheckbox>{pendingBenchmarkFile && !benchmark && !benchmarkAuthorised && <p role="status">The selected file has not been read. Confirm authorisation above to validate it.</p>}<div className="research-actions"><UIButton type="button" className="secondary" disabled={benchmarkBusy || !benchmark || !benchmarkAuthorised} onClick={validateBenchmark}>{benchmarkBusy ? 'Working…' : 'Validate Benchmark Input'}</UIButton><UIButton type="submit" disabled={benchmarkBusy || !benchmark || !benchmarkAuthorised}>{benchmarkBusy ? 'Running local baseline…' : 'Run Local Baseline'}</UIButton></div></form>{benchmarkPreview && <BenchmarkPreview family={benchmarkFamily} report={benchmarkPreview} />}{benchmarkRun && <BenchmarkRunReport family={benchmarkFamily} run={benchmarkRun} />}
    </section>
    <section className="research-workspace" aria-labelledby="pilot-workspace-title"><h3 id="pilot-workspace-title">Double-Annotation Pilot</h3><p>Upload one de-identified package containing two independent label sets and adjudications. The analysis shows coverage, disagreement resolution, Cohen’s κ and formal-study readiness.</p><form onSubmit={analysePilot}><label className="pilot-upload">Pilot package JSON<UIInput key={researchFilesAuthorised ? "authorised" : "unauthorised"} aria-label="Pilot package JSON" disabled={!researchFilesAuthorised} type="file" accept="application/json,.json" onChange={importPilot} /><small>{pilotFile}</small></label><UIButton type="submit" disabled={pilotBusy || !pilotPackage}>{pilotBusy ? 'Analysing pilot…' : 'Analyse Pilot Package'}</UIButton></form>{pilotReport && <PilotReport report={pilotReport} />}</section>
    <section className="research-workspace" aria-labelledby="validity-workspace-title"><h3 id="validity-workspace-title">Auditor Validity Checks</h3><p>Validate a frozen human-label dataset, then optionally compare it against prediction data. These metrics evaluate the Auditor, not a benchmark target.</p><form onSubmit={validateResearch}><div className="research-upload-grid"><label>Annotation dataset JSON<UIInput key={researchFilesAuthorised ? "authorised" : "unauthorised"} aria-label="Annotation dataset JSON" disabled={!researchFilesAuthorised} type="file" accept="application/json,.json" onChange={importDataset} /><small>{datasetFile}</small></label><label>Prediction set JSON<UIInput key={researchFilesAuthorised ? "authorised" : "unauthorised"} aria-label="Prediction set JSON" disabled={!researchFilesAuthorised} type="file" accept="application/json,.json" onChange={importPredictions} /><small>{predictionFile}</small></label></div><UIButton type="submit" disabled={validityBusy || !dataset}>{validityBusy ? 'Validating research files…' : 'Validate Research Files'}</UIButton></form>{message && <p className="research-message" role="status">{message}</p>}{datasetReport && <DatasetReport report={datasetReport} />}{validityReport && <div className="validity-report"><h3>Auditor validity metrics</h3><p>Stage scores use decided predictions. The full-reference comparison below includes uncertain failures and leaves missing evidence unmeasured. Memory and relationship recall assumes the imported candidate inventory is complete.</p>{[ ["Question assessments", validityReport.test_assessment_coverage], ["Answer judgments", validityReport.evaluator_coverage] ].map(([label, raw]) => { const coverage = raw as import("../types/domain").PredictionCoverage | undefined; return coverage ? <p key={String(label)}>{String(label)}: {coverage.decided} / {coverage.expected} decided · {coverage.missing} missing · {coverage.abstained} uncertain</p> : null; })}<ResearchValidityChart report={validityReport} /><UIButton disabled={!validityReport.metric_version || !validityReport.annotation_fingerprint_sha256 || !validityReport.prediction_fingerprint_sha256} onClick={() => saveBlob(new Blob([JSON.stringify(validityReport, null, 2)], {type: 'application/json'}), 'auditor-validity-metrics.json')}>Download metrics & provenance</UIButton></div>}</section>
    {error && <UIAlert className="alert" role="alert">{error}</UIAlert>}
    <section className="research-workspace" aria-labelledby="formal-matrix-title">
      <h3 id="formal-matrix-title">{researchSource?'Research Comparison Matrix':'Synthetic Comparison Matrix'}</h3>
      <p>Create a separately labelled exploratory matrix for engineering checks, or select formal Experiment B to freeze its analysis plan. Formal B requires one fixed target model, paired Weak and Strong policies, a development split and at least three runs per condition. Every condition receives the same human-labelled test suite.</p>
      <p>Validate the dataset and download its review receipt. After reviewing that exact release, record the receipt’s dataset_fingerprint_sha256 in the pilot package.</p>
      {dataset && pilotPackage && !matchingPilotDataset && <p role="status">The pilot is not bound to the currently validated dataset. Creation remains unavailable until the reviewed release matches.</p>}
      <form onSubmit={createMatrix}>
        <div className="benchmark-controls-grid">
          <label>Target runtime<UISelect aria-label="Formal matrix target runtime" value={matrixProvider} onChange={(event) => { const provider = event.target.value as TargetProvider; setMatrixProvider(provider); setMatrixModel(provider === 'openrouter' ? 'openai/gpt-6-luna' : provider === 'ollama' ? 'qwen3:1.7b' : 'rule-based-target-ai'); if(freezeStudyDesign&&provider!=='rule_based'&&Number(repetitionsInput)<3)setRepetitionsInput('3'); }}><UIOption value="openrouter">OpenRouter</UIOption><UIOption value="ollama">Local Ollama</UIOption><UIOption value="rule_based">Deterministic rule-based baseline</UIOption></UISelect></label>
          <label>Target models<UITextArea aria-label="Formal matrix target model" value={matrixModel} onChange={(event) => setMatrixModel(event.target.value)} required rows={3} /><small>Enter one deployed model name per line. Models share the selected service; local models must already be installed.</small></label>
          <fieldset><legend>Memory strategies</legend>{(['no_memory', 'full_context', 'weak_first_hit', 'strong_rule_based', 'strong_score_based', 'scope_aware', 'temporal_importance'] as MemoryStrategy[]).map((strategy) => <UICheckbox checked={selectedStrategies.includes(strategy)} onChange={() => toggleStrategy(strategy)} key={strategy} className="consent">{memoryStrategyLabel(strategy)}</UICheckbox>)}</fieldset>
        </div>
        <p role="status">{conditionCount} conditions per scenario · {matrixModels.length} models × {selectedStrategies.length} strategies. Choose 2–8 conditions.</p>
        {freezeStudyDesign&&<p>Formal Experiment B uses one fixed target model with both Weak first-hit and Strong rule-based memory policies and at least three repeats per policy, including the deterministic baseline.</p>}
        {freezeStudyDesign&&!validFormalStudyConditions&&<p role="alert">Select exactly one model and include both required memory policies before saving the formal plan.</p>}
        <UICheckbox checked={checkDistinctHistories} onChange={event=>setCheckDistinctHistories(event.target.checked)} disabled={matrixBusy||matrixRunning||matrixRestoring}>Check for reused development histories</UICheckbox>{checkDistinctHistories&&<label>Development annotation dataset JSON<UIInput key={researchFilesAuthorised ? "authorised" : "unauthorised"} aria-label="Development annotation dataset JSON" type="file" accept="application/json,.json" disabled={!researchFilesAuthorised||matrixBusy||matrixRunning||matrixRestoring} onChange={importDevelopment}/><small>{developmentFile}</small></label>}<p>Checks whole conversation content across the two supplied datasets before saving the plan. Different names, dates or spacing cannot hide exact reuse. Paraphrases and independent authorship still require separate evidence.</p>
        <UICheckbox checked={freezeStudyDesign} disabled={matrixBusy||matrixRunning||matrixRestoring} onChange={event=>{setFreezeStudyDesign(event.target.checked);if(event.target.checked){setCheckDistinctHistories(true);if(Number(repetitionsInput)<3)setRepetitionsInput('3');}}}>Run as formal Experiment B with a frozen analysis plan</UICheckbox>{freezeStudyDesign&&<fieldset><legend>Planned analysis</legend><label>How were the formal scenes selected?<UITextArea aria-label="Formal scene selection rule" value={samplingRule} onChange={event=>setSamplingRule(event.target.value)} rows={3} maxLength={1000} disabled={matrixBusy||matrixRunning||matrixRestoring}/></label><small>20–1000 characters. Describe the source inventory and selection rule, including any exclusions.</small><label>Primary outcome<UISelect aria-label="Formal primary outcome" value={primaryOutcome} disabled={matrixBusy||matrixRunning||matrixRestoring} onChange={event=>setPrimaryOutcome(event.target.value)}>{[['overall_memory_health','Overall memory health'],['accuracy','Accuracy'],['freshness','Freshness'],['conflict_resolution','Conflict resolution'],['appropriate_use','Appropriate use']].map(([value,label])=><UIOption key={value} value={value}>{label}</UIOption>)}</UISelect></label><p>Planned unit: source history. Repeated answers are not independent scenes. Report unfinished runs and missing judgments without inventing scores.</p></fieldset>}
        <label>Runs per condition<UIInput type="text" inputMode="numeric" aria-label="Runs per condition" value={repetitionsInput} onChange={event=>setRepetitionsInput(event.target.value)} /></label>
        <p>{validRepetitions?`${conditionCount*Number(repetitionsInput)} planned runs per scenario.`:freezeStudyDesign?'Formal Experiment B requires 3–5 runs per condition, including local Ollama and the deterministic baseline.':'Choose a whole number from 1 to 5.'} Repeats use the same reviewed questions, settings and recorded seed. A model service may not reproduce answers exactly; repeats are not independent histories.</p>
        {!validModels && <p role="alert">Use distinct, non-empty model names of at most 100 characters.</p>}
        <fieldset><legend>Success criteria from the pilot</legend><p>Choose these percentages before collecting new results. Creation saves them with the server time; later edits require a new reviewed experiment.</p><div className="research-upload-grid">{successCriteriaFields.map(field=><label key={field.key}>{field.label}<UIInput type="text" inputMode="decimal" aria-label={field.label} value={criteriaInputs[field.key]} onChange={event=>setCriteriaInputs(current=>({...current,[field.key]:event.target.value}))} required /></label>)}</div></fieldset>
        {!validSuccessCriteria && <p role="status">Enter all four percentages from 0 to 100 to freeze the plan.</p>}
        {researchSource?<fieldset><legend>Permission for this research release</legend><label>Source permission receipt<UIInput key={researchFilesAuthorised ? "authorised" : "unauthorised"} aria-label="Source permission receipt JSON" type="file" accept="application/json,.json" disabled={!researchFilesAuthorised||matrixBusy||matrixRunning||matrixRestoring} onChange={importSourceRelease}/><small>{sourceReleaseFile}</small></label><p>The receipt must bind to this dataset and declare deidentification, research use and storage permission. Cloud targets also require cloud processing permission. Personal history used for product demonstrations is excluded. These declarations require a team review; the app cannot authenticate them.</p><UICheckbox aria-label="Research data confirmation" checked={researchConfirmed} onChange={event=>setResearchConfirmed(event.target.checked)}>I confirm that the reviewed release permits this research use and saving its deidentified histories on the audit server.</UICheckbox>{!freezeStudyDesign&&<p role="status">Select formal Experiment B to import a research release.</p>}</fieldset>:<UICheckbox aria-label="Synthetic data confirmation" checked={syntheticConfirmed} onChange={(event) => setSyntheticConfirmed(event.target.checked)} className="consent">I confirm that this is authorised synthetic data and may be materialised as operational audit records.</UICheckbox>}
        <UIButton type="submit" disabled={matrixBusy || matrixRunning || matrixRestoring || !dataset || !pilotPackage || !matchingPilotDataset || !pilotReport?.ready_for_formal_evaluation || !sourceConfirmed || !validModels || !validSuccessCriteria || (checkDistinctHistories&&!developmentDataset) || (freezeStudyDesign&&(!validStudyDesign||!validFormalStudyConditions)) || !validRepetitions || conditionCount < 2 || conditionCount > 8}>{matrixBusy ? 'Creating matrix…' : freezeStudyDesign?'Create Formal Experiment B':'Create Exploratory Matrix'}</UIButton>
      </form>
      {matrix && <div className="research-report" role="status"><h3>{matrix.acceptance_protocol?.study_mode==='formal_experiment_b'?'Formal Experiment B matrix created':'Exploratory synthetic matrix created'}</h3><p><b>{matrix.scenario_count}</b> scenarios × <b>{matrix.condition_count}</b> conditions × <b>{matrix.repetition_count??1}</b> runs per condition = <b>{matrix.total_audit_runs}</b> runs.</p><p>{matrix.acceptance_protocol?.study_mode==='formal_experiment_b'?'Frozen formal plan':'Exploratory engineering check'} · {releaseLabel(matrix.dataset_version)}. Source files and human labels are not stored in this browser plan.</p>{matrix.acceptance_protocol ? <UIPanel><UISummary>Saved success criteria</UISummary><p>Saved before these runs: {new Date(matrix.acceptance_protocol.frozen_at).toLocaleString()}</p><UITable><thead><tr><th>Measure</th><th>Required percentage</th></tr></thead><tbody>{successCriteriaFields.map(field=><tr key={field.key}><th scope="row">{field.label}</th><td>{matrix.acceptance_protocol!.criteria[field.key]}%</td></tr>)}</tbody></UITable><p>{matrix.acceptance_protocol.distinct_history_check==='no_normalized_history_overlap'?'Development overlap check: no matching normalized histories in the supplied datasets.':'Development overlap check: not recorded for this plan.'}</p>{matrix.acceptance_protocol.study_design?<UIPanel><UISummary>Saved analysis plan</UISummary><p>Scene selection: {matrix.acceptance_protocol.study_design.sampling_rule}</p><p>Primary outcome: {humanise(matrix.acceptance_protocol.study_design.primary_outcome)}. Planned unit: source history. Missing results remain unmeasured.</p></UIPanel>:<p>Analysis plan: not recorded. Exploratory runs do not establish a predeclared formal study.</p>}<p>Frozen criteria do not verify independent labels or that earlier results were unseen.</p></UIPanel> : <p>Success criteria: Not recorded for this saved plan. Prepare a new reviewed experiment before collecting formal results.</p>}<p role="status">{matrixCompleted === null ? 'Continue to verify saved progress.' : `${matrixCompleted} / ${matrix.total_audit_runs} runs verified complete.`}</p><UIButton type="button" disabled={matrixRunning || matrixBusy || matrixRestoring || !matrix.acceptance_protocol} onClick={runMatrix}>{matrixRunning ? 'Running experiments…' : `Run ${matrix.total_audit_runs} Experiments`}</UIButton></div>}
      <FormalStudySummary matrix={matrix} executionBusy={matrixRunning||matrixBusy||matrixRestoring}/>
      <FrozenThresholdCheck matrix={matrix} dataset={dataset} predictions={predictions} executionBusy={matrixRunning||matrixBusy} onRestorePending={pending=>{matrixOperation.current=pending;setMatrixRestoring(pending);}} onRestore={plan=>{setMatrix(plan);setMatrixCompleted(null);setMessage('Saved execution plan restored. Review its frozen criteria, then run the conditions when ready.');}} />
    </section>
  </section>;
}
