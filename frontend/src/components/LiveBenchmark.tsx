import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Collapse, Input, Progress, Select, Space } from 'antd';
import { UIInput } from './ui';
import { api } from '../services/api';
import { saveBlob } from '../services/download';

type LiveCase = {intervention?:{name?:string;policy_version?:string;removed_memory_ids?:string[]};memory_preparation?:{system?:string;sdk_version?:string;latency_ms?:number;source_attribution?:string;native_llm_calls?:number|null;embedding_calls?:number|string|null;preparation_charged_here?:boolean};case_id:string;question:string;expected_answer:string;response_text:string;lexical_match:boolean;token_f1:number;message_count:number;assistant_message_count:number;memory_evidence?:Array<{canonical_value:string;retrieved:boolean;supplied:boolean;lifecycle_state:string}>;stored_memory_count:number;retained_memory_count:number;retrieved_memory_ids:string[];supplied_memory_ids:string[];execution_metadata:{request_attempts:number;latency_ms:number|null;memory_input?:{record_count:number;context_sha256:string;instruction_sha256:string;prompt_sha256:string}|null}};
export type LiveBenchmarkResult={run_id:string;provider:string;model:string;temperature:number;runner_version:string;adapter_version:string;source_fingerprint_sha256:string;configuration_fingerprint_sha256:string;seed_control:string;target_memory_capacity:number;notice:string;conditions:Array<{strategy:string;cases:LiveCase[];lexical_matches:number;total:number;percentage:number}>};
const strategyOptions=[{value:'no_memory',label:'No memory'},{value:'full_context',label:'Full context'},{value:'weak_first_hit',label:'Weak first-hit'},{value:'scope_aware',label:'Scope-aware'},{value:'strong_rule_based',label:'Strong rule-based'},{value:'temporal_importance',label:'Temporal & importance'}];
const measured=(value:unknown):value is number=>typeof value==='number'&&Number.isInteger(value)&&value>=0;
function preparationSummary(result:LiveBenchmarkResult){
  const items=result.conditions.flatMap(c=>c.cases.filter(x=>x.memory_preparation?.system==='mem0_oss'&&(x.memory_preparation.preparation_charged_here===true||(x.memory_preparation.preparation_charged_here===undefined&&c.strategy==='mem0_native'))));
  if(!items.length)return null;
  const known=items.filter(x=>measured(x.memory_preparation?.native_llm_calls)&&measured(x.memory_preparation?.embedding_calls));
  const modelCalls=items.filter(x=>measured(x.memory_preparation?.native_llm_calls)).reduce((n,x)=>n+Number(x.memory_preparation?.native_llm_calls),0);
  const embeddingCalls=items.filter(x=>measured(x.memory_preparation?.embedding_calls)).reduce((n,x)=>n+Number(x.memory_preparation?.embedding_calls),0);
  return <p>Memory preparation: {modelCalls} recorded model calls · {embeddingCalls} recorded embedding calls · {items.length-known.length} preparations not measured. Shared preparation is counted once.</p>;
}
const label=(value:string)=>({mem0_native:'Mem0 original',mem0_generic:'Mem0 + generic instruction',mem0_directed:'Mem0 + diagnosis-guided filtering'}[value]??strategyOptions.find(o=>o.value===value)?.label??value);

