import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import { JudgmentDifferences } from './JudgmentDifferences';
import { UIAlert, UIButton, UICard, UIInput, UISelect, UIOption } from './ui';
import type { ExperimentStatisticsRun } from './ExperimentStatistics';
import type { AuditResult, Dimension, EvaluationReviewItem, BlindEvaluationReviewItem } from '../types/domain';

const Charts = lazy(() => import('./ResultVisualizations').then(module => ({default:module.ComparisonVisualizations})));
const dimensionLabels: Record<Dimension,string> = {accuracy:'Accuracy',freshness:'Freshness',conflict_resolution:'Conflict Resolution',appropriate_use:'Appropriate Use'};

/** Presentation overlay from persisted resolved labels. Automated audit evidence is immutable. */
export function reviewedChartResult(original: AuditResult, items: EvaluationReviewItem[]): AuditResult {
  if (!items.some(item => item.human_review)) return original;
  const verdict = (item: EvaluationReviewItem) => item.human_review?.human_passed ?? item.automated.passed;
  const dimensions = original.dimensions.map(score => {
    const rows = items.filter(item => item.test.dimension === score.dimension);
    const decided = rows.filter(item => verdict(item) !== null);
    const passed = decided.filter(item => verdict(item) === true).length;
    return {...score,passed,total:decided.length,percentage:decided.length ? passed/decided.length*100 : null,uncertain_count:rows.length-decided.length};
  });
  const measured = dimensions.flatMap(score => score.percentage === null ? [] : [score.percentage]);
  return {...original,dimensions,overall_score:measured.length ? measured.reduce((sum,value)=>sum+value,0)/measured.length : null,
    tests_passed:items.filter(item=>verdict(item)===true).length,tests_total:items.filter(item=>verdict(item)!==null).length,
    uncertain_count:items.filter(item=>verdict(item)===null).length,evaluated_count:items.length};
}

