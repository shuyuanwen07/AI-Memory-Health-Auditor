import { Alert, Button, Card, Input, InputNumber, Select, Space, Table, Tag } from 'antd';
import { useState,useEffect,useRef } from 'react';
import { api } from '../services/api';
import { friendlyText } from '../services/display';
import { defaultTargetProfile, TargetProfileEditor, type TargetMemoryProfile } from './TargetProfileEditor';
import { TestSuiteReview } from './TestSuiteReview';
import type { TestCase,MemoryStrategy } from '../types/domain';
interface FactCorrespondence { expected_fact_units:number;stored_fact_units:number;supplied_fact_units:number|null;facts:Array<{reference_label:string;reference_text:string;stored_related_text:string[];supplied_related_text:string[]|null}> }
interface MemoryAvailability {expected_fact_units:number;observed_fact_units:number;eligible_fact_units:number;capacity_excluded_fact_units:number;facts:Array<{reference_label:string;reference_text:string;matching_record_eligibility:Array<{record_text:string;eligibility:string}>}>}
interface DiagnosisCase {input_delivery?:{expected_fact_units:number;retrieved_fact_units:number|null;selected_not_supplied_fact_units:number|null;context_budget_excluded_fact_units:number;profile_filter_excluded_fact_units:number;notice:string};memory_availability?:MemoryAvailability;fact_correspondence?:FactCorrespondence;automated_passed:boolean|null;test_id:string;question:string;dimension:string;response:string;assessment:string;layer:string;explanation:string;supporting_source_count:number;stored_source_coverage:number;sent_source_coverage:number|null}
interface Diagnosis {repair_recommendation?:{status:string;focus:string;title:string;rationale:string;notice:string};source_memory_capacity?:number;suggested_memory_capacity?:number;suggested_memory_strategy?:MemoryStrategy;cases:DiagnosisCase[];suggested_profile:TargetMemoryProfile;notice:string;paired_probes:{complete_groups:number;recall_use_gaps:number}}
interface Package {experiment_id:string;runs:Array<{run_id:string;label:string}>;notice:string}

