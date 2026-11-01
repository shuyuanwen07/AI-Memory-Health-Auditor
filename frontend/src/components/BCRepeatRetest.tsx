import { useEffect, useState } from 'react';
import { Card } from 'antd';

type RepeatCount = { repeat: number; saved: number; pass: number | null };
export type RetestCondition = {
  strategy: string; planned: number; saved: number; errors: number; remaining: number;
  reviewed: number; pass: number | null; fail: number | null; unresolved: number | null;
  safe_incomplete?: number | null;
  repeats: RepeatCount[];
};
export type BCRetestReport = {
  format: 'bc-astra-repeat-retest-v2'; updated_at: string;
  provider: 'openai'; model: 'gpt-6-astra'; reasoning_effort: 'max';
  questions_per_strategy: 16; repetitions: 3; planned_per_strategy: 48;
  review_status: 'pending' | 'ai_reviewed' | 'human_confirmed';
  review_reasoning_effort?: 'high' | 'max';
  source_flags?: { B: number; C: number };
  studies: Array<{ id: 'B' | 'C'; label: string; source_units: number; conditions: RetestCondition[] }>;
};
const ids = ['weak_first_hit', 'strong_rule_based', 'scope_aware', 'temporal_importance'];
const labels: Record<string, string> = {
  weak_first_hit: 'First-match retrieval', strong_rule_based: 'Relationship-priority retrieval',
  scope_aware: 'Match the task and project', temporal_importance: 'Consider time and importance',
};
const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const count = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v) && v >= 0;
export function isBCRetestReport(value: unknown): value is BCRetestReport {
  if (!record(value) || value.format !== 'bc-astra-repeat-retest-v2' || value.provider !== 'openai'
    || value.model !== 'gpt-6-astra' || value.reasoning_effort !== 'max' || value.questions_per_strategy !== 16
    || value.repetitions !== 3 || value.planned_per_strategy !== 48 || typeof value.updated_at !== 'string'
    || !['pending', 'ai_reviewed', 'human_confirmed'].includes(String(value.review_status))
    || !Array.isArray(value.studies) || value.studies.length !== 2) return false;
  const studies = value.studies;
  return ['B', 'C'].every(id => studies.filter((s: unknown) => record(s) && s.id === id).length === 1)
    && studies.every((s: unknown) => {
      if (!record(s) || typeof s.label !== 'string' || !count(s.source_units)
        || !Array.isArray(s.conditions) || s.conditions.length !== 4) return false;
      const conditions = s.conditions;
      return ids.every(id => conditions.filter((c: unknown) => record(c) && c.strategy === id).length === 1)
      && conditions.every((c: unknown) => {
        if (!record(c) || c.planned !== 48 || !count(c.saved) || !count(c.errors) || !count(c.remaining)
          || c.saved + c.errors + c.remaining !== 48 || !count(c.reviewed) || c.reviewed > c.saved
          || !Array.isArray(c.repeats) || c.repeats.length !== 3) return false;
        const repeats = c.repeats;
        if (![1, 2, 3].every(n => repeats.filter((r: unknown) => record(r) && r.repeat === n).length === 1)
          || !repeats.every((r: unknown) => record(r) && count(r.saved) && r.saved <= 16
            && (r.pass === null || (count(r.pass) && r.pass <= r.saved)))
          || repeats.reduce((n: number, r: RepeatCount) => n + r.saved, 0) !== c.saved) return false;
        if (c.reviewed === 0) return c.pass === null && c.fail === null && c.unresolved === null;
        return count(c.pass) && count(c.fail) && count(c.unresolved) && c.pass + c.fail + c.unresolved === c.reviewed;
      });
    });
}
export function useBCRepeatRetest(refreshToken = 0) {
  const [report, setReport] = useState<BCRetestReport | null>(null);
  useEffect(() => {
    let active = true;
    const refresh = () => fetch('/reports/bc-astra-repeat-retest-v2.json', { cache: 'no-store' })
      .then(r => r.ok ? r.json() : null).then(v => { if (active && isBCRetestReport(v)) setReport(v); }).catch(() => {});
    void refresh(); const timer = window.setInterval(() => void refresh(), 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, [refreshToken]);
  return report;
}
export function BCRepeatRetest({ report }: { report: BCRetestReport }) {
  const reviewed = report.studies.some(s => s.conditions.some(c => c.reviewed > 0));
  const reviewLabel = report.review_status === 'human_confirmed' ? 'Human-confirmed AI-assisted review'
    : report.review_status === 'ai_reviewed' ? `Independent Astra ${report.review_reasoning_effort??'high'} review · human confirmation pending` : 'Answer collection · review pending';
  return <Card title="B & C · Astra repeated comparison" className="compact-policies" style={{ gridColumn: '1 / -1', display: 'block' }}>
    <p className="compact-note">OpenAI GPT-6 Astra · max reasoning · 16 questions × 3 repeats = 48 planned answers per strategy in each study.</p>
    <p role="status">{reviewLabel}</p>
    {reviewed && <div className="scope-replay-legend"><span><i className="scope-accepted"/>Pass</span><span><i style={{background:'#8c9eae'}}/>Fail</span><span><i className="scope-pending"/>Unresolved reference or judgment</span></div>}
    <div className="bc-repeat-studies" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 24rem), 1fr))', gap: 16 }}>
      {report.studies.map(study => <figure className="scope-replay" key={study.id} aria-label={`${study.id} Astra repeated retest`}>
        <figcaption>{study.id} · {study.label}</figcaption>
        <p className="compact-note">{study.conditions.reduce((n, c) => n + c.saved, 0)}/192 answers saved · {study.conditions.reduce((n, c) => n + c.errors, 0)} request errors</p>
        {study.conditions.map(c => {
          const finalCounts = c.pass !== null && c.remaining === 0 && c.reviewed === c.saved;
          return <div className="scope-replay-row" key={c.strategy}>
          <span>{labels[c.strategy]}</span>
          <div className="scope-replay-track" role="img" aria-label={finalCounts ? `${c.pass}/48 passed; ${c.fail} failed; ${c.unresolved} unresolved; ${c.errors} missing` : `${c.saved}/48 answered; review pending`}>
            {finalCounts ? <><i className="scope-accepted" style={{width:`${100*c.pass!/48}%`}}/><i style={{width:`${100*c.fail!/48}%`,background:'#8c9eae'}}/><i className="scope-pending" style={{width:`${100*c.unresolved!/48}%`}}/></>
              : <i style={{width:`${100*c.saved/48}%`,background:'#9aaec2'}}/>}
          </div>
          <small>{finalCounts ? `${c.pass}/48 passed · ${c.unresolved} unresolved` : `${c.saved}/48 answered · review pending`}</small>
          {c.pass !== null && <small>{c.pass} pass · {c.fail} fail · {c.unresolved} unresolved · {c.saved-c.reviewed} awaiting review{typeof c.safe_incomplete==='number'?` · ${c.safe_incomplete} safe but incomplete`:''}</small>}
          {finalCounts && <small>Repeats: {c.repeats.map(r => r.pass === null ? 'pending' : `${r.pass}/16`).join(' · ')}</small>}
        </div>;})}
      </figure>)}
    </div>
    <p className="compact-note">B uses 4 related synthetic histories; C uses 16 stratified benchmark cases. Equal answer counts do not imply equal difficulty. Repeats reuse questions and are not independent histories.</p>
    {!!report.source_flags?.C && <p className="compact-note">C: {report.source_flags.C}/16 questions or reference answers flagged for human adjudication. These are unresolved, not automatic model failures.</p>}
    {reviewed && <p className="compact-note">Pass counts use source-aware review. Missing answers and unresolved judgments remain in the planned denominator.</p>}
    <a href="/reports/bc-astra-repeat-retest-v2.json">Counts and study status →</a>
  </Card>;
}
