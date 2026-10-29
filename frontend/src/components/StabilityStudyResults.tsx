import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { saveBlob } from '../services/download';
import { SESSION_ENDED } from '../services/access';
import { reasoningRequestDescription } from '../services/reasoningEvidence';
import {
  decodeStabilityStudyPackage, hasSavedStabilityStudyPackage, readSavedStabilityStudyPackage,
  removeSavedStabilityStudyPackage, saveStabilityStudyPackage, stabilitySummaryCsv,
  repeatAgreement, summarizeSplit, type DecodedStabilityPackage, type JsonRecord,
  type StabilityRun, type StabilitySplit, type StudySplitName,
} from '../services/stabilityStudyPackage';
import { UIButton, UICheckbox, UITable } from './ui';
import './stabilityStudyResults.css';

const MAX_STUDY_PACKAGE_BYTES = 50 * 1024 * 1024;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function field(value: unknown, key: string): unknown { return isRecord(value) ? value[key] : undefined; }

function printable(value: unknown): string {
  if (value === null || value === undefined) return 'Not recorded';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try { return JSON.stringify(value, null, 2); } catch { return 'Could not display this value.'; }
}

function ratioPercent(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : 'Not recorded';
}

function armName(arm: string): string {
  if (arm === 'weak_first_hit') return 'First-match retrieval';
  if (arm === 'strong_rule_based') return 'Relationship-priority retrieval';
  return arm;
}

function actualModel(metadata: unknown): string {
  const requested = field(metadata, 'requested_model');
  const reported = field(metadata, 'reported_model');
  if (typeof requested === 'string' && typeof reported === 'string') return `${requested} → ${reported}`;
  if (typeof reported === 'string') return reported;
  if (typeof requested === 'string') return `${requested} (actual model not reported)`;
  return 'Actual model not recorded';
}

function sourceReviewRecord(source: unknown): JsonRecord | null {
  const review = isRecord(source) && Object.prototype.hasOwnProperty.call(source, 'agent_review') ? source.agent_review : source;
  return isRecord(review) ? review : null;
}

function recordedCriticalItems(review: JsonRecord | null): unknown[] | null {
  const items = review?.critical_errors;
  return Array.isArray(items) && items.every(item=>isRecord(item) || (typeof item==='string' && item.trim())) ? items : null;
}

function sourceReviewIsComplete(review: JsonRecord | null): boolean {
  return !!review && review.reviewable !== false
    && (review.review_status === 'reviewed' || (review.review_status === undefined && ['reviewed','completed'].includes(String(review.status))))
    && (review.status === undefined || ['reviewed','completed'].includes(String(review.status)))
    && recordedCriticalItems(review) !== null;
}

function sourceReviewLabel(source: unknown): string {
  const review=sourceReviewRecord(source), findings=recordedCriticalItems(review);
  if (!sourceReviewIsComplete(review)) return findings?.length ? `${findings.length} critical findings recorded; review incomplete` : 'Not reviewed or status unknown';
  return findings!.length ? `${findings!.length} critical ${findings!.length===1?'finding':'findings'}` : 'Reviewed; 0 critical findings recorded';
}

function textField(value: unknown, ...keys: string[]): string | null {
  for (const key of keys) {const item=field(value,key);if(typeof item==='string' && item.trim())return item;}
  return null;
}

function SourceQuotation({ evidence }: { evidence: unknown }) {
  const quote=textField(evidence,'source_quote');
  if (!quote) return <p>Exact source quotation not recorded.</p>;
  const supplied=field(evidence,'supplied_quote_verified');
  return <div><p><b>Original source:</b> {textField(evidence,'source_message_id') ?? 'Message not recorded'} · {textField(evidence,'source_role') ?? 'Role not recorded'} · {textField(evidence,'source_date','source_observed_date') ?? 'Date not recorded'}</p>
    <blockquote style={{whiteSpace:'pre-wrap'}}>{quote}</blockquote>
    <p>{supplied===true?'Present in supplied memories':supplied===false?'Not present in supplied memories':'Supplied-memory availability not recorded'}</p></div>;
}

const SOURCE_FINDING_LABELS: Record<string,string> = {
  unsupported_identity_or_event_merge:'Unsupported person or event link',
  wrong_temporal_or_state_binding:'Wrong date or state',
  material_source_contradiction:'Source contradiction',
  fabricated_historical_or_user_fact:'Unsupported historical or user fact',
  wrong_event_binding:'Wrong person or event binding',
};

function SourceReviewTechnicalRecord({source}: {source:unknown}) {
  const [open,setOpen]=useState(false);
  return <details onToggle={event=>setOpen(event.currentTarget.open)}><summary>Source review technical record</summary>{open&&<pre>{printable(source)}</pre>}</details>;
}

