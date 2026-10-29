import { useEffect, useState } from 'react';
import { Card, Tag } from 'antd';
import { api } from '../services/api';

type Metric = { numerator: number; denominator: number; value: number | null };
type Comparison = { metric: Metric; threshold: number; direction: 'min' | 'max'; met_descriptively: boolean | null };
type Summary = { format: 'ac3-heldout-public-summary-v1'; cases: number; histories: number;
  acceptance: string; limitations: string; human_reference: { unresolved: number };
  automatic: { abstain_reference_fail: number; abstain_reference_pass: number;
    category_missing?: number; category_correct?: number; category_incorrect?: number };
  metrics?: { classification_accuracy_decided?: Metric };
  history_bootstrap?: { status: string; intervals: Record<string, { lower: number | null; upper: number | null }> };
  evidence_sufficiency?: { status: 'insufficient' | 'unassessed' | 'minimums_met_descriptively';
    checks: Record<string, { observed: number | null; minimum: number | null; met: boolean | null }> };
  source_sha256?: { frozen?: string; run?: string; review_1?: string; review_2?: string };
  threshold_comparison_descriptive: Record<string, Comparison> };

const criteria = [
  ['failure_detection_recall_min', 'Failure detection'],
  ['failure_classification_accuracy_min', 'Failure type · predeclared metric'],
  ['test_validity_min', 'Question validity'],
  ['false_positive_rate_max', 'False positives'],
] as const;

export const AC3_PRIMARY_STUDY_SHA = 'ec20077e07ead83925fa38bb67936d81773098e0762c1e4627ae3b94d8ff0f58';
export const AC3_PRIMARY_RUN_SHA = '46c3670eafb67a2f6e3a5e40b08e5a6fa2f126a7cbd5e1aad14752c389eafdb1';

export function isAc3HeldoutSummary(value: unknown): value is Summary {
  if (!value || typeof value !== 'object') return false;
  const s = value as Summary;
  if (s.format !== 'ac3-heldout-public-summary-v1' || !Number.isInteger(s.cases) || s.cases < 1
    || !Number.isInteger(s.histories) || s.histories < 1 || typeof s.acceptance !== 'string'
    || typeof s.limitations !== 'string' || !s.human_reference || !s.automatic || !s.threshold_comparison_descriptive) return false;
  if (![s.human_reference.unresolved, s.automatic.abstain_reference_fail, s.automatic.abstain_reference_pass]
    .every(n => Number.isInteger(n) && n >= 0)) return false;
  if (s.automatic.category_missing !== undefined && (!Number.isInteger(s.automatic.category_missing)
    || s.automatic.category_missing < 0 || s.automatic.category_missing > (s.threshold_comparison_descriptive.failure_classification_accuracy_min?.metric?.denominator ?? -1))) return false;
  return criteria.every(([key]) => {
    const x = s.threshold_comparison_descriptive[key];
    if (!x || !x.metric || !['min', 'max'].includes(x.direction) || typeof x.threshold !== 'number'
      || x.threshold < 0 || x.threshold > 1 || !Number.isInteger(x.metric.numerator)
      || !Number.isInteger(x.metric.denominator) || x.metric.numerator < 0
      || x.metric.denominator < x.metric.numerator) return false;
    const v = x.metric.value;
    return x.metric.denominator === 0 ? v === null : typeof v === 'number' && Math.abs(v - x.metric.numerator / x.metric.denominator) < 1e-9;
  });
}

// A submitted primary aggregate is produced only after the backend validates
// both blind reviews. Match its exact frozen study and evidence identifiers so
// another study cannot make this one appear reviewed.
export function isReviewedAc3Primary(item: { study_id: string; study_role: string; summary: unknown }, primarySha: string, runSha?: string): boolean {
  if (item.study_role !== 'primary_validation' || item.study_id !== primarySha || !isAc3HeldoutSummary(item.summary)) return false;
  const summary = item.summary;
  const hashes = summary.source_sha256;
  return summary.cases === 120 && hashes?.frozen === primarySha
    && typeof hashes.run === 'string' && /^[a-f0-9]{64}$/.test(hashes.run)
    && (!runSha || hashes.run === runSha)
    && typeof hashes.review_1 === 'string' && /^[a-f0-9]{64}$/.test(hashes.review_1)
    && typeof hashes.review_2 === 'string' && /^[a-f0-9]{64}$/.test(hashes.review_2)
    && hashes.review_1 !== hashes.review_2;
}

type StudySummary = { study_id: string; study_role: string; summary: Summary };