export function LiveBenchmark(){
  const [payload,setPayload]=useState<object|object[]|null>(null),[filename,setFilename]=useState('No file selected');
  const [preview,setPreview]=useState<Array<{question:string;expected_answer:string;messages?:unknown[]}>|null>(null);
  const [provider,setProvider]=useState('ollama'),[model,setModel]=useState('qwen3:1.7b');
  const [strategies,setStrategies]=useState(['weak_first_hit','scope_aware']);
  const [includeMem0,setIncludeMem0]=useState(false);
  const [nativeRepair,setNativeRepair]=useState(false);
  const [authorised,setAuthorised]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [result,setResult]=useState<LiveBenchmarkResult|null>(null);const active=useRef(false);const controller=useRef<AbortController|null>(null);
  useEffect(()=>()=>controller.current?.abort(),[]);
  async function load(file:File){
    if(active.current)return;active.current=true;setBusy(true);setPayload(null);setPreview(null);setResult(null);setAuthorised(false);setError('');
    try{if(file.size>1_000_000)throw new Error('Choose a benchmark subset smaller than 1 MB.');
      const value=JSON.parse(await file.text());if(!value||typeof value!=='object')throw new Error('Choose a JSON object or array of cases.');
      const validated=await api.validateLongMemEval(value);if(validated.cases.length>8)throw new Error('Choose at most 8 cases for this live pilot. No cases are silently omitted.');
      setPayload(value);setFilename(file.name);setPreview(validated.cases);}
    catch(e){setError(e instanceof Error?e.message:'The benchmark could not be loaded.');}
    finally{active.current=false;setBusy(false);}
  }
  async function run(){if(active.current||!payload||!authorised||!strategies.length||!model.trim())return;
    active.current=true;setBusy(true);setError('');setResult(null);const pending=new AbortController();controller.current=pending;
    try{const value=await api.runLiveBenchmark({payload,source_authorised:true,source_label:filename,provider,model:model.trim(),strategies,include_mem0:includeMem0,native_repair_comparison:nativeRepair,max_cases:8,temperature:0,random_seed:42},pending.signal);if(!pending.signal.aborted)setResult(value);}
    catch(e){if(!pending.signal.aborted)setError(e instanceof Error?e.message:'The real-model comparison could not finish.');}
    finally{if(controller.current===pending){if(!pending.signal.aborted){active.current=false;setBusy(false);}controller.current=null;}}
  }
  return <section className="research-workspace" aria-labelledby="live-benchmark-title">
    <h3 id="live-benchmark-title">Real-model benchmark comparison</h3>
    <p>Test the same imported LongMemEval questions with one model and several memory strategies. This calls the real model; the rule baseline below is a separate simulation.</p>
    <p><small>Up to 8 cases and 4 strategies per pilot. The ordinary memory writer extracts user facts; assistant-only evidence may be omitted. Scores below are lexical proxies; use the upstream evaluator and independent review for research conclusions.</small></p>
    {error&&<Alert type="error" showIcon title={error}/>}
    <div className="benchmark-controls-grid">
      <label>Live benchmark JSON<UIInput aria-label="Live benchmark JSON" type="file" accept=".json,application/json" disabled={busy} onChange={e=>{const f=e.target.files?.[0];if(f)void load(f);}}/><small>{filename}</small></label>
      <label>Model provider<Select aria-label="Live benchmark provider" value={provider} disabled={busy} options={[{value:'ollama',label:'Local Qwen (Ollama)'},{value:'openrouter',label:'OpenRouter'}]} onChange={v=>{setIncludeMem0(false);setNativeRepair(false);setProvider(v);setModel(v==='ollama'?'qwen3:1.7b':'');setResult(null);}}/></label>
      <label>Deployed model<Input aria-label="Live benchmark model" value={model} disabled={busy} onChange={e=>{setModel(e.target.value);if(e.target.value!=='qwen3:1.7b'){setIncludeMem0(false);setNativeRepair(false);}setResult(null);}}/></label>
      <label>Memory strategies<Select aria-label="Live benchmark strategies" mode="multiple" maxCount={nativeRepair?1:includeMem0?3:4} value={strategies} disabled={busy} options={strategyOptions} onChange={v=>{setStrategies(v);setResult(null);}}/></label>
    </div>
    <Checkbox aria-label="Include native Mem0 comparison" checked={includeMem0} disabled={busy||provider!=='ollama'||model.trim()!=='qwen3:1.7b'||strategies.length>3} onChange={e=>{setIncludeMem0(e.target.checked);if(!e.target.checked)setNativeRepair(false);setResult(null);}}>Compare with native Mem0 using the same Qwen answer settings</Checkbox>
    {includeMem0&&<Checkbox aria-label="Compare native generic and directed repairs" checked={nativeRepair} disabled={busy||strategies.length>1} onChange={e=>{setNativeRepair(e.target.checked);setResult(null);}}>Compare original, generic instruction and diagnosis-guided filtering (choose one controlled reference)</Checkbox>}
    {nativeRepair&&<p>Three native conditions share one extraction and retrieval snapshot. Only the declared instruction or supplied records change. No model training. Preferences and missing-task cases are retained as checks against regressions.</p>}
    {includeMem0&&<Alert type="info" title="Local Mem0 service required. It adds native fact extraction and embedding work; these costs are separate from answer calls. Source timestamps and per-fact attribution are unavailable in this OSS pilot."/>}
    {preview&&<Collapse items={[{key:'questions',label:`Review ${preview.length} imported questions and reference answers`,children:preview.map((c,i)=><article key={i}><h4>Case {i+1}</h4><p>{c.question}</p><p>Reference: {c.expected_answer}</p><small>{c.messages?.length ?? 0} history messages</small></article>)}]}/>}
    <Checkbox aria-label="Live benchmark source authorisation" checked={authorised} disabled={busy} onChange={e=>setAuthorised(e.target.checked)}>I may process this source with the selected provider and have reviewed the imported questions.</Checkbox>
    <p>{preview?`${preview.length*(strategies.length+(includeMem0?(nativeRepair?3:1):0))} model answers requested; provider retries may add calls.`:'Select a permitted benchmark subset to preview the questions.'}</p>
    <Button aria-label="Run Real-Model Comparison" type="primary" disabled={busy||!payload||!authorised||!strategies.length||!model.trim()} loading={busy} onClick={()=>void run()}>{busy?'Working…':'Run Real-Model Comparison'}</Button>
    {busy&&controller.current&&<Button onClick={()=>{controller.current?.abort();setError('Comparison cancelled. The in-flight model call may finish, but the server will stop before the next case.');setBusy(false);active.current=false;}}>Cancel comparison</Button>}
    {busy&&<p role="status">Results are temporary; download them before leaving.</p>}
    {result&&<div role="status" className="research-report"><h3>Real-model comparison completed</h3><p>Model: {result.model} · Same imported questions in every condition</p>
      <div role="img" aria-label="Lexical reference match rates by memory strategy">{result.conditions.map((c,i)=><article key={c.strategy}><b>{label(c.strategy)} · {c.lexical_matches}/{c.total} lexical matches</b><Progress percent={c.percentage} format={percent=>`${percent}%`} strokeColor={i%2?'#087f8c':'#64748b'}/></article>)}</div>
      <p>{result.conditions.reduce((n,c)=>n+c.total,0)} completed answers · {result.conditions.reduce((n,c)=>n+c.cases.reduce((sum,x)=>sum+x.execution_metadata.request_attempts,0),0)} answer model requests</p>
      {preparationSummary(result)}
      <Alert type="info" showIcon title="Word matches are an initial check. Review the answers and explanations before drawing a research conclusion."/>
      <Space wrap><Button onClick={()=>saveBlob(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}),'live-benchmark-evidence.json')}>Download Evidence</Button>{result.conditions.map(c=><Button key={c.strategy} onClick={()=>saveBlob(new Blob([c.cases.map(x=>JSON.stringify({question_id:x.case_id,hypothesis:x.response_text})).join('\n')+'\n'],{type:'application/x-ndjson'}),`${c.strategy}-hypotheses.jsonl`)}>Export {label(c.strategy)} hypotheses</Button>)}</Space>
      <Collapse items={[{key:'method',label:'How this comparison is measured',children:<><p>Each question uses a separate memory store. The model sees the selected memories and the question; reference answers remain with the evaluator. The same model and base answer settings are used for every strategy. Native repair conditions share preparation; generic adds a careful-answer instruction, while diagnosis-guided filtering changes only separable task facts supplied to the reader.</p><p>Native memory preparation counts observed SDK model and embedding attempts for completed operations. Setup, lower-level network retries, aborted preparation, hardware and monetary costs are not measured. Historical missing counts remain unknown.</p><p>The result measures word matches, rather than whether an explanation is fully correct. These are not official benchmark scores. The ordinary writer extracts user facts, so assistant-only evidence may not be retained.</p></>}]}/>
      <Collapse items={result.conditions.map(c=>({key:c.strategy,label:`Inspect ${label(c.strategy)} answers and supply evidence`,children:c.cases.map((x,i)=><article key={x.case_id}><h4>Case {i+1}</h4><p>{x.question}</p><p>Reference: {x.expected_answer}</p><p>Model answer: {x.response_text}</p><p>{x.lexical_match?'Lexical match':'No lexical match'} · {x.retrieved_memory_ids.length} retrieved · {x.supplied_memory_ids.length} supplied · {x.retained_memory_count}/{x.stored_memory_count} records retained</p>{x.memory_evidence?.map((m,j)=><p key={j}>Memory {j+1}: {m.canonical_value} · {m.supplied?'Supplied to model':m.retrieved?'Retrieved, not supplied':'Not retrieved'}</p>)}{x.memory_preparation?.system==='mem0_oss'&&<p>Mem0 OSS {x.memory_preparation.sdk_version} · memory preparation {Math.round(x.memory_preparation.latency_ms??0)} ms · {measured(x.memory_preparation.native_llm_calls)&&measured(x.memory_preparation.embedding_calls)?`${x.memory_preparation.native_llm_calls} model calls · ${x.memory_preparation.embedding_calls} embedding calls`:'preparation calls not measured'} · {x.memory_preparation.preparation_charged_here===false?'shared preparation already counted':'preparation counted here'} · original-message attribution unavailable</p>}{x.intervention?.name&&<p>Intervention: {x.intervention.name} · {x.intervention.removed_memory_ids?.length??0} retrieved records withheld by the frozen rule</p>}<p>{x.execution_metadata.request_attempts} provider attempts · {x.message_count} history messages · {x.assistant_message_count} assistant messages in source</p></article>)}))}/>
    </div>}
  </section>;
}