type ReviewRow = {run:ExperimentStatisticsRun;item:EvaluationReviewItem;sources?:BlindEvaluationReviewItem['source_statements']};
export function ReviewedMethodComparison({runs}: {runs:ExperimentStatisticsRun[]}) {
  return <ReviewedMethodSession key={runs.map(run=>run.result.run_id).join(",")} runs={runs}/>;
}
function ReviewedMethodSession({runs}: {runs:ExperimentStatisticsRun[]}) {
  const [reviews,setReviews] = useState<Record<string,EvaluationReviewItem[]>>({});
  const [sources,setSources] = useState<Record<string,BlindEvaluationReviewItem['source_statements']>>({});
  const [reviewer,setReviewer] = useState('');
  const [notes,setNotes] = useState<Record<string,string>>({});
  const [categories,setCategories] = useState<Record<string,Dimension>>({});
  const [loading,setLoading] = useState(true);
  const [saving,setSaving] = useState(false);
  const [error,setError] = useState('');
  const [confirmation,setConfirmation] = useState('');
  const generation = useRef(0);
  const runKey = runs.map(run=>run.result.run_id).join(',');
  const load = useCallback(async () => {
    const version = ++generation.current;
    setLoading(true);setError('');
    try {
      const batches = await Promise.all(runKey.split(',').filter(Boolean).map(async id => {
        const items = await api.evaluationReview(id);
        const pending = items.some(item=>item.automated.passed===null&&!item.human_review);
        const blind = pending ? await api.blindEvaluationReview(id) : [];
        return {id,items,blind};
      }));
      if (version !== generation.current) return;
      setReviews(Object.fromEntries(batches.map(batch=>[batch.id,batch.items])));
      setSources(Object.fromEntries(batches.flatMap(batch=>batch.blind.map(item=>[item.automated.evaluation_id,item.source_statements]))));
    } catch (cause) {if(version===generation.current)setError(cause instanceof Error?cause.message:'Review data could not be loaded.');}
    finally {if(version===generation.current)setLoading(false);}
  },[runKey]);
  useEffect(()=>{void load();return()=>{generation.current++;};},[load]);
  useEffect(()=>{
    const refresh=()=>{if(document.visibilityState==='visible'&&!saving)void load();};
    window.addEventListener('focus',refresh);
    document.addEventListener('visibilitychange',refresh);
    return()=>{window.removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',refresh);};
  },[load,saving]);
  const pending:ReviewRow[] = runs.flatMap(run=>(reviews[run.result.run_id]??[]).filter(item=>item.automated.passed===null&&!item.human_review).map(item=>({run,item,sources:sources[item.automated.evaluation_id]})));
  const resolved = Object.values(reviews).flat().filter(item=>item.human_review).length;
  const chartRuns = runs.map(run=>({...run,result:reviewedChartResult(run.result,reviews[run.result.run_id]??[])}));
  const save = async ({run,item}:ReviewRow,passed:boolean) => {
    const id = item.automated.evaluation_id;
    if(!reviewer.trim()||(!passed&&!categories[id])) return;
    setSaving(true);setError('');setConfirmation('');
    try {
      const saved = await api.reviewEvaluation(run.result.run_id,id,{human_passed:passed,human_failure_type:passed?null:categories[id],reviewer_label:reviewer.trim(),review_role:'reference',based_on_review_ids:[],note:notes[id]?.trim()||undefined});
      // Use the acknowledged saved record immediately, then reconcile with storage.
      setReviews(current=>({...current,[run.result.run_id]:(current[run.result.run_id]??[]).map(row=>row.automated.evaluation_id===id?{...row,human_review:saved,human_reviews:[...row.human_reviews.filter(review=>review.review_id!==saved.review_id),saved]}:row)}));
      setConfirmation(`Human ${passed?'Pass':'Fail'} saved. The chart has been updated.`);
      await load();
    } catch(cause){setError(cause instanceof Error?cause.message:'The review could not be saved.');}
    finally{setSaving(false);}
  };
  return <>
    {resolved>0&&<UIAlert role="status"><b>Human-reviewed chart · {resolved} resolved answers</b><p>Saved human reference/adjudication labels take priority in this chart; other answers retain automated judgments. Detailed reports preserve the original automated results. This is not independent blind validation.</p></UIAlert>}
    <Suspense fallback={<p role="status">Loading comparison charts…</p>}><Charts runs={chartRuns} hideFailureChart /></Suspense>
    <JudgmentDifferences runs={runs} reviews={reviews} ready={!loading && !error} />
    <section aria-label="Pending human review"><p>For independent calibration, assign the blind-review links before reviewers read model reports. Inline decisions below are reference labels.</p><ul>{runs.map((run,index)=><li key={run.result.run_id}><a href={`/blind-review/${run.result.run_id}`}>Independent review · Batch {index+1}</a></li>)}</ul><h2>Human review needed{pending.length?` (${pending.length})`:''}</h2><UIButton className="secondary" disabled={loading||saving} onClick={()=>void load()}>Refresh human reviews</UIButton>
      {confirmation&&<UIAlert role="status">{confirmation}</UIAlert>}
      {error&&<UIAlert role="alert">{error}<UIButton onClick={()=>void load()} disabled={saving||loading}>Retry loading reviews</UIButton></UIAlert>}
      {loading&&<p role="status">Loading answers for review…</p>}
      {!loading&&!error&&!pending.length&&<p>No automated judgments are awaiting resolution. Independent review is still needed to validate assessment accuracy.</p>}
      {pending.length>0&&<><p>Check the source, expected behaviour and answer. Saving a human reference label updates the chart automatically; the original automated judgment stays recorded.</p>
        <label>Reviewer name or pseudonym<UIInput aria-label="Reviewer name or pseudonym" value={reviewer} maxLength={80} disabled={saving} onChange={event=>setReviewer(event.target.value)} /></label>
        {pending.map(row=>{const {item}=row;const id=item.automated.evaluation_id;return <UICard key={id} className="evaluation-review-card">
          <h3>{dimensionLabels[item.test.dimension]}</h3><p>{row.run.label}</p>
          <p><b>Question:</b> {item.test.prompt}</p><p><b>Expected behaviour:</b> {item.test.expected_behavior}</p><p><b>Model answer:</b> {item.response.response_text}</p>
          <b>Supporting source statements</b>{row.sources?.length?<ul>{row.sources.map((source,index)=><li key={index}>{source.role?`${source.role}: `:""}{source.content}</li>)}</ul>:<p>Source excerpts are unavailable. Verify the original conversation before deciding.</p>}
          <div className="form-grid"><label>Failure category<UISelect aria-label={`Failure category for ${item.test.prompt}`} value={categories[id]??''} disabled={saving} onChange={event=>setCategories(current=>({...current,[id]:event.target.value as Dimension}))}><UIOption value="" disabled>Choose if marking Fail</UIOption>{Object.entries(dimensionLabels).map(([key,label])=><UIOption key={key} value={key}>{label}</UIOption>)}</UISelect></label>
          <label>Review note<UIInput aria-label={`Review note for ${item.test.prompt}`} value={notes[id]??''} disabled={saving} onChange={event=>setNotes(current=>({...current,[id]:event.target.value}))} /></label></div>
          <div className="row"><UIButton disabled={saving||loading||!reviewer.trim()} onClick={()=>void save(row,true)}>Confirm Pass</UIButton><UIButton className="danger" disabled={saving||loading||!reviewer.trim()||!categories[id]} onClick={()=>void save(row,false)}>Confirm Fail</UIButton></div>
        </UICard>;})}</>}
    </section>
  </>;
}
