import { useEffect, useState } from 'react';
import { Card } from 'antd';
import { api } from '../services/api';
import type { RetrievalImprovementBasis, RetrievalImprovementSummary } from '../services/api';

const basisLabels:Record<RetrievalImprovementBasis,string>={
  single_human_reference:'Single human reference',
  independent_human_consensus:'Independent human consensus',
  mixed_human_review:'Mixed human review basis',
  pending:'Awaiting human review',
};

type Arm = RetrievalImprovementSummary['methods'][number]['before'];
function ArmResult({name,arm}:{name:string;arm:Arm}) {
  const measured=arm.review_basis!=='pending' && arm.decided>0;
  const percentage=measured ? 100*arm.passed/arm.decided : null;
  return <div className="retrieval-arm">
    <span>{name}</span>
    <div className="compact-track" aria-hidden="true"><i style={{width:`${percentage??0}%`}}/></div>
    <b>{measured ? `${arm.passed}/${arm.decided} · ${percentage!.toFixed(1)}%` : 'Awaiting review'}</b>
    <small>{basisLabels[arm.review_basis]}</small>
  </div>;
}

export function RetrievalImprovement({data}:{data:RetrievalImprovementSummary|null}) {
  if(!data) return null;
  return <Card title="Retrieval · Before and after" className="compact-retrieval">
    <p className="compact-note">{data.scenarios_completed}/{data.scenarios_planned} scenarios complete · {data.planned_pairs} planned question pairs</p>
    {data.methods.map(method=><div className="retrieval-method" key={method.mode}>
      <h3>{method.label}</h3>
      <ArmResult name="Before" arm={method.before}/>
      <ArmResult name="After" arm={method.after}/>
      <small>{method.matched} matched question pairs · {method.unresolved} unresolved{method.improved!==null && method.regressed!==null ? ` · ${method.improved} improved · ${method.regressed} worsened` : ' · Pair outcomes awaiting review'}</small>
    </div>)}
    <p className="compact-note">{data.notice}</p>
  </Card>;
}

export function useRetrievalImprovement() {
  const [data,setData]=useState<RetrievalImprovementSummary|null>(null);
  const [error,setError]=useState(false);
  const [revision,setRevision]=useState(0);
  useEffect(()=>{
    const refresh=()=>{if(document.visibilityState==='visible')setRevision(n=>n+1);};
    window.addEventListener('focus',refresh);document.addEventListener('visibilitychange',refresh);
    const timer=window.setInterval(refresh,30000);
    return ()=>{window.removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',refresh);window.clearInterval(timer);};
  },[]);
  useEffect(()=>{let active=true;api.retrievalImprovementLatest().then(value=>{if(active){setData(value);setError(false);}}).catch(()=>{if(active){setData(null);setError(true);}});return()=>{active=false;};},[revision]);
  return {data,error,refresh:()=>setRevision(n=>n+1)};
}
