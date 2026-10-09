import { saveBlob } from '../services/download';
import { ValidationWorkbench } from "./ValidationWorkbench";
import { UICard, UIAlert } from './ui';
import { UIPanel, UISummary, UIButton } from './ui';
import { lazy, Suspense } from 'react';
import type { AuditResult, Dimension, DimensionScores, FailureDetail, RetrievalQualityScores } from '../types/domain';
import { EvaluationReview } from './EvaluationReview';
import { assessmentLabel, friendlyText } from '../services/display';

const ScoreRadarChart = lazy(() => import('./ResultVisualizations').then((module) => ({ default: module.ScoreRadarChart })));

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
    'Audit summary', result.run_id, '', '', '', result.overall_score ?? ((result.uncertain_count ?? 0) > 0 ? 'Awaiting review' : 'Not tested'),
    result.tests_passed, result.tests_total, '', '', '', '', '', '', '',
  ]];

  result.dimensions.forEach((dimension) => rows.push([
    'Dimension summary', result.run_id, labels[dimension.dimension], '', '',
    dimension.percentage ?? ((dimension.uncertain_count ?? 0) > 0 ? 'Awaiting review' : 'Not tested'), dimension.passed, dimension.total,
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
  saveBlob(new Blob([csv], { type: 'text/csv;charset=utf-8' }), 'memory-health-report.csv');
}

function overallAssessment(score: number | null, coveredDimensions: number) {
  if (score === null) return 'No overall score is available until at least one completed test has been evaluated.';
  return `Automatically assessed average: ${score.toFixed(1)}% across ${coveredDimensions} tested ${coveredDimensions === 1 ? 'dimension' : 'dimensions'}. Independent review is needed before drawing a reliability conclusion.`;
}

function AnswerOutcomes({ result }: { result: AuditResult }) {
  const uncertain = result.uncertain_count ?? 0;
  const failed = Math.max(0, result.tests_total - result.tests_passed);
  const completed = result.tests_total + uncertain;
  const outcomes = [
    { label: 'Passed', count: result.tests_passed, className: 'passed' },
    { label: 'Failed', count: failed, className: 'failed' },
    { label: 'Awaiting review', count: uncertain, className: 'uncertain' },
  ];
  return <section className="answer-outcomes" aria-label="Answer outcomes">
    <h3>{completed} completed {completed === 1 ? 'answer' : 'answers'}</h3>
    <div className="outcome-counts">{outcomes.map(outcome => <span key={outcome.className} className={outcome.className}><b>{outcome.count}</b> {outcome.label}</span>)}</div>
    {completed > 0 && <div className="outcome-bar" role="img" aria-label={`${result.tests_passed} passed, ${failed} failed, ${uncertain} awaiting review out of ${completed} completed answers`}>{outcomes.filter(outcome => outcome.count > 0).map(outcome => <span key={outcome.className} className={outcome.className} style={{ width: `${outcome.count / completed * 100}%` }}/>)}</div>}
    <p>{completed === 0 ? 'No assessed answers are available.' : uncertain > 0 ? 'The percentage above uses decided assessments only. Awaiting review does not mean passed.' : 'These are automated assessments; independent review is required for a reliability claim.'}</p>
  </section>;
}

function DimensionCard({ score }: { score: DimensionScores }) {
  const isMeasured = score.percentage !== null;
  return <UICard className="dimension"><h3>{labels[score.dimension]}</h3><strong>{!isMeasured && (score.uncertain_count ?? 0) > 0 ? 'Awaiting review' : formatPercentage(score.percentage)}</strong><span>{isMeasured ? `${score.passed} of ${score.total} tests passed` : (score.uncertain_count ?? 0) > 0 ? 'Completed answers need independent review' : 'No completed tests in this dimension'}</span>{(score.uncertain_count ?? 0) > 0 && <small>{score.uncertain_count} uncertain assessment(s) excluded from scoring</small>}</UICard>;
}

const retrievalLabels: Array<[keyof RetrievalQualityScores, string, string]> = [
  ['evidence_recall_at_k', 'Evidence recall @ k', 'Required source evidence retrieved'],
  ['evidence_precision_at_k', 'Evidence precision @ k', 'Retrieved source evidence that was relevant'],
  ['update_evidence_recall', 'Update evidence recall', 'Freshness-test evidence retrieved'],
  ['conflict_evidence_coverage', 'Conflict evidence coverage', 'Conflict-test evidence retrieved'],
  ['unnecessary_memory_retrieval_rate', 'Unnecessary retrieval', 'Lower is better'],
];

function RetrievalQuality({ scores }: { scores?: RetrievalQualityScores }) {
  if (!scores) return <section className="retrieval-quality"><h2>Retrieval Evidence Quality</h2><p className="empty">No retrieval trace with source evidence is available for these completed tests.</p></section>;
  const excludedNotice = (scores.unlinked_attempts_excluded ?? 0) > 0 ? <p className="trace-note">{scores.unlinked_attempts_excluded} retrieval attempts without a linked saved answer are excluded. Their input and outcome remain unverified.</p> : null;
  if (!scores.tests_measured) return <section className="retrieval-quality"><h2>Retrieval Evidence Quality</h2><p className="empty">No retrieval trace with source evidence is available for these completed tests.</p>{excludedNotice}</section>;
  return <section className="retrieval-quality" aria-label="Retrieval evidence quality">
    <div><h2>Retrieval Evidence Quality</h2><p className="trace-note">These proxies match source messages and normalised fact text in retrieved records. Reworded or bundled source evidence can score lower despite containing the required information. They do not measure causal model use or the final supplied context.</p></div>
    {excludedNotice}
    <div className="retrieval-grid">{retrievalLabels.map(([key, label, note]) => <UICard key={key} className="retrieval-card"><span>{label}</span><strong>{formatPercentage(scores[key] as number | null)}</strong><small>{note}</small></UICard>)}</div>
  </section>;
}

function FailureEvidence({ failure }: { failure: FailureDetail }) {
  return <>{!failure.evidence.length ? <p className="empty evidence-empty">No traceable ground-truth evidence was returned for this failure.</p> : <ul className="evidence-list">{failure.evidence.map((memory, index) => <li key={memory.memory_id}><b>Supporting memory {index + 1}</b><span>{memory.canonical_value}</span></li>)}</ul>}<p><b>Original conversation evidence</b></p>{failure.source_statements?.length ? <ul className="evidence-list">{failure.source_statements.map((source,index)=><li key={index}><b>Source {index+1} · {source.role} · {new Date(source.timestamp).toLocaleString()}</b><span>{source.content}</span></li>)}</ul> : <p className="empty">Original source statements are unavailable for this failure. Review its trace before relying on the diagnosis.</p>}</>;
}

function FailureCard({ failure }: { failure: FailureDetail }) {
  const label = labels[failure.test.dimension];
  return <UIPanel className="failure-card"><UISummary><b>{label}</b><span>Failure: {friendlyText(failure.evaluation.reason)}</span></UISummary><div className="failure-content"><p><b>Why this failed</b><br />{friendlyText(failure.evaluation.reason)}</p><p><b>Behavioural test</b><br />{failure.test.prompt}</p><p><b>Expected behaviour</b><br />{failure.test.expected_behavior}</p><p><b>Target AI response</b><br />{failure.response.response_text || 'The target AI returned no text.'}</p><p><b>Ground-truth evidence</b></p><FailureEvidence failure={failure} /><p className="failure-meta">Evaluator: {assessmentLabel(failure.evaluation.evaluator)}</p></div></UIPanel>;
}

export function ResultDashboard({ result }: { result: AuditResult }) {
  const measuredDimensions = result.dimensions.filter((dimension) => dimension.percentage !== null).length;
  const hasCompletedTests = result.tests_total > 0;
  return <section className="result-dashboard" aria-label="Memory Health report details"><div className="report-hero"><p>{measuredDimensions === 4 ? 'OVERALL MEMORY HEALTH' : 'TESTED ABILITY AVERAGE'}</p><h2>{result.overall_score === null && (result.uncertain_count ?? 0) > 0 ? 'Unscored' : formatPercentage(result.overall_score)}</h2><span>{hasCompletedTests ? `${result.tests_passed} of ${result.tests_total} tests passed` : (result.uncertain_count ?? 0) > 0 ? `${result.uncertain_count} completed answers await review` : 'No completed tests are available for scoring'}</span></div><AnswerOutcomes result={result}/><div className="failure-heading"><div><h2>Results at a glance</h2><p>{result.overall_score === null && (result.uncertain_count ?? 0) > 0 ? 'No definitive score is available while completed answers await review.' : overallAssessment(result.overall_score, measuredDimensions)}</p></div><UIButton type="button" className="secondary" onClick={() => downloadAuditResultCsv(result)}>Download CSV</UIButton></div><p>{result.uncertain_count??0} uncertain assessments are excluded from the score. Scores are automated until calibrated against independent human labels.</p><p className="report-coverage">Score coverage: {measuredDimensions} of {result.dimensions.length} Memory Health dimensions have definitive scores. Untested dimensions are excluded from the macro-average. Uncertain assessments also stay outside the score. {measuredDimensions < 4 && 'A formal overall Memory Health score requires all four dimensions.'}</p>{result.evaluation_warnings?.map((warning) => <UIAlert className="alert" role="status" key={warning}>{friendlyText(warning)}</UIAlert>)}<div className="dimension-grid">{result.dimensions.map((dimension) => <DimensionCard key={dimension.dimension} score={dimension} />)}</div><Suspense fallback={<p className="chart-loading" role="status">Loading Memory Health profile…</p>}><ScoreRadarChart result={result} /></Suspense><RetrievalQuality scores={result.retrieval_quality} /><div className="failure-heading"><div><h2>Answers marked as failed</h2><p>A failed answer can reflect the test setup. Inspect diagnosis before attributing a memory defect.</p></div><span className="failure-count">{result.failures.length} flagged</span></div>{result.failures.length === 0 ? <p className="empty">No completed answers were marked as failed.</p> : <div className="failure-list">{result.failures.map((failure) => <FailureCard key={failure.failure_id} failure={failure} />)}</div>}<EvaluationReview runId={result.run_id} /><ValidationWorkbench runId={result.run_id}/></section>;
}
