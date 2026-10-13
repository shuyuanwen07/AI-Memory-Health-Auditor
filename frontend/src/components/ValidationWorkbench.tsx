import { Alert, Button, Card, Checkbox, Input, InputNumber, Select, Space, Table, Tag } from 'antd';
import { lazy,Suspense,useState,useEffect,useRef } from 'react';
import type { ExperimentStatisticsRun } from './ExperimentStatistics';
import { ExperimentAMethodChart } from './ExperimentAMethodChart';
const ConditionCharts = lazy(() => import('./ResultVisualizations').then(module=>({default:module.ComparisonVisualizations})));
import { api } from '../services/api';
import { friendlyText } from '../services/display';
import { defaultTargetProfile, TargetProfileEditor, type TargetMemoryProfile } from './TargetProfileEditor';
import { TestSuiteReview, hasDuplicateQuestions } from './TestSuiteReview';
import type { TestCase,MemoryStrategy } from '../types/domain';
interface FactCorrespondence { expected_fact_units:number;stored_fact_units:number;supplied_fact_units:number|null;facts:Array<{reference_label:string;reference_text:string;stored_related_text:string[];supplied_related_text:string[]|null}> }
interface MemoryAvailability {expected_fact_units:number;observed_fact_units:number;eligible_fact_units:number;capacity_excluded_fact_units:number;facts:Array<{reference_label:string;reference_text:string;matching_record_eligibility:Array<{record_text:string;eligibility:string}>}>}
interface DiagnosisCase {input_delivery?:{expected_fact_units:number;retrieved_fact_units:number|null;selected_not_supplied_fact_units:number|null;context_budget_excluded_fact_units:number;profile_filter_excluded_fact_units:number;notice:string};memory_availability?:MemoryAvailability;fact_correspondence?:FactCorrespondence;automated_passed:boolean|null;test_id:string;question:string;dimension:string;response:string;assessment:string;layer:string;explanation:string;supporting_memory_ids?:string[];supporting_source_count:number;stored_source_coverage:number;sent_source_coverage:number|null}
interface Diagnosis {repair_recommendation?:{status:string;focus:string;title:string;rationale:string;notice:string};source_memory_capacity?:number;suggested_memory_capacity?:number;suggested_memory_strategy?:MemoryStrategy;cases:DiagnosisCase[];suggested_profile:TargetMemoryProfile;notice:string;paired_probes:{complete_groups:number;recall_use_gaps:number}}
interface DiagnosticFinding {test_id:string;focus:string;evidence_memory_ids:string[];summary:string;next_check:string;model_confidence:number}
interface DiagnosticAgentReport {version:string;summary:string;findings:DiagnosticFinding[];notice:string}
interface DiagnosticAgentResponse {run_id:string;diagnosis_version:string;execution_id?:string;provider?:string;model?:string;reported_model?:string|null;diagnostic_agent:DiagnosticAgentReport|null;notice?:string}
const actionMessages:Record<string,string>={restore:'Restoring saved experiment…',diagnosis:'Inspecting diagnosis…',diagnosticAgent:'Running the diagnostic Agent…',histories:'Refreshing reviewed histories…',review:'Saving question decision…',humanValidityReview:'Saving human validity decision…',regenerate:'Regenerating question…',execute:'Executing prepared conditions…',findings:'Loading method findings…',select:'Loading selected question suite…',comparison:'Loading condition comparison…',repair:'Preparing repair comparison…',held_out:'Preparing new-history validation…',interventions:'Preparing diagnostic interventions…',follow_up:'Preparing exploratory follow-up…',methods:'Preparing audit-method comparison…',mapping:'Saving researcher-reviewed defect mappings…'};
interface MethodInventoryTemplate {schema_version:string;comparison_id:string;release_id:string;source_fingerprint_sha256:string;annotation_mode:string;reviewers:string[];defects:Array<{defect_id:string;dimension:string;supporting_memory_ids:string[];source_message_ids:string[];explanation:string}>;fixed_template_release_id:string;fixed_template_reviewers:string[];fixed_template_draft_generator_version:string;fixed_template_draft_fingerprint_sha256:string;fixed_template_review_confirmed:boolean;fixed_template_questions:Array<{template_id:string;dimension:string;prompt:string;expected_behavior:string;supporting_memory_ids:string[];source_message_ids:string[];test_type:string}>}
interface Package {experiment_id:string;runs:Array<{run_id:string;label:string}>;notice:string;comparison_id?:string;study_role?:string;test_budget?:number;inventory_template?:MethodInventoryTemplate;inventory_draft?:string;failure_inventory_payload?:Record<string,unknown>;failure_inventory_fingerprint_sha256?:string}
type MethodResults=Awaited<ReturnType<typeof api.methodComparisonResults>>;
type DiscoveryEntry=MethodResults['conditions'][number]['discovery_mapping']['entries'][number];
interface DiscoveryDraft {mapping_release_id:string;reviewer_pseudonym:string;entries:DiscoveryEntry[]}

