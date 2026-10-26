import { useRef, useState } from 'react';
import { Alert, Button, Checkbox, Collapse, Space, Table } from 'antd';
import { UIInput } from './ui';
import { api } from '../services/api';
import { saveBlob } from '../services/download';
import type { RankingAgreementResult } from './BenchmarkRankingAgreement';
import type { AuditRun } from '../types/domain';
import { BenchmarkExecutionPlan } from './BenchmarkExecutionPlan';
import { memoryStrategyLabel } from '../services/display';

interface RepeatInput {
  planned_trial_ids:string[];
  trials:Array<{trial_id:string;unavailable_reason?:string;comparison?:{
    reference_run_id:string;candidate_run_id:string;reference_benchmark:Record<string,unknown>;candidate_benchmark:Record<string,unknown>;
  }|null}>;
}
export interface RepeatedRankingResult {
  plan_provenance?:'caller_declared_analysis_plan'|'server_frozen_preexecution_plan';
  version:string;status:'complete'|'partial';planned_trials:number;measured_trials:number;missing_trials:number;
  invalid_trials:number;unmeasured_trials:number;directional_trials:number;consistent_trials:number;reversed_trials:number;
  both_tied_trials:number;inconclusive_tie_trials:number;ranking_agreement_percentage:number|null;notice:string;
  provider?:string|null;model?:string|null;reference_strategy?:AuditRun['memory_strategy']|null;candidate_strategy?:AuditRun['memory_strategy']|null;
  trials:Array<{trial_id:string;status:'measured'|'missing'|'invalid'|'unmeasured';reason?:string|null;report?:RankingAgreementResult|null}>;
  suites:Array<{label:string;score_basis:string;measured_trials:number;reference_mean_percentage:number|null;
    candidate_mean_percentage:number|null;reference_standard_deviation:number|null;candidate_standard_deviation:number|null;ordering:string}>;
}

