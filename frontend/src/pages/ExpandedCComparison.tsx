import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Skeleton, Table, Tag } from 'antd';

export const EXPANDED_C_REPORT_PATH = '/reports/phase4-c-expanded-v6.json';
export type ExpandedCStrategy = 'weak_first_hit' | 'strong_rule_based';

/** Contract for the aggregate-only public report in frontend/public/reports/. */
export interface ExpandedCAccuracy {
  correct?: number | null;
  total?: number | null;
  accuracy_percent?: number | null;
}

export interface ExpandedCRepetition {
  repetition: number;
  weak_correct?: number | null;
  strong_correct?: number | null;
  total?: number | null;
}

export interface ExpandedCCategoryResult {
  category: string;
  case_count: number;
  repetitions: number;
  weak: ExpandedCAccuracy;
  strong: ExpandedCAccuracy;
}

export interface ExpandedCSegment {
  case_count?: number;
  repetitions?: number;
  per_repetition?: ExpandedCRepetition[];
  aggregate?: {
    weak?: ExpandedCAccuracy | null;
    strong?: ExpandedCAccuracy | null;
  } | null;
  protocol_sha256?: string | null;
  run_sha256?: string | null;
  winner?: string | null;
  interpretation?: string | null;
  category_results?: ExpandedCCategoryResult[];
  coverage?: { target_answers?: number; usable_grades?: number; complete?: boolean };
  operational_diagnostics?: {
    target_latency_ms_mean?: { weak?: number; strong?: number };
    target_input_tokens?: { weak?: number; strong?: number };
    estimated_cost_usd?: number;
    billing_uncertain?: boolean;
    recovered_http_429_attempts?: number;
    unresolved_requests?: number;
    note?: string;
  };
  human_review?: { status?: string; review_items?: number; independent_histories?: number };
}

export interface ExpandedCReport {
  format: 'phase4-c-expanded-v6';
  study_id: string;
  generated_at: string;
  source: {
    revision?: string;
    license?: string;
    source_sha256?: string;
    dataset?: string;
    citation?: string;
  };
  baseline_v5: ExpandedCSegment;
  extension_v6?: ExpandedCSegment | null;
  combined?: ExpandedCSegment | null;
  decision?: {
    selected_strategy?: string | null;
    rule?: string | null;
    reason?: string | null;
    repeat_wins?: number;
  } | null;
  limitations?: string[];
}

type PageState = 'loading' | 'empty' | 'ready' | 'error';
type ComparisonRow = { key: string; caseSet: string; caseCount: string; weak: string; strong: string; repeats: string; winner: string };

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const isText = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0;
const isOptionalText = (value: unknown) => value === undefined || value === null || typeof value === 'string';
const isOptionalNumber = (value: unknown) => value === undefined || value === null || (typeof value === 'number' && Number.isFinite(value));
const isOptionalCount = (value: unknown) => value === undefined || value === null || (typeof value === 'number' && Number.isInteger(value) && value >= 0);

/** Overlay the later source-bound review without modifying the archived collection. */
export async function withLatestCReview(report: ExpandedCReport): Promise<ExpandedCReport> {
  try {
    const response = await fetch('/reports/proposal-final-results-v1.json', { cache: 'no-store' });
    if (!response.ok) return report;
    const value: unknown = await response.json();
    if (!isRecord(value) || value.format !== 'proposal-final-results-dashboard-v1' || !isRecord(value.proposal_c)
      || !isRecord(value.proposal_c.expanded_v5_v6) || !isRecord(value.proposal_c.expanded_v5_v6.v6_human_review)) return report;
    const review = value.proposal_c.expanded_v5_v6.v6_human_review;
    if (!isText(review.status) || review.review_items !== 180 || review.independent_histories !== 30 || !report.extension_v6) return report;
    const caveat = 'The user reports independent review before automatic scores; original declarations conflict, and identities and procedures are not independently authenticated.';
    return { ...report, extension_v6: { ...report.extension_v6, human_review: {
      status: review.status, review_items: 180, independent_histories: 30,
    } }, limitations: [...(report.limitations ?? []).filter(item => !item.includes('have not yet received independent human review')), caveat] };
  } catch { return report; }
}
const isOptionalHash = (value: unknown) => value === undefined || value === null || (typeof value === 'string' && /^[a-f0-9]{64}$/i.test(value));