export function ValidationWorkbench({runId}: {runId:string}) {
  const [diagnosis,setDiagnosis]=useState<Diagnosis|null>(null);
  const [profile,setProfile]=useState(defaultTargetProfile);
  const [note,setNote]=useState('');
  const [strategy,setStrategy]=useState<MemoryStrategy>('scope_aware');
  const [capacity,setCapacity]=useState<number|null>(50);
  const [histories,setHistories]=useState<Array<{conversation_id:string;label:string}>>([]);
  const [history,setHistory]=useState<string|undefined>();
  const storageKey=`mha-validation-plan-${runId}`;
  const [packageData,setPackage]=useState<Package|null>(()=>{try{return JSON.parse(sessionStorage.getItem(storageKey)||'null') as Package|null;}catch{return null;}});
  const [reviewRun,setReviewRun]=useState('');
  const [tests,setTests]=useState<TestCase[]>([]);
  const [finished,setFinished]=useState<string[]>([]);
  const [busy,setBusy]=useState(false);
  const [activeCondition,setActiveCondition]=useState('');
  const [pauseRequested,setPauseRequested]=useState(false);
  const pauseAfterCurrent=useRef(false);
  const [error,setError]=useState('');
  const [methodResults,setMethodResults]=useState<{conditions:Array<{run_id:string;label:string;actual_calls:number|null;completed_answers?:number;unknown_attempt_records?:number;resolved_labels:number;human_confirmed_distinct_findings:number}>;notice:string}|null>(null);
  const [result,setResult]=useState<Awaited<ReturnType<typeof api.results>>|null>(null);
  useEffect(()=>{if(packageData)sessionStorage.setItem(storageKey,JSON.stringify(packageData));},[packageData,storageKey]);
  const restore=()=>act(async()=>{if(!packageData)return;const completed:string[]=[];let selected='';for(const run of packageData.runs){const state=await api.getAudit(run.run_id);if(state.status==='COMPLETED')completed.push(run.run_id);else if(state.status==='TESTS_GENERATED'&&!selected)selected=run.run_id;}setFinished(completed);selected=selected||completed[0]||'';if(selected){setReviewRun(selected);setTests((await api.testReview(selected)).tests);}});
  const act=async(action:()=>Promise<void>)=>{setBusy(true);setError('');try {await action();}catch(cause){setError(cause instanceof Error?cause.message:'This step could not be completed.');}finally{setBusy(false);}};
  const load=()=>act(async()=>{
    const data=await api.diagnosis(runId);setDiagnosis(data);setProfile(data.suggested_profile);setStrategy(data.suggested_memory_strategy||'scope_aware');setCapacity(data.suggested_memory_capacity??data.source_memory_capacity??50);setHistories(await api.validationHistories());
  });
  const refreshHistories=()=>act(async()=>{setHistories(await api.validationHistories());});
  const prepare=(kind:'repair'|'held_out'|'interventions'|'follow_up'|'methods')=>act(async()=>{
    const data=kind==='methods'?await api.methodComparison(runId):kind==='interventions'?await api.interventions(runId):kind==='follow_up'?await api.followUp(runId,4):await api.repairExperiment(runId,{targeted_profile:profile,targeted_memory_strategy:strategy,targeted_memory_capacity:diagnosis?.source_memory_capacity===undefined?undefined:capacity,diagnosis_note:note,validation_conversation_id:kind==='held_out'?history:undefined});
    setPackage(data);setFinished([]);setResult(null);
    for(const run of data.runs) await api.generate(run.run_id);
    setReviewRun(data.runs[0].run_id);
    setTests((await api.testReview(data.runs[0].run_id)).tests);
  });
  const review=async(test:TestCase,status:'accepted'|'rejected')=>{await act(async()=>{if(!packageData)return;await api.reviewTest(reviewRun,test.test_id,status);setTests((await api.testReview(reviewRun)).tests);});};
  const regenerate=async(test:TestCase)=>{await act(async()=>{if(!packageData)return;await api.regenerateTest(reviewRun,test.test_id);setTests((await api.testReview(reviewRun)).tests);});};
  const execute=()=>act(async()=>{
    if(!packageData)return;
    pauseAfterCurrent.current=false;setPauseRequested(false);
    let latestCompleted='';
    try {
    for(const run of packageData.runs){
      if(finished.includes(run.run_id))continue;
      setActiveCondition(run.label);
      const state=await api.getAudit(run.run_id);
      if(state.status==='FAILED')await api.retry(run.run_id);
      const current=await api.getAudit(run.run_id);
      if(current.status==='TESTS_GENERATED')await api.execute(run.run_id);
      const after=await api.getAudit(run.run_id);
      if(after.status==='TESTS_EXECUTED')await api.evaluate(run.run_id);
      const final=await api.getAudit(run.run_id);
      if(final.status!=='COMPLETED')throw new Error('This condition did not complete. Inspect its saved report before retrying.');
      setFinished(previous=>[...previous,run.run_id]);
      latestCompleted=run.run_id;
      if(pauseAfterCurrent.current)break;
    }
    if(latestCompleted)setResult(await api.results(latestCompleted));
    } finally {setActiveCondition('');}
  });
  return <Card title="Diagnosis & validation" style={{marginTop:24}}>
    <p>Inspect the evidence, record a general repair rule, then compare it with the original and a generic instruction control. Use new histories for independent validation.</p>
    {error&&<Alert type="error" title={error} showIcon/>}
    {!diagnosis?<Button onClick={load} loading={busy}>Inspect diagnosis</Button>:<>
      <Alert type="info" title={diagnosis.notice} showIcon/>
      {diagnosis.repair_recommendation&&<Alert style={{marginTop:12}} showIcon type={diagnosis.repair_recommendation.status==='requires_review'?'warning':'info'} title={diagnosis.repair_recommendation.title} description={<><p>{diagnosis.repair_recommendation.rationale}</p><p>{diagnosis.repair_recommendation.notice}</p></>}/>}
      <p><Tag>{diagnosis.paired_probes.complete_groups} paired groups</Tag><Tag>{diagnosis.paired_probes.recall_use_gaps} recall-to-task gaps</Tag></p>
      <Table rowKey="test_id" pagination={{pageSize:5}} dataSource={diagnosis.cases} columns={[
        {title:'Question',dataIndex:'question'},
        {title:'Observed result',dataIndex:'automated_passed',render:(value:boolean|null)=>value===null?'Uncertain':value?'Passed · provenance needs review':'Failed'},
        {title:'Diagnostic hypothesis',dataIndex:'layer',render:(value:string)=>(({no_memory_reference:'Memory disabled · baseline outcome',input_delivery_review:'Check input assembly',context_budget_review:'Check context limits',profile_filter_review:'Check memory profile filters',retention_hypothesis:'Check retention capacity',availability_review:'Check past memory availability',answer_and_history_review:'Check answer & update context',policy_exclusion_hypothesis:'Check memory exclusion rules',fact_correspondence_review:'Check fact correspondence',fact_supply_review:'Check supplied facts',unobserved_pass:'Pass · evidence incomplete',unattributed_pass:'Pass · support needs review'} as Record<string,string>)[value] ?? value.replaceAll('_',' '))},
        {title:'Evidence and limits',dataIndex:'explanation'},
        {title:'Fact correspondence',render:(_,row:DiagnosisCase)=>row.fact_correspondence ? `${row.fact_correspondence.stored_fact_units}/${row.fact_correspondence.expected_fact_units} exact stored · ${row.fact_correspondence.supplied_fact_units===null?'input unobserved':`${row.fact_correspondence.supplied_fact_units}/${row.fact_correspondence.expected_fact_units} exact supplied`}` : 'Not recorded'},
        {title:'Source coverage',render:(_,row:DiagnosisCase)=>`${row.stored_source_coverage}/${row.supporting_source_count} stored · ${row.sent_source_coverage===null?'input unobserved':`${row.sent_source_coverage}/${row.supporting_source_count} supplied`}`},
      ]} expandable={{expandedRowRender:row=><><p><b>Answer:</b> {row.response}</p><p><b>Automated assessment:</b> {friendlyText(row.assessment)}</p>{row.input_delivery&&<><p>Exact supporting facts: {row.input_delivery.retrieved_fact_units===null?"retrieval not recorded":`${row.input_delivery.retrieved_fact_units}/${row.input_delivery.expected_fact_units} retrieved`} · {row.input_delivery.selected_not_supplied_fact_units===null?"final supply not recorded":`${row.input_delivery.selected_not_supplied_fact_units} selected but not supplied`} · {row.input_delivery.context_budget_excluded_fact_units} excluded by context limits · {row.input_delivery.profile_filter_excluded_fact_units} excluded by profile filters.</p><p>{row.input_delivery.notice}</p></>}{row.memory_availability&&<><p>At answer time: {row.memory_availability.eligible_fact_units}/{row.memory_availability.expected_fact_units} exact fact pairs eligible for retrieval · {row.memory_availability.capacity_excluded_fact_units} excluded by capacity · {row.memory_availability.observed_fact_units}/{row.memory_availability.expected_fact_units} with eligibility recorded.</p><p>Historical records can remain visible after removal from active memory. Missing eligibility records remain unknown.</p>{row.memory_availability.facts.map((fact,i)=><Card size="small" key={i}><b>{fact.reference_label} · retrieval eligibility</b>{fact.matching_record_eligibility.map((r,j)=><p key={j}>{r.record_text} · {({eligible:'Available for retrieval',capacity_excluded:'Removed by capacity limit',superseded_excluded:'Older state excluded by policy',diagnostic_excluded:'Diagnostic packet excluded',excluded_other:'Excluded by another rule',unobserved:'Eligibility not recorded'} as Record<string,string>)[r.eligibility]??'Eligibility not recorded'}</p>)}</Card>)}</>}{row.fact_correspondence && <><p>Exact matches compare source and normalised fact text. Different wording can preserve meaning; check these facts before attributing a defect.</p>{row.fact_correspondence.facts.map((fact,index)=><Card key={index} size="small"><p><b>{fact.reference_label}:</b> {fact.reference_text}</p><p><b>Stored from related sources:</b> {fact.stored_related_text.join(" · ") || "No related record"}</p><p><b>Actually supplied from related sources:</b> {fact.supplied_related_text===null ? "Input not observed" : fact.supplied_related_text.join(" · ") || "No related record supplied"}</p></Card>)}</>}</>}}/>
      <TargetProfileEditor value={profile} onChange={setProfile} disabled={busy}/>
      <label>Targeted retrieval strategy<Select virtual={false} aria-label="Targeted retrieval strategy" style={{width:'100%',marginBottom:16}} disabled={busy} value={strategy} onChange={setStrategy} options={[
        {value:'weak_first_hit',label:'First matching memory'}, {value:'scope_aware',label:'Match the task and project'},
        {value:'strong_score_based',label:'Rank by relevance'}, {value:'strong_rule_based',label:'Prioritise requirements and updates'},
        {value:'temporal_importance',label:'Consider time and importance'}, {value:'full_context',label:'Replay all retained memories'},
        {value:'no_memory',label:'Supply no memories'}]}/></label>
      <p>The original and generic controls retain the original retrieval strategy. Only the targeted condition uses this selection.</p>
      {diagnosis.source_memory_capacity!==undefined&&<label>Candidate memory capacity<InputNumber aria-label="Candidate memory capacity" min={1} max={500} precision={0} disabled={busy} value={capacity} onChange={setCapacity}/><small>Original capacity: {diagnosis.source_memory_capacity} records. Only the targeted condition uses the candidate capacity. Increasing capacity changes the memory budget and may increase cost.</small></label>}
      <label>Why this configuration addresses the diagnosis<Input.TextArea aria-label="Repair rationale" disabled={busy} value={note} onChange={event=>setNote(event.target.value)} rows={3} maxLength={2000}/></label>
      <Space wrap style={{marginTop:16}}>
        <Button disabled={note.trim().length<10||!profile.label.trim()||busy||(diagnosis.source_memory_capacity!==undefined&&(!capacity||capacity<1||capacity>500))} onClick={()=>prepare('repair')}>Prepare repair comparison</Button>
<Button disabled={busy} onClick={()=>prepare('methods')}>Prepare audit-method comparison</Button>
        <Button disabled={busy} onClick={()=>void act(async()=>setMethodResults(await api.methodComparisonResults(runId)))}>Inspect confirmed method findings</Button>
        <Button disabled={busy} onClick={()=>prepare('interventions')}>Prepare diagnostic interventions</Button>
        <Button disabled={busy||!diagnosis.cases.some(row=>row.automated_passed===false)} onClick={()=>prepare('follow_up')}>Prepare exploratory follow-up</Button>
      </Space>
      <Card title="Independent new-history validation" style={{marginTop:16}}>
        <p>First import and confirm another history through New audit. A different record alone does not prove independence; review for shared facts or scenario templates before treating it as held out.</p>
        <Button style={{marginBottom:12}} onClick={refreshHistories} loading={busy}>Refresh reviewed histories</Button>
        <Select virtual={false} aria-label="Independent validation history" style={{width:'100%'}} placeholder="Choose another reviewed history" value={history} onChange={setHistory} options={histories.map(item=>({value:item.conversation_id,label:item.label}))}/>
        <Button style={{marginTop:12}} disabled={!history||note.trim().length<10||busy||(diagnosis.source_memory_capacity!==undefined&&(!capacity||capacity<1||capacity>500))} onClick={()=>prepare('held_out')}>Prepare new-history validation</Button>
      </Card>
    </>}
    {packageData&&<Card title="Prepared experiment" style={{marginTop:16}}>
      <Alert type="warning" title={packageData.notice} showIcon/>
      {!reviewRun&&<Button onClick={restore} disabled={busy}>Restore saved experiment</Button>}
      <p>{packageData.runs.length} conditions · {reviewRun?`${finished.length} completed`:"restore the saved plan to verify progress"}</p>
      <Select virtual={false} aria-label="Condition suite to review" style={{width:'100%',marginBottom:16}} value={reviewRun} disabled={busy} options={packageData.runs.map(run=>({value:run.run_id,label:run.label}))} onChange={value=>void act(async()=>{setReviewRun(value);setTests((await api.testReview(value)).tests);})}/>
      {finished.length>0&&<p>The shared questions are frozen because testing has started. You can inspect them and continue pending conditions.</p>}
      <TestSuiteReview tests={tests} busy={busy||finished.length>0} onReview={review} onRegenerate={regenerate}/>
      <Button type="primary" loading={busy} disabled={finished.length===packageData.runs.length||!tests.length||tests.some(test=>test.quality_status!=='accepted')} onClick={execute}>{finished.length?'Continue / verify saved conditions':'Run prepared conditions'}</Button>
      {activeCondition&&<p role="status">Running {activeCondition}. <Button disabled={pauseRequested} onClick={()=>{pauseAfterCurrent.current=true;setPauseRequested(true);}}>Pause after current condition</Button></p>}
      {pauseRequested&&!activeCondition&&<p role="status">The queue paused after saving the current condition. Continue to run the remaining conditions.</p>}
      <ul>{packageData.runs.map(run=><li key={run.run_id}>{run.label} · {finished.includes(run.run_id)?<a href={`/audits/${run.run_id}`}>View completed report</a>:reviewRun?'Pending':'Awaiting verification'} </li>)}</ul>
      {packageData.runs.length>1&&finished.length===packageData.runs.length&&<a href={`/compare?before=${packageData.runs[0].run_id}&after=${packageData.runs[packageData.runs.length-1].run_id}`}>Compare first and last conditions →</a>}
    </Card>}
    {methodResults&&<Card title="Audit-method evidence"><Alert type="info" title={methodResults.notice}/><Table rowKey="run_id" dataSource={methodResults.conditions} columns={[{title:'Method',dataIndex:'label'},{title:'Completed answers',dataIndex:'completed_answers'},{title:'Recorded request attempts',dataIndex:'actual_calls',render:(value:number|null)=>value===null?'Not recorded':value},{title:'Answers missing attempt evidence',dataIndex:'unknown_attempt_records'},{title:'Resolved human references',dataIndex:'resolved_labels'},{title:'Confirmed distinct findings',dataIndex:'human_confirmed_distinct_findings'}]}/></Card>}
    {result&&<Card title="Latest condition result"><p>{result.tests_passed}/{result.tests_total} decided tests passed; {result.uncertain_count??0} remain uncertain.</p><a href={`/audits/${result.run_id}`}>Open evidence and full report →</a></Card>}
  </Card>;
}
export type {Diagnosis,Package};
