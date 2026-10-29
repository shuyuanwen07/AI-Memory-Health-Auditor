import { useEffect, useState } from 'react';
import { Card, Tag } from 'antd';

type Counts = { valid: number; invalid: number; unresolved: number; denominator: number };
type Summary = { format:'ac2-ai-followup-public-v1'; status:'human_confirmed_ai_followup';
  original_human_adjudicated_structural:Counts; mixed_structural:Counts;
  ai_followup_counts:{invalid:number;uncertain:number}; limitations:string[] };

function validCounts(value: Counts | undefined): value is Counts {
  return !!value && ['valid','invalid','unresolved','denominator'].every(k => Number.isInteger(value[k as keyof Counts]) && value[k as keyof Counts] >= 0)
    && value.denominator > 0 && value.valid + value.invalid + value.unresolved === value.denominator;
}

export function isAc2AiFollowupSummary(value:unknown):value is Summary {
  if (!value || typeof value !== 'object') return false;
  const x=value as Summary;
  return x.format==='ac2-ai-followup-public-v1' && x.status==='human_confirmed_ai_followup'
    && validCounts(x.original_human_adjudicated_structural) && validCounts(x.mixed_structural)
    && x.original_human_adjudicated_structural.denominator===x.mixed_structural.denominator
    && !!x.ai_followup_counts && Number.isInteger(x.ai_followup_counts.invalid)
    && Number.isInteger(x.ai_followup_counts.uncertain) && x.ai_followup_counts.invalid>=0 && x.ai_followup_counts.uncertain>=0
    && x.ai_followup_counts.invalid+x.ai_followup_counts.uncertain===x.original_human_adjudicated_structural.unresolved
    && x.mixed_structural.valid===x.original_human_adjudicated_structural.valid
    && x.mixed_structural.invalid===x.original_human_adjudicated_structural.invalid+x.ai_followup_counts.invalid
    && x.mixed_structural.unresolved===x.ai_followup_counts.uncertain
    && Array.isArray(x.limitations) && x.limitations.every(item=>typeof item==='string');
}

const rows = [{key:'valid',label:'Valid',color:'#23836f'}, {key:'invalid',label:'Invalid',color:'#c24b4b'},
  {key:'unresolved',label:'Unresolved',color:'#c08335'}] as const;

export function Ac2AiFollowupSummary() {
  const [summary,setSummary]=useState<Summary|null>(null);
  useEffect(()=>{
    let active=true;
    fetch('/reports/ac2-ai-followup-v1.json',{cache:'no-store'})
      .then(r=>r.ok?r.json():null).then(value=>{if(active&&isAc2AiFollowupSummary(value))setSummary(value);})
      .catch(()=>{if(active)setSummary(null);});
    return ()=>{active=false;};
  },[]);
  if(!summary)return null;
  const bars=[{label:'Original human-confirmed adjudication',counts:summary.original_human_adjudicated_structural},
    {label:'With human-confirmed AI follow-up',counts:summary.mixed_structural}];
  return <Card title="AC2 · Structural follow-up" style={{marginTop:16}}>
    <p><Tag color="blue">AI-assisted · human-confirmed</Tag> Original judgments retained · no target answers run</p>
    {bars.map(({label,counts})=><div key={label} style={{margin:'12px 0'}}>
      <div>{label}</div>
      <div role="img" aria-label={`${label}: ${rows.map(r=>`${r.label} ${counts[r.key]}`).join(', ')}`} style={{display:'flex',height:18,borderRadius:9,overflow:'hidden',background:'#eee'}}>
        {rows.filter(r=>counts[r.key]>0).map(r=><span key={r.key} style={{width:`${counts[r.key]/counts.denominator*100}%`,background:r.color}} />)}
      </div>
      <div style={{display:'flex',flexWrap:'wrap',gap:'4px 16px',marginTop:5}}>{rows.map(r=><span key={r.key}><span aria-hidden="true" style={{color:r.color}}>●</span> {r.label}: {counts[r.key]}</span>)}</div>
    </div>)}
    <small>The user reports two people separately reviewed the same AI follow-up; this is not independently blinded first-pass labelling. Unresolved items remain open. The isolated retrieval reconstruction is not the original AC2 run.</small>
  </Card>;
}