/** Saved engineering review, separate from model grading and acceptance gates. */
export function RunSourceReview({run}: {run:StabilityRun}) {
  const review=sourceReviewRecord(run.source_review), findings=recordedCriticalItems(review);
  const claims=Array.isArray(review?.claims)?review.claims.filter(isRecord):[];
  const complete=sourceReviewIsComplete(review);
  return <section aria-label="Source check" className="stability-run-source-check">
    <h6>Source review (separate from the original grade)</h6>
    <p><b>Original automatic grade:</b> {run.grade_outcome}. <b>Source check:</b> {sourceReviewLabel(run.source_review)}.</p>
    {!complete && <p>The source review is missing, incomplete or in an unsupported format. No zero-finding or safety conclusion is inferred.</p>}
    {textField(review,'finding') && <p>{textField(review,'finding')}</p>}
    <p>These are saved engineering findings, not independent human gold or a new grade. Each reply keeps its own split, condition and round; package gates remain separate.</p>
    {findings?.map((finding,index)=>{
      const quote=textField(finding,'claim','response_claim','target_quote');
      const linked=quote?claims.filter(item=>typeof item.claim==='string' && item.claim.trim() && (item.claim===quote || item.claim.includes(quote) || quote.includes(item.claim))):[];
      const evidence=[...linked.flatMap(item=>[item,...(Array.isArray(item.additional_source_evidence)?item.additional_source_evidence:[]),...(Array.isArray(item.additional_original_evidence)?item.additional_original_evidence:[])]),...(textField(finding,'source_quote')?[finding]:[])];
      const seen=new Set<string>();const unique=evidence.filter(item=>{const key=JSON.stringify([field(item,'source_message_id'),field(item,'source_quote')]);if(seen.has(key))return false;seen.add(key);return true;});
      const category=textField(finding,'category');
      return <article key={index}><h6>Critical finding {index+1}{category?` · ${SOURCE_FINDING_LABELS[category] ?? category.replaceAll('_',' ')}`:''}</h6>
        <p>{typeof finding==='string'?finding:textField(finding,'explanation','reason','details','source_reason') ?? 'Explanation not recorded; inspect the technical review below.'}</p>
        <p><b>Exact answer claim:</b></p>{quote?<blockquote style={{whiteSpace:'pre-wrap'}}>{quote}</blockquote>:<p>Exact answer claim not recorded.</p>}
        {unique.length?unique.map((item,i)=><SourceQuotation key={i} evidence={item}/>):<p>Exact source quotation not recorded. Inspect the original review before drawing a conclusion.</p>}
      </article>;
    })}
    {claims.length>0?<details><summary>Reviewed claims and source quotations ({claims.length})</summary>
      {claims.map((claim,index)=><article key={index}><p><b>Exact answer claim:</b></p><blockquote style={{whiteSpace:'pre-wrap'}}>{textField(claim,'claim') ?? 'Not recorded'}</blockquote>
        <p>Recorded source support: {textField(claim,'source_support') ?? 'Not recorded'}</p><p>{textField(claim,'explanation') ?? 'Explanation not recorded'}</p>
        <SourceQuotation evidence={claim}/>{[...(Array.isArray(claim.additional_source_evidence)?claim.additional_source_evidence:[]),...(Array.isArray(claim.additional_original_evidence)?claim.additional_original_evidence:[])].map((item,i)=><SourceQuotation key={i} evidence={item}/>)}</article>)}
    </details>:<p>Readable claim/source details not recorded.</p>}
    {review && ['omissions','usefulness','pipeline_losses','review_limitations'].some(key=>review[key]!==undefined) && <details><summary>Omissions and review limits</summary>
      {['omissions','usefulness','pipeline_losses','review_limitations'].map(key=>review[key]!==undefined?<div key={key}><b>{key.replaceAll('_',' ')}</b><pre>{printable(review[key])}</pre></div>:null)}
    </details>}
    <SourceReviewTechnicalRecord source={run.source_review}/>
  </section>;
}