export function RepeatedBenchmarkRanking(){
  const [authorised,setAuthorised]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [input,setInput]=useState<RepeatInput|null>(null),[name,setName]=useState('No file selected');
  const [report,setReport]=useState<RepeatedRankingResult|null>(null);
  const [planId,setPlanId]=useState('');
  const active=useRef(false),revision=useRef(0);
  function authorise(checked:boolean){revision.current++;active.current=false;setBusy(false);setAuthorised(checked);setInput(null);setName('No file selected');setReport(null);setError('');}
  async function load(file:File){
    if(!authorised||active.current)return;const operation=++revision.current;active.current=true;setBusy(true);setInput(null);setName('No file selected');setReport(null);setError('');
    try{
      if(file.size>10_000_000)throw new Error('Choose a repeated comparison file smaller than 10 MB.');
      const text=await file.text();if(operation!==revision.current)return;const value=JSON.parse(text);
      if(!value||!Array.isArray(value.planned_trial_ids)||!Array.isArray(value.trials))throw new Error('Choose a package with planned_trial_ids and trials.');
      setInput(value);setName(file.name);
    }catch(cause){if(operation===revision.current)setError(cause instanceof Error?cause.message:'The repeated comparison could not be read.');}
    finally{if(operation===revision.current){active.current=false;setBusy(false);}}
  }
  async function compare(){
    if(!authorised||!input||active.current)return;const operation=revision.current;active.current=true;setBusy(true);setReport(null);setError('');
    try{
      const body={...input,trials:input.trials.map(trial=>({...trial,
        comparison:trial.comparison?{...trial.comparison,reference_benchmark:{...trial.comparison.reference_benchmark,source_authorised:true},
          candidate_benchmark:{...trial.comparison.candidate_benchmark,source_authorised:true}}:null}))};
      const value=await (planId.trim()?api.analyseBenchmarkPlan(planId.trim(),body):api.compareRepeatedBenchmarkRankings(body));
      if(operation===revision.current)setReport(value);
    }catch(cause){if(operation===revision.current)setError(cause instanceof Error?cause.message:'Repeated results could not be compared.');}
    finally{if(operation===revision.current){active.current=false;setBusy(false);}}
  }
  const percentage=(value:number|null)=>value===null?'Not measured':`${value}%`;
  const deviation=(value:number|null)=>value===null?'Not measured':`${value} percentage points`;
  return <section aria-labelledby="repeated-ranking-title">
    <BenchmarkExecutionPlan onPlanReady={id=>{revision.current++;active.current=false;setBusy(false);setPlanId(id);setReport(null);}}/>
    <h4 id="repeated-ranking-title">Compare repeated results</h4>
    <p>Supply at least three planned trials using distinct saved audit and benchmark executions. Missing and invalid trials remain visible. A complete plan is required for aggregate scores.</p>
    <Checkbox aria-label="Repeated ranking source authorisation" checked={authorised} onChange={event=>authorise(event.target.checked)}>I am authorised to process every benchmark source in this repeated comparison package.</Checkbox>
    <label>Repeated comparison package<UIInput type="file" aria-label="Repeated ranking package" accept=".json,application/json" disabled={!authorised||busy} onChange={event=>{const file=event.target.files?.[0];if(file)void load(file);}}/><small>{name}</small></label>
    <label>Frozen execution plan ID (optional)<UIInput aria-label="Ranking frozen execution plan ID" value={planId} disabled={busy} onChange={event=>{revision.current++;setPlanId(event.target.value);setReport(null);}}/></label>
    <p>{planId.trim()?'Analysis will use the server plan and its original execution receipts.':'Without a saved plan ID, this is descriptive analysis of an uploaded plan.'}</p>
    <Space wrap><Button disabled={!authorised||!input||busy} loading={busy} onClick={()=>void compare()}>Compare repeated rankings</Button>
      <Button onClick={()=>saveBlob(new Blob([JSON.stringify({planned_trial_ids:['trial-1','trial-2','trial-3'],trials:[1,2,3].map(i=>({trial_id:`trial-${i}`,comparison:null,unavailable_reason:'Awaiting saved repeat evidence.'}))},null,2)],{type:'application/json'}),'repeated-ranking-input-template.json')}>Download input template</Button></Space>
    {error&&<Alert type="error" showIcon title={error}/>}
    {report&&<div className="research-report">
      <h5>{report.status==='complete'?'All planned trials measured':'Repeated comparison is incomplete'}</h5>
      <p><small>{report.plan_provenance==='server_frozen_preexecution_plan'?'Analysis bound to a server plan saved before these executions. Independent review and earlier unseen results remain unverified; this is not an official benchmark score.':'Descriptive analysis of saved results. The uploaded plan does not establish pre-registration, independent review or an official benchmark score.'}</small></p>
      {report.model&&<p>{report.model} · Strategy 1: {report.reference_strategy?memoryStrategyLabel(report.reference_strategy):'Not measured'} · Strategy 2: {report.candidate_strategy?memoryStrategyLabel(report.candidate_strategy):'Not measured'}</p>}
      <p>{report.measured_trials} / {report.planned_trials} trials measured · {report.missing_trials} missing · {report.invalid_trials} invalid · {report.unmeasured_trials} without full dimension coverage</p>
      <p>Ranking agreement: <b>{percentage(report.ranking_agreement_percentage)}</b> · {report.consistent_trials} of {report.directional_trials} directional trials agree · {report.reversed_trials} reversed · {report.both_tied_trials} both tied · {report.inconclusive_tie_trials} one question set tied</p>
      <Table pagination={false} scroll={{x:650}} rowKey="label" dataSource={report.suites} columns={[
        {title:'Question set / score',dataIndex:'label',render:(label:string,row:RepeatedRankingResult['suites'][number])=><span>{label}<br/><small>{row.score_basis==='dimension_macro_average'?'Four-dimension Overall Memory Health':'Benchmark response accuracy'} · {row.measured_trials} measured repeats</small></span>},
        {title:'Strategy 1 mean / variability',render:(_,row:RepeatedRankingResult['suites'][number])=><span>{percentage(row.reference_mean_percentage)}<br/>Sample SD: {deviation(row.reference_standard_deviation)}</span>},
        {title:'Strategy 2 mean / variability',render:(_,row:RepeatedRankingResult['suites'][number])=><span>{percentage(row.candidate_mean_percentage)}<br/>Sample SD: {deviation(row.candidate_standard_deviation)}</span>},
      ]}/>
      <Table pagination={false} scroll={{x:550}} rowKey="trial_id" dataSource={report.trials} columns={[
        {title:'Planned trial',dataIndex:'trial_id'},{title:'Status',dataIndex:'status'},
        {title:'Evidence or reason',render:(_,row:RepeatedRankingResult['trials'][number])=>row.reason??row.report?.agreement??'No evidence'},
      ]}/>
      <Button onClick={()=>saveBlob(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}),'repeated-policy-ranking-agreement.json')}>Download repeated comparison evidence</Button>
      <Collapse items={[{key:'evidence',label:'Inspect per-trial evidence and limits',children:<><p>{report.notice}</p><pre style={{maxHeight:400,overflow:'auto'}}>{JSON.stringify(report.trials,null,2)}</pre></>}]} />
    </div>}
  </section>;
}
