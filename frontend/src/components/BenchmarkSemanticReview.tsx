import { useRef, useState } from 'react';
import { Alert, Button, Collapse, Input, Progress, Select, Space } from 'antd';
import { UIInput } from './ui';
import { api } from '../services/api';
import { saveBlob } from '../services/download';

export type SemanticReviewResult = {
  version:string;run_id:string;strategy:string;evaluator_model:string;evaluator_revision:string;
  total:number;reviewed:number;correct:number;pending:number;percentage:number|null;lexical_disagreements:number;notice:string;
  cases:Array<{case_id:string;category:string;question:string;expected_answer:string;response_text:string;lexical_match:boolean;semantic_correct:boolean|null}>;
  categories:Array<{category:string;total:number;reviewed:number;correct:number;percentage:number|null}>;
};
const conditionLabel=(s:string)=>({no_memory:'No memory',full_context:'Full context',weak_first_hit:'Weak first-hit',scope_aware:'Scope-aware',strong_rule_based:'Strong rule-based',temporal_importance:'Temporal & importance',mem0_native:'Mem0 original',mem0_generic:'Mem0 + generic instruction',mem0_directed:'Mem0 + diagnosis-guided filtering'}[s]??'Saved condition');
const categoryLabel=(s:string)=>({'single-session-user':'User facts','single-session-assistant':'Assistant facts','single-session-preference':'Personal preferences','multi-session':'Across sessions','temporal-reasoning':'Time reasoning','knowledge-update':'Updated facts'}[s]??'Other questions');

