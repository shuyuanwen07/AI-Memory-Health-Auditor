import { useEffect, useState } from 'react';
import { Card } from 'antd';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { FOUR_STRATEGIES } from './FourStrategyComparison';

type Counts = { agreed_pass: number; agreed_fail: number; uncertain: number; disagreement: number; total: number; distinct_questions: number };
type Summary = { format: 'four-strategy-human-public-summary-v1'; source_run_sha256: string;
  strategies: Record<string, Counts>; reviewer_procedure: Array<{ completed_by_human: boolean; completed_independently: boolean;
    has_seen_automated_or_aggregate_results: boolean; used_ai_assistance: boolean }>;
  adjudicated: false; automatic_scores_replaced: false };
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const count = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v) && v >= 0;

export function isFourStrategyHumanSummary(value: unknown, runHash: string): value is Summary {
  if (!object(value) || value.format !== 'four-strategy-human-public-summary-v1' || value.source_run_sha256 !== runHash
    || !object(value.strategies) || value.adjudicated !== false || value.automatic_scores_replaced !== false
    || !Array.isArray(value.reviewer_procedure) || value.reviewer_procedure.length !== 2) return false;
  if (!value.reviewer_procedure.every(d => object(d) && d.completed_by_human === true
      && ['completed_independently','has_seen_automated_or_aggregate_results','used_ai_assistance'].every(k => typeof d[k] === 'boolean'))) return false;
  if (Object.keys(value.strategies).length !== FOUR_STRATEGIES.length) return false;
  return FOUR_STRATEGIES.every(({id}) => {
    const row = (value.strategies as Record<string, unknown>)[id];
    return object(row) && count(row.agreed_pass) && count(row.agreed_fail) && count(row.uncertain) && count(row.disagreement)
      && row.total === 90 && row.distinct_questions === 30
      && row.agreed_pass + row.agreed_fail + row.uncertain + row.disagreement === 90;
  });
}

export function FourStrategyHumanResults() {
  const [data, setData] = useState<Summary | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let active = true;
    Promise.all(['/reports/four-strategy-human-review-v1.json','/reports/phase4-c-four-strategy-v7.json']
      .map(path => fetch(path,{cache:'no-store'}).then(r => r.ok ? r.json() : null)))
      .then(([summary,run]: unknown[]) => {
        if (active && object(run) && typeof run.run_sha256 === 'string' && isFourStrategyHumanSummary(summary,run.run_sha256)) setData(summary);
      }).catch(() => { if (active) setData(null); }).finally(() => { if (active) setLoaded(true); });
    return () => { active = false; };
  }, []);
  if (!data) return loaded ? <Card title="Four strategies · human review" style={{marginTop:16}}>
    <p>Human-review results are not available on this dashboard yet. Automatic scores above remain separate.</p>
  </Card> : null;
  const rows=FOUR_STRATEGIES.map(s => ({name:s.label,...data.strategies[s.id]}));
  const blind=data.reviewer_procedure.every(d => d.completed_independently && !d.has_seen_automated_or_aggregate_results);
  return <Card title="Four strategies · human review" style={{marginTop:16}}>
    <div role="img" aria-label="Human reviewer agreement by strategy" style={{width:'100%',height:300}}>
      <ResponsiveContainer><BarChart data={rows} layout="vertical" margin={{left:30,right:20}}>
        <CartesianGrid strokeDasharray="3 3"/><XAxis type="number" domain={[0,90]}/><YAxis type="category" dataKey="name" width={180}/><Tooltip/><Legend/>
        <Bar dataKey="agreed_pass" name="Both pass" stackId="a" fill="#23836f"/>
        <Bar dataKey="agreed_fail" name="Both fail" stackId="a" fill="#c24b4b"/>
        <Bar dataKey="uncertain" name="Uncertain" stackId="a" fill="#d39b32"/>
        <Bar dataKey="disagreement" name="Disagreement" stackId="a" fill="#785aa6"/>
      </BarChart></ResponsiveContainer>
    </div>
    <p>90 answers per strategy · 30 shared cases · automated scores are unchanged.</p>
    <p>{blind ? 'Both reviewers report independent review without seeing automated results.' : 'Review procedure is recorded; independent blind review is not established.'} Identity and procedure are not independently authenticated.</p>
  </Card>;
}
