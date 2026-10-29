import { useCallback, useEffect, useState } from 'react';
import { Button, Card, Progress, Tag } from 'antd';

type Counts = { completed: number; failed: number; other: number };
type Snapshot = { format: 'ac1-extraction-progress-v1'; observed_at_utc: string; expected_histories: number;
  result_histories: number; started_without_result: number; not_yet_observed: number;
  outcomes: { completed: number; partial: number; failed: number; runtime_changed: number };
  stage_outcomes: Record<string, Counts>; protocol_sha256: string; runtime_source_sha256: string;
  result_receipts_sha256: string; interpretation: string };
const stages = [['memory_extraction','Memory extraction'], ['relationship_analysis','Relationship analysis'],
  ['independent_memory_review','Automated review']] as const;

function isSnapshot(value: unknown): value is Snapshot {
  if (!value || typeof value !== 'object') return false;
  const s = value as Snapshot;
  if (s.format !== 'ac1-extraction-progress-v1' || !s.outcomes || !s.stage_outcomes
    || ![s.expected_histories,s.result_histories,s.started_without_result,s.not_yet_observed].every(n => Number.isInteger(n) && n >= 0)
    || s.expected_histories === 0 || s.result_histories + s.started_without_result + s.not_yet_observed !== s.expected_histories
    || ![s.outcomes.completed,s.outcomes.partial,s.outcomes.failed,s.outcomes.runtime_changed].every(n => Number.isInteger(n) && n >= 0)
    || s.outcomes.completed + s.outcomes.partial + s.outcomes.failed + s.outcomes.runtime_changed !== s.result_histories
    || typeof s.observed_at_utc !== 'string' || typeof s.interpretation !== 'string'
    || ![s.protocol_sha256,s.runtime_source_sha256,s.result_receipts_sha256].every(x => typeof x === 'string' && /^[a-f0-9]{64}$/.test(x))) return false;
  return stages.every(([role]) => {
    const c=s.stage_outcomes[role]; return !!c && [c.completed,c.failed,c.other].every(n => Number.isInteger(n) && n >= 0)
      && c.completed+c.failed+c.other <= s.result_histories;
  });
}

export function Ac1ExtractionProgress() {
  const [snapshot,setSnapshot]=useState<Snapshot | null>(null);
  const [refreshing,setRefreshing]=useState(false);
  const refresh=useCallback(() => {
    setRefreshing(true);
    fetch('/reports/ac1-extraction-progress-v1.json',{cache:'no-store'})
      .then(r => r.ok ? r.json() : null)
      .then(value => { if (isSnapshot(value)) setSnapshot(value); })
      .catch(() => undefined)
      .finally(() => setRefreshing(false));
  },[]);
  useEffect(() => { refresh(); },[refresh]);
  if (!snapshot) return null;
  return <Card title="AC1 · Extraction collection" style={{marginTop:16}}
    extra={<Button onClick={refresh} loading={refreshing}>Refresh</Button>}>
    <p><strong>{snapshot.result_histories}/{snapshot.expected_histories}</strong> history result files observed <Tag>Collection snapshot</Tag></p>
    <Progress percent={snapshot.result_histories / snapshot.expected_histories * 100} showInfo={false} strokeColor="#23836f" />
    <p>{snapshot.outcomes.completed} complete · {snapshot.outcomes.partial} partial · {snapshot.outcomes.failed + snapshot.outcomes.runtime_changed} failed or changed · {snapshot.started_without_result} started without a result</p>
    <div style={{display:'flex', flexWrap:'wrap', gap:'8px 24px'}}>
      {stages.map(([role,label]) => <span key={role}>{label}: <b>{snapshot.stage_outcomes[role].completed}/{snapshot.expected_histories}</b></span>)}
    </div>
    <p><small>Counts describe collection only, not correctness or AC1 acceptance. A started marker does not confirm a live process.</small></p>
    <details><summary>Snapshot details</summary><p>Observed: {snapshot.observed_at_utc} · Protocol {snapshot.protocol_sha256.slice(0,12)}… · Runtime {snapshot.runtime_source_sha256.slice(0,12)}… · Receipt set {snapshot.result_receipts_sha256.slice(0,12)}…</p></details>
  </Card>;
}
