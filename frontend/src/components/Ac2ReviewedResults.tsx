import { useEffect, useState } from 'react';
import { Card, Tag } from 'antd';
type Row={valid:number;invalid:number;unresolved:number;denominator:number};
type Summary={format:string;results:{grounded:Row;structurally_executable:Row};source_sha256:string};
export function Ac2ReviewedResults(){
  const [s,setSummary]=useState<Summary|null>(null);
  useEffect(()=>{fetch('/reports/ac2-reviewed-aggregate-v1.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then((v:Summary|null)=>{
    if(v?.format==='ac2-reviewed-aggregate-v1' && [v.results?.grounded,v.results?.structurally_executable].every(x=>x && x.denominator===120 && [x.valid,x.invalid,x.unresolved].every(n=>Number.isInteger(n)&&n>=0) && x.valid+x.invalid+x.unresolved===120))setSummary(v);
  }).catch(()=>undefined);},[]);
  if(!s)return null;
  return <Card title="AC2 · Human review of generated questions" style={{marginTop:16}}>
    <p><Tag color="blue">120 questions</Tag><Tag>AI-assisted review</Tag></p>
    {([['grounded','Source grounding'],['structurally_executable','Structural executability']] as const).map(([key,label])=>{const x=s.results[key];return <div key={key} style={{margin:'16px 0'}}>
      <div>{label}</div>
      <div role="img" aria-label={`${label}: ${x.valid} valid, ${x.invalid} invalid, ${x.unresolved} unresolved`} style={{display:'flex',height:20,overflow:'hidden',borderRadius:10,margin:'8px 0'}}>
        <span style={{width:`${x.valid/120*100}%`,background:'#23836f'}}/><span style={{width:`${x.invalid/120*100}%`,background:'#ca6060'}}/><span style={{width:`${x.unresolved/120*100}%`,background:'#d6a441'}}/>
      </div>
      <small>Valid {x.valid} · Invalid {x.invalid} · Unresolved {x.unresolved}</small>
    </div>;})}
    <small>Unresolved includes uncertainty and reviewer disagreement; it is neither a pass nor a fail. These are question reviews, separate from automatic gate checks and target-answer accuracy. Two independent human reviewers were reported by the user; identity and independence are not independently authenticated.</small>
    <details><summary>Evidence</summary><p>Reviewed summary SHA-256: {s.source_sha256}</p></details>
  </Card>;
}
