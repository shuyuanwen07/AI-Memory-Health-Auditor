import { SavedAnswerReassessment } from './SavedAnswerReassessment';
import { saveBlob } from '../services/download';
import { useState } from 'react';
import { spreadsheetCsvCell } from '../services/csvExport';
import { ValidationWorkbench } from "./ValidationWorkbench";
import { UICard, UIAlert } from './ui';
import { UIPanel, UISummary, UIButton } from './ui';
import type { AssessmentDetail, AuditAnswerDetail, AuditResult, AuditRun, Dimension, DimensionScores, FailureDetail, RetrievalQualityScores } from '../types/domain';
import { EvaluationReview } from './EvaluationReview';
import { assessmentLabel, friendlyText } from '../services/display';


const labels: Record<Dimension, string> = {
  accuracy: 'Accuracy', freshness: 'Freshness', conflict_resolution: 'Conflict Resolution', appropriate_use: 'Appropriate Use',
};

function formatPercentage(value: number | null) {
  return value === null ? 'Not tested' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

type ExportMemoryProfile = {
  label: string; version: number; max_retrieved_records: number; context_character_budget: number;
  isolate_project_scope: boolean; prefer_current_state: boolean; output_token_limit?: number | null;
  identity_analysis?: 'off' | 'evidence_links'; identity_analysis_output_token_limit?: number;
  reasoning_effort?: 'low' | 'medium'; identity_analysis_reasoning_effort?: 'low';
  identity_analysis_failure_policy?: 'fail_closed' | 'continue_without_advisory';
  answer_validation?: 'off' | 'source_grounding'; answer_validation_output_token_limit?: number;
  answer_validation_reasoning_effort?: 'low' | 'medium';
};
type AuditExportConfiguration = {
  target_provider: string | null; configured_target_model: string | null; reported_target_models: string[];
  target_configuration: string | null; memory_strategy: string | null; temperature: number | null;
  random_seed: number | null; test_budget: number | null; prompt_template_version: string | null;
  memory_maintenance_policy: string | null; target_memory_capacity: number | null;
  target_memory_writer: string | null; target_memory_writer_version: string | null;
  target_system_adapter: string | null; target_system_adapter_version: string | null;
  retrieval_mode: string | null; retrieval_provider: string | null; retrieval_model: string | null;
  question_generation_provider: string | null; question_generation_model: string | null;
  semantic_review_provider: string | null; semantic_review_model: string | null;
  answer_assessment_provider: string | null; answer_assessment_model: string | null;
  target_memory_profile: ExportMemoryProfile | null;
};

function savedAnswers(result: AuditResult): AuditAnswerDetail[] {
  if (result.answers?.length) return result.answers;
  return [
    ...result.failures.map((failure) => ({
      test: failure.test, response: failure.response, evaluation: failure.evaluation,
      outcome: 'fail' as const, reason: failure.evaluation.reason,
      evidence: failure.evidence, source_statements: failure.source_statements,
    })),
    ...(result.uncertain_answers ?? []).map((answer) => ({
      test: answer.test, response: answer.response, evaluation: answer.evaluation,
      outcome: 'uncertain' as const, reason: answer.evaluation.reason,
      evidence: answer.evidence, source_statements: answer.source_statements,
    })),
  ];
}

function uncertainAnswerDetails(result: AuditResult): AssessmentDetail[] {
  if (result.uncertain_answers?.length) return result.uncertain_answers;
  return (result.answers ?? []).flatMap((answer) => answer.outcome === 'uncertain' && answer.evaluation
    ? [{test:answer.test,response:answer.response,evaluation:answer.evaluation,evidence:answer.evidence,source_statements:answer.source_statements}]
    : []);
}

function safeMemoryProfile(profile?: ExportMemoryProfile | null): ExportMemoryProfile | null {
  if (!profile) return null;
  return {
    label: profile.label,
    version: profile.version,
    max_retrieved_records: profile.max_retrieved_records,
    context_character_budget: profile.context_character_budget,
    isolate_project_scope: profile.isolate_project_scope,
    prefer_current_state: profile.prefer_current_state,
    output_token_limit: profile.output_token_limit,
    identity_analysis: profile.identity_analysis,
    identity_analysis_output_token_limit: profile.identity_analysis_output_token_limit,
    ...(profile.reasoning_effort!==undefined?{reasoning_effort:profile.reasoning_effort}:{}),
    ...(profile.identity_analysis_reasoning_effort!==undefined?{identity_analysis_reasoning_effort:profile.identity_analysis_reasoning_effort}:{}),
    ...(profile.identity_analysis_failure_policy!==undefined?{identity_analysis_failure_policy:profile.identity_analysis_failure_policy}:{}),
    ...(profile.answer_validation!==undefined?{answer_validation:profile.answer_validation}:{}),
    ...(profile.answer_validation_output_token_limit!==undefined?{answer_validation_output_token_limit:profile.answer_validation_output_token_limit}:{}),
    ...(profile.answer_validation_reasoning_effort!==undefined?{answer_validation_reasoning_effort:profile.answer_validation_reasoning_effort}:{}),
  };
}

function auditExportConfiguration(result: AuditResult, run?: AuditRun): AuditExportConfiguration {
  const reportedTargetModels = [...new Set(savedAnswers(result)
    .map((answer) => answer.response.execution_metadata?.reported_model)
    .filter((model): model is string => Boolean(model)))];
  const profile = run?.target_memory_profile ?? result.reproducibility?.target_memory_profile;
  return {
    target_provider: run?.provider ?? null,
    configured_target_model: run?.model ?? null,
    reported_target_models: reportedTargetModels,
    target_configuration: run?.target_configuration ?? null,
    memory_strategy: run?.memory_strategy ?? null,
    temperature: run?.temperature ?? null,
    random_seed: run?.random_seed ?? null,
    test_budget: run?.test_budget ?? null,
    prompt_template_version: run?.prompt_template_version ?? null,
    memory_maintenance_policy: run?.memory_maintenance_policy ?? null,
    target_memory_capacity: run?.target_memory_capacity ?? null,
    target_memory_writer: run?.target_memory_writer ?? null,
    target_memory_writer_version: run?.target_memory_writer_version ?? null,
    target_system_adapter: run?.target_system_adapter ?? null,
    target_system_adapter_version: run?.target_system_adapter_version ?? null,
    retrieval_mode: run?.retrieval_mode ?? null,
    retrieval_provider: run?.retrieval_provider ?? null,
    retrieval_model: run?.retrieval_model ?? null,
    question_generation_provider: run?.pipeline_provider ?? null,
    question_generation_model: run?.pipeline_model ?? null,
    semantic_review_provider: run?.semantic_review_provider ?? null,
    semantic_review_model: run?.semantic_review_model ?? null,
    answer_assessment_provider: run?.evaluator_provider ?? null,
    answer_assessment_model: run?.evaluator_model ?? null,
    target_memory_profile: safeMemoryProfile(profile),
  };
}

const configurationColumns: Array<[keyof AuditExportConfiguration, string]> = [
  ['target_provider','Configured target provider'], ['configured_target_model','Configured target model'],
  ['reported_target_models','Reported target model(s)'], ['target_configuration','Target configuration'],
  ['memory_strategy','Memory strategy'], ['temperature','Temperature'], ['random_seed','Random seed'],
  ['test_budget','Test budget'], ['prompt_template_version','Target prompt template version'],
  ['memory_maintenance_policy','Memory maintenance policy'], ['target_memory_capacity','Target memory capacity'],
  ['target_memory_writer','Target memory writer'], ['target_memory_writer_version','Target memory writer version'],
  ['target_system_adapter','Target system adapter'], ['target_system_adapter_version','Target system adapter version'],
  ['retrieval_mode','Retrieval mode'], ['retrieval_provider','Retrieval provider'], ['retrieval_model','Retrieval model'],
  ['question_generation_provider','Question generation provider'], ['question_generation_model','Question generation model'],
  ['semantic_review_provider','Semantic review provider'], ['semantic_review_model','Semantic review model'],
  ['answer_assessment_provider','Answer assessment provider'], ['answer_assessment_model','Answer assessment model'],
  ['target_memory_profile','Target memory profile (sanitized)'],
];

function exportCell(value: unknown): string {
  if (value == null || value === '') return 'Not recorded';
  if (Array.isArray(value)) return value.length ? value.join('; ') : 'Not reported';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

/** Build a portable report locally; audit results are never uploaded to export it. */
export function buildAuditResultCsv(result: AuditResult, run?: AuditRun) {
  const baseHeader = [
    'Record type', 'Run ID', 'Dimension', 'Test ID', 'Response ID', 'Evaluation ID', 'Outcome',
    'Overall score (%)', 'Passed tests', 'Total tests', 'Assessment reason', 'Prompt',
    'Expected behaviour', 'Target response', 'Evaluator-cited memory IDs', 'Linked reference memories',
    'Original source statements', 'Evaluator', 'Awaiting review count', 'Excluded evidence count',
    'Expected questions',
  ];
  const header = [...baseHeader, ...configurationColumns.map(([,label]) => label)];
  const rows: unknown[][] = [[
    'Audit summary', result.run_id, '', '', '', '', '', result.overall_score ?? ((result.excluded_evidence_count ?? 0) > 0 ? 'Evidence unavailable' : (result.uncertain_count ?? 0) > 0 ? 'Awaiting review' : 'Not tested'),
    result.tests_passed, result.tests_total, '', '', '', '', '', '', '', '',
    result.uncertain_count ?? 0, result.excluded_evidence_count ?? 0, result.expected_tests ?? '',
  ]];

  if((result.excluded_evidence_count??0)>0) rows.push([
    'Evidence coverage',result.run_id,'','','','','','','',result.expected_tests??'',
    `${result.evaluated_count??result.tests_total+(result.uncertain_count??0)} usable question assessments; ${result.excluded_evidence_count} excluded for missing or inconsistent evidence.`,
    '','','','','','','','','',result.expected_tests??'',
  ]);
  result.dimensions.forEach((dimension) => rows.push([
    'Dimension summary', result.run_id, labels[dimension.dimension], '', '', '', '',
    dimension.percentage ?? ((dimension.excluded_evidence_count??0)>0?'Evidence unavailable':(dimension.uncertain_count ?? 0) > 0 ? 'Awaiting review' : 'Not tested'), dimension.passed, dimension.total,
    '', '', '', '', '', '', '', '',
    dimension.uncertain_count ?? 0, dimension.excluded_evidence_count ?? 0, dimension.expected_tests ?? '',
  ]));

  const answers = savedAnswers(result);
  answers.forEach((answer) => {
    const recordType = answer.outcome === 'fail' ? 'Failure detail'
      : answer.outcome === 'uncertain' ? 'Review required'
        : answer.outcome === 'unassessed' ? 'Unassessed answer' : 'Answer detail';
    const outcome = answer.outcome === 'uncertain' ? 'Awaiting review'
      : answer.outcome === 'unassessed' ? 'Unassessed' : answer.outcome === 'pass' ? 'Passed' : 'Failed';
    rows.push([
      recordType, result.run_id, labels[answer.test.dimension], answer.test.test_id,
      answer.response.response_id, answer.evaluation?.evaluation_id ?? '', outcome,
      '', '', '', answer.reason ?? answer.evaluation?.reason ?? '', answer.test.prompt,
      answer.test.expected_behavior, answer.response.response_text,
      answer.evaluation?.evidence_memory_ids.join('; ') ?? '',
      answer.evidence.map((memory) => `${memory.memory_id}: ${memory.canonical_value}`).join(' | '),
      (answer.source_statements ?? []).map((source) => `${source.role} · ${source.timestamp}: ${source.content}`).join(' | '),
      answer.evaluation?.evaluator ?? '', answer.outcome === 'uncertain' ? 1 : 0,
      answer.outcome === 'unassessed' ? 1 : 0, '',
    ]);
  });

  rows.push(['Export format',result.run_id,'','','','','','','Formula-like text has a leading tab in this spreadsheet CSV. Original saved records are unchanged.']);
  const configuration = auditExportConfiguration(result, run);
  const configurationValues = configurationColumns.map(([key]) => exportCell(configuration[key]));
  const dataRows = rows.map((row) => [
    ...Array.from({length:baseHeader.length}, (_, index) => row[index] ?? ''),
    ...configurationValues,
  ]);
  return [header, ...dataRows].map((row) => row.map((value) => spreadsheetCsvCell(value)).join(',')).join('\r\n');
}

export function buildAuditResultJson(result: AuditResult, run?: AuditRun) {
  const exportedResult = {...result};
  if (result.reproducibility?.target_memory_profile) {
    exportedResult.reproducibility = {...result.reproducibility, target_memory_profile: undefined};
  }
  return {
    export_schema_version: 'memory-health-audit-export-v1',
    run_configuration: auditExportConfiguration(result, run),
    result: exportedResult,
  };
}

function downloadAuditResultCsv(result: AuditResult, run?: AuditRun) {
  const csv = buildAuditResultCsv(result, run);
  saveBlob(new Blob([csv], { type: 'text/csv;charset=utf-8' }), 'memory-health-report.csv');
}

function downloadAuditResultJson(result: AuditResult, run?: AuditRun) {
  saveBlob(new Blob([JSON.stringify(buildAuditResultJson(result, run), null, 2)], { type: 'application/json;charset=utf-8' }), `memory-health-report-${result.run_id}.json`);
}

function overallAssessment(score: number | null, coveredDimensions: number) {
  if (score === null) return 'No overall score is available until at least one completed test has been evaluated.';
  return `Average across ${coveredDimensions} tested ${coveredDimensions === 1 ? 'ability' : 'abilities'}. Automated results; independent review required.`;
}

function AnswerOutcomes({ result }: { result: AuditResult }) {
  const uncertain = result.uncertain_count ?? uncertainAnswerDetails(result).length;
  const failed = Math.max(0, result.tests_total - result.tests_passed);
  const unassessed = result.answers?.filter(answer => answer.outcome === 'unassessed').length ?? 0;
  const completed = result.tests_total + uncertain;
  const savedAnswers = completed + unassessed;
  const outcomes = [
    { label: 'Passed', count: result.tests_passed, className: 'passed' },
    { label: 'Failed', count: failed, className: 'failed' },
    { label: 'Awaiting review', count: uncertain, className: 'uncertain' },
    { label: 'Unassessed', count: unassessed, className: 'unassessed' },
  ];
  return <section className="answer-outcomes" aria-label="Answer outcomes">
    <h3>{(result.excluded_evidence_count??0)>0 ? `${completed} of ${result.expected_tests??completed+(result.excluded_evidence_count??0)} question assessments usable${unassessed ? `; ${unassessed} saved ${unassessed === 1 ? 'answer is' : 'answers are'} unassessed` : ''}` : `${completed} completed ${completed === 1?'answer':'answers'}${unassessed ? `; ${unassessed} saved ${unassessed === 1 ? 'answer is' : 'answers are'} unassessed` : ''}`}</h3>
    <div className="outcome-counts">{outcomes.map(outcome => <span key={outcome.className} className={outcome.className}><b>{outcome.count}</b> {outcome.label}</span>)}</div>
    {savedAnswers > 0 && <div className="outcome-bar" role="img" aria-label={unassessed ? `${result.tests_passed} passed, ${failed} failed, ${uncertain} awaiting review, ${unassessed} unassessed out of ${savedAnswers} saved answers` : `${result.tests_passed} passed, ${failed} failed, ${uncertain} awaiting review out of ${completed} completed answers`}>{outcomes.filter(outcome => outcome.count > 0).map(outcome => <span key={outcome.className} className={outcome.className} style={{ width: `${outcome.count / savedAnswers * 100}%` }}/>)}</div>}
    <p>{savedAnswers === 0 ? 'No assessed answers are available.' : unassessed > 0 ? 'Unassessed saved answers are excluded from the score until a valid assessment is available.' : uncertain > 0 ? 'The percentage above uses decided assessments only. Awaiting review does not mean passed.' : 'These are automated assessments; independent review is required for a reliability claim.'}</p>
  </section>;
}

function DimensionOverview({ scores, failures, uncertainAnswers, answers }: { scores: DimensionScores[]; failures: FailureDetail[]; uncertainAnswers: AssessmentDetail[]; answers: AuditAnswerDetail[] }) {
  return <section className="dimension-overview" aria-label="Memory performance by dimension">
    <h2>Four memory abilities</h2>
    <p>Pass rate · 0–100% · Decided answers only</p>
    <div className="dimension-bar-chart">{(Object.keys(labels) as Dimension[]).map(key => {
      const score = scores.find(item => item.dimension === key);
      const value = score?.percentage ?? null;
      const pending = score?.uncertain_count ?? 0;
      const excluded=score?.excluded_evidence_count??0;
      const failureCount = failures.filter(failure => failure.test.dimension === key).length;
      const detailedUncertainCount = Math.max(
        uncertainAnswers.filter(answer => answer.test.dimension === key).length,
        answers.filter(answer => answer.test.dimension === key && answer.outcome === 'uncertain').length,
      );
      const unassessedCount = answers.filter(answer => answer.test.dimension === key && answer.outcome === 'unassessed').length;
      const uncertainCount = Math.max(detailedUncertainCount, pending);
      const pendingCount = uncertainCount + unassessedCount;
      const state = value === null ? excluded>0?'Evidence unavailable':uncertainCount > 0 ? 'Awaiting review' : unassessedCount > 0 ? 'Unassessed answers' : 'Not tested' : formatPercentage(value);
      return <div className="dimension-bar-column" key={key}>
        <strong>{state}</strong>
        <div className={`dimension-bar-track ${value === null ? 'unscored' : ''}`} role="img" aria-label={`${labels[key]}: ${state}${value !== null ? `, ${score!.passed} of ${score!.total} tests passed` : ''}${uncertainCount > 0 ? `, ${uncertainCount} awaiting review` : ''}${unassessedCount > 0 ? `, ${unassessedCount} unassessed` : ''}`}>
          {value !== null && <span className="dimension-bar-fill" style={{height:`${Math.max(0,Math.min(100,value))}%`}}/>}
        </div>
        <h3>{labels[key]}</h3>
        <span>{value !== null ? `${score!.passed} of ${score!.total} tests passed` : excluded>0?'Saved questions lack usable assessment evidence':uncertainCount > 0 ? 'Completed answers need independent review' : unassessedCount > 0 ? 'Saved answers lack a unique valid assessment' : 'No completed tests in this dimension'}</span>
        {excluded>0&&<small>{excluded} evidence unavailable · excluded from score</small>}
        {uncertainCount > 0 && <small>{uncertainCount} awaiting review · excluded from score</small>}
        {unassessedCount > 0 && <small>{unassessedCount} unassessed · excluded from score</small>}
        <a href={`#dimension-details-${key}`} aria-label={`View ${labels[key]} details: ${failureCount} failures, ${uncertainCount} answers awaiting review${unassessedCount ? `, ${unassessedCount} unassessed` : ''}`}>
          {failureCount > 0 && `${failureCount} failure ${failureCount === 1 ? 'detail' : 'details'}`}
        {failureCount > 0 && pendingCount > 0 && ' · '}
          {uncertainCount > 0 && `Review ${uncertainCount} awaiting`}
          {uncertainCount > 0 && unassessedCount > 0 && ' · '}
          {unassessedCount > 0 && `Inspect ${unassessedCount} unassessed`}
          {failureCount === 0 && pendingCount === 0 && 'View details · no failures'}
        </a>
      </div>;
    })}</div>
  </section>;
}

const retrievalLabels: Array<[keyof RetrievalQualityScores, string, string]> = [
  ['evidence_recall_at_k', 'Required fact text matched', 'Exact source-and-text matches among required facts'],
  ['evidence_precision_at_k', 'Retrieved fact text matched', 'Exact matches among retrieved facts'],
  ['update_evidence_recall', 'Update fact text matched', 'Exact matches for freshness-test facts'],
  ['conflict_evidence_coverage', 'Conflict fact text matched', 'Exact matches for conflict-test facts'],
  ['unnecessary_memory_retrieval_rate', 'Retrieved text without a match', 'Paraphrases may also be unmatched; lower is not always better'],
];

function RetrievalQuality({ scores }: { scores?: RetrievalQualityScores }) {
  if (!scores) return <section className="retrieval-quality"><h2>Retrieval Evidence Quality</h2><p className="empty">No retrieval trace with source evidence is available for these completed tests.</p></section>;
  const excludedNotice = (scores.unlinked_attempts_excluded ?? 0) > 0 ? <p className="trace-note">{scores.unlinked_attempts_excluded} retrieval attempts without a linked saved answer are excluded. Their input and outcome remain unverified.</p> : null;
  if (!scores.tests_measured) return <section className="retrieval-quality"><h2>Retrieval Evidence Quality</h2><p className="empty">No retrieval trace with source evidence is available for these completed tests.</p>{excludedNotice}</section>;
  return <section className="retrieval-quality" aria-label="Retrieval evidence quality">
    <h2>Retrieval Evidence Quality</h2><p className="trace-note">Text matching checks · Not model accuracy or proof of memory use.</p>
    {excludedNotice}
    <div className="retrieval-summary-chart">{retrievalLabels.map(([key, label]) => {
      const value = scores[key] as number | null;
      return <div key={key} className="retrieval-summary-row"><span>{label}</span><div className={`retrieval-summary-track ${value === null ? 'unscored' : ''}`} role="img" aria-label={`${label}: ${formatPercentage(value)}`}>{value !== null && <span style={{width:`${Math.max(0,Math.min(100,value))}%`}}/>}</div><strong>{formatPercentage(value)}</strong></div>;
    })}</div>
    <UIPanel><UISummary>How to interpret these matching checks</UISummary><p>A 0% text match does not mean no relevant memory was sent. Inspect Memory retrieval and model input for the actual context. Reworded or bundled facts can match poorly while still supplying the required information. These checks do not measure causal model use or final supplied context.</p><ul>{retrievalLabels.map(([key,label,note])=><li key={key}><b>{label}:</b> {note}</li>)}</ul></UIPanel>
  </section>;
}

function FailureEvidence({ failure }: { failure: FailureDetail }) {
  return <>{!failure.evidence.length ? <p className="empty evidence-empty">No traceable ground-truth evidence was returned for this failure.</p> : <ul className="evidence-list">{failure.evidence.map((memory, index) => <li key={memory.memory_id}><b>Supporting memory {index + 1}</b><span>{memory.canonical_value}</span></li>)}</ul>}<p><b>Original conversation evidence</b></p>{failure.source_statements?.length ? <ul className="evidence-list">{failure.source_statements.map((source,index)=><li key={index}><b>Source {index+1} · {source.role} · {new Date(source.timestamp).toLocaleString()}</b><span>{source.content}</span></li>)}</ul> : <p className="empty">Original source statements are unavailable for this failure. Review its trace before relying on the diagnosis.</p>}</>;
}

function FailureCard({ failure }: { failure: FailureDetail }) {
  const label = labels[failure.test.dimension];
  return <UIPanel className="failure-card"><UISummary><b>{label}</b><span>Failure: {friendlyText(failure.evaluation.reason)}</span></UISummary><div className="failure-content"><p><b>Tested ability</b><br />{label}</p><p><b>Observed error category</b><br />{failure.evaluation.failure_classification?.status === 'classified' && failure.evaluation.failure_type ? labels[failure.evaluation.failure_type] : 'Awaiting classification'}</p><p>{friendlyText(failure.evaluation.failure_classification?.reason ?? 'Historical category labels followed the question dimension and need independent verification.')}</p><p><b>Why this failed</b><br />{friendlyText(failure.evaluation.reason)}</p><p><b>Behavioural test</b><br />{failure.test.prompt}</p><p><b>Expected behaviour</b><br />{failure.test.expected_behavior}</p><p><b>Target AI response</b><br />{failure.response.response_text || 'The target AI returned no text.'}</p><p><b>Ground-truth evidence</b></p><FailureEvidence failure={failure} /><p className="failure-meta">Evaluator: {assessmentLabel(failure.evaluation.evaluator)}</p></div></UIPanel>;
}

function ReviewRequiredAnswers({ result }: { result: AuditResult }) {
  const answers = uncertainAnswerDetails(result);
  const count = result.uncertain_count ?? answers.length;
  if (!count) return null;
  return <section aria-label="Answers needing review" className="review-required-answers">
    <h2>Why these answers need review</h2>
    <p>These automated assessments could not decide Pass or Fail, so they are excluded from the score. Inspect the saved evidence and use Review Evaluations below to record a separate reference label. Review labels never replace the original automated result.</p>
    {!answers.length ? <p>Individual explanations are unavailable in this report. Open Review Evaluations below to inspect the saved assessments.</p> : answers.map((answer, index) => <ReviewRequiredCard key={answer.evaluation.evaluation_id} answer={answer} position={index + 1}/>)}
  </section>;
}

function ReviewRequiredCard({ answer, position }: { answer: AssessmentDetail; position: number }) {
  const status = answer.evaluation.judge_execution?.verdict_status;
  const nextStep = status === 'review_source_uncertainty'
    ? 'Check whether the question and reference support a clear verdict. The evidence check could not establish one; this does not establish a model failure.'
    : status === 'review_disagreement'
      ? 'Compare both assessments with the original conversation. The semantic assessment and rule check disagree; neither decision has been accepted as the final result.'
      : status === 'uncertain_fallback'
        ? 'Check the assessment service and saved evidence. The automated assessment could not be completed reliably; this does not establish a model failure.'
        : 'Inspect the question, reference and complete model answer against the original conversation before deciding Pass or Fail.';
  return <UICard className="review-required-card">
    <h3>Answer {position} · {labels[answer.test.dimension]} · Awaiting review</h3>
    <UIAlert role="status"><b>Suggested next step</b><br/>{nextStep}</UIAlert>
    <p><b>Why review is needed</b><br/>{friendlyText(answer.evaluation.reason) || 'The saved assessment has no explanation. Check its evidence before assigning a verdict.'}</p>
    <p><b>Question</b><br/>{answer.test.prompt}</p>
    <p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}><b>Original model answer</b><br/>{answer.response.response_text || 'The model returned no text.'}</p>
    <p>Answer limit sent with this request: {answer.response.execution_metadata?.requested_output_token_limit != null ? `${answer.response.execution_metadata.requested_output_token_limit} tokens` : 'Not recorded'}.</p>
    <UIPanel><UISummary>Inspect the reference and original conversation</UISummary>
      <p><b>Expected behaviour</b><br/>{answer.test.expected_behavior}</p>
      <p>These are reference memories linked to the question or assessment. Their presence here does not mean the automated evaluator verified them or the model received them.</p>
      {answer.evidence.map((memory,index)=><p key={memory.memory_id}><b>Reference memory {index+1}</b><br/>{memory.canonical_value}</p>)}
      {answer.source_statements?.length ? answer.source_statements.map((source,index)=><p key={index} style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}><b>Source {index+1} · {source.role}</b><br/>{source.content}</p>) : <p>No original source statements are linked to this assessment. Check the complete conversation in the review area.</p>}
    </UIPanel>
  </UICard>;
}

