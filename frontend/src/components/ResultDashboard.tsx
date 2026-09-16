import type { AuditResult, Dimension, DimensionScores, FailureDetail } from '../types/domain';
import { EvaluationReview } from './EvaluationReview';

const labels: Record<Dimension, string> = {
  accuracy: 'Accuracy', freshness: 'Freshness', conflict_resolution: 'Conflict Resolution', appropriate_use: 'Appropriate Use',
};

function formatPercentage(value: number | null) {
  return value === null ? 'Not tested' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

function csvCell(value: unknown) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`;
}

/** Build a portable report locally; audit results are never uploaded to export it. */
export function buildAuditResultCsv(result: AuditResult) {
  const header = [
    'Record type', 'Run ID', 'Dimension', 'Test ID', 'Outcome', 'Overall score (%)',
    'Passed tests', 'Total tests', 'Failure reason', 'Prompt', 'Expected behaviour',
    'Target response', 'Evidence memory IDs', 'Evidence memories', 'Evaluator',
  ];
  const rows: unknown[][] = [[
    'Audit summary', result.run_id, '', '', '', result.overall_score ?? 'Not tested',
    result.tests_passed, result.tests_total, '', '', '', '', '', '', '',
  ]];

  result.dimensions.forEach((dimension) => rows.push([
    'Dimension summary', result.run_id, labels[dimension.dimension], '', '',
    dimension.percentage ?? 'Not tested', dimension.passed, dimension.total,
    '', '', '', '', '', '', '',
  ]));

  result.failures.forEach((failure) => rows.push([
    'Failure detail', result.run_id, labels[failure.test.dimension], failure.test.test_id,
    'Failed', '', '', '', failure.evaluation.reason, failure.test.prompt,
    failure.test.expected_behavior, failure.response.response_text,
    failure.evaluation.evidence_memory_ids.join('; '),
    failure.evidence.map((memory) => `${memory.memory_id}: ${memory.canonical_value}`).join(' | '),
    failure.evaluation.evaluator,
  ]));

  return [header, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n');
}

function downloadAuditResultCsv(result: AuditResult) {
  const csv = buildAuditResultCsv(result);
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `memory-health-audit-${result.run_id}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function overallAssessment(score: number | null, coveredDimensions: number) {
  if (score === null) return 'No overall score is available until at least one completed test has been evaluated.';
  const reliability = score >= 85 ? 'consistently reliable' : score >= 65 ? 'partly reliable' : 'needs attention';
  return `Memory behaviour was ${reliability} across ${coveredDimensions} tested ${coveredDimensions === 1 ? 'dimension' : 'dimensions'}.`;
}

function DimensionCard({ score }: { score: DimensionScores }) {
  const isMeasured = score.percentage !== null;
  return <article className="dimension"><h3>{labels[score.dimension]}</h3><strong>{formatPercentage(score.percentage)}</strong><span>{isMeasured ? `${score.passed} of ${score.total} tests passed` : 'No completed tests in this dimension'}</span></article>;
}

function FailureEvidence({ failure }: { failure: FailureDetail }) {
  if (!failure.evidence.length) return <p className="empty evidence-empty">No traceable ground-truth evidence was returned for this failure.</p>;
  return <ul className="evidence-list">{failure.evidence.map((memory) => <li key={memory.memory_id}><b>{memory.memory_id}</b><span>{memory.canonical_value}</span></li>)}</ul>;
}

function FailureCard({ failure }: { failure: FailureDetail }) {
  const label = labels[failure.test.dimension];
  return <details className="failure-card"><summary><b>{label}</b><span>Failure: {failure.evaluation.reason}</span></summary><div className="failure-content"><p><b>Why this failed</b><br />{failure.evaluation.reason}</p><p><b>Behavioural test</b><br />{failure.test.prompt}</p><p><b>Expected behaviour</b><br />{failure.test.expected_behavior}</p><p><b>Target AI response</b><br />{failure.response.response_text || 'The target AI returned no text.'}</p><p><b>Ground-truth evidence</b></p><FailureEvidence failure={failure} /><p className="failure-meta">Evaluator: {failure.evaluation.evaluator} · Test ID: {failure.test.test_id}</p></div></details>;
}

export function ResultDashboard({ result }: { result: AuditResult }) {
  const measuredDimensions = result.dimensions.filter((dimension) => dimension.percentage !== null).length;
  const hasCompletedTests = result.tests_total > 0;
  return <section className="result-dashboard" aria-label="Memory Health report details"><div className="report-hero"><p>OVERALL MEMORY HEALTH</p><h2>{formatPercentage(result.overall_score)}</h2><span>{hasCompletedTests ? `${result.tests_passed} of ${result.tests_total} tests passed` : 'No completed tests are available for scoring'}</span></div><div className="failure-heading"><div><h2>Results at a glance</h2><p>{overallAssessment(result.overall_score, measuredDimensions)}</p></div><button type="button" className="secondary" onClick={() => downloadAuditResultCsv(result)}>Download CSV</button></div><p className="report-coverage">Score coverage: {measuredDimensions} of {result.dimensions.length} Memory Health dimensions were tested. Untested dimensions are excluded from the macro-average.</p><div className="dimension-grid">{result.dimensions.map((dimension) => <DimensionCard key={dimension.dimension} score={dimension} />)}</div><div className="failure-heading"><div><h2>Detected Memory Failures</h2><p>Open a failure to inspect the test, target response, and supporting ground truth.</p></div><span className="failure-count">{result.failures.length} detected</span></div>{result.failures.length === 0 ? <p className="empty">No failures were detected in the completed tests.</p> : <div className="failure-list">{result.failures.map((failure) => <FailureCard key={failure.failure_id} failure={failure} />)}</div>}<EvaluationReview runId={result.run_id} /></section>;
}
