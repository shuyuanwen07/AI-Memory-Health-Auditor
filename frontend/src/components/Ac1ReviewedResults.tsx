import { useEffect, useState } from 'react';
import { Card, Progress, Tag } from 'antd';
import { Ac1FullnessResults } from './Ac1FullnessResults';

type Ratio = { numerator: number; denominator: number; value: number };
type Measures = { supported_candidate_precision_decided: Ratio; reference_fact_id_matched_coverage: Ratio; relationship_precision_decided: Ratio; reference_relationship_coverage_conservative: Ratio };
type Summary = {format:string; primary_histories:number; partial_histories:number; primary:Measures; sensitivity:Measures; source_sha256:string};
const rows = [
  ['supported_candidate_precision_decided', 'Source-supported candidates'],
  ['reference_fact_id_matched_coverage', 'Reference fact IDs with a match'],
  ['relationship_precision_decided', 'Supported extracted relationships'],
  ['reference_relationship_coverage_conservative', 'Reference relationships with a match'],
] as const;

export function Ac1ReviewedResults() {
  const [s,setSummary]=useState<Summary | null>(null);
  useEffect(()=>{fetch('/reports/ac1-reviewed-aggregate-v2.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then((v:Summary|null)=>{
    if(v?.format==='ac1-reviewed-aggregate-v2' && v.primary_histories===29 && v.partial_histories===1 && rows.every(([k])=>[v.primary?.[k],v.sensitivity?.[k]].every(x=>x && x.denominator>0 && x.numerator>=0 && x.numerator<=x.denominator && Math.abs(x.value-x.numerator/x.denominator)<1e-9)))setSummary(v);
  }).catch(()=>undefined);},[]);
  if(!s)return null;
  return <Card title="AC1 · Reviewed extraction results" style={{marginTop:16}}>
    <p><Tag color="blue">29 complete histories</Tag><Tag>1 partial · sensitivity analysis</Tag></p>
    {rows.map(([key,label])=>{const x=s.primary[key], y=s.sensitivity[key]; return <div key={key} style={{margin:'12px 0'}}>
      <div style={{display:'flex',justifyContent:'space-between',gap:12,flexWrap:'wrap'}}><span>{label}</span><b>{x.numerator}/{x.denominator} · {(x.value*100).toFixed(1)}%</b></div>
      <Progress percent={x.value*100} showInfo={false} strokeColor="#23836f" />
      <small>Including observed partial output: {y.numerator}/{y.denominator}</small>
    </div>;})}
    <small>Reference facts are not exhaustive; a fact ID can match only part of the fact, so its match rate is not strict recall. Relationship matches can also involve partial endpoints. Missing output in H04 is unknown, not a confirmed omission. User reports two independent human reviews with AI assistance; identities and independence are not independently authenticated.</small>
    <Ac1FullnessResults />
    <details><summary>Evidence</summary><p>Reviewed summary SHA-256: {s.source_sha256}. Earlier retrospective review is separate.</p></details>
  </Card>;
}
