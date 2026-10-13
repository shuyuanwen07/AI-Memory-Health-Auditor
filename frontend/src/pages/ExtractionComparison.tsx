import {useEffect,useId,useRef,useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {Select,Tag} from 'antd';
import {api} from '../services/api';
import {friendlyText,modelDisplayName,relationshipEvidenceLabel} from '../services/display';
import {comparisonColours} from '../services/chartColours';
import {ModelPicker} from '../components/ModelPicker';
import {CurrentModelPreset} from '../components/CurrentModelPreset';
import {OperationChart} from '../components/AssessorOperationCharts';
import {UIAlert,UIButton,UIPanel,UISummary} from '../components/ui';
import type {AuditRun,ExtractionComparison} from '../types/domain';

type Entry=ExtractionComparison['entries'][number];
const name=(entry:Entry)=>entry.selection.provider==='rule_based'?'Rules':modelDisplayName(entry.selection.model??'Selected model');
const sourceName=(run:AuditRun)=>`${run.reproducibility?.target_memory_profile?.label??modelDisplayName(run.model)} · ${new Date(run.created_at).toLocaleString()}`;

function CoverageChart({entries}:{entries:Entry[]}){
  const id=useId(),description=useId();const width=Math.max(520,entries.length*110+260);
  const metrics=[['Facts','fact_coverage_percent'],['Relationships','relationship_coverage_percent']] as const;
  return <section><h2>Exact reference matches</h2><div className="reliability-legend">{entries.map((entry,index)=><span key={index}><i style={{background:comparisonColours[index%comparisonColours.length]}}/>{name(entry)}</span>)}</div>
    <div role="region" aria-label="Scrollable extraction comparison" tabIndex={0} style={{overflowX:'auto'}}>
      <svg viewBox={`0 0 ${width} 290`} style={{width:'100%',minWidth:width}} role="img" aria-labelledby={id} aria-describedby={description}>
        <title id={id}>Exact fact and relationship coverage by extractor</title><desc id={description}>{metrics.map(([label,key])=>`${label}: ${entries.map(entry=>`${name(entry)} ${entry.checks?.[key]==null?(entry.checks?'No reference links':'Not extracted'):`${entry.checks[key]}%`}`).join(', ')}`).join('; ')}</desc>
        {[0,50,100].map(percent=><g key={percent}><line x1={45} x2={width-10} y1={220-percent*1.6} y2={220-percent*1.6} stroke="#dbe4ea"/><text x={37} y={224-percent*1.6} textAnchor="end" fontSize={12}>{percent}%</text></g>)}
        {metrics.map(([label,key],group)=>{const span=(width-60)/2;const center=45+span*(group+.5);const step=Math.min(55,span/(entries.length+1));return <g key={key}>
          <text x={center} y={261} textAnchor="middle" fontSize={13}>{label}</text>
          {entries.map((entry,index)=>{const value=entry.checks?.[key]??null;const x=center+(index-(entries.length-1)/2)*step;return <g key={index}><title>{name(entry)} · {label}: {value==null?'Not measured':`${value}%`}</title>
            {value==null?<text x={x} y={205} textAnchor="middle" fontSize={10} transform={`rotate(-35 ${x} 205)`}>{entry.checks?'No links':'Not extracted'}</text>:<>
              {value>0?<rect x={x-14} y={220-value*1.6} width={28} height={value*1.6} fill={comparisonColours[index%comparisonColours.length]}/>:<circle cx={x} cy={220} r={3} fill={comparisonColours[index%comparisonColours.length]}/>}
              <text x={x} y={210-value*1.6} textAnchor="middle" fontSize={11}>{Number(value.toFixed(1))}%</text></>}
          </g>;})}</g>;})}
      </svg>
    </div><small>Scroll horizontally on smaller screens. Exact text matches are not semantic accuracy; valid paraphrases may not match.</small>
  </section>;
}

export function ExtractionComparisonPage(){
  const [params,setParams]=useSearchParams();const id=params.get('comparison')??'';
  const [sources,setSources]=useState<AuditRun[]>([]),[saved,setSaved]=useState<ExtractionComparison[]>([]);
  const [source,setSource]=useState(''),[models,setModels]=useState('');
  const [plan,setPlan]=useState<ExtractionComparison|null>(null),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[step,setStep]=useState('');
  const epoch=useRef(0),running=useRef(false),requestKey=useRef<string|null>(null);
  useEffect(()=>{const version=++epoch.current;running.current=false;setBusy(false);setLoading(true);setPlan(null);setError('');setStep('');
    const task=id?api.extractionComparison(id).then(value=>{if(epoch.current===version)setPlan(value);}):Promise.all([api.audits(),api.extractionComparisons()]).then(([audits,plans])=>{if(epoch.current===version){setSources(audits.filter(run=>run.status==='COMPLETED'));setSaved(plans);}});
    task.catch(cause=>{if(epoch.current===version)setError(cause instanceof Error?cause.message:'Saved progress could not load.');}).finally(()=>{if(epoch.current===version)setLoading(false);});
    return()=>{epoch.current++;};
  },[id]);
  const selected=[...new Set(models.split('\n').map(value=>value.trim()).filter(Boolean))];
  const save=async()=>{if(running.current)return;const version=epoch.current;running.current=true;setBusy(true);setError('');
    try{requestKey.current??=crypto.randomUUID();const next=await api.createExtractionComparison({creation_request_key:requestKey.current,source_run_id:source,
      extractors:[{provider:'rule_based'},...selected.map(model=>({provider:'openrouter' as const,model}))]});
      if(epoch.current===version){setPlan(next);setParams({comparison:next.comparison_id});}
    }catch(cause){if(epoch.current===version)setError(cause instanceof Error?cause.message:'The comparison could not be saved.');}
    finally{if(epoch.current===version){running.current=false;setBusy(false);}}
  };
  const extract=async()=>{if(!plan||running.current)return;const version=epoch.current;running.current=true;setBusy(true);setError('');let current=plan;
    const problems:string[]=[];
    try{current=await api.extractionComparison(plan.comparison_id);if(epoch.current!==version)return;setPlan(current);
      if(!current.inputs_match||!current.runtime_matches)throw new Error('Saved inputs or software changed. Start a new comparison.');
      for(let index=0;index<current.entries.length;index++){
        if(epoch.current!==version)return;const entry=current.entries[index];if(entry.status==='completed')continue;setStep(`Extracting memories · ${name(entry)}`);
        try{await api.extractComparisonEntry(current.comparison_id,index);}catch(cause){problems.push(`${name(entry)}: ${cause instanceof Error?cause.message:'Extraction failed.'}`);}
        if(epoch.current!==version)return;current=await api.extractionComparison(current.comparison_id);if(epoch.current!==version)return;setPlan(current);
        if(!current.inputs_match||!current.runtime_matches)break;
      }
      if(epoch.current===version&&problems.length)setError(problems.join(' '));
    }catch(cause){if(epoch.current===version)setError(cause instanceof Error?cause.message:'Extraction could not finish. Saved progress is retained.');}
    finally{if(epoch.current===version){running.current=false;setBusy(false);setStep('');}}
  };
  const rows=plan?.entries.map((entry,index)=>({entry,name:name(entry),colour:comparisonColours[index%comparisonColours.length]}))??[];
  return <section className="page"><h1>Compare memory extractors</h1><p>Same conversation · Frozen reference memories · Separate model outputs</p>
    {loading&&<p role="status">Loading saved progress…</p>}{error&&<UIAlert role="alert">{friendlyText(error)}</UIAlert>}{step&&<p role="status">{step}</p>}
    {!id&&!loading&&<><label>Reference audit<Select aria-label="Reference audit" style={{width:'100%'}} showSearch optionFilterProp="label" value={source||undefined}
      placeholder="Choose a completed audit" disabled={busy} onChange={value=>{setSource(value);requestKey.current=null;}} options={sources.map(run=>({value:run.run_id,label:sourceName(run)}))}/></label>
      <ModelPicker label="OpenRouter memory extractors" provider="openrouter" value={models} multiple disabled={busy} onChange={value=>{setModels(value);requestKey.current=null;}}/>
      <CurrentModelPreset disabled={busy} onSelect={value=>{setModels(value);requestKey.current=null;}}/>
      <p>Choose up to four fixed-version models. Rules are included. Saving is free of model calls; extraction may incur charges.</p>
      <UIButton disabled={busy||!source||selected.length<1||selected.length>4} onClick={()=>void save()}>Save extraction comparison</UIButton>
      {saved.length>0&&<UIPanel><UISummary>Saved extraction comparisons</UISummary>{saved.map(item=><p key={item.comparison_id}><a href={`/extraction-models?comparison=${item.comparison_id}`}>{new Date(item.created_at).toLocaleString()} · {item.entries.map(name).join(' · ')}</a></p>)}</UIPanel>}
    </>}
    {plan&&<><p>{sourceName(plan.source)} · {plan.entries.filter(entry=>entry.status==='completed').length} of {plan.entries.length} outputs saved</p>
      {!plan.inputs_match&&<UIAlert role="status">Reference inputs cannot be verified. Original outputs and reference snapshot remain available; start a new comparison.</UIAlert>}
      {plan.inputs_match&&!plan.runtime_matches&&<UIAlert role="status">The software changed. Saved results are read-only; start a new comparison to continue.</UIAlert>}
      {plan.inputs_match&&<><CoverageChart entries={plan.entries}/><h2>Recorded extraction time & cost</h2><div className="visual-grid">
        <OperationChart title="Recorded extraction time" unit="s" subject="extractor" rows={rows.map(row=>({name:row.name,colour:row.colour,value:row.entry.usage.observed_elapsed_ms==null?null:row.entry.usage.observed_elapsed_ms/1000,
          coverage:`${row.entry.usage.timed_invocations}/${row.entry.usage.recorded_invocations} timed${row.entry.usage.failed_http_attempts?` · ${row.entry.usage.failed_http_attempts} failed`:''}`}))}/>
        <OperationChart title="Reported extraction credits" unit="credits" subject="extractor" rows={rows.map(row=>({name:row.name,colour:row.colour,value:row.entry.usage.observed_cost_credits,
          coverage:`${row.entry.usage.cost_reported_invocations}/${row.entry.usage.recorded_invocations} reported${row.entry.usage.complete_cost_coverage?'':' · partial'}`}))}/>
      </div><p>Recorded extraction calls only. Failed and retried calls stay in the record; missing usage remains unknown. Reported credits are not a full invoice.</p></>}
      <UIButton disabled={busy||!plan.inputs_match||!plan.runtime_matches||plan.entries.every(entry=>entry.status==='completed')} onClick={()=>void extract()}>{busy?'Extracting…':'Continue unfinished extractions'}</UIButton>
      <UIPanel><UISummary>Frozen reference memories · {plan.reference_memories.length}</UISummary>{plan.reference_memories.map((memory,index)=><p key={index}><b>Reference {index+1}</b> · {memory.canonical_value}</p>)}</UIPanel>
      {plan.entries.map((entry,index)=><UIPanel key={index}><UISummary>{name(entry)} · {entry.status==='completed'?'Output saved':entry.status==='failed'?'Needs attention':entry.status==='started'?'Unfinished operation':'Not extracted'}</UISummary>
        <Tag>{entry.operations.length} recorded operations</Tag><p>{entry.usage.request_attempts==null?'Call counts not recorded':`${entry.usage.request_attempts} call attempts · ${entry.usage.failed_http_attempts??0} failed`} · {entry.usage.observed_total_tokens==null?'Tokens not recorded':`${entry.usage.observed_total_tokens} reported tokens`}</p>
        {entry.candidates===null?<p>No candidate output saved.</p>:entry.candidates.length===0?<p>The extractor returned no memories.</p>:entry.candidates.map((memory,position)=><div key={position}><h3>Memory {position+1}</h3><p>{memory.canonical_value}</p><small>{memory.source_message_ids.length} source messages linked</small>
          {memory.relationships.map((relation,number)=><p key={number}>{relationshipEvidenceLabel(relation.type)} · Memory {entry.candidates!.findIndex(candidate=>candidate.memory_id===relation.target_memory_id)+1}</p>)}</div>)}
      </UIPanel>)}
      <a href="/extraction-models">Start another extraction comparison</a>
    </>}
  </section>;
}