function isAccuracy(value: unknown): value is ExpandedCAccuracy {
  return value === undefined || value === null || (isRecord(value)
    && isOptionalCount(value.correct) && isOptionalCount(value.total)
    && isOptionalNumber(value.accuracy_percent) && (!numeric(value.accuracy_percent) || (value.accuracy_percent >= 0 && value.accuracy_percent <= 100))
    && !(numeric(value.correct) && numeric(value.total) && value.correct > value.total));
}

function isSegment(value: unknown): value is ExpandedCSegment {
  if (value === undefined || value === null) return true;
  if (!isRecord(value) || !isOptionalCount(value.case_count) || !isOptionalCount(value.repetitions)
      || !isOptionalHash(value.protocol_sha256) || !isOptionalHash(value.run_sha256)
      || !isOptionalText(value.winner) || !isOptionalText(value.interpretation)) return false;
  if (value.aggregate !== undefined && value.aggregate !== null) {
    if (!isRecord(value.aggregate) || !isAccuracy(value.aggregate.weak) || !isAccuracy(value.aggregate.strong)) return false;
  }
  if (value.per_repetition !== undefined) {
    if (!Array.isArray(value.per_repetition)) return false;
    if (!value.per_repetition.every(item => isRecord(item) && typeof item.repetition === 'number'
        && Number.isInteger(item.repetition) && item.repetition > 0
        && isOptionalCount(item.weak_correct) && isOptionalCount(item.strong_correct) && isOptionalCount(item.total)
        && !(numeric(item.weak_correct) && numeric(item.total) && item.weak_correct > item.total)
        && !(numeric(item.strong_correct) && numeric(item.total) && item.strong_correct > item.total))) return false;
  }
  if (value.category_results !== undefined) {
    if (!Array.isArray(value.category_results) || !value.category_results.every(item => isRecord(item)
        && isText(item.category) && isOptionalCount(item.case_count) && isOptionalCount(item.repetitions)
        && isAccuracy(item.weak) && isAccuracy(item.strong))) return false;
  }
  if (value.coverage !== undefined && (!isRecord(value.coverage)
      || !isOptionalCount(value.coverage.target_answers) || !isOptionalCount(value.coverage.usable_grades)
      || (value.coverage.complete !== undefined && typeof value.coverage.complete !== 'boolean'))) return false;
  if (value.operational_diagnostics !== undefined) {
    const diagnostics = value.operational_diagnostics;
    if (!isRecord(diagnostics) || !isOptionalNumber(diagnostics.estimated_cost_usd)
        || (diagnostics.billing_uncertain !== undefined && typeof diagnostics.billing_uncertain !== 'boolean')
        || !isOptionalCount(diagnostics.recovered_http_429_attempts) || !isOptionalCount(diagnostics.unresolved_requests)
        || !isOptionalText(diagnostics.note)) return false;
    for (const field of ['target_latency_ms_mean', 'target_input_tokens'] as const) {
      const pair = diagnostics[field];
      if (pair !== undefined && (!isRecord(pair) || !isOptionalNumber(pair.weak) || !isOptionalNumber(pair.strong))) return false;
    }
  }
  if (value.human_review !== undefined && (!isRecord(value.human_review)
      || !isOptionalText(value.human_review.status) || !isOptionalCount(value.human_review.review_items)
      || !isOptionalCount(value.human_review.independent_histories))) return false;
  return true;
}

export function isExpandedCReport(value: unknown): value is ExpandedCReport {
  if (!isRecord(value) || value.format !== 'phase4-c-expanded-v6' || !isText(value.study_id) || !isText(value.generated_at)
      || !isRecord(value.source) || !isRecord(value.baseline_v5) || !isSegment(value.baseline_v5)
      || !isSegment(value.extension_v6) || !isSegment(value.combined)) return false;
  const source = value.source;
  if (!isOptionalText(source.revision) || !isOptionalText(source.license) || !isOptionalHash(source.source_sha256)
      || !isOptionalText(source.dataset) || !isOptionalText(source.citation)) return false;
  if (value.decision !== undefined && value.decision !== null) {
    if (!isRecord(value.decision) || !isOptionalText(value.decision.selected_strategy)
        || !isOptionalText(value.decision.rule) || !isOptionalText(value.decision.reason)
        || !isOptionalCount(value.decision.repeat_wins)) return false;
  }
  return value.limitations === undefined || (Array.isArray(value.limitations) && value.limitations.every(isText));
}

