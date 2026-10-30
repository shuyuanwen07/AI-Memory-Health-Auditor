import { useRef, useState } from 'react';
import { Alert, Button, Checkbox, Collapse, Space, Table } from 'antd';
import { UIInput } from './ui';
import { api } from '../services/api';
import { saveBlob } from '../services/download';

export interface BenchmarkPlan {
  plan_id:string;created_at:string;plan_fingerprint_sha256:string;notice:string;
  protocol:{trials:Array<{trial_id:string;reference_run_id:string;candidate_run_id:string}>;
    sampling_rule:string;evaluator_model:string;evaluator_revision:string;planned_target_calls:number;
    benchmark:{case_ids:string[];configuration:Record<string,unknown>}};
  executions:Record<string,{status:string;error_code?:string;benchmark_run_id?:string;evidence_fingerprint_sha256?:string;dashboard_summary?:{metric:'lexical_match';conditions:Array<{strategy:string;matched:number;total:number;case_ids?:string[]}>};human_reviews?:Array<{review_id:string;reviewers:Array<{reviewer:string;judgments:Array<{strategy:string;case_id:string;verdict:'pass'|'fail'|'uncertain'}>}>}>}>;
}
interface PlanInput {benchmark:Record<string,unknown>;trials:unknown[];sampling_rule:string;evaluator_model:string;evaluator_revision:string}
const template={benchmark:{payload:[],source_authorised:false,dataset_provenance:{dataset_version:'',license:'',citation:''},provider:'openrouter',model:'openai/gpt-6-luna',strategies:['weak_first_hit','strong_rule_based'],target_memory_profile:{output_token_limit:192}},trials:[1,2,3].map(i=>({trial_id:`repeat-${i}`,reference_run_id:'',candidate_run_id:''})),sampling_rule:'',evaluator_model:'',evaluator_revision:'',metadata_storage_authorised:false};

