import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Collapse, Select, Space } from 'antd';
import { UIInput } from './ui';
import { api } from '../services/api';
import { memoryStrategyLabel } from '../services/display';
import { saveBlob } from '../services/download';
import type { AuditRun } from '../types/domain';
import { RepeatedBenchmarkRanking } from './RepeatedBenchmarkRanking';

export interface RankingAgreementResult {
  version:string;provider:string;model:string;reference_strategy:AuditRun['memory_strategy'];candidate_strategy:AuditRun['memory_strategy'];
  agreement:'consistent'|'reversed'|'both_tied'|'inconclusive_tie'|'inconclusive_missing_dimensions';notice:string;
  suites:Array<{label:string;total:number;reference_correct:number;candidate_correct:number;reference_percentage:number|null;candidate_percentage:number|null;ordering:string;score_basis?:'dimension_macro_average'|'response_accuracy';dimensions?:Array<{dimension:string;total:number;reference_percentage:number|null;candidate_percentage:number|null}>}>;
}
export function BenchmarkRankingAgreement(){
  const [runs,setRuns]=useState<AuditRun[]>([]),[reference,setReference]=useState(''),[candidate,setCandidate]=useState('');
  const [files,setFiles]=useState<{reference:object|null;candidate:object|null}>({reference:null,candidate:null});
  const [names,setNames]=useState({reference:'No file selected',candidate:'No file selected'});
  const [sourceAuthorised,setSourceAuthorised]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[report,setReport]=useState<RankingAgreementResult|null>(null);
  const active=useRef(false),revisionRef=useRef(0);
  useEffect(()=>{let current=true;api.audits().then(value=>{if(current)setRuns(value.filter(r=>r.status==='COMPLETED'&&r.provider!=='rule_based'&&!!r.experiment_id&&!r.reproducibility?.assessment_source_run_id&&!r.reproducibility?.shared_answer_source_run_id));}).catch(()=>{if(current)setError('Saved audits could not be loaded. Reopen this panel to try again.');});return()=>{current=false;};},[]);
  const choices=runs.filter(r=>['weak_first_hit','strong_rule_based'].includes(r.memory_strategy)&&runs.some(peer=>['weak_first_hit','strong_rule_based'].includes(peer.memory_strategy)&&peer.experiment_id===r.experiment_id&&peer.memory_strategy!==r.memory_strategy&&peer.provider===r.provider&&peer.model===r.model)).map((r,index)=>({value:r.run_id,label:`Audit ${index+1} · ${new Date(r.created_at).toLocaleString()} · ${r.model} · ${memoryStrategyLabel(r.memory_strategy)}`}));
  async function load(kind:'reference'|'candidate',file:File){
    if(active.current||!sourceAuthorised)return;const revision=++revisionRef.current;active.current=true;setBusy(true);setError('');setReport(null);setFiles(v=>({...v,[kind]:null}));setNames(v=>({...v,[kind]:'No file selected'}));
    try{if(file.size>10_000_000)throw new Error('Choose an assessment input smaller than 10 MB.');const text=await file.text();if(revision!==revisionRef.current)return;const value:unknown=JSON.parse(text);
      if(!value||typeof value!=='object'||!('source' in value)||!('evidence' in value)||!('rows' in value)||!('strategy' in value))throw new Error('Choose an assessment input downloaded from Review saved benchmark assessments.');
      setFiles(v=>({...v,[kind]:value}));setNames(v=>({...v,[kind]:file.name}));
    }catch(cause){if(revision===revisionRef.current)setError(cause instanceof SyntaxError?'Choose a valid assessment JSON file.':cause instanceof Error?cause.message:'The file could not be read.');}
    finally{if(revision===revisionRef.current){active.current=false;setBusy(false);}}
  }
  async function compare(){
    if(active.current||!sourceAuthorised||!reference||!candidate||reference===candidate||!files.reference||!files.candidate)return;
    const operation=revisionRef.current;active.current=true;setBusy(true);setError('');setReport(null);
    try{const value=await api.compareBenchmarkRankings({reference_run_id:reference,candidate_run_id:candidate,reference_benchmark:{...files.reference,source_authorised:sourceAuthorised},candidate_benchmark:{...files.candidate,source_authorised:sourceAuthorised}});if(operation===revisionRef.current)setReport(value);}
    catch(cause){if(operation===revisionRef.current)setError(cause instanceof Error?cause.message:'These results could not be compared.');}
    finally{if(operation===revisionRef.current){active.current=false;setBusy(false);}}
  }
  function updateSourceAuthorisation(checked:boolean){revisionRef.current++;active.current=false;setBusy(false);setSourceAuthorised(checked);setFiles({reference:null,candidate:null});setNames({reference:'No file selected',candidate:'No file selected'});setReport(null);setError('');}
  const headings={consistent:'Both question sets favour the same strategy',reversed:'The two question sets favour different strategies',both_tied:'Both question sets are tied',inconclusive_tie:'One question set is tied — agreement is inconclusive',inconclusive_missing_dimensions:'Auditor dimension coverage is incomplete — ranking is not measured'};
  return <section aria-labelledby="ranking-agreement-title" className="research-workspace">
    <h3 id="ranking-agreement-title">Does the benchmark agree?</h3>
    <p>Compare strategy ordering across audit and benchmark questions. Same model and memory settings required. Saved-result checks make no model calls; running a repeat in the execution plan below calls the selected model.</p>
    {error&&<Alert type="error" title={error} showIcon/>}
    <p><small>Choose two strategies from one completed experiment. Download each benchmark assessment input from the review section above.</small></p>
    <Checkbox aria-label="Ranking benchmark source authorisation" checked={sourceAuthorised} onChange={e=>updateSourceAuthorisation(e.target.checked)}>I am authorised to process the original benchmark sources in these assessment files. Checking permits the browser to read them and send them to this local Auditor for comparison.</Checkbox>
    <div className="benchmark-controls-grid">{(['reference','candidate'] as const).map((kind,index)=><div key={kind}>
      <label>Strategy {index+1} audit<Select virtual={false} notFoundContent={kind==='reference'?'No completed strategy pair. Create and run a shared-question memory strategy comparison first.':'Select a first strategy with another completed strategy in the same experiment.'} aria-label={`Ranking ${kind} audit`} disabled={busy} options={kind==='reference'?choices:choices.filter(choice=>{const first=runs.find(r=>r.run_id===reference);const other=runs.find(r=>r.run_id===choice.value);return !!first&&!!other&&other.run_id!==first.run_id&&other.experiment_id===first.experiment_id&&other.memory_strategy!==first.memory_strategy&&other.provider===first.provider&&other.model===first.model;})} value={(kind==='reference'?reference:candidate)||undefined} onChange={value=>{(kind==='reference'?setReference:setCandidate)(value);if(kind==='reference')setCandidate('');setReport(null);setError('');}} showSearch optionFilterProp="label"/></label>
      <label>Strategy {index+1} benchmark assessments<UIInput type="file" aria-label={`Ranking ${kind} assessments`} accept=".json,application/json" disabled={busy||!sourceAuthorised} onChange={e=>{const file=e.target.files?.[0];if(file)void load(kind,file);}}/><small>{names[kind]}</small></label>
    </div>)}</div>
    <Button aria-label="Check ranking agreement" type="primary" loading={busy} disabled={busy||!sourceAuthorised||!reference||!candidate||reference===candidate||!files.reference||!files.candidate} onClick={()=>void compare()}>Check ranking agreement</Button>
    {report&&<div className="research-report"><h4>{headings[report.agreement]}</h4>
      <figure aria-label="Policy ranking across question sets"><div className="reliability-legend"><span><i style={{background:'#087ea4'}}/>Strategy 1 · {memoryStrategyLabel(report.reference_strategy)}</span><span><i style={{background:'#16806a'}}/>Strategy 2 · {memoryStrategyLabel(report.candidate_strategy)}</span></div>
        {report.suites.map(suite=><div key={suite.label} style={{margin:'20px 0'}}><b>{suite.label} · {suite.total} questions</b><small> · {suite.score_basis==='dimension_macro_average'?'Overall Memory Health · four abilities weighted equally':'Response accuracy'}</small>{([['reference','#087ea4'],['candidate','#16806a']] as const).map(([key,color],index)=><div key={key} style={{marginTop:10}}><span>{suite[`${key}_percentage`]===null?`Strategy ${index+1}: Not measured`:suite.score_basis==='dimension_macro_average'?`Strategy ${index+1}: Overall Memory Health ${suite[`${key}_percentage`]}%`:`Strategy ${index+1}: ${suite[`${key}_correct`]} / ${suite.total} · ${suite[`${key}_percentage`]}%`}</span>{suite.score_basis==='dimension_macro_average'&&<small> · {suite[`${key}_correct`]} of {suite.total} valid answers passed</small>}{suite[`${key}_percentage`]!==null&&<div style={{height:14,background:'#eef2f5',borderRadius:7,overflow:'hidden'}}><div style={{width:`${suite[`${key}_percentage`]}%`,height:'100%',background:color}}/></div>}</div>)}{suite.dimensions?.length? <Collapse items={[{key:'dimensions',label:'View dimension scores and question counts',children:<ul>{suite.dimensions.map(row=><li key={row.dimension}>{row.dimension.replaceAll('_',' ')} · {row.total} questions · Strategy 1 {row.reference_percentage===null?'Not measured':`${row.reference_percentage}%`} · Strategy 2 {row.candidate_percentage===null?'Not measured':`${row.candidate_percentage}%`}</li>)}</ul>}]} />:null}</div>)}
        <figcaption>Compare the ordering within each question set. Scores across the two sets are not directly comparable.</figcaption>
      </figure><Alert type="info" showIcon title="Descriptive agreement only. Independent human validation and repeated trials are still needed."/>
      <Space><Button onClick={()=>saveBlob(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}),'policy-ranking-agreement.json')}>Download comparison evidence</Button></Space>
      <Collapse items={[{key:'limits',label:'What this comparison can show',children:<p>{report.notice}</p>}]} />
    </div>}
    <RepeatedBenchmarkRanking />
  </section>;
}