function runDetails(run: StabilityRun, splitName: StudySplitName) {
  const graderMetadata = field(run.semantic_grade, 'execution_metadata') ?? field(run.grading_attempt, 'execution');
  return <details className="stability-run" key={`${run.round}:${run.arm}`}>
    <summary><span>Round {run.round} · {armName(run.arm)} · {run.status} · {run.grade_outcome}</span><span> · Source: {sourceReviewLabel(run.source_review)}</span></summary>
    <p><b>Target model:</b> {actualModel(run.execution_metadata)}</p>
    <p><b>Grading model:</b> {actualModel(graderMetadata)}</p>
    <p><b>Target reasoning request:</b> {reasoningRequestDescription(run.execution_metadata)}</p>
    <p><b>Grader reasoning request:</b> {reasoningRequestDescription(graderMetadata)}</p>
    <h6>Target answer</h6><pre>{run.response_text ?? 'No answer recorded.'}</pre>
    <RunSourceReview run={run}/>
    <details><summary>Original grade and request details</summary>
    <h6>{splitName === 'safety_guards' ? 'Original safety-guard assessment' : 'Original semantic grade'}</h6><pre>{printable(run.semantic_grade)}</pre>
    {run.grading_attempt && <><h6>Original grading attempt (separate from valid semantic grades)</h6><pre>{printable(run.grading_attempt)}</pre></>}
    {run.failure_diagnostics && <><h6>Recorded execution failure diagnostics</h6><pre>{printable(run.failure_diagnostics)}</pre></>}
    {run.auxiliary_analysis && <>
      <h6>{run.auxiliary_analysis.degraded === true ? 'Auxiliary suggestions not used' : 'Auxiliary identity check'}</h6>
      {run.auxiliary_analysis.degraded === true && <p>The identity suggestion was rejected. The same planned final model answered using its existing memories. This is a failed auxiliary check, separate from the final answer and its original grade.</p>}
      <p>HTTP response status: {printable(run.auxiliary_analysis.http_execution_status)} · Identity validation: {printable(run.auxiliary_analysis.analyzer_status)}</p>
      <pre>{printable(run.auxiliary_analysis)}</pre>
    </>}
    <h6>Execution metadata</h6><pre>{printable(run.execution_metadata)}</pre>
    <h6>Input replay receipt</h6><pre>{printable(run.input_receipt)}</pre>
    {Array.isArray(run.extra_agent_executions) && run.extra_agent_executions.length > 0 && <><h6>Additional review executions</h6>
      {run.extra_agent_executions.filter(isRecord).filter(item=>item.agent_role==='target_identity_evidence').map((item,index)=><p key={index}><b>Identity analysis reasoning request:</b> {reasoningRequestDescription(item.execution)}</p>)}
      <pre>{printable(run.extra_agent_executions)}</pre></>}
    </details>
  </details>;
}

const GATE_LABELS: Record<string, string> = {
  actual_Luna_identity: 'Requested model and execution roles',
  usable_targets: 'Complete target answers',
  grade_coverage: 'Original grading coverage',
  input_replay: 'Offline input replay',
  critical_source_safety_guards: 'Source safety review',
  final_case_source_safety: 'All benchmark replies source review',
  actual_memory_preparation: 'Saved memory decisions and replay',
  three_grade_unanimity: 'Agreement across three rounds',
  Strong_round_correct_range: 'Target condition results across rounds',
  Strong_mean_accuracy: 'Target condition average accuracy',
  Strong_at_least_Weak: 'Target condition compared with baseline',
  auxiliary_validation_coverage: 'Auxiliary output validation coverage',
  frozen_protocol_binding: 'Frozen protocol consistency',
};

function compactEvidence(value: unknown): string {
  if (isRecord(value)) {
    // Prefer complete recorded quality counts to object insertion order.
    if (typeof value.correct === 'number' && typeof value.planned === 'number'
        && typeof value.graded === 'number') {
      return `Correct: ${printable(value.correct)}/${printable(value.planned)} · Graded: ${printable(value.graded)}/${printable(value.planned)}`;
    }
    const values = Object.entries(value).filter(([, item]) =>
      typeof item === 'string' || typeof item === 'number' || typeof item === 'boolean').slice(0, 3);
    return values.length ? values.map(([key, item]) => `${key.replaceAll('_', ' ')}: ${printable(item)}`).join(' · ').slice(0, 220)
      : 'See the full technical evidence below.';
  }
  if (Array.isArray(value)) return 'See the full per-stage evidence below.';
  return printable(value).slice(0, 220);
}

function RecordedReplaySummary({ replay, label }: { replay: unknown; label: string }) {
  if (!isRecord(replay)) return null;
  const target = replay.target_input_comparisons ?? replay.compared_trials;
  return <p><b>{label}:</b> status {printable(replay.status)} · Target inputs: {printable(target)}/{printable(replay.planned_trials)} · Grader inputs: {printable(replay.grader_input_comparisons)}/{printable(replay.planned_grader_input_comparisons)}. These are recorded counts; a target-only ratio does not describe grader replay coverage.</p>;
}

function FinalSourceReviewScope({ gate }: { gate: unknown }) {
  const observed = field(gate, 'observed');
  const planned = field(observed, 'planned_trials');
  const count = typeof planned === 'number' && Number.isInteger(planned) && planned > 0
    ? String(planned) : 'All planned';
  const requiredArms = field(observed, 'critical_error_required_arms');
  const scoped = Array.isArray(requiredArms) && requiredArms.length > 0 && requiredArms.every(arm=>typeof arm === 'string');
  return <><p>Recorded scope: {count} ordinary final replies; synthetic safety guards are reviewed separately. Pending or missing reviews do not establish source safety.</p>
    {scoped && <p>Zero critical errors is required for: {requiredArms.map(arm=>armName(String(arm))).join(', ')}. Recorded findings in required conditions: {printable(field(observed,'required_arm_critical_error_count'))}; findings across all conditions: {printable(field(observed,'critical_error_count'))}. Findings in comparison conditions remain reported.</p>}</>;
}