export function BenchmarkExecutionPlan({onPlanReady}:{onPlanReady:(id:string)=>void}){
  const [authorised,setAuthorised]=useState(false),[storage,setStorage]=useState(false),[busy,setBusy]=useState(false);
  const [input,setInput]=useState<PlanInput|null>(null),[name,setName]=useState('No execution file selected');
  const [plan,setPlan]=useState<BenchmarkPlan|null>(null),[planId,setPlanId]=useState(''),[error,setError]=useState('');
  const [evidence,setEvidence]=useState<Array<{planId:string;trial:string;value:unknown}>>([]);
  const [listed,setListed]=useState(false);
  const [savedPlans,setSavedPlans]=useState<BenchmarkPlan[]>([]);
  const active=useRef(false),revision=useRef(0);
  function consent(checked:boolean){revision.current++;setAuthorised(checked);setInput(null);setName('No execution file selected');setEvidence([]);setError('');}
  async function operation(work:(current:()=>boolean)=>Promise<void>){
    if(active.current)return;active.current=true;setBusy(true);setError('');const token=revision.current;
    try{await work(()=>token===revision.current);}catch(cause){if(token===revision.current)setError(cause instanceof Error?cause.message:'The plan operation failed.');}
    finally{active.current=false;setBusy(false);}
  }
  function load(file:File){if(!authorised||active.current)return;void operation(async current=>{
    setInput(null);setName('No execution file selected');
    if(file.size>10_000_000)throw new Error('Choose an execution plan file smaller than 10 MB.');
    const value=JSON.parse(await file.text());if(!current())return;
    if(!value||!value.benchmark||!Array.isArray(value.trials))throw new Error('Choose a plan containing benchmark and trials.');
    setInput(value);setName(file.name);
  });}
  function adopt(value:BenchmarkPlan){setPlan(value);setPlanId(value.plan_id);onPlanReady(value.plan_id);}
  function freeze(){if(!authorised||!storage||!input)return;void operation(async current=>{
    const value=await api.createBenchmarkPlan({...input,benchmark:{...input.benchmark,source_authorised:true},metadata_storage_authorised:true});
    if(current())adopt(value);
  });}
  function restore(){if(!planId.trim())return;void operation(async current=>{
    const value=await api.restoreBenchmarkPlan(planId.trim());if(current())adopt(value);
  });}
  function find(){void operation(async current=>{const values=await api.listBenchmarkPlans();if(current()){setSavedPlans(values);setListed(true);}});}
  function reviewTemplate(trial:string){
    if(!plan)return;
    const execution=plan.executions[trial];
    const judgments=(execution.dashboard_summary?.conditions??[]).flatMap(row=>(row.case_ids??[]).map(case_id=>({strategy:row.strategy,case_id,verdict:'uncertain'})));
    saveBlob(new Blob([JSON.stringify({evidence_fingerprint_sha256:execution.evidence_fingerprint_sha256,independent_review_confirmed:false,reviewers:[{reviewer:'',judgments},{reviewer:'',judgments}]},null,2)],{type:'application/json'}),`benchmark-human-review-${trial}.json`);
  }
  function importReview(trial:string,file:File){if(!plan||active.current)return;void operation(async current=>{
    if(file.size>1_000_000)throw new Error('Choose a review file smaller than 1 MB.');
    const value=JSON.parse(await file.text());
    await api.importBenchmarkHumanReview(plan.plan_id,trial,value);
    const refreshed=await api.restoreBenchmarkPlan(plan.plan_id);if(current())adopt(refreshed);
  });}
  function execute(trial:string){if(!authorised||!input||!plan)return;void operation(async current=>{
    setPlan({...plan,executions:{...plan.executions,[trial]:{status:'Status pending'}}});
    try {
      const value=await api.executeBenchmarkPlan(plan.plan_id,{trial_id:trial,benchmark:{...input.benchmark,source_authorised:true}});
      if(!current())return;
      // Preserve evidence and disable redispatch before the status refresh.
      setEvidence(previous=>[...previous,{planId:plan.plan_id,trial,value}]);
      setPlan({...plan,executions:{...plan.executions,[trial]:{status:'COMPLETED'}}});
      const refreshed=await api.restoreBenchmarkPlan(plan.plan_id);if(current())adopt(refreshed);
    } catch(cause) {
      // A lost reply may have completed server-side. Restore its receipt,
      // never resend the model request to determine whether it succeeded.
      try {const restored=await api.restoreBenchmarkPlan(plan.plan_id);if(current())adopt(restored);}catch{/* Keep the unknown state until an explicit restore. */}
      throw cause;
    }
  });}
  return <section aria-labelledby="benchmark-execution-plan-title">
    <h4 id="benchmark-execution-plan-title">Plan and run the benchmark comparison</h4>
    <p>1. Prepare at least three paired audit runs for first-match retrieval and relationship-priority retrieval, using reviewed questions with no target answers. 2. Save this plan before running those audits. 3. Run each benchmark repeat below and save its original answers. 4. Import the scored answers under Compare repeated results.</p>
    <Checkbox aria-label="Planned benchmark source authorisation" checked={authorised} onChange={event=>consent(event.target.checked)}>I am authorised to process the benchmark source with the selected model service.</Checkbox>
    <label>Execution plan file<UIInput aria-label="Benchmark execution plan file" type="file" accept=".json,application/json" disabled={!authorised||busy} onChange={event=>{const file=event.target.files?.[0];if(file)load(file);}}/><small>{name}</small></label>
    <Checkbox aria-label="Benchmark plan metadata permission" checked={storage} disabled={busy} onChange={event=>setStorage(event.target.checked)}>I permit saving the plan settings, source fingerprints, licence/citation and execution status on this server.</Checkbox>
    <Space wrap><Button disabled={!authorised||!storage||!input||busy} onClick={freeze}>Save frozen benchmark plan</Button><Button onClick={()=>saveBlob(new Blob([JSON.stringify(template,null,2)],{type:'application/json'}),'benchmark-execution-plan-template.json')}>Download execution plan template</Button></Space>
    <p>The template is incomplete until your team supplies the permitted subset, saved audit IDs, matching settings, selection rule and evaluator standard. Source text and full benchmark answers are not saved on the server.</p>
    <label>Saved execution plan ID<UIInput aria-label="Saved benchmark execution plan ID" value={planId} disabled={busy} onChange={event=>{revision.current++;setPlanId(event.target.value);setPlan(null);setEvidence([]);onPlanReady('');}}/></label>
    <Space wrap><Button disabled={!planId.trim()||busy} onClick={restore}>Restore benchmark plan</Button><Button disabled={busy} onClick={find}>Find saved benchmark plans</Button></Space>{savedPlans.length>0&&<ul>{savedPlans.map(value=><li key={value.plan_id}><Button disabled={busy} onClick={()=>adopt(value)}>{value.plan_id}</Button> · {new Date(value.created_at).toLocaleString()}</li>)}</ul>}
    {busy&&<p role="status" aria-live="polite">Working on your benchmark plan…</p>}
    {listed&&savedPlans.length===0&&<p role="status">No saved benchmark plans found.</p>}
    {error&&<Alert role="alert" type="error" showIcon title={error}/>}
    {plan&&<div className="research-report"><h5>Execution plan saved</h5><p>Plan ID: <b>{plan.plan_id}</b> · saved {new Date(plan.created_at).toLocaleString()}</p>
      <p>{plan.protocol.trials.length} planned repeats · {plan.protocol.benchmark.case_ids.length} benchmark cases · {plan.protocol.planned_target_calls} planned answer slots. Run your saved Auditor pairs separately with their frozen settings.</p>
      <p>A restored plan needs its matching execution file and current source permission before starting any repeat. A recorded repeat cannot be silently run again; keep failed or missing evidence in the analysis.</p>
      <Table pagination={false} scroll={{x:550}} rowKey="trial_id" dataSource={plan.protocol.trials} columns={[
        {title:'Repeat',dataIndex:'trial_id'},
        {title:'Saved execution status',render:(_,row)=>plan.executions[row.trial_id]?.status??'Not started'},
        {title:'Action',render:(_,row)=><Button aria-label={`Run benchmark ${row.trial_id}`} disabled={busy||!authorised||!input||!!plan.executions[row.trial_id]} onClick={()=>execute(row.trial_id)}>Run this repeat</Button>},
      ]}/>
      <h5>Independent human review</h5><p>Use the original downloaded benchmark answers and source evidence to review each case. Download a trial template, enter both reviewer pseudonyms and each verdict, confirm independence in the file, then import it. Review versions are retained; unresolved disagreements remain separate.</p>
      {plan.protocol.trials.filter(t=>plan.executions[t.trial_id]?.dashboard_summary?.conditions.some(c=>c.case_ids?.length)).map(t=><div key={`review-${t.trial_id}`}><b>{t.trial_id}</b> <Button disabled={busy} onClick={()=>reviewTemplate(t.trial_id)}>Download review JSON</Button> <label>Import completed review <input type="file" accept=".json,application/json" disabled={busy} onChange={e=>{const file=e.target.files?.[0];if(file)importReview(t.trial_id,file);e.currentTarget.value='';}}/></label> · {plan.executions[t.trial_id].human_reviews?.length??0} saved versions</div>)}
      <Button onClick={()=>saveBlob(new Blob([JSON.stringify(plan,null,2)],{type:'application/json'}),'frozen-benchmark-plan.json')}>Download frozen execution plan</Button>
      <Collapse items={[{key:'plan',label:'Inspect frozen settings and limits',children:<><p>{plan.notice}</p><pre style={{maxHeight:350,overflow:'auto'}}>{JSON.stringify(plan,null,2)}</pre></>}]} />
    </div>}
    {evidence.map(item=><div className="research-report" key={`${item.planId}:${item.trial}`}><h5>Original answers available for {item.trial}</h5><p>Plan {item.planId}. Save these answers before leaving this page or switching plans. The server retains their fingerprint, not the full reply. This is execution evidence; scoring and independent review still need to be supplied.</p><Button onClick={()=>saveBlob(new Blob([JSON.stringify(item.value,null,2)],{type:'application/json'}),`benchmark-original-${item.trial}.json`)}>Download original benchmark answers</Button><Collapse items={[{key:'answers',label:'Inspect original answer file',children:<pre style={{maxHeight:350,overflow:'auto'}}>{JSON.stringify(item.value,null,2)}</pre>}]} /></div>)}
  </section>;
}