export function BenchmarkSemanticReview(){
  const [source,setSource]=useState<object|object[]|null>(null),[evidence,setEvidence]=useState<object|null>(null);
  const [rows,setRows]=useState<unknown[]|null>(null),[strategy,setStrategy]=useState('');
  const [options,setOptions]=useState<Array<{label:string;value:string}>>([]),[revision,setRevision]=useState('');
  const [names,setNames]=useState({source:'No file selected',evidence:'No file selected',scores:'No file selected'});
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[report,setReport]=useState<SemanticReviewResult|null>(null);
  const active=useRef(false);
  async function load(kind:'source'|'evidence'|'scores',file:File){
    if(active.current)return;active.current=true;setBusy(true);setReport(null);setError('');
    if(kind==='source')setSource(null);if(kind==='evidence'){setEvidence(null);setOptions([]);setStrategy('');}if(kind==='scores')setRows(null);
    setNames(n=>({...n,[kind]:'No file selected'}));
    try{
      if(file.size>(kind==='evidence'?5_000_000:kind==='source'?1_000_000:2_000_000))throw new Error('This file exceeds the saved pilot size limit.');
      const text=await file.text();
      let value:unknown;
      if(kind==='scores'&&!text.trimStart().startsWith('['))value=text.split(/\r?\n/).filter(l=>l.trim()).map(l=>JSON.parse(l));
      else value=JSON.parse(text);
      if(kind==='source'){
        if(!value||typeof value!=='object')throw new Error('Choose the original benchmark JSON.');setSource(value);
      }else if(kind==='evidence'){
        if(!value||typeof value!=='object'||!('conditions' in value)||!Array.isArray(value.conditions)||!value.conditions.length||value.conditions.length>4)throw new Error('Choose a downloaded live comparison evidence file.');
        const choices=value.conditions.map((c:unknown)=>{
          if(!c||typeof c!=='object'||!('strategy' in c)||typeof c.strategy!=='string')throw new Error('The saved comparison has an invalid condition.');
          return {value:c.strategy,label:conditionLabel(c.strategy)};
        });
        if(new Set(choices.map(c=>c.value)).size!==choices.length)throw new Error('The saved comparison contains duplicate conditions.');
        setEvidence(value);setOptions(choices);setStrategy(choices[0].value);
      }else{
        if(!Array.isArray(value)||!value.length||value.length>20)throw new Error('Choose a JSON array or JSONL file with 1–20 automated evaluation rows.');setRows(value);
      }
      setNames(n=>({...n,[kind]:file.name}));
    }catch(e){setError(e instanceof SyntaxError?'Choose a valid JSON file, or one complete JSON object per line for evaluation output.':e instanceof Error?e.message:'The file could not be loaded.');}
    finally{active.current=false;setBusy(false);}
  }
  async function analyse(){
    if(active.current||!source||!evidence||!rows||!strategy||!/^[0-9a-f]{40}$/.test(revision))return;
    active.current=true;setBusy(true);setError('');setReport(null);
    try{setReport(await api.importSemanticReview({source,evidence,rows,strategy,evaluator_revision:revision}));}
    catch(e){setError(e instanceof Error?e.message:'These assessments could not be matched to the saved comparison.');}
    finally{active.current=false;setBusy(false);}
  }
  return <section aria-labelledby="semantic-review-title" className="research-workspace">
    <h3 id="semantic-review-title">Review saved benchmark assessments</h3>
    <p>Compare imported semantic assessments with the initial word matches. This checks saved files and makes no model calls.</p>
    <p><small>Use the original benchmark source, downloaded comparison evidence and the matching LongMemEval evaluator output. Imported automated labels do not establish human agreement or verify who ran the evaluator.</small></p>
    {error&&<Alert type="error" showIcon title={error}/>}
    <div className="benchmark-controls-grid">
      {(['source','evidence','scores'] as const).map(kind=><label key={kind}>{({source:'Original benchmark source',evidence:'Saved comparison evidence',scores:'Automated evaluation output'})[kind]}<UIInput aria-label={`Semantic review ${kind}`} type="file" accept={kind==='scores'?'.json,.jsonl,application/json,application/x-ndjson':'.json,application/json'} disabled={busy} onChange={e=>{const f=e.target.files?.[0];if(f)void load(kind,f);}}/><small>{names[kind]}</small></label>)}
      <label>Evaluated condition<Select aria-label="Semantic review condition" value={strategy||undefined} disabled={busy||!options.length} options={options} onChange={v=>{setStrategy(v);setReport(null);setError('');}}/></label>
      <label>Evaluator code revision<Input aria-label="Semantic review evaluator revision" placeholder="40-character upstream commit" value={revision} disabled={busy} onChange={e=>{setRevision(e.target.value.trim());setReport(null);}}/><small>Recorded as declared provenance; file origin is not independently verified.</small></label>
    </div>
    <Button aria-label="Validate & compare assessments" type="primary" disabled={busy||!source||!evidence||!rows||!strategy||!/^[0-9a-f]{40}$/.test(revision)} loading={busy} onClick={()=>void analyse()}>Validate & compare assessments</Button>
    {report&&<div className="research-report">
      <h4>Imported automated assessment summary</h4><p>{conditionLabel(report.strategy)} · Evaluator: {report.evaluator_model}</p>
      <p>{report.reviewed} of {report.total} answers reviewed · {report.correct} labelled correct · {report.pending} awaiting assessment</p>
      {report.percentage===null?<Alert type="info" title="Assessment incomplete — no overall score is shown."/>:<><p>{report.percentage}% labelled correct in this saved pilot</p><Progress percent={report.percentage} strokeColor="#087f8c"/></>}
      <p>{report.lexical_disagreements} assessments differ from the initial word matches.</p>
      <Alert type="info" showIcon title="Imported automated labels require independent review. Complete pilot coverage is not an official full-benchmark score."/>
      <Space wrap><Button onClick={()=>saveBlob(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}),'bound-semantic-assessments.json')}>Download assessment report</Button></Space>
      <Collapse items={[{key:'categories',label:'Results by question type',children:report.categories.map(c=><p key={c.category}>{categoryLabel(c.category)}: {c.correct} correct · {c.reviewed}/{c.total} reviewed · {c.percentage===null?'awaiting complete assessment':`${c.percentage}%`}</p>)},{key:'answers',label:'Inspect answers and changed assessments',children:report.cases.map((c,i)=><article key={c.case_id}><h4>Case {i+1}</h4><p>{c.question}</p><p>Reference: {c.expected_answer}</p><p>Model answer: {c.response_text}</p><p>Word match: {c.lexical_match?'yes':'no'} · Imported semantic assessment: {c.semantic_correct===null?'awaiting assessment':c.semantic_correct?'correct':'incorrect'}</p></article>)},{key:'provenance',label:'Assessment method and traceability',children:<><p>{report.notice}</p><p>Evaluator revision: {report.evaluator_revision}</p><p>Source, configuration, saved evidence and assessment fingerprints are retained in the downloaded report.</p></>}]} />
    </div>}
  </section>;
}