function AcceptanceOverview({ evidence, replay }: { evidence: unknown; replay: unknown }) {
  const gates = field(evidence, 'gates');
  return <section className="stability-acceptance-overview" aria-labelledby="stability-package-status-title">
    <h4 id="stability-package-status-title">Package stage status: <span>{printable(field(evidence, 'overall_status'))}</span></h4>
    <p>This is the stage status recorded in this package, not formal research acceptance. The checks below display the package’s recorded decisions; this browser does not reassess them.</p>
    {isRecord(gates) && Object.keys(gates).length > 0 ? <div className="comparison-scroll"><UITable>
      <thead><tr><th>Recorded check</th><th>Status</th><th>Observed</th><th>Requirement</th></tr></thead>
      <tbody>{Object.entries(gates).map(([key, gate]) => <tr key={key}>
        <th scope="row">{GATE_LABELS[key] ?? key.replaceAll('_', ' ')}</th>
        <td>{printable(field(gate, 'status'))}</td><td>{compactEvidence(field(gate, 'observed'))}</td><td>{compactEvidence(field(gate, 'threshold'))}{key === 'final_case_source_safety' && <FinalSourceReviewScope gate={gate} />}</td>
      </tr>)}</tbody>
    </UITable></div> : <p>No individual acceptance checks were recorded.</p>}
    <RecordedReplaySummary replay={replay} label="Stage offline replay" />
    <RecordedReplaySummary replay={field(replay, 'independent_safety_guards')} label="Independent safety offline replay" />
    <p className="stability-overview-note">Full recorded values, protocol, provenance, replay proof and limitations remain available in the technical evidence below.</p>
  </section>;
}

export function RecordedCaseSourceReviews({ splits }: { splits: StabilitySplit[] }) {
  let reviewed=0, critical=0, unknown=0;
  const seen=new Set<string>();
  const groups=new Map<string,{split:string;arm:string;reviewed:number;critical:number;unreviewed:number}>();
  for(const split of splits)for(const entry of split.cases)for(const run of entry.runs){
    const key=JSON.stringify([split.name,entry.case_id,String(run.round),run.arm]);
    if(seen.has(key))continue;
    seen.add(key);
    const groupKey=JSON.stringify([split.name,run.arm]);
    const group=groups.get(groupKey) ?? {split:split.name,arm:run.arm,reviewed:0,critical:0,unreviewed:0};
    groups.set(groupKey,group);
    const source=run.source_review;
    if(source===null||source===undefined){group.unreviewed++;continue;}
    // Guard automatic findings are not independent source-review records.
    const review=sourceReviewRecord(source);
    if(review===null){group.unreviewed++;continue;}
    group.critical+=recordedCriticalItems(review)?.length ?? 0;
    if(!sourceReviewIsComplete(review)){
      unknown++;group.unreviewed++;continue;
    }
    const count=recordedCriticalItems(review)!.length;
    reviewed++;critical+=count;group.reviewed++;
  }
  return <section className="stability-package-meta" aria-label="Recorded case source reviews">
    <h5>Recorded case source reviews</h5>
    {reviewed>0?<p>{reviewed} reviewed {reviewed===1?'reply':'replies'}; {critical} critical {critical===1?'finding':'findings'}.</p>
      :<p>No interpretable case source-review counts recorded.</p>}
    {unknown>0&&<p>{unknown} source-review {unknown===1?'record has':'records have'} an unknown or incomplete format; critical findings are not assumed to be zero.</p>}
    <div className="comparison-scroll"><UITable aria-label="Source reviews by split and condition"><thead><tr><th>Split</th><th>Condition</th><th>Reviewed replies</th><th>Recorded critical findings</th><th>Unreviewed or unknown</th></tr></thead>
      <tbody>{[...groups.values()].map(group=><tr key={JSON.stringify([group.split,group.arm])}><td>{group.split.replaceAll('_',' ')}</td><td>{armName(group.arm)}</td><td>{group.reviewed}</td><td>{group.reviewed>0||group.critical>0?group.critical:'Not assessed'}</td><td>{group.unreviewed}</td></tr>)}</tbody></UITable></div>
    <p>Unreviewed replies have no recorded source-safety assessment. Absence of a finding does not mean safe. These counts describe saved reviews only, do not establish full review coverage, and do not replace the package’s recorded acceptance gates or original grades.</p>
  </section>;
}

