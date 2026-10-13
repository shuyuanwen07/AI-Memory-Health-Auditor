import {useEffect,useRef,useState} from 'react';
import {Button,Progress,Tag} from 'antd';
import {api} from '../services/api';
import {memoryStrategyLabel,modelDisplayName} from '../services/display';
import {UIButton,UISelect,UIOption,UIAlert} from './ui';
import type {FormalMatrixCreateResponse,AcceptanceCheckReport,ReviewedSavedAcceptanceReport,SavedFormalRunPage} from '../types/domain';

export function FrozenThresholdCheck({matrix,dataset,predictions,onRestore,onRestorePending,executionBusy=false}:{matrix:FormalMatrixCreateResponse|null;dataset:object|null;predictions:object|null;onRestore?:(plan:FormalMatrixCreateResponse)=>void;onRestorePending?:(pending:boolean)=>void;executionBusy?:boolean}) {
  const [saved,setSaved]=useState<SavedFormalRunPage|null>(null);
  const [page,setPage]=useState(0);const [refresh,setRefresh]=useState(0);
  const [loading,setLoading]=useState(true);const [loadError,setLoadError]=useState('');
  useEffect(()=>{let current=true;setLoading(true);setLoadError('');
    api.savedFormalRuns(page*25).then(result=>{if(current){const last=Math.max(0,Math.ceil(result.total/25)-1);if(page>last){setSaved(null);setPage(last);}else setSaved(result);}}).catch(()=>{if(current){setSaved(null);setLoadError('Saved experiments could not be loaded. Try again.');}}).finally(()=>{if(current)setLoading(false);});
    return ()=>{current=false;};
  },[page,refresh,matrix]);
  const cached=(matrix?.scenarios||[]).flatMap((scenario,s)=>scenario.run_ids.map((id,c)=>({id,label:`Scenario ${s+1} · condition ${(matrix?.condition_count?c%matrix.condition_count:c)+1}${(matrix?.repetition_count??1)>1?` · run ${Math.floor(c/matrix!.condition_count)+1} of ${matrix!.repetition_count}`:''}`,criteria:!!matrix?.acceptance_protocol})));
  const stored=(saved?.items||[]).map((run,index)=>({id:run.run_id,label:`Saved run ${(saved?.offset||0)+index+1} · ${run.study_mode==='formal_experiment_b'?'Experiment B':'Exploratory'} · ${run.provider==='rule_based'?'Local rule-based baseline':modelDisplayName(run.model)} · ${memoryStrategyLabel(run.memory_strategy)}${run.repetition_index&&run.repetition_count?` · run ${run.repetition_index} of ${run.repetition_count}`:''} · ${new Date(run.created_at).toLocaleString()}${run.has_frozen_criteria?'':' · criteria unavailable'}`,criteria:run.has_frozen_criteria}));
  const runs=[...stored,...cached.filter(run=>!stored.some(item=>item.id===run.id))];
  const [selected,setSelected]=useState(runs[0]?.id||'');
  const effectiveSelected=runs.some(run=>run.id===selected)?selected:runs[0]?.id||'';
  const hasCriteria=!!runs.find(run=>run.id===effectiveSelected)?.criteria;
  const [report,setReport]=useState<AcceptanceCheckReport|ReviewedSavedAcceptanceReport|null>(null);
  const [error,setError]=useState(''); const [busy,setBusy]=useState(false); const [operation,setOperation]=useState<'saved'|'uploaded'|'restore'|null>(null);
  const revision=useRef(0); const active=useRef(false);
  useEffect(()=>{revision.current++;setReport(null);setError('');},[dataset,predictions,effectiveSelected,matrix,page,refresh]);
  const check=async()=>{
    if (!dataset || !predictions || active.current) return;
    active.current=true;setBusy(true);setOperation('uploaded');setReport(null);setError(''); const current=revision.current;
    try {const result=await api.checkFrozenThresholds({dataset,predictions,frozen_run_id:effectiveSelected});if (revision.current===current)setReport(result);}
    catch(reason){if(revision.current===current)setError(reason instanceof Error?reason.message:'Threshold check could not be completed.');}
    finally{active.current=false;setBusy(false);setOperation(null);}
  };
  const restore=async()=>{
    if (!effectiveSelected || active.current || executionBusy || !onRestore) return;
    active.current=true;onRestorePending?.(true);setBusy(true);setOperation('restore');setError('');const current=revision.current;
    try {const plan=await api.restoreFormalPlan(effectiveSelected);if(revision.current===current)onRestore(plan);}
    catch(reason){if(revision.current===current)setError(reason instanceof Error?reason.message:'The saved execution plan could not be restored.');}
    finally{active.current=false;onRestorePending?.(false);setBusy(false);setOperation(null);}
  };
  const checkSaved=async()=>{
    if (!effectiveSelected || active.current) return;
    active.current=true;setBusy(true);setOperation('saved');setReport(null);setError('');const current=revision.current;
    try {const result=await api.checkReviewedSavedThresholds(effectiveSelected);if(revision.current===current)setReport(result);}
    catch(reason){if(revision.current===current)setError(reason instanceof Error?reason.message:'Saved review check could not be completed.');}
    finally {active.current=false;setBusy(false);setOperation(null);}
  };
  return <section aria-label="Frozen threshold check"><h3>Do the results meet the saved thresholds?</h3>
    <p>Choose a saved experiment. Check its reviewed answers directly, or compare uploaded evidence with its saved criteria.</p>
    {loading&&<p role="status">Loading saved experiments…</p>}
    {loadError&&<UIAlert role="alert">{loadError}</UIAlert>}
    {!loading&&!runs.length&&!loadError&&<p>No frozen experiments saved yet. Create a reviewed experiment first.</p>}
    <UIButton disabled={busy||loading} onClick={()=>setRefresh(value=>value+1)}>Refresh saved experiments</UIButton>
    {saved&&saved.total>25&&<nav aria-label="Saved threshold experiment pages"><UIButton disabled={busy||loading||page===0} onClick={()=>setPage(value=>value-1)}>Previous saved experiments</UIButton><span>Page {page+1} of {Math.ceil(saved.total/25)}</span><UIButton disabled={busy||loading||(page+1)*25>=saved.total} onClick={()=>setPage(value=>value+1)}>Next saved experiments</UIButton></nav>}
    <label>Saved experiment<UISelect aria-label="Threshold reference experiment" value={effectiveSelected} onChange={event=>setSelected(event.target.value)} disabled={busy||loading||!runs.length}>{runs.map(run=><UIOption key={run.id} value={run.id}>{run.label}</UIOption>)}</UISelect></label>
    {effectiveSelected && <div><Button type="link" href={`/audits/${encodeURIComponent(effectiveSelected)}`}>Review these answers</Button><Button type="link" href={`/blind-review/${encodeURIComponent(effectiveSelected)}`}>Independent blind review</Button></div>}
    {onRestore&&<><UIButton disabled={busy||loading||executionBusy||!effectiveSelected||!hasCriteria} onClick={restore}>{operation==='restore'?'Restoring execution plan…':'Restore execution plan'}</UIButton><p>Restores the complete saved plan. Model calls start only when you choose to run it.</p></>}
    <UIButton disabled={busy||!hasCriteria||!effectiveSelected||loading} onClick={checkSaved}>{operation==='saved'?'Checking saved reviews…':'Check reviewed saved answers'}</UIButton>
    <p>Uses the selected experiment’s saved answers and resolved review labels. No files or new model calls are required. Missing labels remain unmeasured.</p>
    <p>For uploaded evidence, use the full matching annotation release and predictions for this scenario only.</p>
    <UIButton disabled={busy||!dataset||!predictions||!hasCriteria||!effectiveSelected||loading} onClick={check}>{operation==='uploaded'?'Checking thresholds…':'Check frozen thresholds'}</UIButton>
    {error&&<UIAlert role="alert">{error}</UIAlert>}
    {report&&<>{'review_coverage' in report ? <section aria-label="Saved review coverage"><h4>Actual-answer review coverage</h4><p>{report.review_coverage.resolved_labels}/{report.review_coverage.expected_tests} resolved · {report.review_coverage.missing_labels} missing · {report.review_coverage.ambiguous_tests} ambiguous</p><p>{report.review_coverage.independently_adjudicated} with two recorded reviewers and a current final decision. Reviewer names do not prove human independence.</p></section> : report.saved_evidence_binding ? <section aria-label="Saved answer verification"><h4>Do these results belong to the selected experiment?</h4><Tag color={report.saved_evidence_binding.status==='verified'?'green':'orange'}>{report.saved_evidence_binding.status==='verified'?'Saved answers verified':'Saved evidence incomplete'}</Tag><p>{report.saved_evidence_binding.matched}/{report.saved_evidence_binding.reference_cases} matched · {report.saved_evidence_binding.missing} missing · {report.saved_evidence_binding.mismatched} mismatched · {report.saved_evidence_binding.ambiguous} ambiguous</p><small>Checks the selected scenario and condition. Numerical thresholds below describe supplied evidence; saved-result acceptance also requires this verification. {report.saved_evidence_binding.notice}</small></section> : <p>Saved-answer verification: Not recorded. These values check supplied evidence only.</p>}<p role="status">{report.saved_result_thresholds_met?'Saved evidence matches and all numerical thresholds are met. Independent evidence is still required.':report.all_thresholds_met?'Supplied numerical thresholds met; saved-result acceptance is not established.':'Some thresholds are unmet or lack evidence.'}</p>
      <div role="img" aria-label={report.measures.map(row=>`${row.label}: ${row.observed_percent===null?'Not measured':`${row.observed_percent.toFixed(1)}%`}; ${row.status.replaceAll('_',' ')}`).join('; ')}>
        {report.measures.map(row=><div key={row.key} style={{marginBottom:18}}><b>{row.label}</b> <Tag color={row.status==='meets_threshold'?'green':row.status==='threshold_not_met'?'red':'orange'}>{row.status==='meets_threshold'?'Meets threshold':row.status==='threshold_not_met'?'Does not meet':'Insufficient evidence'}</Tag>
          <p>{row.observed_percent===null?'Not measured':`${Number(row.observed_percent.toFixed(1))}%`} · {row.numerator}/{row.denominator} cases · {row.direction==='minimum'?'minimum':'maximum'} {row.threshold_percent}%</p>
          {row.observed_percent!==null&&<Progress percent={row.observed_percent} showInfo={false} strokeColor={row.status==='meets_threshold'?'#16806a':'#b7791f'} />}
          <small>{row.definition} {row.reason}</small></div>)}
      </div><p>{report.notice}</p></>}
  </section>;
}