function numeric(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function aggregate(segment: ExpandedCSegment | null | undefined, strategy: 'weak' | 'strong'): ExpandedCAccuracy | null {
  if (!segment) return null;
  const explicit = segment.aggregate?.[strategy];
  if (explicit && (numeric(explicit.correct) || numeric(explicit.total) || numeric(explicit.accuracy_percent))) return explicit;
  const repeated = segment.per_repetition ?? [];
  if (!repeated.length) return null;
  const correctValues = repeated.map(item => strategy === 'weak' ? item.weak_correct : item.strong_correct);
  const totals = repeated.map(item => item.total);
  if (!correctValues.every(numeric) || !totals.every(numeric)) return null;
  const correct = correctValues.reduce((sum, value) => sum + value, 0);
  const total = totals.reduce((sum, value) => sum + value, 0);
  return { correct, total, accuracy_percent: total ? correct * 100 / total : null };
}

function formatAccuracy(value: ExpandedCAccuracy | null): string {
  if (!value) return 'Not available';
  const count = numeric(value.correct) && numeric(value.total) ? `${value.correct}/${value.total}` : null;
  const percent = numeric(value.accuracy_percent)
    ? `${value.accuracy_percent.toFixed(1)}%`
    : numeric(value.correct) && numeric(value.total) && value.total > 0
      ? `${((value.correct / value.total) * 100).toFixed(1)}%` : null;
  if (count && percent) return `${count} (${percent})`;
  if (count) return `${count} · percentage unavailable`;
  if (percent) return `${percent} · counts unavailable`;
  return 'Not available';
}

function formatCaseCount(segment: ExpandedCSegment | null | undefined, expected: number): string {
  return numeric(segment?.case_count) ? `${segment.case_count} cases` : `${expected} cases planned`;
}

function repeatSummary(segment: ExpandedCSegment | null | undefined, caseCount: number): string {
  const rows = segment?.per_repetition;
  if (!rows?.length) return 'Per-repeat scores unavailable';
  return rows.map(row => {
    const firstMatch = numeric(row.weak_correct) && numeric(row.total) ? `First-match ${row.weak_correct}/${row.total}` : 'First-match —';
    const relationshipPriority = numeric(row.strong_correct) && numeric(row.total) ? `Relationship-priority ${row.strong_correct}/${row.total}` : 'Relationship-priority —';
    return `R${row.repetition}: ${firstMatch}, ${relationshipPriority}`;
  }).join(' · ') + ` (expected ${caseCount} cases per repeat)`;
}

function winnerLabel(value: string | null | undefined): string {
  if (!value) return 'Not recorded';
  if (value === 'weak_first_hit') return 'First-match ranked higher';
  if (value === 'strong_rule_based') return 'Relationship-priority ranked higher';
  if (value === 'no_clear_winner' || value === 'tie') return 'No clear winner';
  return value;
}

function comparisonRows(report: ExpandedCReport): ComparisonRow[] {
  const entries: Array<{ key: string; label: string; expected: number; value?: ExpandedCSegment | null }> = [
    { key: 'baseline_v5', label: 'Existing v5 subset', expected: 14, value: report.baseline_v5 },
    { key: 'extension_v6', label: 'New v6 cases', expected: 30, value: report.extension_v6 },
    { key: 'combined', label: 'Combined comparison', expected: 44, value: report.combined },
  ];
  return entries.map(({key, label, expected, value}) => ({
    key, caseSet: label, caseCount: value ? formatCaseCount(value, expected) : `${expected} cases · results pending`,
    weak: formatAccuracy(aggregate(value, 'weak')), strong: formatAccuracy(aggregate(value, 'strong')),
    repeats: repeatSummary(value, expected), winner: winnerLabel(value?.winner),
  }));
}

function strategyLabel(value: string | null | undefined): string {
  if (value === 'weak_first_hit') return 'First-match retrieval';
  if (value === 'strong_rule_based') return 'Relationship-priority retrieval';
  if (value === 'no_clear_winner' || value === 'tie') return 'No clear winner';
  return value || 'Not chosen';
}

function neutralPolicyLabels(value: string): string {
  return value.replace(/\bWeak\b/g, 'First-match retrieval').replace(/\bStrong\b/g, 'Relationship-priority retrieval');
}

export function ExpandedCComparisonPage() {
  const [report, setReport] = useState<ExpandedCReport | null>(null);
  const [state, setState] = useState<PageState>('loading');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setState('loading');
    setError('');
    try {
      const response = await fetch(EXPANDED_C_REPORT_PATH, { cache: 'no-store' });
      if (response.status === 404) {
        setReport(null);
        setState('empty');
        return;
      }
      if (!response.ok) throw new Error(`Report request failed (${response.status}).`);
      const text = await response.text();
      if (!text.trim() || /^\s*</.test(text)) {
        setReport(null);
        setState('empty');
        return;
      }
      const value: unknown = JSON.parse(text);
      if (!isExpandedCReport(value)) throw new Error('The expanded C report does not match the required v6 schema.');
      setReport(await withLatestCReview(value));
      setState('ready');
    } catch (cause) {
      setReport(null);
      setError(cause instanceof Error ? cause.message : 'The expanded C report could not be loaded.');
      setState('error');
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return <main className="page"><Card title="Expanded Proposal C comparison" extra={<Button onClick={() => void load()} loading={state === 'loading'}>Refresh report</Button>}>
    <p>Compare the preserved 14-case v5 subset, 30 newly selected cases and their 44-case combined result. The report is aggregate-only; source conversations remain in the evidence bundle.</p>
    <p><a href="/four-strategy-comparison">Open the separate four-strategy v7 supplement →</a></p>
    {state === 'loading' && <section role="status" aria-label="Loading expanded C report"><Skeleton active paragraph={{ rows: 4 }}/></section>}
    {state === 'empty' && <section className="empty" role="status"><b>Expanded C results are not published yet</b><p>This page will show the existing 14 cases, the new 30-case comparison and their combined totals after the evidence report is added.</p></section>}
    {state === 'error' && <Alert role="alert" type="error" showIcon title="Expanded C report could not be loaded" description={error}/>}
    {state === 'ready' && report && <>
      <Alert type="warning" showIcon title="Exploratory benchmark comparison" description="The displayed scores use the saved automated grading process. They are not an official full-benchmark result and do not establish independent human calibration."/>
      <section aria-label="Strategy recommendation" style={{marginTop: 16, marginBottom: 16}}>
        <h2>Current choice</h2>
        <p><Tag color={report.decision?.selected_strategy === 'strong_rule_based' ? 'green' : report.decision?.selected_strategy === 'weak_first_hit' ? 'blue' : 'default'}>{strategyLabel(report.decision?.selected_strategy)}</Tag></p>
        {report.decision?.rule && <p>Decision rule: {neutralPolicyLabels(report.decision.rule)}</p>}
        <p>{neutralPolicyLabels(report.decision?.reason || report.combined?.interpretation || 'The evidence report has not supplied a decision rationale yet.')}</p>
        {numeric(report.decision?.repeat_wins) && <p>Relationship-priority retrieval led in {report.decision.repeat_wins}/3 paired repetitions under the frozen v6 rule.</p>}
      </section>
      <p><b>{report.source.dataset || 'LongMemEval'}</b> · {report.source.revision || 'Revision not recorded'} · {report.source.license || 'Licence not recorded'}</p>
      {report.source.citation && <p>{report.source.citation}</p>}
      <p>Target: {report.baseline_v5 && report.extension_v6 ? 'settings recorded in the frozen v5/v6 protocols' : 'see frozen protocol records'} · {report.baseline_v5?.repetitions ?? report.extension_v6?.repetitions ?? 3} repeats per case set</p>
      <Table<ComparisonRow> rowKey="key" pagination={false} dataSource={comparisonRows(report)} scroll={{x:1050}} columns={[
        {title: 'Case set', dataIndex: 'caseSet', render: (label: string, row) => <span>{label}<br/><small>{row.caseCount}</small></span>},
        {title: 'First-match accuracy', dataIndex: 'weak'},
        {title: 'Relationship-priority accuracy', dataIndex: 'strong'},
        {title: 'Repeat results', dataIndex: 'repeats'},
        {title: 'Within-set ordering', dataIndex: 'winner'},
      ]}/>
      <p><small>Aggregate counts combine repeated answers; percentages use the denominators supplied by the frozen report. Missing scores remain “Not available.” The combined row is secondary and keeps the v5 and v6 segments visible separately.</small></p>
      {report.extension_v6?.category_results?.length ? <section aria-label="v6 category results">
        <h2>Where the new comparison changed</h2>
        <p>Category totals pool three repeats over each selected case; they are descriptive and small.</p>
        <Table rowKey="category" pagination={false} size="small" dataSource={report.extension_v6.category_results} columns={[
          {title: 'Question type', dataIndex: 'category'},
          {title: 'Cases', dataIndex: 'case_count'},
          {title: 'First-match', dataIndex: 'weak', render: (value: ExpandedCAccuracy) => formatAccuracy(value)},
          {title: 'Relationship-priority', dataIndex: 'strong', render: (value: ExpandedCAccuracy) => formatAccuracy(value)},
        ]}/>
      </section> : null}
      {report.extension_v6?.operational_diagnostics && <section aria-label="Operational trade-offs">
        <h2>Cost and response time</h2>
        <p>Mean target latency: First-match {numeric(report.extension_v6.operational_diagnostics.target_latency_ms_mean?.weak)
          ? `${(report.extension_v6.operational_diagnostics.target_latency_ms_mean.weak / 1000).toFixed(2)} s` : 'not available'}; Relationship-priority {numeric(report.extension_v6.operational_diagnostics.target_latency_ms_mean?.strong)
          ? `${(report.extension_v6.operational_diagnostics.target_latency_ms_mean.strong / 1000).toFixed(2)} s` : 'not available'}.</p>
        <p>Target input tokens: First-match {report.extension_v6.operational_diagnostics.target_input_tokens?.weak?.toLocaleString() ?? 'not available'}; Relationship-priority {report.extension_v6.operational_diagnostics.target_input_tokens?.strong?.toLocaleString() ?? 'not available'}.</p>
        <p>Estimated v6 cost: {numeric(report.extension_v6.operational_diagnostics.estimated_cost_usd)
          ? `US$${report.extension_v6.operational_diagnostics.estimated_cost_usd.toFixed(3)}` : 'not available'}.
          {' '}{report.extension_v6.operational_diagnostics.note}</p>
      </section>}
      {report.extension_v6?.coverage && <Alert style={{marginTop: 16}} type={report.extension_v6.coverage.complete ? 'success' : 'warning'} showIcon
        title="Collection and human review" description={`Saved ${report.extension_v6.coverage.target_answers ?? '—'} target answers and ${report.extension_v6.coverage.usable_grades ?? '—'} usable automatic grades. Human review: ${report.extension_v6.human_review?.status || 'not recorded'} (${report.extension_v6.human_review?.review_items ?? '—'} blinded answer rows from ${report.extension_v6.human_review?.independent_histories ?? '—'} source histories).`}/>}
      <section aria-label="Frozen protocols">
        <h2>Frozen protocols and evidence</h2>
        <p>v5 protocol: {report.baseline_v5.protocol_sha256 || 'Not recorded'} · run evidence: {report.baseline_v5.run_sha256 || 'Not recorded'}</p>
        <p>v6 protocol: {report.extension_v6?.protocol_sha256 || 'Not available'} · run evidence: {report.extension_v6?.run_sha256 || 'Not available'}</p>
        {report.source.source_sha256 && <p>Source SHA-256: <code>{report.source.source_sha256}</code></p>}
      </section>
      <section aria-label="Limitations">
        <h2>Limitations</h2>
        {report.limitations?.length ? <ul>{report.limitations.map((limitation, index) => <li key={`${index}:${limitation}`}>{limitation}</li>)}</ul> : <p>Limitations have not been supplied in this report.</p>}
      </section>
      <p><small>Study {report.study_id} · prepared {new Date(report.generated_at).toLocaleString()}</small></p>
    </>}
  </Card></main>;
}