function SourceReuseScope({ provenance }: { provenance: unknown }) {
  const scope=field(provenance,'source_reuse_scope');
  if(!isRecord(scope))return <section className="stability-package-meta"><h5>Source reuse scope</h5>
    <p>Not recorded. Selection metadata alone does not establish full-source separation.</p></section>;
  const separation=(value:unknown)=>value===true?'Declared separate':value===false?'Not declared separate':'Not recorded';
  const reuse=scope.public_distractor_conversations_may_repeat;
  return <section className="stability-package-meta"><h5>Source reuse scope</h5>
    <p>This describes the package’s recorded separation rule and metadata checks. This browser does not independently verify source overlap.</p>
    <ul><li>Questions: {separation(scope.question_disjoint)}</li><li>Answer-bearing evidence: {separation(scope.answer_evidence_disjoint)}</li>
      <li>Public distractor conversations may repeat: {reuse===true?'Yes':reuse===false?'No':'Not recorded'}</li>
      <li>Full-source separation: {scope.full_source_disjoint===false?'Not claimed':scope.full_source_disjoint===true?'Declared; not independently verified here':'Not recorded'}</li>
      <li>Recorded metadata checks: {scope.metadata_checks_status==='legacy_declared'?'Legacy declaration; not a new verification':printable(scope.metadata_checks_status)}</li></ul>
    {reuse===true&&<p>Repeated conversations are permitted only when they are public distractors on both sides. This is not full-source separation.</p>}
    {typeof scope.scope_disclosure==='string'&&<p>{scope.scope_disclosure}</p>}
  </section>;
}

function PilotAuxiliaryGateNote({ protocol }: { protocol: unknown }) {
  const requirements=field(protocol,'additional_acceptance_requirements');
  const stages=field(requirements,'applies_to_stages');
  const knownStages=['development-pilot','safety-guards','final'];
  if(!Array.isArray(stages)||!stages.every(stage=>typeof stage==='string'&&knownStages.includes(stage))) {
    return <p>Development pilot: whether the auxiliary validation gate applies is not recorded clearly in this protocol. No applicability decision is inferred.</p>;
  }
  if(stages.includes('development-pilot'))return <p>Development pilot: auxiliary validation is required by this protocol. Validation coverage requirement: {ratioPercent(field(requirements,'auxiliary_validation_coverage_minimum'))}. See the recorded gate status above.</p>;
  return <p>Development pilot: descriptive auxiliary results only. This protocol does not apply an auxiliary validation gate to this pilot.</p>;
}

function AuxiliaryReport({ evidence, protocol }: { evidence: unknown; protocol: unknown }) {
  const stages = field(evidence, 'stages');
  if (!isRecord(stages)) return null;
  return <section className="stability-package-meta"><h5>Auxiliary identity suggestions</h5>
    <p>Validated means the saved output contract and source-quote checks passed. It does not prove that an identity relationship is semantically true.</p>
    <p>The target condition is the whole preregistered condition and can use operator-accepted identity suggestions or continue without them. This study therefore does not isolate retrieval or hold total call cost equal. Grades for valid and degraded subgroups are descriptive comparisons.</p>
    <p>Rejected suggestions are never counted as validated. Each required stage must independently meet its auxiliary coverage gate; unknown states and unexpected calls fail it. Source safety clearance requires a completed review with zero critical errors; pending or failed reviews do not provide clearance. Every final answer with rejected suggestions still requires source safety review.</p>
    {Object.entries(stages).map(([name, summary]) => {
      const total = field(summary, 'total');
      const rows = field(summary, 'by_split_arm_round');
      return <div key={name}><h6>Stage: {name}</h6>
        {name === 'development-pilot' && <PilotAuxiliaryGateNote protocol={protocol} />}
        <p>{printable(field(total, 'attempted'))} attempted · {printable(field(total, 'validated'))} validated · {printable(field(total, 'degraded'))} continued without suggestions · {printable(field(total, 'unknown'))} unknown</p>
        <p>Validation coverage: {ratioPercent(field(total, 'validation_coverage'))} · Degraded rate: {ratioPercent(field(total, 'degraded_rate'))} · Continued answers without source safety clearance: {printable(field(total, 'degraded_unreviewed'))}</p>
        <div className="comparison-scroll"><UITable><thead><tr><th>Split</th><th>Round</th><th>Condition</th><th>Planned eligible</th><th>Attempted</th><th>Validated</th><th>Degraded</th><th>Blocked</th><th>Skipped</th><th>Unknown</th><th>Unexpected calls</th><th>Continued answers without source safety clearance</th></tr></thead>
          <tbody>{Array.isArray(rows) && rows.filter(isRecord).map((row, index) => <tr key={index}>
            <td>{printable(row.split)}</td><td>{printable(row.round)}</td><td>{typeof row.arm === 'string' ? armName(row.arm) : 'Not recorded'}</td>
            {['planned_eligible','attempted','validated','degraded','blocked','skipped','unknown','unexpected_calls','degraded_unreviewed'].map(key => <td key={key}>{printable(row[key])}</td>)}
          </tr>)}</tbody></UITable></div>
      </div>;
    })}
  </section>;
}

