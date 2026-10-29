import { useCallback, useEffect, useState } from 'react';
import { Button, Card, Progress, Tag } from 'antd';
import { api } from '../services/api';
import { AC3_PRIMARY_STUDY_SHA, isReviewedAc3Primary } from './Ac3HeldoutResults';

type Study = { expected: number; settled: number; dispatched: number; unknown: number; not_dispatched: number; scope_observed: boolean };
type Snapshot = { format: 'ac3-ledger-progress-v1'; observed_at_utc: string; primary: Study; repeat: Study;
  frozen_sha256: { primary: string; repeat: string }; interpretation: string };
type ReviewProgress = {format:'ac3-review-progress-v1'; questions:number; reviewer_declarations_complete:number; run_sha256:string};
const PRIMARY=AC3_PRIMARY_STUDY_SHA;
const REPEAT='d5f88c4d118ffd0ffb941d564cf1c33cce82dd10ee78f8aaa33f91e508df2246';

function isSnapshot(value: unknown): value is Snapshot {
  if (!value || typeof value !== 'object') return false;
  const s=value as Snapshot;
  if (s.format !== 'ac3-ledger-progress-v1' || typeof s.observed_at_utc !== 'string' || typeof s.interpretation !== 'string'
    || s.frozen_sha256?.primary !== PRIMARY || s.frozen_sha256?.repeat !== REPEAT) return false;
  return ([['primary',120],['repeat',40]] as const).every(([name,total])=>{
    const x=s[name];
    return !!x && x.expected===total && typeof x.scope_observed==='boolean'
      && [x.settled,x.dispatched,x.unknown,x.not_dispatched].every(n=>Number.isInteger(n) && n>=0)
      && x.settled+x.dispatched+x.unknown+x.not_dispatched===total;
  });
}

export function Ac3LedgerProgress() {
  const [snapshot,setSnapshot]=useState<Snapshot | null>(null), [refreshing,setRefreshing]=useState(false);
  const [review,setReview]=useState<ReviewProgress|null>(null);
  const [reviewedResult,setReviewedResult]=useState(false);
  const refresh=useCallback(()=>{
    setRefreshing(true);
    fetch('/reports/ac3-ledger-progress-v1.json',{cache:'no-store'})
      .then(r=>r.ok?r.json():null).then(value=>{if(isSnapshot(value))setSnapshot(value);})
      .catch(()=>undefined).finally(()=>setRefreshing(false));
    fetch('/reports/ac3-review-progress-v1.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then((v:ReviewProgress|null)=>{
      if(v?.format==='ac3-review-progress-v1' && v.questions===120 && Number.isInteger(v.reviewer_declarations_complete) && v.reviewer_declarations_complete>=0 && v.reviewer_declarations_complete<=2 && /^[a-f0-9]{64}$/.test(v.run_sha256))setReview(v);
    }).catch(()=>undefined);
    api.ac3StudySummaries().then(value=>{
      setReviewedResult(value.studies.some(item=>isReviewedAc3Primary(item,PRIMARY)));
    }).catch(()=>undefined);
  },[]);
  useEffect(()=>{refresh();},[refresh]);
  if(!snapshot)return null;
  return <Card title="AC3 · Collection progress" style={{marginTop:16}} extra={<Button loading={refreshing} onClick={refresh}>Refresh</Button>}>
    <p><Tag>Count-only snapshot</Tag></p>
    {([['primary','Main experiment'],['repeat','Stability repeat']] as const).map(([key,label])=>{
      const v=snapshot[key], awaiting=v.dispatched+v.unknown;
      return <div key={key} style={{margin:'12px 0'}}>
        <div style={{display:'flex',justifyContent:'space-between',gap:12,flexWrap:'wrap'}}><span>{label}</span><b>{v.settled}/{v.expected} requests settled</b></div>
        <Progress percent={v.settled/v.expected*100} showInfo={false} strokeColor="#23836f" />
        <small>{v.scope_observed ? `${awaiting} outstanding · ${v.not_dispatched} not dispatched` : 'No ledger scope observed yet'}</small>
        {key==='primary' && (reviewedResult ? <div><Tag color="green">Human-review declarations: 2/2</Tag><small> Submitted blind reviews are linked to this study; independence and identity are user-reported.</small></div> : review && <div><Tag>Review template snapshot: {review.reviewer_declarations_complete}/2</Tag><small> This snapshot may predate submitted reviews.</small></div>)}
      </div>;
    })}
    <small>Settled requests are not accuracy or acceptance results. Outstanding requests do not prove that a process is still running.</small>
    <details><summary>Snapshot details</summary><p>Observed: {snapshot.observed_at_utc} · Frozen protocols {snapshot.frozen_sha256.primary.slice(0,12)}… / {snapshot.frozen_sha256.repeat.slice(0,12)}…</p></details>
  </Card>;
}
