import { useEffect, useState } from 'react';
import { Card, Progress, Tag } from 'antd';
type Summary={format:string;history_count:number;pairs:number;same_exact_answer_count:number;same_automatic_verdict_count:number;human_reviewed_repeat_answers:boolean;evidence_file_sha256:string};
export function Ac3StabilitySummary(){
  const [s,setSummary]=useState<Summary|null>(null);
  useEffect(()=>{fetch('/reports/ac3-stability-summary.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then((v:Summary|null)=>{
    if(v?.format==='ac3-stability-descriptive-v1' && v.history_count===10 && v.pairs===40 && v.human_reviewed_repeat_answers===false && [v.same_exact_answer_count,v.same_automatic_verdict_count].every(n=>Number.isInteger(n)&&n>=0&&n<=40) && /^[a-f0-9]{64}$/.test(v.evidence_file_sha256))setSummary(v);
  }).catch(()=>undefined);},[]);
  if(!s)return null;
  return <Card title="AC3 · Repeat stability" style={{marginTop:16}}>
    <p><Tag color="blue">10 histories · 40 paired questions</Tag><Tag>Automatic judgment</Tag></p>
    {([['Automatic verdict unchanged',s.same_automatic_verdict_count],['Answer text exactly the same',s.same_exact_answer_count]] as const).map(([label,count])=><div key={label} style={{margin:'12px 0'}}>
      <div style={{display:'flex',justifyContent:'space-between',gap:12,flexWrap:'wrap'}}><span>{label}</span><b>{count}/{s.pairs} · {(count/s.pairs*100).toFixed(1)}%</b></div>
      <Progress percent={count/s.pairs*100} showInfo={false} strokeColor="#23836f" />
    </div>)}
    <small>This is repeat consistency of automatic judgments, not accuracy or AC3 acceptance. Repeat answers have not been human reviewed; repeated questions are not independent cases.</small>
    <details><summary>Evidence</summary><p>Paired evidence SHA-256: {s.evidence_file_sha256}</p></details>
  </Card>;
}
