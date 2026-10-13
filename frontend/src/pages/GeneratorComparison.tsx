import {lazy,Suspense,useEffect,useRef,useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {Progress,Select,Tag} from 'antd';
import {api} from '../services/api';
import {memoryStrategyLabel,modelDisplayName,friendlyText} from '../services/display';
import {comparisonColours} from '../services/chartColours';
import {ModelPicker} from '../components/ModelPicker';
import {CurrentModelPreset} from '../components/CurrentModelPreset';
import {GeneratorQualityCharts,generatorName} from '../components/GeneratorQualityCharts';
import {InitialGenerationCharts} from '../components/InitialGenerationCharts';
import {GeneratorUsageCharts} from '../components/GeneratorUsageCharts';
import {TestSuiteReview} from '../components/TestSuiteReview';
import {UIAlert,UIButton,UIPanel,UISummary} from '../components/ui';
import type {AuditRun,GeneratorComparisonBatch,TestCase} from '../types/domain';

const Charts=lazy(()=>import('../components/ResultVisualizations').then(module=>({default:module.ComparisonVisualizations})));
const sourceLabel=(run:AuditRun)=>`${modelDisplayName(run.model)} · ${memoryStrategyLabel(run.memory_strategy)} · ${new Date(run.created_at).toLocaleString()}`;

export function GeneratorComparisonPage(){
  const [params,setParams]=useSearchParams();const id=params.get('comparison')??'';
  const [source,setSource]=useState(params.get('source')??'');const [models,setModels]=useState('');
  const [audits,setAudits]=useState<AuditRun[]>([]);const [saved,setSaved]=useState<GeneratorComparisonBatch[]>([]);
  const [batch,setBatch]=useState<GeneratorComparisonBatch|null>(null);
  const [questions,setQuestions]=useState<Record<string,TestCase[]>>({});
  const [loading,setLoading]=useState(true);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [step,setStep]=useState('');
  const loadVersion=useRef(0);const actionEpoch=useRef(0);const running=useRef(false);const actionBatch=useRef('');const requestKey=useRef('');
  useEffect(()=>()=>{actionEpoch.current++;},[]);
  useEffect(()=>{requestKey.current='';},[source,models]);
  useEffect(()=>{
    if(running.current&&actionBatch.current===id){setLoading(false);return;}
    if(running.current){actionEpoch.current++;running.current=false;setBusy(false);setStep('');}
    const version=++loadVersion.current;setLoading(true);setError('');setBatch(null);setQuestions({});
    (id?api.generatorComparison(id).then(value=>{if(version===loadVersion.current)setBatch(value);})
      :Promise.all([api.audits(),api.generatorComparisons()]).then(([runs,groups])=>{
        if(version===loadVersion.current){setAudits(runs.filter(run=>run.status==='COMPLETED'&&run.target_memory_writer==='rule_based'&&run.target_system_adapter==='controlled-memory'));setSaved(groups);}
      })).catch(cause=>{if(version===loadVersion.current)setError(cause instanceof Error?cause.message:'Saved comparison could not be loaded.');})
      .finally(()=>{if(version===loadVersion.current)setLoading(false);});
    return()=>{loadVersion.current++;};
  },[id]);
  const selected=[...new Set(models.split('\n').map(value=>value.trim()).filter(Boolean))];
  const invalidAlias=selected.some(model=>{const base=model.toLowerCase().split(':')[0];return base.endsWith('latest')||base==='openrouter/auto';});
  const work=async(mode:'generate'|'run')=>{
    if(running.current)return;
    const epoch=++actionEpoch.current;const currentAction=()=>epoch===actionEpoch.current;
    running.current=true;actionBatch.current=id;loadVersion.current++;setBusy(true);setError('');
    let current=batch;
    try{
      if(!current){
        requestKey.current ||= crypto.randomUUID();
        current=await api.createGeneratorComparison({creation_request_key:requestKey.current,source_run_id:source,
          generators:[{provider:'rule_based'},...selected.map(model=>({provider:'openrouter' as const,model}))]});
        if(!currentAction())return;
        actionBatch.current=current.comparison_id;setBatch(current);setParams({comparison:current.comparison_id});
      }
      setStep('Preparing fixed target settings');
      current=await api.prepareGeneratorComparison(current.comparison_id);if(!currentAction())return;setBatch(current);
      const failures:string[]=[];
      for(const entry of current.entries){
        if(!currentAction())return;
        if(!entry.run||entry.run.status==='COMPLETED')continue;
        setStep(`${mode==='generate'?'Generating questions':'Testing target'} · ${generatorName(entry)}`);
        try{
          let run=await api.getAudit(entry.run.run_id);if(!currentAction())return;
          if(run.status==='FAILED')run=await api.retry(run.run_id);if(!currentAction())return;
          if(mode==='generate'&&run.status==='CREATED'){
            await api.generate(run.run_id);if(!currentAction())return;run=await api.getAudit(run.run_id);
          }
          if(mode==='run'){
            if(run.status==='CREATED')throw new Error('Generate and inspect questions before running this condition.');
            if(run.status==='TESTS_GENERATED'){await api.execute(run.run_id);if(!currentAction())return;run=await api.getAudit(run.run_id);}
            if(run.status==='TESTS_EXECUTED'){await api.evaluate(run.run_id);if(!currentAction())return;run=await api.getAudit(run.run_id);}
            if(run.status!=='COMPLETED')throw new Error('This condition is unfinished. Inspect its saved progress.');
          }
          if(run.status==='CANCELLED')throw new Error('This condition was cancelled. Its saved evidence remains available.');
        }catch(cause){failures.push(`${generatorName(entry)}: ${cause instanceof Error?cause.message:'Condition could not finish.'}`);}
        const refreshed=await api.generatorComparison(current.comparison_id);if(!currentAction())return;setBatch(refreshed);
      }
      if(currentAction()&&failures.length)setError(failures.join(' '));
    }catch(cause){
      if(!currentAction())return;
      setError(cause instanceof Error?cause.message:'The comparison could not finish. Saved progress is retained.');
      if(current)try{const refreshed=await api.generatorComparison(current.comparison_id);if(currentAction())setBatch(refreshed);}catch{/* Keep last confirmed state. */}
    }finally{if(currentAction()){running.current=false;setBusy(false);setStep('');}}
  };
  const inspect=async(runId:string)=>{
    if(busy)return;const epoch=++actionEpoch.current;running.current=true;actionBatch.current=id;setBusy(true);setError('');
    try{const suite=await api.testReview(runId);if(epoch===actionEpoch.current)setQuestions(previous=>({...previous,[runId]:suite.tests}));}
    catch(cause){if(epoch===actionEpoch.current)setError(cause instanceof Error?cause.message:'Questions could not be loaded.');}
    finally{if(epoch===actionEpoch.current){running.current=false;setBusy(false);}}
  };
  const changeQuestion=async(test:TestCase,decision?:'accepted'|'rejected',note?:string)=>{
    if(busy||!batch)return;const epoch=++actionEpoch.current;running.current=true;actionBatch.current=id;setBusy(true);setError('');
    try{
      if(decision)await api.reviewTest(test.run_id,test.test_id,decision,note);else await api.regenerateTest(test.run_id,test.test_id);
      if(epoch!==actionEpoch.current)return;
      const suite=await api.testReview(test.run_id);if(epoch!==actionEpoch.current)return;
      setQuestions(previous=>({...previous,[test.run_id]:suite.tests}));
      const refreshed=await api.generatorComparison(batch.comparison_id);if(epoch===actionEpoch.current)setBatch(refreshed);
    }catch(cause){if(epoch===actionEpoch.current)setError(cause instanceof Error?cause.message:'The question could not be updated.');}
    finally{if(epoch===actionEpoch.current){running.current=false;setBusy(false);}}
  };
  const generated=batch?.entries.filter(entry=>entry.quality.saved_questions>0).length??0;
  const completed=batch?.entries.filter(entry=>entry.result).length??0;
  const valid=batch?.runtime_matches&&batch.inputs_match;
  const readyForTarget=batch?.entries.some(entry=>entry.run&&['TESTS_GENERATED','TESTS_EXECUTED','FAILED'].includes(entry.run.status)&&entry.quality.accepted>0&&entry.quality.rejected===0&&entry.quality.pending===0);
  const needsQuestions=batch?.entries.some(entry=>entry.quality.saved_questions===0&&entry.run?.status!=='COMPLETED'&&entry.run?.status!=='CANCELLED');
  const chartRuns=batch?.entries.flatMap((entry,index)=>entry.result?[{label:generatorName(entry),groupLabel:generatorName(entry),
    groupKey:`${entry.selection.provider}:${entry.selection.model??'rules'}`,colour:comparisonColours[index%comparisonColours.length],result:entry.result}]:[])??[];
  return <section className="page"><h1>Compare test generators</h1><p>Different questions · Same reference memories · Fixed target settings</p>
    {loading&&<p role="status">Loading saved progress…</p>}{error&&<UIAlert role="alert">{friendlyText(error)}</UIAlert>}
    {!id&&!loading&&<>
      <label>Reference audit<Select aria-label="Reference audit" className="ui-select" style={{width:'100%'}} showSearch optionFilterProp="label" value={source||undefined} onChange={setSource} disabled={busy}
        placeholder="Choose a completed controlled audit" options={audits.map(run=>({value:run.run_id,label:sourceLabel(run)}))}/></label>
      <label>OpenRouter test generators<ModelPicker provider="openrouter" label="OpenRouter test generators" multiple value={models} onChange={setModels} disabled={busy}/></label>
      <CurrentModelPreset disabled={busy} onSelect={setModels}/>
      <p>Choose up to four models. Rules are included. Generating questions may incur charges; target testing is a separate step.</p>
      {invalidAlias&&<UIAlert role="status">Choose fixed model names instead of automatic or latest aliases.</UIAlert>}
      <UIButton disabled={busy||!source||selected.length<1||selected.length>4||invalidAlias} onClick={()=>void work('generate')}>Generate comparison questions</UIButton>
      {saved.length>0&&<UIPanel><UISummary>Saved generator comparisons</UISummary>{saved.map(item=><p key={item.comparison_id}><a href={`/generator-models?comparison=${item.comparison_id}`}>
        {new Date(item.created_at).toLocaleString()} · {item.entries.map(generatorName).join(' · ')}</a></p>)}</UIPanel>}
    </>}
    {batch&&<>
      <p>{sourceLabel(batch.source)}</p>
      <Progress percent={Math.round(completed/batch.entries.length*100)} format={()=>`${generated} of ${batch.entries.length} suites · ${completed} results`}/>
      {step&&<p role="status">{step}</p>}
      {!batch.inputs_match&&<UIAlert role="status">Reference inputs cannot be verified. Saved reports remain available; start a new comparison.</UIAlert>}
      {batch.inputs_match&&!batch.runtime_matches&&<UIAlert role="status">The software changed. Saved charts and reports are read-only; start a new comparison to run more tests.</UIAlert>}
      {batch.inputs_match&&<GeneratorQualityCharts entries={batch.entries}/>}
      {batch.inputs_match&&<InitialGenerationCharts entries={batch.entries}/>}
      {batch.inputs_match&&<GeneratorUsageCharts entries={batch.entries}/>}
      <div className="provider-grid">{batch.entries.map((entry,index)=><div className="target" key={index}>
        <strong>{generatorName(entry)}</strong><Tag color={entry.result?'green':entry.run?.status==='FAILED'?'red':'gold'}>
          {entry.result?'Complete':entry.run?.status==='CANCELLED'?'Cancelled':entry.run?.status==='FAILED'?'Needs attention':entry.quality.rejected||entry.quality.pending?'Review questions':entry.quality.saved_questions?'Questions saved':entry.generation?.latest_status==='failed'?'Generation failed':'Awaiting questions'}</Tag>
        {entry.run&&<>
          {entry.quality.saved_questions>0&&<UIButton disabled={busy} onClick={()=>void inspect(entry.run!.run_id)}>Inspect questions · {generatorName(entry)}</UIButton>}
          <a href={`/audits/${entry.run.run_id}`}>{entry.result?'Inspect answers & evidence':'Open saved progress'}</a>
        </>}
      </div>)}</div>
      {batch.entries.flatMap(entry=>entry.run&&questions[entry.run.run_id]?[<UIPanel key={entry.run.run_id} open><UISummary>{generatorName(entry)} · Question review</UISummary>
        <TestSuiteReview tests={questions[entry.run.run_id]} busy={busy||!valid||entry.run.status!=='TESTS_GENERATED'}
          onReview={(test,decision,note)=>void changeQuestion(test,decision,note)} onRegenerate={test=>void changeQuestion(test)}/>
      </UIPanel>]:[])}
      <div className="actions"><UIButton disabled={busy||!valid||!needsQuestions} onClick={()=>void work('generate')}>{busy?'Working…':'Continue question generation'}</UIButton>
        <UIButton disabled={busy||!valid||!readyForTarget||completed===batch.entries.length} onClick={()=>void work('run')}>Run target tests</UIButton></div>
      {chartRuns.length>0&&batch.inputs_match&&<><h2>Target answers to different question suites</h2><p>Different question difficulty can change scores. These bars do not establish a better generator or improved target memory.</p>
        <Suspense fallback={<p>Loading results chart…</p>}><Charts runs={chartRuns} compact hideFailureChart singleSetting={chartRuns.length===1}/></Suspense></>}
      <a href="/generator-models">Start another generator comparison</a>
    </>}
  </section>;
}
