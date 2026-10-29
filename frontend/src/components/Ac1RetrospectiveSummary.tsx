import { useEffect, useState } from 'react';
import { Card, Tag } from 'antd';

type Summary = {
  format: 'ac1-retrospective-adjudicated-v1'; scope: string;
  candidate_valid: { numerator: number; denominator: number; agreed_original: number; later_adjudicated: number };
  reference_coverage: { full: number; partial: number; total: number };
  limitations: string[];
};

function isSummary(value: unknown): value is Summary {
  if (!value || typeof value !== 'object') return false;
  const s = value as Summary, c = s.candidate_valid, r = s.reference_coverage;
  if (s.format !== 'ac1-retrospective-adjudicated-v1' || typeof s.scope !== 'string' || !c || !r
    || !Array.isArray(s.limitations) || s.limitations.some(x => typeof x !== 'string')) return false;
  if (![c.numerator, c.denominator, c.agreed_original, c.later_adjudicated, r.full, r.partial, r.total]
    .every(x => Number.isInteger(x) && x >= 0)) return false;
  return c.denominator > 0 && c.numerator <= c.denominator
    && c.agreed_original + c.later_adjudicated === c.numerator && r.total > 0 && r.full + r.partial === r.total;
}

export function Ac1RetrospectiveSummary() {
  const [summary, setSummary] = useState<Summary | null>(null);
  useEffect(() => {
    let active = true;
    fetch('/reports/ac1-retrospective-adjudicated-v1.json', { cache: 'no-store' })
      .then(r => r.ok ? r.json() : null)
      .then(value => { if (active && isSummary(value)) setSummary(value); })
      .catch(() => { if (active) setSummary(null); });
    return () => { active = false; };
  }, []);
  if (!summary) return null;
  const c = summary.candidate_valid, r = summary.reference_coverage;
  return <Card title="AC1 · Retrospective source review" style={{ marginTop: 16 }}>
    <p><Tag color="orange">Retrospective · AI-assisted · not independently blinded</Tag></p>
    <p><b>{c.numerator}/{c.denominator}</b> candidates judged valid · {c.agreed_original} originally agreed, {c.later_adjudicated} later adjudicated</p>
    <p><b>{r.full}/{r.total}</b> listed reference units fully covered · {r.partial}/{r.total} partially covered</p>
    <div role="img" aria-label={`Listed reference coverage: ${r.full} full, ${r.partial} partial`} style={{ display: 'flex', height: 20, width: '100%', borderRadius: 10, overflow: 'hidden', background: '#eee' }}>
      <span style={{ width: `${r.full / r.total * 100}%`, background: '#23836f' }} />
      <span style={{ width: `${r.partial / r.total * 100}%`, background: '#c08335' }} />
    </div>
    <p style={{ marginTop: 8 }}>● Full: {r.full}　<span style={{ color: '#a46822' }}>● Partial: {r.partial}</span></p>
    <small>The reference list is not known to be exhaustive. These retrospective judgments do not establish complete recall or AC1 acceptance; six candidates require source context.</small>
    <details><summary>Review limitations</summary><ul>{summary.limitations.map(x => <li key={x}>{x}</li>)}</ul></details>
  </Card>;
}
