import { useState, type ChangeEvent, type FormEvent } from 'react';
import { api } from '../services/api';
import type { AnnotationImportReport, BinaryClassificationMetrics, LongMemEvalValidationResponse, ResearchValidityReport } from '../types/domain';

type JsonObject = Record<string, unknown>;
type BenchmarkPayload = JsonObject | JsonObject[];

function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

async function parseJsonFile(file: File): Promise<unknown> {
  try { return JSON.parse(await file.text()); }
  catch { throw new Error(`“${file.name}” is not valid JSON.`); }
}

function displayMetric(value: number | null) {
  return value === null ? 'Not measured' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

function MetricCard({ title, metrics }: { title: string; metrics: BinaryClassificationMetrics }) {
  return <article className="validity-card">
    <h3>{title}</h3>
    <div className="validity-values"><span><small>Precision</small><b>{displayMetric(metrics.precision)}</b></span><span><small>Recall</small><b>{displayMetric(metrics.recall)}</b></span><span><small>F1</small><b>{displayMetric(metrics.f1)}</b></span><span><small>Cohen’s κ</small><b>{metrics.cohens_kappa === null ? 'Not measured' : metrics.cohens_kappa.toFixed(2)}</b></span></div>
    <p><small>{metrics.labelled_cases} labelled cases · Accuracy {displayMetric(metrics.accuracy)} · False-positive rate {displayMetric(metrics.false_positive_rate)}</small></p>
  </article>;
}

function DatasetReport({ report }: { report: AnnotationImportReport }) {
  return <div className="research-report" role="status"><h3>Annotation dataset validated</h3><p><b>{report.dataset_id}</b> · version {report.dataset_version} · {report.validation_status}</p><p className="fingerprint"><small>SHA-256 fingerprint</small><code>{report.fingerprint_sha256}</code></p><div className="research-counts"><span>{report.conversations} conversations</span><span>{report.gold_memories} gold memories</span><span>{report.gold_relationships} relationships</span><span>{report.gold_tests} tests</span><span>{report.gold_evaluations} evaluations</span></div></div>;
}

function BenchmarkReport({ benchmark }: { benchmark: LongMemEvalValidationResponse }) {
  return <div className="research-report"><h3>LongMemEval-compatible input validated</h3><p><b>{benchmark.report.cases_imported}</b> cases · {benchmark.report.source_format} · adapter {benchmark.report.adapter_version}</p><p>{benchmark.report.notice}</p>{benchmark.report.dimension_hints.length > 0 && <p><small>Dimension hints: {benchmark.report.dimension_hints.join(', ')}</small></p>}</div>;
}

/**
 * Ephemeral research import panel. Files stay in the browser apart from the
 * validation request; the backend explicitly does not persist the payload.
 */
export function ResearchValidation() {
  const [dataset, setDataset] = useState<JsonObject | null>(null);
  const [predictions, setPredictions] = useState<JsonObject | null>(null);
  const [benchmark, setBenchmark] = useState<BenchmarkPayload | null>(null);
  const [datasetFile, setDatasetFile] = useState('No file selected');
  const [predictionFile, setPredictionFile] = useState('No file selected');
  const [benchmarkFile, setBenchmarkFile] = useState('No file selected');
  const [datasetReport, setDatasetReport] = useState<AnnotationImportReport | null>(null);
  const [validityReport, setValidityReport] = useState<ResearchValidityReport | null>(null);
  const [benchmarkReport, setBenchmarkReport] = useState<LongMemEvalValidationResponse | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const importDataset = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; if (!file) return;
    try {
      const parsed = await parseJsonFile(file);
      if (!isObject(parsed)) throw new Error('The annotation dataset must be a JSON object.');
      setDataset(parsed); setDatasetFile(file.name); setDatasetReport(null); setValidityReport(null); setError('');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The annotation dataset could not be read.'); }
  };
  const importPredictions = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; if (!file) return;
    try {
      const parsed = await parseJsonFile(file);
      if (!isObject(parsed)) throw new Error('The prediction set must be a JSON object.');
      setPredictions(parsed); setPredictionFile(file.name); setValidityReport(null); setError('');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The prediction set could not be read.'); }
  };
  const importBenchmark = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; if (!file) return;
    try {
      const parsed = await parseJsonFile(file);
      if (!isObject(parsed) && !(Array.isArray(parsed) && parsed.every(isObject))) throw new Error('The benchmark file must contain a JSON object or array of objects.');
      setBenchmark(parsed); setBenchmarkFile(file.name); setBenchmarkReport(null); setError('');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The benchmark file could not be read.'); }
  };
  const validate = async (event: FormEvent) => {
    event.preventDefault();
    if (!dataset) { setError('Select an annotation dataset before validation.'); return; }
    setBusy(true); setError(''); setMessage('');
    try {
      const annotation = await api.validateAnnotationDataset(dataset);
      const [validity, benchmarkResult] = await Promise.all([
        predictions ? api.researchValidity(dataset, predictions) : Promise.resolve(null),
        benchmark ? api.validateLongMemEval(benchmark) : Promise.resolve(null),
      ]);
      setDatasetReport(annotation); setValidityReport(validity); setBenchmarkReport(benchmarkResult);
      setMessage(predictions ? 'Research files were validated. Metrics use the imported frozen labels and predictions.' : 'Annotation dataset was validated. Add a prediction set to calculate validity metrics.');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Research validation could not be completed.'); }
    finally { setBusy(false); }
  };

  return <section className="research-validation" aria-labelledby="research-validation-title"><h2 id="research-validation-title">Research Validation</h2><p>Validate local, de-identified research artefacts without adding them to operational audit history. Annotation and prediction files are required for Auditor validity metrics; LongMemEval-compatible input is optional.</p><form onSubmit={validate}><div className="research-upload-grid"><label>Annotation dataset JSON<input aria-label="Annotation dataset JSON" type="file" accept="application/json,.json" onChange={importDataset} /><small>{datasetFile}</small></label><label>Prediction set JSON<input aria-label="Prediction set JSON" type="file" accept="application/json,.json" onChange={importPredictions} /><small>{predictionFile}</small></label><label>Optional LongMemEval-compatible JSON<input aria-label="LongMemEval-compatible JSON" type="file" accept="application/json,.json" onChange={importBenchmark} /><small>{benchmarkFile}</small></label></div><button type="submit" disabled={busy || !dataset}>{busy ? 'Validating research files…' : 'Validate Research Files'}</button></form>{error && <p className="alert" role="alert">{error}</p>}{message && <p className="research-message" role="status">{message}</p>}{datasetReport && <DatasetReport report={datasetReport} />}{validityReport && <div className="validity-report"><h3>Auditor validity metrics</h3><p>Positive class: a detected target-AI failure where applicable. “Not measured” means the imported labels did not provide a valid denominator.</p><div className="validity-grid"><MetricCard title="Memory Extraction" metrics={validityReport.extraction} /><MetricCard title="Relationship Classification" metrics={validityReport.relationship} /><MetricCard title="Test Validity" metrics={validityReport.test_validity} /><MetricCard title="Behaviour Evaluator" metrics={validityReport.evaluator} /></div></div>}{benchmarkReport && <BenchmarkReport benchmark={benchmarkReport} />}</section>;
}