export function Ac3HeldoutResults() {
  const [summaries, setSummaries] = useState<StudySummary[]>([]);
  useEffect(() => {
    let active = true;
    const load = async () => {
      let verified: StudySummary[] = [];
      try {
        const result = await api.ac3StudySummaries();
        verified = result.studies.filter((item): item is StudySummary =>
          typeof item.study_id === 'string' && typeof item.study_role === 'string' && isAc3HeldoutSummary(item.summary)
          && (item.study_role !== 'primary_validation' || isReviewedAc3Primary(item, AC3_PRIMARY_STUDY_SHA, AC3_PRIMARY_RUN_SHA)));
      } catch { /* retain the archived aggregate fallback */ }
      if (verified.some(item => isReviewedAc3Primary(item, AC3_PRIMARY_STUDY_SHA, AC3_PRIMARY_RUN_SHA))) {
        if (active) setSummaries(verified);
        return;
      }
      try {
        const response = await fetch('/reports/ac3-heldout-public-summary-v1.json', { cache: 'no-store' });
        const value: unknown = response.ok ? await response.json() : null;
        const archived = { study_id: AC3_PRIMARY_STUDY_SHA, study_role: 'primary_validation', summary: value };
        if (isReviewedAc3Primary(archived, AC3_PRIMARY_STUDY_SHA, AC3_PRIMARY_RUN_SHA)) {
          verified = [archived as StudySummary, ...verified];
        }
      } catch { /* other verified summaries remain visible */ }
      if (active) setSummaries(verified);
    };
    void load();
    return () => { active = false; };
  }, []);
  return <>{summaries.map(item => <SummaryCard key={item.study_id} summary={item.summary}
    title={`AC3 · ${item.study_role === 'primary_validation' ? 'Main validation' : item.study_role === 'stability_repeat' ? 'Stability repeat' : 'Auditor held-out comparison'}${item.study_id === 'archived' ? '' : ` · ${item.study_id.slice(0,8)}`}`} />)}</>;
}

function SummaryCard({summary, title}: {summary: Summary; title: string}) {
  return <Card title={title} style={{ marginTop: 16 }}>
    <p>{summary.cases} questions · {summary.histories} synthetic histories · <Tag>Descriptive results</Tag></p>
    {summary.evidence_sufficiency?.status === 'insufficient' && <p><Tag color="orange">Insufficient evidence</Tag> One or more predeclared sample or coverage minimums were not met.</p>}
    {summary.evidence_sufficiency?.status === 'unassessed' && <p><Tag>Evidence sufficiency not assessed</Tag></p>}
    {criteria.map(([key, label]) => {
      const c = summary.threshold_comparison_descriptive[key];
      const percent = c.metric.value === null ? null : c.metric.value * 100;
      const met = c.metric.value === null ? null : c.direction === 'min' ? c.metric.value >= c.threshold : c.metric.value <= c.threshold;
      const metricKey = ({ failure_detection_recall_min: 'failure_recall_conservative', failure_classification_accuracy_min: 'classification_accuracy_conservative', false_positive_rate_max: 'false_positive_rate_decided' } as Record<string, string>)[key];
      const interval = summary.history_bootstrap?.intervals?.[metricKey];
      return <div key={key} style={{ margin: '12px 0' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <span>{label}</span><strong>{percent === null ? 'Not measured' : `${percent.toFixed(1)}% · ${c.metric.numerator}/${c.metric.denominator}`}</strong>
        </div>
        <div role="img" aria-label={`${label}: ${percent === null ? 'not measured' : `${percent.toFixed(1)} percent`}`} style={{ height: 12, background: '#edf0f2', borderRadius: 6, overflow: 'hidden' }}>
          <div style={{ width: `${percent ?? 0}%`, height: '100%', background: '#23836f' }} />
        </div>
        <small>Target {c.direction === 'min' ? '≥' : '≤'}{(c.threshold * 100).toFixed(0)}% {met !== null && <Tag color={met ? 'green' : 'red'}>{met ? 'Target met' : 'Target not met'}</Tag>}{interval && typeof interval.lower === 'number' && typeof interval.upper === 'number' ? ` · History resampling interval ${(interval.lower * 100).toFixed(1)}–${(interval.upper * 100).toFixed(1)}%` : ''}</small>
        {key === 'failure_classification_accuracy_min' && typeof summary.automatic.category_missing === 'number' && <p style={{ margin: '4px 0' }}>
          {c.metric.denominator - summary.automatic.category_missing}/{c.metric.denominator} classified · {summary.automatic.category_missing} unclassified. Unclassified cases count as misses in the predeclared metric.
          {' '}Accuracy among classified cases: {!summary.metrics?.classification_accuracy_decided ? 'not available' : summary.metrics.classification_accuracy_decided.value === null ? 'not defined (no classified cases)' : `${(summary.metrics.classification_accuracy_decided.value * 100).toFixed(1)}%`}.
        </p>}
      </div>;
    })}
    <p>Human unresolved: {summary.human_reference.unresolved} · Auditor abstentions: {summary.automatic.abstain_reference_fail + summary.automatic.abstain_reference_pass}</p>
    {summary.evidence_sufficiency && <p><small>Sample and coverage checks: {summary.evidence_sufficiency.status.replaceAll('_', ' ')}.</small></p>}
    <small>{summary.limitations} Intervals resample observed synthetic histories and do not establish population generalisation. Formal acceptance remains subject to provenance and review checks.</small>
  </Card>;
}
