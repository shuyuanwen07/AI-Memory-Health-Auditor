import { UICard, UIPanel, UISummary } from './ui';
import { friendlyText } from '../services/display';
import type { ExperimentStatisticsRun } from './ExperimentStatistics';
import type { EvaluationReviewItem } from '../types/domain';

const outcomes = [{label:'Pass',colour:'#16806a'},{label:'Fail',colour:'#b43f45'},{label:'Awaiting review',colour:'#b7791f'}];
const verdict = (value:boolean|null) => value===null?'Awaiting review':value?'Pass':'Fail';
const pct = (numerator:number,denominator:number) => denominator?`${Math.round(numerator/denominator*100)}%`:'Not measured';
const shortLabel = (run:ExperimentStatisticsRun) => (run.groupLabel??run.label).split(' · ').slice(-1)[0]??run.label;

/** Match only unambiguous questions within the same displayed target/strategy condition. */
export function judgmentDifferencePairs(runs:ExperimentStatisticsRun[],reviews:Record<string,EvaluationReviewItem[]>) {
  const buckets = new Map<string,{rule:EvaluationReviewItem[];hybrid:EvaluationReviewItem[];condition:string}>();
  runs.forEach(run=>{
    const name=run.groupLabel??run.label;
    const mode=name.endsWith('Model tests + rule review')?'rule':name.endsWith('Model tests + hybrid review')?'hybrid':null;
    if(!mode)return;
    const condition=name.slice(0,name.lastIndexOf(' · '));
    (reviews[run.result.run_id]??[]).forEach(item=>{
      const key=JSON.stringify([condition,item.test.dimension,item.test.prompt,item.test.expected_behavior]);
      const bucket=buckets.get(key)??{rule:[],hybrid:[],condition};bucket[mode].push(item);buckets.set(key,bucket);
    });
  });
  return [...buckets.values()].flatMap(bucket=>{
    const paired = bucket.hybrid.flatMap(hybrid=>{
      const receipt=hybrid.response.execution_metadata;
      if(!receipt?.shared_source_response_id)return [];
      const sources=bucket.rule.filter(rule=>rule.response.response_id===receipt.shared_source_response_id && rule.response.run_id===receipt.shared_source_run_id);
      return sources.length===1 && sources[0].automated.passed!==hybrid.automated.passed ? [{condition:bucket.condition,rule:sources[0],hybrid}] : [];
    });
    if(paired.length)return paired;
    if(bucket.rule.length!==1 || bucket.hybrid.length!==1 || bucket.hybrid[0].response.execution_metadata?.shared_source_response_id || bucket.rule[0].automated.passed===bucket.hybrid[0].automated.passed)return [];
    return [{condition:bucket.condition,rule:bucket.rule[0],hybrid:bucket.hybrid[0]}];
  });
}

