import { useEffect, useState } from 'react';
import { Card, Progress, Tag } from 'antd';

type Summary = { format: string; histories: number; questions: number; automatic_question_gate: {accepted: number; rejected: number}; automatic_suite_gate: {accepted: number; rejected: number}; reviewers_declared_complete: number; source_sha256: string; corrected_offline: boolean };

export function Ac2GenerationSummary() {
  const [data, setData] = useState<Summary | null>(null);
  useEffect(() => { fetch('/reports/ac2-generation-summary-v1.json', {cache:'no-store'}).then(r => r.ok ? r.json() : null).then((s: Summary | null) => {
    if (s?.format === 'ac2-generation-summary-v1' && s.questions === 120 && s.histories === 30 && s.automatic_question_gate.accepted + s.automatic_question_gate.rejected === 120 && s.automatic_suite_gate.accepted + s.automatic_suite_gate.rejected === 30) setData(s);
  }).catch(() => undefined); }, []);
  if (!data) return null;
  return <Card title="AC2 · Generated test checks" style={{marginTop:16}}>
    <p><Tag color="blue">Automatic checks</Tag><Tag>Reviewer declarations {data.reviewers_declared_complete}/2</Tag></p>
    <div>Individual questions · <b>{data.automatic_question_gate.accepted}/{data.questions} accepted</b></div>
    <Progress percent={data.automatic_question_gate.accepted / data.questions * 100} showInfo={false} strokeColor="#23836f" />
    <div>Complete sets · <b>{data.automatic_suite_gate.accepted}/{data.histories} accepted</b></div>
    <Progress percent={data.automatic_suite_gate.accepted / data.histories * 100} showInfo={false} strokeColor="#577fbb" />
    <small>Automatic gate results are not human validity judgments. A set is accepted only when every question passes the gate. An offline status correction was applied; generation was not repeated.</small>
    <details><summary>Source</summary><p>Corrected output SHA-256: {data.source_sha256} · Reviewer completion declarations: {data.reviewers_declared_complete}/2</p></details>
  </Card>;
}