export function ValidationWorkbench({runId}: {runId:string}) {
  return <ValidationSession key={runId} runId={runId}/>;
}
function ValidationSession({runId}: {runId:string}) {
  const [diagnosis,setDiagnosis]=useState<Diagnosis|null>(null);
  const [diagnosticAgent,setDiagnosticAgent]=useState<DiagnosticAgentResponse|null>(null);
  const [profile,setProfile]=useState(defaultTargetProfile);
  const [note,setNote]=useState('');
  const [strategy,setStrategy]=useState<MemoryStrategy>('scope_aware');
  const [capacity,setCapacity]=useState<number|null>(50);
  const [histories,setHistories]=useState<Array<{conversation_id:string;label:string}>>([]);
  const [history,setHistory]=useState<string|undefined>();
  const storageKey=`mha-validation-plan-${runId}`;
  const [packageData,setPackage]=useState<Package|null>(()=>{try{const value=JSON.parse(sessionStorage.getItem(storageKey)||'null') as Package|null;return value&&typeof value.experiment_id==='string'&&Array.isArray(value.runs)&&value.runs.every(run=>typeof run.run_id==='string'&&typeof run.label==='string')?value:null;}catch{return null;}});
  const [reviewRun,setReviewRun]=useState('');
  const [tests,setTests]=useState<TestCase[]>([]);
  const [suiteTests,setSuiteTests]=useState<Record<string,TestCase[]>>({});
  const [finished,setFinished]=useState<string[]>([]);
  const [questionsFrozen,setQuestionsFrozen]=useState(false);
  const [busyAction,setBusyAction]=useState('');
  const busy=!!busyAction;
  const actionInProgress=useRef(false);
  const [activeCondition,setActiveCondition]=useState('');
  const [pauseRequested,setPauseRequested]=useState(false);
  const pauseAfterCurrent=useRef(false);
  const [error,setError]=useState('');
  const [templateReviewConfirmed,setTemplateReviewConfirmed]=useState(false);
  const [methodResults,setMethodResults]=useState<MethodResults|null>(null);
  const [discoveryDrafts,setDiscoveryDrafts]=useState<Record<string,DiscoveryDraft>>({});
  const [discoveryConfirmations,setDiscoveryConfirmations]=useState<Record<string,boolean>>({});
  const [comparisonRuns,setComparisonRuns]=useState<ExperimentStatisticsRun[]>([]);
  const [result,setResult]=useState<Awaited<ReturnType<typeof api.results>>|null>(null);
  useEffect(()=>{if(packageData){try{sessionStorage.setItem(storageKey,JSON.stringify(packageData));}catch{setError("This browser could not save the validation plan. Keep this page open; experiment records remain available in Experiments.");}}},[packageData,storageKey]);
  const loadComparison=async(plan:Package)=>{const values=await Promise.all(plan.runs.map(async run=>({label:run.label,groupLabel:run.label,result:await api.results(run.run_id)})));setComparisonRuns(values);};
  const restore=()=>act('restore',async()=>{
    if(!packageData)return;
    const completed:string[]=[];let selected='';let frozen=false;
    const savedSuites:Record<string,TestCase[]>={};
    for(const run of packageData.runs){
      const state=await api.getAudit(run.run_id);
      if(state.status==='COMPLETED')completed.push(run.run_id);
      if(state.status==='COMPLETED'||state.status==='TESTS_EXECUTED')frozen=true;
      if(state.status==='TESTS_GENERATED'||state.status==='TESTS_EXECUTED'||state.status==='COMPLETED'){
        try{
          const suite=await api.testReview(run.run_id);
          savedSuites[run.run_id]=suite.tests;
          if(!selected)selected=run.run_id;
        }catch{
          // Keep restoring other saved suites; the user can retry this run from the selector.
        }
      }
    }
    selected=selected||completed[0]||'';
    setSuiteTests(savedSuites);setFinished(completed);setQuestionsFrozen(frozen);setReviewRun(selected);setTests(savedSuites[selected]??[]);
    if(packageData.runs.length>1&&completed.length===packageData.runs.length)await loadComparison(packageData);
  });
  const act=async(kind:string,action:()=>Promise<void>)=>{if(actionInProgress.current)return;actionInProgress.current=true;setBusyAction(kind);setError('');try {await action();}catch(cause){setError(cause instanceof Error?cause.message:'This step could not be completed.');}finally{actionInProgress.current=false;setBusyAction('');}};
  const load=()=>act('diagnosis',async()=>{
    const data=await api.diagnosis(runId);setDiagnosis(data);setDiagnosticAgent(null);setProfile(data.suggested_profile);setStrategy(data.suggested_memory_strategy||'scope_aware');setCapacity(data.suggested_memory_capacity??data.source_memory_capacity??50);setHistories(await api.validationHistories());
  });
  const runAgent=()=>act('diagnosticAgent',async()=>{setDiagnosticAgent(await api.runDiagnosticAgent(runId));});
  const refreshHistories=()=>act('histories',async()=>{setHistories(await api.validationHistories());});
  const loadMethodResults=async(comparisonId?:string)=>{
    const report=await api.methodComparisonResults(runId,comparisonId);
    setMethodResults(report);
    setDiscoveryDrafts(current=>Object.fromEntries(report.conditions.map(condition=>{
      const saved=condition.discovery_mapping;
      return [condition.run_id,current[condition.run_id]??{
        mapping_release_id:saved.release_id??'discovery-map-v1',
        reviewer_pseudonym:saved.reviewer_pseudonym??'',
        entries:saved.entries.map(entry=>({...entry,defect_ids:[...entry.defect_ids]})),
      }];
    })));
  };
  const updateDiscoveryDraft=(runKey:string,update:(draft:DiscoveryDraft)=>DiscoveryDraft)=>setDiscoveryDrafts(current=>{
    const draft=current[runKey];return draft?{...current,[runKey]:update(draft)}:current;
  });
  const saveDiscoveryMapping=(condition:MethodResults['conditions'][number])=>act('mapping',async()=>{
    if(!methodResults)throw new Error('Load the saved Experiment A results before mapping responses.');
    const draft=discoveryDrafts[condition.run_id];
    if(!draft||!methodResults.inventory.fingerprint_sha256)throw new Error('A frozen source-defect inventory is required before mapping responses.');
    await api.freezeMethodComparisonDiscoveryMapping(condition.run_id,{
      schema_version:'mha-experiment-a-discovery-map-v1',comparison_id:methodResults.comparison_id,
      inventory_fingerprint_sha256:methodResults.inventory.fingerprint_sha256,
      mapping_release_id:draft.mapping_release_id,reviewer_pseudonym:draft.reviewer_pseudonym,
      completed_by_human:true,entries:draft.entries.map(entry=>({response_id:entry.response_id,test_id:entry.test_id,defect_ids:entry.defect_ids})),
    });
    setDiscoveryConfirmations(current=>({...current,[condition.run_id]:false}));
    await loadMethodResults(methodResults.comparison_id);
  });
  const prepare=(kind:'repair'|'held_out'|'interventions'|'follow_up'|'methods')=>act(kind,async()=>{
    const data=kind==='methods'?await api.methodComparison(runId):kind==='interventions'?await api.interventions(runId):kind==='follow_up'?await api.followUp(runId,4):await api.repairExperiment(runId,{targeted_profile:profile,targeted_memory_strategy:strategy,targeted_memory_capacity:diagnosis?.source_memory_capacity===undefined?undefined:capacity,diagnosis_note:note,validation_conversation_id:kind==='held_out'?history:undefined});
    const prepared=data.study_role==='audit_method_comparison'
      ? {...data,inventory_draft:JSON.stringify(data.inventory_template,null,2)} : data;
    setTemplateReviewConfirmed(false);setDiscoveryDrafts({});setDiscoveryConfirmations({});
    setPackage(prepared);setFinished([]);setQuestionsFrozen(false);setReviewRun('');setTests([]);setSuiteTests({});setResult(null);setComparisonRuns([]);setMethodResults(null);
    if(data.study_role==='audit_method_comparison') return;
    for(const run of data.runs) await api.generate(run.run_id);
    setReviewRun(data.runs[0].run_id);
    const firstSuite=(await api.testReview(data.runs[0].run_id)).tests;
    setTests(firstSuite);setSuiteTests({[data.runs[0].run_id]:firstSuite});
  });
  const downloadJson=(filename:string,value:unknown)=>{
    const link=document.createElement('a');const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
    link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),0);
  };
  const freezeMethodInventory=()=>act('methods',async()=>{
    if(!packageData?.comparison_id||!packageData.inventory_draft)throw new Error('Create an audit-method comparison before freezing its failure inventory.');
    if(!templateReviewConfirmed)throw new Error('Review the rule-generated fixed-template draft and confirm it before freezing.');
    const inventory=JSON.parse(packageData.inventory_draft) as Record<string,unknown>;
    inventory.fixed_template_review_confirmed=true;
    const frozen=await api.freezeMethodComparisonInventory(runId,inventory);
    const next={...packageData,failure_inventory_payload:inventory,failure_inventory_fingerprint_sha256:frozen.inventory_fingerprint_sha256};
    setPackage(next);
    const generatedSuites:Record<string,TestCase[]>={};
    for(const run of next.runs){
      await api.generate(run.run_id);
      generatedSuites[run.run_id]=(await api.testReview(run.run_id)).tests;
    }
    setSuiteTests(generatedSuites);setReviewRun(next.runs[0].run_id);
    setTests(generatedSuites[next.runs[0].run_id]??[]);
  });
  const review=async(test:TestCase,status:'accepted'|'rejected',note?:string)=>{await act('review',async()=>{if(!packageData)return;await api.reviewTest(test.run_id,test.test_id,status,note);const refreshed=(await api.testReview(test.run_id)).tests;setSuiteTests(current=>({...current,[test.run_id]:refreshed}));if(test.run_id===reviewRun)setTests(refreshed);});};
  const reviewHumanValidity=async(test:TestCase,decision:'accepted'|'rejected',reviewerPseudonym:string,note?:string)=>{await act('humanValidityReview',async()=>{await api.reviewTestHumanValidity(test.run_id,test.test_id,decision,reviewerPseudonym,note);const refreshed=(await api.testReview(test.run_id)).tests;setSuiteTests(current=>({...current,[test.run_id]:refreshed}));if(test.run_id===reviewRun)setTests(refreshed);});};
  const regenerate=async(test:TestCase)=>{await act('regenerate',async()=>{if(!packageData)return;await api.regenerateTest(test.run_id,test.test_id);const refreshed=(await api.testReview(test.run_id)).tests;setSuiteTests(current=>({...current,[test.run_id]:refreshed}));if(test.run_id===reviewRun)setTests(refreshed);});};
  const isMethodComparison=packageData?.study_role==='audit_method_comparison';
  const allMethodTestsReady=Boolean(packageData?.runs.length)&&packageData!.runs.every(run=>{
    const suite=suiteTests[run.run_id]??(run.run_id===reviewRun?tests:[]);
    return suite.length>0&&suite.every(test=>test.quality_status==='accepted'&&test.human_validity_status==='accepted')&&!hasDuplicateQuestions(suite);
  });
  const execute=()=>act('execute',async()=>{
    if(!packageData)return;
    pauseAfterCurrent.current=false;setPauseRequested(false);
    let latestCompleted='';
    const completed=new Set(finished);
    try {
    for(const run of packageData.runs){
      if(finished.includes(run.run_id))continue;
      setActiveCondition(run.label);
      const state=await api.getAudit(run.run_id);
      if(state.status==='FAILED')await api.retry(run.run_id);
      const current=await api.getAudit(run.run_id);
      if(current.status==='TESTS_GENERATED'){setQuestionsFrozen(true);await api.execute(run.run_id);}
      if(current.status==='TESTS_EXECUTED'||current.status==='COMPLETED')setQuestionsFrozen(true);
      const after=await api.getAudit(run.run_id);
      if(after.status==='TESTS_EXECUTED')await api.evaluate(run.run_id);
      const final=await api.getAudit(run.run_id);
      if(final.status!=='COMPLETED')throw new Error('This condition did not complete. Inspect its saved report before retrying.');
      setFinished(previous=>[...previous,run.run_id]);
      latestCompleted=run.run_id;
      completed.add(run.run_id);
      if(pauseAfterCurrent.current)break;
    }
    if(latestCompleted)setResult(await api.results(latestCompleted));
    if(packageData.runs.length>1&&completed.size===packageData.runs.length)await loadComparison(packageData);
    } finally {setActiveCondition('');}
  });
  return <Card className="validation-workbench" title="Diagnosis & validation" style={{marginTop:24}}>
    <p>Inspect the evidence, record a general repair rule, then compare it with the original and a generic instruction control. Use new histories for independent validation.</p>
    {busy&&<p role="status">{actionMessages[busyAction]}</p>}
    {error&&<Alert type="error" title={error} showIcon/>}
    {!diagnosis?<Button onClick={load} disabled={busy} loading={busyAction==='diagnosis'}>Inspect diagnosis</Button>:<>
      <Alert type="info" title={diagnosis.notice} showIcon/>
      <Space wrap style={{marginTop:12,marginBottom:8}}>
        <Button disabled={busy||diagnosis.cases.length===0} loading={busyAction==='diagnosticAgent'} onClick={runAgent}>Ask diagnostic Agent to review these hypotheses</Button>
        <small>This uses the audit’s configured model. Its confidence is an uncalibrated estimate; it cannot establish cause or replace human review.</small>
      </Space>
      {diagnosticAgent&&<Card title="Post-run diagnostic Agent" style={{marginBottom:16}}>
        {diagnosticAgent.diagnostic_agent?<>
          <Alert type="warning" showIcon title={diagnosticAgent.diagnostic_agent.notice} description={<>{diagnosticAgent.diagnostic_agent.summary}<br/>Model: {diagnosticAgent.reported_model||diagnosticAgent.model} · Evidence record: {diagnosticAgent.execution_id}</>}/>
          <Table style={{marginTop:12}} rowKey="test_id" pagination={false} dataSource={diagnosticAgent.diagnostic_agent.findings} columns={[
            {title:'Question',dataIndex:'test_id'},
            {title:'Area to review',dataIndex:'focus',render:(value:string)=>value.replaceAll('_',' ')},
            {title:'Evidence',render:(_,row:DiagnosticFinding)=>row.evidence_memory_ids.join(', ')||'Insufficient recorded memory evidence'},
            {title:'Interpretation',dataIndex:'summary'},
            {title:'Next check',dataIndex:'next_check'},
            {title:'Model estimate',dataIndex:'model_confidence',render:(value:number)=>`${Math.round(value*100)}%`},
          ]}/>
        </>:<Alert type="info" showIcon title={diagnosticAgent.notice||'No cases required additional review.'}/>}</Card>}
      {diagnosis.repair_recommendation&&<Alert style={{marginTop:12}} showIcon type={diagnosis.repair_recommendation.status==='requires_review'?'warning':'info'} title={diagnosis.repair_recommendation.title} description={<><p>{diagnosis.repair_recommendation.rationale}</p><p>{diagnosis.repair_recommendation.notice}</p></>}/>}
      <p><Tag>{diagnosis.paired_probes.complete_groups} paired groups</Tag><Tag>{diagnosis.paired_probes.recall_use_gaps} recall-to-task gaps</Tag></p>
      <Table scroll={{x:1100}} rowKey="test_id" pagination={{pageSize:5}} dataSource={diagnosis.cases} columns={[
        {title:'Question',dataIndex:'question'},
        {title:'Observed result',dataIndex:'automated_passed',render:(value:boolean|null)=>value===null?'Uncertain':value?'Passed · provenance needs review':'Failed'},
        {title:'Diagnostic hypothesis',dataIndex:'layer',render:(value:string)=>(({no_memory_reference:'Memory disabled · baseline outcome',encoding_hypothesis:'Check memory writing',generation_hypothesis:'Check supplied context and answer',unobserved:'Cause not established',uncertain_assessment:'Resolve uncertain assessment',retrieval_hypothesis:'Check memory retrieval',input_delivery_review:'Check input assembly',context_budget_review:'Check context limits',profile_filter_review:'Check memory profile filters',retention_hypothesis:'Check retention capacity',availability_review:'Check past memory availability',answer_and_history_review:'Check answer & update context',policy_exclusion_hypothesis:'Check memory exclusion rules',fact_correspondence_review:'Check fact correspondence',fact_supply_review:'Check supplied facts',unobserved_pass:'Pass · evidence incomplete',unattributed_pass:'Pass · support needs review'} as Record<string,string>)[value] ?? value.replaceAll('_',' '))},
        {title:'Evidence and limits',dataIndex:'explanation'},
        {title:'Fact correspondence',render:(_,row:DiagnosisCase)=>row.fact_correspondence ? `${row.fact_correspondence.stored_fact_units}/${row.fact_correspondence.expected_fact_units} exact stored · ${row.fact_correspondence.supplied_fact_units===null?'input unobserved':`${row.fact_correspondence.supplied_fact_units}/${row.fact_correspondence.expected_fact_units} exact supplied`}` : 'Not recorded'},
        {title:'Source coverage',render:(_,row:DiagnosisCase)=>`${row.stored_source_coverage}/${row.supporting_source_count} stored · ${row.sent_source_coverage===null?'input unobserved':`${row.sent_source_coverage}/${row.supporting_source_count} supplied`}`},
      ]} expandable={{expandedRowRender:row=><div className="diagnosis-evidence-details"><p><b>Answer:</b> {row.response}</p><p><b>Automated assessment:</b> {friendlyText(row.assessment)}</p>{row.input_delivery&&<><p>Exact supporting facts: {row.input_delivery.retrieved_fact_units===null?"retrieval not recorded":`${row.input_delivery.retrieved_fact_units}/${row.input_delivery.expected_fact_units} retrieved`} · {row.input_delivery.selected_not_supplied_fact_units===null?"final supply not recorded":`${row.input_delivery.selected_not_supplied_fact_units} selected but not supplied`} · {row.input_delivery.context_budget_excluded_fact_units} recorded exclusions by context limits · {row.input_delivery.profile_filter_excluded_fact_units} recorded exclusions by profile filters.</p><p>{row.input_delivery.notice}</p></>}{row.memory_availability&&<><p>At answer time: eligibility recorded for {row.memory_availability.observed_fact_units}/{row.memory_availability.expected_fact_units} exact supporting facts · {row.memory_availability.eligible_fact_units} recorded eligible · {row.memory_availability.capacity_excluded_fact_units} recorded exclusions by capacity.</p><p>Historical records can remain visible after removal from active memory. Missing eligibility records remain unknown.</p>{row.memory_availability.facts.map((fact,i)=><Card size="small" key={i}><b>{fact.reference_label} · retrieval eligibility</b>{fact.matching_record_eligibility.map((r,j)=><p key={j}>{r.record_text} · {({eligible:'Available for retrieval',capacity_excluded:'Removed by capacity limit',superseded_excluded:'Older state excluded by policy',diagnostic_excluded:'Diagnostic packet excluded',excluded_other:'Excluded by another rule',unobserved:'Eligibility not recorded'} as Record<string,string>)[r.eligibility]??'Eligibility not recorded'}</p>)}</Card>)}</>}{row.fact_correspondence && <><p>Exact matches compare source and normalised fact text. Different wording can preserve meaning; check these facts before attributing a defect.</p>{row.fact_correspondence.facts.map((fact,index)=><Card key={index} size="small"><p><b>{fact.reference_label}:</b> {fact.reference_text}</p><p><b>Stored from related sources:</b> {fact.stored_related_text.join(" · ") || "No related record"}</p><p><b>Actually supplied from related sources:</b> {fact.supplied_related_text===null ? "Input not observed" : fact.supplied_related_text.join(" · ") || "No related record supplied"}</p></Card>)}</>}</div>}}/>
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
        <Button disabled={note.trim().length<10||!profile.label.trim()||busy||(diagnosis.source_memory_capacity!==undefined&&(!capacity||capacity<1||capacity>500))} loading={busyAction==='repair'} onClick={()=>prepare('repair')}>Prepare repair comparison</Button>
<Button disabled={busy} loading={busyAction==='methods'} onClick={()=>prepare('methods')}>Prepare audit-method comparison</Button>
        <Button disabled={busy} loading={busyAction==='findings'} onClick={()=>void act('findings',async()=>{await loadMethodResults(packageData?.comparison_id);})}>Inspect confirmed method findings</Button>
        <Button disabled={busy} loading={busyAction==='interventions'} onClick={()=>prepare('interventions')}>Prepare diagnostic interventions</Button>
        <Button disabled={busy||!diagnosis.cases.some(row=>row.automated_passed===false)} loading={busyAction==='follow_up'} onClick={()=>prepare('follow_up')}>Prepare exploratory follow-up</Button>
      </Space>
      <Card title="Independent new-history validation" style={{marginTop:16}}>
        <p>First import and confirm another history through New audit. A different record alone does not prove independence; review for shared facts or scenario templates before treating it as held out.</p>
        <Button style={{marginBottom:12}} onClick={refreshHistories} disabled={busy} loading={busyAction==='histories'}>Refresh reviewed histories</Button>
        <Select virtual={false} showSearch={{optionFilterProp:"label"}} notFoundContent={histories.length?"No matching history. Try another phrase.":"No other reviewed histories. Import and confirm one through New audit."} aria-label="Independent validation history" style={{width:'100%'}} placeholder="Search reviewed histories by scenario or date" value={history} onChange={setHistory} options={histories.map(item=>({value:item.conversation_id,label:item.label}))}/>
        <Button style={{marginTop:12}} disabled={!history||note.trim().length<10||busy||(diagnosis.source_memory_capacity!==undefined&&(!capacity||capacity<1||capacity>500))} loading={busyAction==='held_out'} onClick={()=>prepare('held_out')}>Prepare new-history validation</Button>
      </Card>
    </>}
    {packageData&&<Card title="Prepared experiment" style={{marginTop:16}}>
      <Alert type="warning" title={packageData.notice} showIcon/>
      {packageData.study_role==='audit_method_comparison'&&!packageData.failure_inventory_fingerprint_sha256&&<div className="method-inventory-import">
        <h3>Review the generated draft and source inventory</h3>
        <p>Two reviewers must independently inspect the confirmed facts and source messages, record known failures, and resolve disagreements. The fixed-template questions below were drafted once by the deterministic rule generator from confirmed memories. Review each prompt and expected behaviour, edit or replace questions where needed, and add questions if the draft does not meet the frozen budget or dimension minimums. Reviewer/editor pseudonyms are declarations; the app cannot verify identity or independence.</p>
        <p>Rule draft: {packageData.inventory_template?.fixed_template_questions.length??0} of {packageData.test_budget??'unknown'} questions. The final reviewed release must meet the full budget and dimension minimums.</p>
        <Button disabled={busy||!packageData.inventory_template} onClick={()=>packageData.inventory_template&&downloadJson(`experiment-a-rule-draft-and-inventory-${packageData.comparison_id}.json`,packageData.inventory_template)}>Download rule draft &amp; inventory</Button>
        <Input.TextArea aria-label="Frozen failure inventory and fixed templates JSON" rows={16} disabled={busy} value={packageData.inventory_draft??''}
          onChange={event=>setPackage(current=>current?{...current,inventory_draft:event.target.value}:current)} />
        <Checkbox checked={templateReviewConfirmed} disabled={busy} onChange={event=>setTemplateReviewConfirmed(event.target.checked)}>I reviewed the rule-generated draft, made any needed edits or additions, and confirm this final fixed-template release.</Checkbox>
        <Button type="primary" disabled={busy||!packageData.inventory_draft||!templateReviewConfirmed} loading={busyAction==='methods'} onClick={freezeMethodInventory}>Freeze reviewed release and generate three question sets</Button>
        <p>Use an empty <code>defects</code> list only if reviewers found no in-scope failures. The final questions are source-checked and fingerprinted separately from the initial rule draft. The source fingerprint must match.</p>
      </div>}
      {packageData.study_role==='audit_method_comparison'&&packageData.failure_inventory_fingerprint_sha256&&<Alert type="info" showIcon title={`Source inventory and researcher-reviewed templates frozen · ${packageData.failure_inventory_fingerprint_sha256}`} description="The template began as a deterministic rule draft, then was confirmed through the human review step. Reviewer and author declarations are self-reported; check the signed human worksheets before treating them as research evidence."/>}
      {!reviewRun&&<Button onClick={restore} disabled={busy} loading={busyAction==='restore'}>Restore saved experiment</Button>}
      <p>{packageData.runs.length} conditions · {reviewRun?`${finished.length} completed`:"restore the saved plan to verify progress"}</p>
      <Select virtual={false} aria-label="Condition suite to review" style={{width:'100%',marginBottom:16}} value={reviewRun} disabled={busy} options={packageData.runs.map(run=>({value:run.run_id,label:run.label}))} onChange={value=>void act('select',async()=>{const suite=await api.testReview(value);setSuiteTests(current=>({...current,[value]:suite.tests}));setReviewRun(value);setTests(suite.tests);})}/>
      {(questionsFrozen||finished.length>0)&&<p>The shared questions are frozen because testing has started. You can inspect them and continue pending conditions.</p>}
      <TestSuiteReview tests={tests} busy={busy||questionsFrozen||finished.length>0} onReview={review} onRegenerate={regenerate} onHumanValidityReview={isMethodComparison?reviewHumanValidity:undefined}/>
      <Button type="primary" loading={busyAction==='execute'} disabled={busy||finished.length===packageData.runs.length||!tests.length||(isMethodComparison?!allMethodTestsReady:tests.some(test=>test.quality_status!=='accepted'))} onClick={execute}>{finished.length?'Continue / verify saved conditions':'Run prepared conditions'}</Button>
      {isMethodComparison&&!allMethodTestsReady&&<p className="provider-note">Before Experiment A runs, inspect every condition and accept each question’s quality decision and separate human validity decision.</p>}
      {activeCondition&&<p role="status">Running {activeCondition}. <Button disabled={pauseRequested} onClick={()=>{pauseAfterCurrent.current=true;setPauseRequested(true);}}>Pause after current condition</Button></p>}
      {pauseRequested&&!activeCondition&&<p role="status">The queue paused after saving the current condition. Continue to run the remaining conditions.</p>}
      <ul>{packageData.runs.map(run=><li key={run.run_id}>{run.label} · {finished.includes(run.run_id)?<a href={`/audits/${run.run_id}`}>View completed report</a>:<a href={`/audits/${run.run_id}`}>Inspect saved progress</a>} </li>)}</ul>
      {packageData.runs.length>1&&finished.length===packageData.runs.length&&<><p>Compare every condition, including the generic instruction control. A higher score on these same questions is an exploratory result; check new histories before claiming a general improvement.</p><Button disabled={busy} loading={busyAction==='comparison'} onClick={()=>void act('comparison',async()=>{await loadComparison(packageData);})}>{comparisonRuns.length?'Refresh condition comparison':'Show all conditions together'}</Button><Suspense fallback={<p role="status">Loading comparison chart…</p>}>{comparisonRuns.length>0&&<ConditionCharts runs={comparisonRuns}/>}</Suspense><a href={`/compare?before=${packageData.runs[0].run_id}&after=${packageData.runs[packageData.runs.length-1].run_id}`}>Compare first and last conditions →</a></>}
    </Card>}
    {methodResults&&<Card title="Experiment A results">
      <Alert type={methodResults.inventory.status==='frozen'?'info':'warning'} title={methodResults.notice}/>
      <p>Source inventory: {methodResults.inventory.status} · {methodResults.inventory.distinct_failure_count??'not recorded'} distinct failures · Release {methodResults.inventory.release_id??'not recorded'} · reviewers verified: {methodResults.inventory.authorship_verified?'yes':'no'}</p>
      <p>Fixed templates: {methodResults.inventory.fixed_template_question_count??'not recorded'} researcher-reviewed questions · Draft {methodResults.inventory.fixed_template_draft_generator_version??'not recorded'} · reviewed: {methodResults.inventory.fixed_template_review_confirmed?'yes':'no'} · reviewer identity verified: {methodResults.inventory.fixed_template_review_identity_verified?'yes':'no'}</p>
      <p>Equal test caps: {methodResults.planned_test_budgets_equal?'yes':'no'} · Target and evaluation settings match: {methodResults.target_and_evaluation_settings_match?'yes':'no'} · Realised call attempts equal: {methodResults.realised_call_attempts_equal===null?'not measured':methodResults.realised_call_attempts_equal?'yes':'no'}</p>
      {methodResults.conditions.map(condition=>{
        const draft=discoveryDrafts[condition.run_id];
        const frozen=condition.discovery_mapping.status==='frozen';
        const canMap=methodResults.inventory.status==='frozen'&&condition.discovery_mapping.status==='awaiting_researcher_mapping';
        return <Card key={condition.run_id} size="small" title={`Researcher map · ${condition.label}`} style={{marginTop:16}}>
          <Alert type={frozen?'info':'warning'} showIcon title={frozen
            ? `Mapping frozen · ${condition.discovery_mapping.release_id} · ${condition.discovery_mapping.mapped_response_count}/${condition.discovery_mapping.total_response_count} responses`
            : canMap?`Failure Discovery Rate: ${condition.failure_discovery_rate.status}`:`Mapping unavailable · ${condition.discovery_mapping.status}`}
            description={frozen
              ? `Researcher: ${condition.discovery_mapping.reviewer_pseudonym??'not recorded'} · Mapping fingerprint: ${condition.discovery_mapping.fingerprint_sha256??'not recorded'}`
              : canMap?'Review every saved question and answer. Assign each frozen defect it reveals; leave the selection empty only when no known defect was found. Unmapped or unknown records keep the rate unmeasured.':'This saved release cannot be edited here. Check the frozen inventory and response records, then start a new comparison if the mapping is inconsistent.'}/>
          <p>Frozen failure IDs: {methodResults.inventory.defects.length?methodResults.inventory.defects.map(defect=>`${defect.defect_id} (${defect.dimension})`).join(' · '):'No known failures in the frozen inventory.'}</p>
          {methodResults.inventory.defects.map(defect=><p key={defect.defect_id}><b>{defect.defect_id}:</b> {defect.explanation}</p>)}
          {!frozen&&<Space wrap style={{marginBottom:12}}>
            <Input aria-label={`${condition.label} mapping release ID`} placeholder="Mapping release ID" value={draft?.mapping_release_id??''} disabled={busy||!canMap} onChange={event=>updateDiscoveryDraft(condition.run_id,current=>({...current,mapping_release_id:event.target.value}))}/>
            <Input aria-label={`${condition.label} mapping reviewer pseudonym`} placeholder="Reviewer pseudonym" value={draft?.reviewer_pseudonym??''} disabled={busy||!canMap} onChange={event=>updateDiscoveryDraft(condition.run_id,current=>({...current,reviewer_pseudonym:event.target.value}))}/>
          </Space>}
          <Table size="small" scroll={{x:1100}} rowKey="response_id" pagination={{pageSize:5}} dataSource={draft?.entries??condition.discovery_mapping.entries} columns={[
            {title:'Question',dataIndex:'question',width:240},
            {title:'Saved response',dataIndex:'response',width:360},
            {title:'Independent label',dataIndex:'human_passed',width:150,render:(value:boolean|null)=>value===null?'Not resolved':value?'Human-labeled pass':'Human-labeled failure'},
            {title:'Frozen defect IDs found',dataIndex:'defect_ids',width:300,render:(_:string[],entry:DiscoveryEntry)=><Select mode="multiple" virtual={false} aria-label={`Defects found in response ${entry.response_id}`} style={{minWidth:260,width:'100%'}} disabled={busy||!canMap} value={draft?.entries.find(item=>item.response_id===entry.response_id)?.defect_ids??entry.defect_ids} onChange={values=>draft&&updateDiscoveryDraft(condition.run_id,current=>({...current,entries:current.entries.map(item=>item.response_id===entry.response_id?{...item,defect_ids:values}:item)}))} options={methodResults.inventory.defects.map(defect=>({value:defect.defect_id,label:`${defect.defect_id} · ${defect.dimension}`}))}/>},
          ]}/>
          {!frozen&&<>
            <Checkbox checked={discoveryConfirmations[condition.run_id]??false} disabled={busy||!canMap} onChange={event=>setDiscoveryConfirmations(current=>({...current,[condition.run_id]:event.target.checked}))}>I reviewed every response-to-defect link above, including responses with no selected known failure, and confirm this human mapping release.</Checkbox>
            <Button type="primary" style={{marginTop:12}} disabled={busy||!canMap||!draft||!draft.reviewer_pseudonym.trim()||!draft.mapping_release_id.trim()||!discoveryConfirmations[condition.run_id]} loading={busyAction==='mapping'} onClick={()=>saveDiscoveryMapping(condition)}>Freeze response-to-defect mapping</Button>
          </>}
        </Card>;
      })}
      <ExperimentAMethodChart conditions={methodResults.conditions}/>
      <Button disabled={busy} onClick={()=>downloadJson(`experiment-a-results-${methodResults.comparison_id}.json`,methodResults)}>Download Experiment A results (JSON)</Button>
      <Table scroll={{x:1400}} rowKey="run_id" dataSource={methodResults.conditions} columns={[
        {title:'Question method',dataIndex:'label'},
        {title:'Valid questions',render:(_,row)=>`${row.valid_test_count}/${row.test_count}`},
        {title:'Human validity review',render:(_,row)=>`${row.human_validity_accepted_count}/${row.test_count} accepted · ${row.human_validity_pending_count} pending`},
        {title:'Category Coverage',render:(_,row)=>row.category_coverage.value===null?'Not measured':`${row.category_coverage.covered_dimensions}/${row.category_coverage.total_dimensions} · ${Math.round(row.category_coverage.value*100)}%`},
        {title:'Failure Detection Recall',render:(_,row)=>row.response_level.failure_detection_recall===null?`Not measured · ${row.response_level.status}`:`${row.response_level.true_positives}/${row.response_level.true_positives+row.response_level.false_negatives} · ${Math.round(row.response_level.failure_detection_recall*100)}%`},
        {title:'Failure Discovery Rate',render:(_,row)=>row.failure_discovery_rate.value===null?`Not measured · ${row.failure_discovery_rate.status}`:`${row.failure_discovery_rate.discovered_distinct_failures}/${row.failure_discovery_rate.known_distinct_failures} · ${Math.round(row.failure_discovery_rate.value*100)}%`},
        {title:'False-positive rate',render:(_,row)=>row.response_level.false_positive_rate===null?`Not measured · ${row.response_level.status}`:`${row.response_level.false_positives}/${row.response_level.false_positives+row.response_level.true_negatives} · ${Math.round(row.response_level.false_positive_rate*100)}%`},
        {title:'Completed answers',dataIndex:'completed_answers'},
        {title:'Independent labels',render:(_,row)=>`${row.response_level.independently_labelled_responses}/${row.completed_answers}`},
        {title:'Recorded target attempts',dataIndex:'actual_target_call_attempts',render:(value:number|null)=>value===null?'Not recorded':value},
      ]}/>
    </Card>}
    {result&&<Card title="Latest condition result"><p>{result.tests_passed}/{result.tests_total} decided tests passed; {result.uncertain_count??0} remain uncertain.</p><a href={`/audits/${result.run_id}`}>Open evidence and full report →</a></Card>}
  </Card>;
}
export type {Diagnosis,DiagnosticAgentResponse,Package};