export function JudgmentDifferences({runs,reviews,ready}: {runs:ExperimentStatisticsRun[];reviews:Record<string,EvaluationReviewItem[]>;ready:boolean}) {
  const pairs=judgmentDifferencePairs(runs,reviews);
  const summaries=runs.map(run=>{
    const rows=reviews[run.result.run_id];
    const counts=rows?[rows.filter(item=>item.automated.passed===true).length,rows.filter(item=>item.automated.passed===false).length,rows.filter(item=>item.automated.passed===null).length]:[run.result.tests_passed,Math.max(0,run.result.tests_total-run.result.tests_passed),run.result.uncertain_count??0];
    return {run,rows,counts,total:counts.reduce((sum,value)=>sum+value,0)};
  });
  return <section className="judgment-differences" aria-label="Audit judgment differences">
    <UICard className="visual-report-card"><h2>Automated Judgment Distribution</h2><p>What did each method decide? Original automated judgments stay visible here alongside saved reference labels.</p>
      <div className="chart-legend">{outcomes.map(outcome=><span key={outcome.label}><i style={{backgroundColor:outcome.colour}} />{outcome.label}</span>)}</div>
      {summaries.map(({run,counts,total})=><div className="judgment-distribution-row" key={run.result.run_id}>
        <b title={run.label}>{shortLabel(run)}</b>
        {total?<div className="judgment-distribution-bar" role="img" aria-label={`${run.label}: ${counts[0]} pass, ${counts[1]} fail, ${counts[2]} awaiting review, ${total} total`}>{counts.map((count,index)=>count>0&&<span key={outcomes[index].label} style={{width:`${count/total*100}%`,backgroundColor:outcomes[index].colour}} title={`${outcomes[index].label}: ${count} of ${total}`}><strong>{count}</strong></span>)}</div>:<p>No assessed answers</p>}
        <small>{counts[0]} pass · {counts[1]} fail · {counts[2]} awaiting review · {total} total</small>
      </div>)}
      <p className="judgment-limit">Bar width is the share of completed answers, and labels are counts. Different question suites or separately generated answers can change this distribution. A difference alone does not prove a better judge.</p>
    </UICard>
    <UICard className="visual-report-card"><h2>Where Judgments Differ</h2>
      <p>Rule and hybrid review on matching model-generated questions. New comparisons share one saved target answer; older comparisons may contain separate executions. Each case shows whether the shared-answer receipt is present. Repeated trials are paired by their saved-answer receipt. Historical ambiguous matches are excluded.</p>
      {!ready?<p>Load review records to see comparable cases.</p>:!pairs.length?<p>No unambiguous matching questions have different automated judgments in this batch.</p>:pairs.map(({rule,hybrid,condition},index)=><UIPanel key={rule.automated.evaluation_id} open={index===0}><UISummary>{rule.test.prompt} · {verdict(rule.automated.passed)} → {verdict(hybrid.automated.passed)}</UISummary>
        <p>{condition}</p><p><b>Expected behaviour:</b> {rule.test.expected_behavior}</p>
        <p className="judgment-limit">{hybrid.response.execution_metadata?.shared_source_response_id===rule.response.response_id && hybrid.response.execution_metadata?.shared_source_run_id===rule.response.run_id ? 'Controlled same-answer comparison: both evaluators scored the same saved target reply.' : rule.response.response_text===hybrid.response.response_text?'Answer text matches, but these are separate executions.':'Answer text differs; this case is not a controlled same-answer judge comparison.'}</p>
        <div className="judgment-case-grid">{[{label:'Rule review',item:rule},{label:'Hybrid review',item:hybrid}].map(({label,item})=><div key={label}><h3>{label} · {verdict(item.automated.passed)}</h3><p><b>Answer:</b> {item.response.response_text}</p><p><b>Reason:</b> {friendlyText(item.automated.reason)}</p><p><b>Saved reference label:</b> {item.human_review?verdict(item.human_review.human_passed):'Not reviewed'}{item.human_review?.note&&` · ${item.human_review.note}`}</p>{item.human_review&&<p><b>Recorded reviewer label:</b> {item.human_review.reviewer_label} · {item.human_review.review_role}</p>}</div>)}</div>
      </UIPanel>)}
    </UICard>
    <UIPanel><UISummary>Reference-label cross-check</UISummary>
      <p>These figures use saved reference/adjudication labels, not independent blind validation. The application cannot verify who or what supplied a label. Agreement and failure precision exclude automated abstentions; failure detection uses reference-labelled failures and includes cases where the automated result was uncertain. Unreviewed answers cannot establish evaluator accuracy.</p>
      {summaries.map(({run,rows})=>{
        const reviewed=(rows??[]).filter(item=>item.human_review);
        const decided=reviewed.filter(item=>item.automated.passed!==null);
        const agreements=decided.filter(item=>item.automated.passed===item.human_review!.human_passed).length;
        const flagged=decided.filter(item=>item.automated.passed===false);
        const trueFailures=flagged.filter(item=>item.human_review!.human_passed===false).length;
        const humanFailures=reviewed.filter(item=>item.human_review!.human_passed===false).length;
        return <div className="judgment-distribution-row" key={run.result.run_id}><b>{shortLabel(run)}</b><p>{reviewed.length} answers with saved reference labels · {decided.length} with a definitive automatic judgment</p><p>Agreement: {pct(agreements,decided.length)} · Failure precision: {pct(trueFailures,flagged.length)} · Failure detection: {pct(trueFailures,humanFailures)} · False positives: {reviewed.length ? `${flagged.length-trueFailures} among labelled answers` : 'Not measured'}</p></div>;
      })}
    </UIPanel>
  </section>;
}
