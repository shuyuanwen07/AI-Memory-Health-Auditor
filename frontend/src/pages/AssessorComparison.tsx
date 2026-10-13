import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Progress, Select, Tag } from 'antd';
import { api } from '../services/api';
import { memoryStrategyLabel, modelDisplayName } from '../services/display';
import { comparisonColours } from '../services/chartColours';
import { ModelPicker } from '../components/ModelPicker';
import { CurrentModelPreset } from '../components/CurrentModelPreset';
import { AssessorOperationCharts } from '../components/AssessorOperationCharts';
import { UIAlert, UIButton, UIPanel, UISummary } from '../components/ui';
import type { AssessorComparisonBatch, AuditRun } from '../types/domain';

const Charts = lazy(()=>import('../components/ResultVisualizations').then(module=>({default:module.ComparisonVisualizations})));
const assessorName = (entry:AssessorComparisonBatch['entries'][number])=>entry.selection.evaluator_provider==='rule_based'
  ? 'Rules' : modelDisplayName(entry.selection.evaluator_model ?? 'Selected model');
const sourceName = (run:AuditRun)=>`${modelDisplayName(run.model)} · ${memoryStrategyLabel(run.memory_strategy)} · ${new Date(run.created_at).toLocaleString()}`;

export function AssessorComparisonPage() {
  const [params,setParams] = useSearchParams();
  const id = params.get('comparison') ?? '';
  const [source,setSource] = useState(params.get('source') ?? '');
  const [models,setModels] = useState('');
  const [audits,setAudits] = useState<AuditRun[]>([]);
  const [saved,setSaved] = useState<AssessorComparisonBatch[]>([]);
  const [batch,setBatch] = useState<AssessorComparisonBatch|null>(null);
  const [loading,setLoading] = useState(true);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [step,setStep] = useState('');
  const generation = useRef(0);
  const running = useRef(false);
  const actionEpoch = useRef(0);
  const actionBatch = useRef('');
  const requestKey = useRef('');
  useEffect(()=>()=>{actionEpoch.current++;},[]);
  useEffect(()=>{requestKey.current='';},[source,models]);
  useEffect(()=>{
    if(running.current && actionBatch.current===id){setLoading(false);return;}
    if(running.current){actionEpoch.current++;running.current=false;setBusy(false);setStep('');}
    const version = ++generation.current;
    setLoading(true);setError('');setBatch(null);
    (id ? api.assessorComparison(id).then(value=>{if(version===generation.current)setBatch(value);})
      : Promise.all([api.audits(),api.assessorComparisons()]).then(([runs,groups])=>{
        if(version===generation.current){setAudits(runs.filter(run=>run.status==='COMPLETED'));setSaved(groups);}
      })).catch(cause=>{if(version===generation.current)setError(cause instanceof Error?cause.message:'Comparison could not be loaded.');})
      .finally(()=>{if(version===generation.current)setLoading(false);});
    return ()=>{generation.current++;};
  },[id]);
  const selected = [...new Set(models.split('\n').map(model=>model.trim()).filter(Boolean))];
  const invalidAlias = selected.some(model=>{const base=model.toLowerCase().split(':')[0];return base.endsWith('latest')||base==='openrouter/auto';});
  const resume = async()=>{
    if(running.current)return;
    const action=++actionEpoch.current;
    const stillCurrent=()=>action===actionEpoch.current;
    actionBatch.current=id;
    generation.current++;
    running.current=true;setBusy(true);setError('');
    let current=batch;
    try {
      if(!current){
        requestKey.current ||= crypto.randomUUID();
        current=await api.createAssessorComparison({creation_request_key:requestKey.current,source_run_id:source,
          assessors:[{evaluator_provider:'rule_based'},...selected.map(model=>({evaluator_provider:'openrouter' as const,evaluator_model:model}))]});
        if(!stillCurrent())return;
        actionBatch.current=current.comparison_id;
        setBatch(current);setParams({comparison:current.comparison_id});
      }
      setStep('Preparing the same saved answers');
      current=await api.prepareAssessorComparison(current.comparison_id);
      if(!stillCurrent())return;
      setBatch(current);
      const failures:string[]=[];
      for(const entry of current.entries){
        if(!stillCurrent())return;
        if(!entry.run || entry.run.status==='COMPLETED')continue;
        setStep(`Assessing with ${assessorName(entry)}`);
        try {
          let run=await api.getAudit(entry.run.run_id);
          if(!stillCurrent())return;
          if(run.status==='FAILED')run=await api.retry(run.run_id);
          if(!stillCurrent())return;
          if(run.status==='TESTS_EXECUTED')await api.evaluate(run.run_id);
          if(!stillCurrent())return;
          run=await api.getAudit(run.run_id);
          if(run.status!=='COMPLETED')throw new Error('Assessment is unfinished. Open its saved progress.');
        } catch(cause){failures.push(`${assessorName(entry)}: ${cause instanceof Error?cause.message:'Assessment could not finish.'}`);}
        const refreshed=await api.assessorComparison(current.comparison_id);
        if(!stillCurrent())return;
        setBatch(refreshed);
      }
      if(failures.length)setError(failures.join(' '));
    } catch(cause){
      if(!stillCurrent())return;
      setError(cause instanceof Error?cause.message:'The comparison could not finish. Saved results are retained.');
      if(current)try{const refreshed=await api.assessorComparison(current.comparison_id);if(stillCurrent())setBatch(refreshed);}catch{/* Keep last confirmed saved progress. */}
    } finally {if(stillCurrent()){running.current=false;setBusy(false);setStep('');}}
  };
  const completed=batch?.entries.filter(entry=>entry.run?.status==='COMPLETED'&&entry.result).length ?? 0;
  const chartRuns=batch?.entries.flatMap((entry,index)=>entry.result?[{label:assessorName(entry),groupLabel:assessorName(entry),colour:comparisonColours[index%comparisonColours.length],
    groupKey:`${entry.selection.evaluator_provider}:${entry.selection.evaluator_model ?? 'rules'}`,result:entry.result}]:[]) ?? [];
  return <section className="page"><h1>Compare AI assessors</h1>
    <p>{batch&&!batch.inputs_match?'Saved reports · Comparison inputs unverified':'Same questions · Same saved answers · Different assessors'}</p>
    {loading&&<p role="status">Loading saved progress…</p>}
    {error&&<UIAlert role="alert">{error}</UIAlert>}
    {!id&&!loading&&<>
      <label>Answers to assess<Select aria-label="Answers to assess" className="ui-select" style={{width:'100%'}} showSearch optionFilterProp="label"
        value={source||undefined} disabled={busy} onChange={setSource} placeholder="Choose a completed audit"
        options={audits.map(run=>({value:run.run_id,label:sourceName(run)}))}/></label>
      <label>OpenRouter assessors<ModelPicker provider="openrouter" label="OpenRouter assessors" multiple value={models} disabled={busy} onChange={setModels}/></label>
      <CurrentModelPreset disabled={busy} onSelect={setModels}/>
      <p>Choose up to four models. Rules are included as a baseline. AI review requests may incur charges.</p>
      {invalidAlias&&<UIAlert role="status">Choose fixed model names instead of automatic or latest aliases.</UIAlert>}
      <UIButton disabled={busy||!source||selected.length<1||selected.length>4||invalidAlias} onClick={()=>void resume()}>Start assessor comparison</UIButton>
      {saved.length>0&&<UIPanel><UISummary>Saved comparisons</UISummary>{saved.map(item=><p key={item.comparison_id}>
        <a href={`/assessor-models?comparison=${item.comparison_id}`}>{new Date(item.created_at).toLocaleString()} · {item.entries.map(assessorName).join(' · ')}</a></p>)}</UIPanel>}
    </>}
    {batch&&<>
      <p>{sourceName(batch.source)}</p>
      <Progress percent={Math.round(completed/batch.entries.length*100)} format={()=>`${completed} of ${batch.entries.length} complete`}/>
      {step&&<p role="status">{step}</p>}
      {!batch.runtime_matches&&<UIAlert role="status">Software changed. Saved results remain available; start a new comparison to use current software.</UIAlert>}
      {!batch.inputs_match&&<UIAlert role="status">We cannot verify that the reference facts, questions and saved answers still match. View saved reports or start a new comparison.</UIAlert>}
      <div className="provider-grid">{batch.entries.map((entry,index)=><div className="target" key={index}>
        <strong>{assessorName(entry)}</strong><Tag color={entry.result?'green':entry.run?.status==='FAILED'?'red':'gold'}>
          {entry.result?'Complete':entry.run?.status==='FAILED'?'Needs attention':entry.run?'Ready to assess':'Awaiting preparation'}</Tag>
        {entry.result&&<span>{entry.result.tests_passed} passed · {entry.result.tests_total-entry.result.tests_passed} failed · {entry.result.uncertain_count??0} awaiting review</span>}
        {entry.run&&<a href={entry.result?`/audits/${entry.run.run_id}`:'/history'}>{entry.result?'Inspect answers & evidence':'Open saved progress'}</a>}
      </div>)}</div>
      <p>Bars show automated pass rates, not assessor accuracy. Pending answers are excluded; lower or higher scores alone do not identify a better assessor.</p>
      {batch.inputs_match&&chartRuns.length>0&&<Suspense fallback={<p>Loading chart…</p>}><Charts runs={chartRuns} compact hideFailureChart singleSetting={chartRuns.length===1}/></Suspense>}
      {batch.inputs_match&&<AssessorOperationCharts entries={batch.entries}/>}
      <UIButton disabled={busy||!batch.runtime_matches||!batch.inputs_match||completed===batch.entries.length} onClick={()=>void resume()}>{busy?'Comparing assessors…':'Continue unfinished assessments'}</UIButton>
      <a href="/assessor-models">Start another comparison</a>
      <UIPanel><UISummary>What this comparison establishes</UISummary><p>Only the assessor changes. No new target call is made. Independent reference decisions are required to measure assessor accuracy. Recorded time and credits describe the saved assessor calls; unknown observations are not zero.</p></UIPanel>
    </>}
  </section>;
}