function splitSummary(split: StabilitySplit) {
  const counts = summarizeSplit(split);
  const completed = counts.reduce((sum, item) => sum + item.correct + item.incorrect + item.uncertain, 0);
  const errors = counts.reduce((sum, item) => sum + item.error, 0);
  const missing = counts.reduce((sum, item) => sum + item.missing, 0);
  const planned = split.planned_case_ids.length * split.rounds.length * split.arms.length;
  return { completed, errors, missing, planned };
}

function SplitReport({ split }: { split: StabilitySplit }) {
  const stats = splitSummary(split);
  const repeats = repeatAgreement(split);
  const label = split.name === 'development' ? 'Development' : split.name === 'development_regression' ? 'Known failure regression · used questions' : split.name === 'development_repair' ? 'Repair diagnostics · used questions' : split.name === 'evaluation' ? 'Evaluation' : 'Safety guards · engineering checks';
  return <section className="stability-split" aria-labelledby={`stability-${split.name}-title`}>
    <h4 id={`stability-${split.name}-title`}>{label}{split.name === 'safety_guards' || split.name === 'development_regression' || split.name === 'development_repair' ? '' : ' split'}</h4>
    {split.name === 'development_regression' && <p>Previously used questions, kept separate from the development repeat study and new evaluation results. This split is not evidence on unseen questions.</p>}
    {split.name === 'development_repair' && <p>Previously used failures checked after a repair. These diagnostic results do not change the original regression threshold or count as unseen evaluation questions.</p>}
    {split.name === 'safety_guards' && <p>Separate engineering safety checks. These results are not an official benchmark score and are not pooled with the development or evaluation split.</p>}
    <p>{split.planned_case_ids.length} planned cases · {stats.planned} planned result cells · {stats.completed} with an original semantic grade · {stats.errors} {stats.errors === 1 ? 'error' : 'errors'} · {stats.missing} missing</p>
    <div className="comparison-scroll"><UITable>
      <thead><tr><th>Round</th><th>Condition</th><th>Correct</th><th>Incorrect</th><th>Uncertain</th><th>Error</th><th>Missing</th><th>Planned</th></tr></thead>
      <tbody>{summarizeSplit(split).map(row => <tr key={`${row.round}:${row.arm}`}>
        <th scope="row">{row.round}</th><td>{armName(row.arm)}</td><td>{row.correct}</td><td>{row.incorrect}</td><td>{row.uncertain}</td><td>{row.error}</td><td>{row.missing}</td><td>{row.planned_cases}</td>
      </tr>)}</tbody>
    </UITable></div>
    <h5>Repeat consistency</h5>
    {repeats.length === 0 ? <p>Not measured: only one round is included. Repeat consistency requires at least two rounds.</p> : <>
      <p>Exact agreement of the original semantic grade across rounds, among case-condition pairs with a resolved grade in every round. Errors and missing grades are excluded from this denominator.</p>
      <ul>{repeats.map(item => <li key={item.arm}>{armName(item.arm)}: {item.agreed} / {item.resolved} resolved pairs agree · {item.planned} planned pairs</li>)}</ul>
    </>}
    <h5>Question-level trace</h5>
    {split.cases.map(studyCase => <details className="stability-case" key={studyCase.case_id}>
      <summary>{studyCase.case_id} · {studyCase.type}</summary>
      <p><b>Question:</b> {studyCase.question ?? 'Not materialised'}</p>
      <p><b>Reference answer:</b> {studyCase.reference_answer ?? 'Not materialised'}</p>
      {studyCase.runs.map(run => runDetails(run, split.name))}
    </details>)}
  </section>;
}