function UnassessedAnswerCard({ answer, position }: { answer: AuditAnswerDetail; position: number }) {
  return <UICard className="unassessed-answer-card">
    <h4>Saved answer {position} · Unassessed · excluded from score</h4>
    <p><b>Why no assessment is available</b><br/>{answer.reason || 'No unique valid assessment is linked to this saved response.'}</p>
    <p><b>Question</b><br/>{answer.test.prompt}</p>
    <p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}><b>Saved target answer</b><br/>{answer.response.response_text || 'The model returned no text.'}</p>
    <UIPanel><UISummary>Reference and original conversation</UISummary>
      <p>{answer.test.expected_behavior}</p>
      {answer.evidence.map((memory,index)=><p key={memory.memory_id}><b>Reference memory {index+1}</b><br/>{memory.canonical_value}</p>)}
      {answer.source_statements?.length ? answer.source_statements.map((source,index)=><p key={index} style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}><b>Source {index+1} · {source.role}</b><br/>{source.content}</p>) : <p>No original source statements are linked to this answer.</p>}
    </UIPanel>
  </UICard>;
}

export function ResultDashboard({ result, run }: { result: AuditResult; run?: AuditRun }) {
  const [exportNotice,setExportNotice]=useState<{runId:string;format:'CSV'|'JSON';failed:boolean}|null>(null);
  const exportCsv=()=>{
    try { downloadAuditResultCsv(result, run); setExportNotice({runId:result.run_id,format:'CSV',failed:false}); }
    catch { setExportNotice({runId:result.run_id,format:'CSV',failed:true}); }
  };
  const exportJson=()=>{
    try { downloadAuditResultJson(result, run); setExportNotice({runId:result.run_id,format:'JSON',failed:false}); }
    catch { setExportNotice({runId:result.run_id,format:'JSON',failed:true}); }
  };
  const measuredDimensions = result.dimensions.filter((dimension) => dimension.percentage !== null).length;
  const hasCompletedTests = result.tests_total > 0;
  const uncertainAnswers = uncertainAnswerDetails(result);
  return <section className="result-dashboard" aria-label="Memory Health report details">{result.reproducibility?.shared_answer_source_run_id && <UIAlert role="status">{result.reproducibility?.assessment_source_run_id ? 'This reassessment uses the original saved target answers.' : 'These assessment results use the same saved target answers.'} No second target call was made. Retrieval figures below describe the original execution. <a href={`/audits/${result.reproducibility.shared_answer_source_run_id}`}>View original memory and model-input evidence</a>.</UIAlert>}<div className="report-hero"><p>{(result.excluded_evidence_count??0)>0?'PARTIAL RESULT':measuredDimensions === 4 ? 'OVERALL MEMORY HEALTH' : 'TESTED ABILITY AVERAGE'}</p><h2>{result.overall_score === null && (result.uncertain_count ?? 0) > 0 ? 'Unscored' : formatPercentage(result.overall_score)}</h2><span>{hasCompletedTests ? `${result.tests_passed} of ${result.tests_total} tests passed` : (result.uncertain_count ?? 0) > 0 ? `${result.uncertain_count} completed answers await review` : 'No completed tests are available for scoring'}</span></div><AnswerOutcomes result={result}/><div className="failure-heading"><div><h2>Results at a glance</h2><p>{result.overall_score === null && (result.uncertain_count ?? 0) > 0 ? 'No definitive score is available while completed answers await review.' : overallAssessment(result.overall_score, measuredDimensions)}</p></div><div className="report-export-actions"><UIButton type="button" className="secondary" onClick={exportCsv}>Download CSV</UIButton><UIButton type="button" className="secondary" onClick={exportJson}>Download JSON</UIButton></div></div>{exportNotice?.runId===result.run_id && (exportNotice.failed ? <UIAlert role="alert">The {exportNotice.format} could not be prepared. Try downloading again.</UIAlert> : <p role="status">{exportNotice.format === 'CSV' ? 'CSV prepared. Your browser was asked to save memory-health-report.csv.' : 'JSON prepared. Your browser was asked to save the memory-health report.'}</p>)}{result.evaluation_warnings?.map((warning) => <UIAlert className="alert" role="status" key={warning}>{friendlyText(warning)}</UIAlert>)}<DimensionOverview scores={result.dimensions} failures={result.failures} uncertainAnswers={uncertainAnswers} answers={result.answers ?? []}/><UIPanel><UISummary>Score coverage & request settings</UISummary><p>{result.uncertain_count??uncertainAnswers.length} uncertain assessments are excluded from the score. Scores are automated until calibrated against independent human labels.</p><p className="report-coverage">Score coverage: {measuredDimensions} of {result.dimensions.length} Memory Health dimensions have definitive scores. Untested dimensions are excluded from the macro-average. Uncertain assessments also stay outside the score. {measuredDimensions < 4 && 'A formal overall Memory Health score requires all four dimensions.'}</p><p>Configured model answer limit: {result.reproducibility?.target_memory_profile?.output_token_limit != null ? `${result.reproducibility.target_memory_profile.output_token_limit} tokens` : 'Not recorded'}. Tokens are model text units, not words; some models count reasoning too. Rule-based answers do not use this limit.</p></UIPanel><RetrievalQuality scores={result.retrieval_quality} /><ReviewRequiredAnswers result={result}/><div className="failure-heading"><div><h2>Answers marked as failed</h2><p>A failed answer can reflect the test setup. Inspect diagnosis before attributing a memory defect.</p></div><span className="failure-count">{result.failures.length} flagged</span></div>{(Object.keys(labels) as Dimension[]).map(dimension => {
    const failures = result.failures.filter(failure => failure.test.dimension === dimension);
    return <section id={`dimension-details-${dimension}`} key={dimension} className="dimension-failure-details" tabIndex={-1} aria-labelledby={`dimension-details-heading-${dimension}`}>
      <h3 id={`dimension-details-heading-${dimension}`}>{labels[dimension]} answer details</h3>
      {failures.length === 0 ? <p className="empty">No failed answers in this dimension.</p> : <div className="failure-list">{failures.map(failure => <FailureCard key={failure.failure_id} failure={failure}/>)}</div>}
      {uncertainAnswers.filter(answer => answer.test.dimension === dimension).length > 0 && <div className="dimension-pending-answers"><h4>Answers awaiting review</h4>{uncertainAnswers.filter(answer => answer.test.dimension === dimension).map((answer, index) => <ReviewRequiredCard key={answer.evaluation.evaluation_id} answer={answer} position={index + 1}/>)}</div>}
      {(result.answers ?? []).filter(answer => answer.test.dimension === dimension && answer.outcome === 'unassessed').length > 0 && <div className="dimension-unassessed-answers"><h4>Saved answers without an assessment</h4><p>These responses have no unique valid assessment and are excluded from scoring.</p>{(result.answers ?? []).filter(answer => answer.test.dimension === dimension && answer.outcome === 'unassessed').map((answer, index) => <UnassessedAnswerCard key={answer.response.response_id} answer={answer} position={index + 1}/>)}</div>}
    </section>;
  })}<SavedAnswerReassessment key={result.run_id} runId={result.run_id} sourceId={result.reproducibility?.assessment_source_run_id}/><EvaluationReview runId={result.run_id} exposedToAutomatedResults /><ValidationWorkbench runId={result.run_id}/></section>;
}