export function StabilityStudyResults() {
  const [authorised, setAuthorised] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [decoded, setDecoded] = useState<DecodedStabilityPackage | null>(null);
  const [savedAvailable, setSavedAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const revision = useRef(0);
  const authorisedRef = useRef(false);

  const changeAuthorisation = (checked: boolean) => {
    revision.current += 1;
    authorisedRef.current = checked;
    setAuthorised(checked);
    setPendingFile(null);
    setDecoded(null);
    setError('');
    setNotice(checked ? '' : 'The currently loaded package and preview were cleared. A saved local copy remains until you remove it.');
    setBusy(false);
    if (!checked) setSavedAvailable(false);
  };

  useEffect(() => {
    const endSession = () => changeAuthorisation(false);
    window.addEventListener(SESSION_ENDED, endSession);
    return () => window.removeEventListener(SESSION_ENDED, endSession);
  }, []);

  useEffect(() => {
    if (!authorised) return;
    const token = revision.current;
    let cancelled = false;
    void hasSavedStabilityStudyPackage().then(hasSaved => {
      if (!cancelled && token === revision.current && authorisedRef.current) setSavedAvailable(hasSaved);
    }).catch(reason => {
      if (!cancelled && token === revision.current && authorisedRef.current) setError(reason instanceof Error ? reason.message : 'Could not check local package storage.');
    });
    return () => { cancelled = true; };
  }, [authorised]);

  const selectFile = (event: ChangeEvent<HTMLInputElement>) => {
    if (!authorisedRef.current) return;
    setPendingFile(event.target.files?.[0] ?? null);
    setDecoded(null);
    setError('');
    setNotice('');
  };

  const importSelected = async () => {
    if (!authorisedRef.current || !authorised || !pendingFile) return;
    const token = revision.current;
    setBusy(true);
    setError(''); setNotice(''); setDecoded(null);
    try {
      if (pendingFile.size > MAX_STUDY_PACKAGE_BYTES) throw new Error('This package is larger than 50 MB. Select a smaller export.');
      const raw = await pendingFile.text();
      if (token !== revision.current || !authorisedRef.current) return;
      const imported = await decodeStabilityStudyPackage(raw, () => token === revision.current && authorisedRef.current);
      if (token !== revision.current || !authorisedRef.current) return;
      setDecoded(imported);
      setNotice('Package loaded in this page only. Save is a separate, local action.');
    } catch (reason) {
      if (token === revision.current && authorisedRef.current) setError(reason instanceof Error ? reason.message : 'Could not import this study package.');
    } finally {
      if (token === revision.current) setBusy(false);
    }
  };

  const restoreSaved = async () => {
    if (!authorisedRef.current || !authorised || !savedAvailable) return;
    const token = revision.current;
    setBusy(true); setError(''); setNotice(''); setDecoded(null);
    try {
      const raw = await readSavedStabilityStudyPackage();
      if (token !== revision.current || !authorisedRef.current) return;
      if (raw === null) { setSavedAvailable(false); setNotice('There is no saved local package.'); return; }
      const imported = await decodeStabilityStudyPackage(raw, () => token === revision.current && authorisedRef.current);
      if (token !== revision.current || !authorisedRef.current) return;
      setDecoded(imported);
      setNotice('Saved package restored and its payload hash verified.');
    } catch (reason) {
      if (token === revision.current && authorisedRef.current) setError(reason instanceof Error ? reason.message : 'Could not restore the saved package.');
    } finally {
      if (token === revision.current) setBusy(false);
    }
  };

  const saveLocal = async () => {
    if (!authorisedRef.current || !authorised || !decoded) return;
    const token = revision.current;
    setBusy(true); setError(''); setNotice('');
    try {
      await saveStabilityStudyPackage(decoded.raw_envelope);
      if (token !== revision.current || !authorisedRef.current) return;
      setSavedAvailable(true);
      setNotice('The exact original package envelope is saved in this browser’s IndexedDB.');
    } catch (reason) {
      if (token === revision.current && authorisedRef.current) setError(reason instanceof Error ? reason.message : 'Could not save the local package.');
    } finally {
      if (token === revision.current) setBusy(false);
    }
  };

  const removeLocal = async () => {
    if (!authorisedRef.current || !authorised || !savedAvailable) return;
    const token = revision.current;
    setBusy(true); setError(''); setNotice('');
    try {
      await removeSavedStabilityStudyPackage();
      if (token !== revision.current || !authorisedRef.current) return;
      setSavedAvailable(false);
      setNotice('The saved package was removed from this browser.');
    } catch (reason) {
      if (token === revision.current && authorisedRef.current) setError(reason instanceof Error ? reason.message : 'Could not remove the local package.');
    } finally {
      if (token === revision.current) setBusy(false);
    }
  };

  const exportOriginal = () => {
    if (!authorised || !decoded) return;
    saveBlob(new Blob([decoded.raw_envelope], { type: 'application/json' }), `${decoded.payload.study_id}-original-package.json`);
  };

  const exportSummary = () => {
    if (!authorised || !decoded) return;
    saveBlob(new Blob([stabilitySummaryCsv(decoded.payload)], { type: 'text/csv;charset=utf-8' }), `${decoded.payload.study_id}-summary.csv`);
  };

  const evaluation = decoded?.payload.splits.find(split => split.name === 'evaluation');
  const evaluationStats = evaluation ? splitSummary(evaluation) : null;
  const scope=field(decoded?.payload.provenance,'source_reuse_scope');
  const independenceReview=isRecord(scope)&&scope.question_disjoint===true&&scope.answer_evidence_disjoint===true
    ? 'Independent review is still needed to verify frozen, unseen questions and answer-bearing evidence; source-conversation reuse is described below.'
    : 'Independent review is still needed to verify the split was frozen and unseen.';
  const heldOutReadiness = !evaluation ? 'Not included. This package contains no evaluation split.'
    : evaluationStats!.errors + evaluationStats!.missing > 0
      ? `Evaluation split present but incomplete: ${evaluationStats!.completed} graded cells, ${evaluationStats!.errors} ${evaluationStats!.errors === 1 ? 'error' : 'errors'}, ${evaluationStats!.missing} missing. ${independenceReview}`
      : `All ${evaluationStats!.planned} planned evaluation cells have grades. ${independenceReview}`;

  return <section className="research-workspace stability-study-workspace" aria-labelledby="stability-study-title">
    <h3 id="stability-study-title">Stability-study results · local package</h3>
    <p>Import a prepared results package to inspect its protocol, development and evaluation splits, original result grades, separate safety checks, repeat consistency, replay receipts and per-question traces. This panel is read-only and makes no API calls.</p>
    <UICheckbox aria-label="Stability-study package authorisation" checked={authorised} onChange={event => changeAuthorisation(event.target.checked)}>
      I am authorised to open this study package in this browser. Checking allows this browser to read the selected file or restore a saved local copy. No package is sent to the Auditor server. Saving is a separate action and stores the exact package in this browser’s IndexedDB.
    </UICheckbox>
    <p className="stability-privacy-note">The SHA-256 check covers the exact UTF-8 payload text and detects changes; it does not prove who created the package, whether its labels or model claims are true, or whether evaluation data remained unseen. The package may contain research questions, reference answers and model answers. Remove the saved copy when it is no longer needed.</p>
    <div className="stability-import-controls">
      <label htmlFor="stability-study-package-file">Study results JSON</label>
      <input id="stability-study-package-file" aria-label="Study results JSON" className="ui-input" type="file" accept="application/json,.json" disabled={!authorised || busy} onChange={selectFile} />
      <p>{pendingFile ? `${pendingFile.name} selected.` : 'No file selected.'}</p>
      <div className="research-actions">
        <UIButton disabled={!authorised || !pendingFile || busy} onClick={importSelected}>{busy ? 'Reading or checking package…' : 'Read and verify package'}</UIButton>
        <UIButton className="secondary" disabled={!authorised || !savedAvailable || busy} onClick={restoreSaved}>Restore saved package</UIButton>
        <UIButton className="secondary" disabled={!authorised || !savedAvailable || busy} onClick={removeLocal}>Remove saved package</UIButton>
      </div>
    </div>
    {error && <p className="stability-error" role="alert">{error}</p>}
    {notice && <p className="research-message" role="status">{notice}</p>}
    {!authorised && <p role="status">Package reading and restore are disabled until you check the authorisation box.</p>}
    {decoded && authorised && <div className="research-report stability-study-report" role="status">
      <h4>Imported study package</h4>
      <p><b>Study:</b> {decoded.payload.study_id} · <b>Created:</b> {decoded.payload.created_at}</p>
      <p className="stability-hash"><b>Payload SHA-256 verified:</b> <code>{decoded.sha256_verified}</code></p>
      <p>Integrity check only. It does not authenticate the source or validate research claims.</p>
      <p><b>Held-out readiness:</b> {heldOutReadiness}</p>
      <RecordedCaseSourceReviews splits={decoded.payload.splits} />
      <AcceptanceOverview evidence={decoded.payload.acceptance_results} replay={decoded.payload.replay} />
      <SourceReuseScope provenance={decoded.payload.provenance} />
      <div className="research-actions">
        <UIButton disabled={busy} onClick={saveLocal}>Save latest package on this browser</UIButton>
        <UIButton className="secondary" onClick={exportOriginal}>Export original envelope</UIButton>
        <UIButton className="secondary" onClick={exportSummary}>Download summary CSV</UIButton>
      </div>
      {decoded.payload.splits.map(split => <SplitReport split={split} key={split.name} />)}
      <p className="stability-grade-note">Development and evaluation are displayed separately. The safety-guards split contains engineering checks and is never pooled with benchmark results. Source review is shown separately and does not change the package’s original grade. Lexical word overlap is not reported as a semantic score. Missing and errored runs remain visible and are never counted as uncertain or incorrect.</p>
      <AuxiliaryReport evidence={decoded.payload.auxiliary_analysis} protocol={decoded.payload.protocol} />
      <details className="stability-technical-evidence">
        <summary>Technical evidence and limitations</summary>
        <section className="stability-package-meta"><h5>Protocol</h5><pre>{printable(decoded.payload.protocol)}</pre><h5>Provenance</h5><pre>{printable(decoded.payload.provenance)}</pre><h5>Acceptance results</h5><pre>{printable(decoded.payload.acceptance_results)}</pre><h5>Replay proof</h5><pre>{printable(decoded.payload.replay)}</pre>
          <h5>Limitations</h5>{decoded.payload.limitations.length ? <ul>{decoded.payload.limitations.map((item, index) => <li key={`${index}:${item}`}>{item}</li>)}</ul> : <p>No limitations were recorded in this package.</p>}
        </section>
      </details>
    </div>}
  </section>;
}
