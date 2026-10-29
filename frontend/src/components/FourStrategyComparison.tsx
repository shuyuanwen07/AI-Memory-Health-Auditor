import './FourStrategyComparison.css';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Descriptions, Skeleton, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export const FOUR_STRATEGY_REPORT_PATH = '/reports/phase4-c-four-strategy-v7.json';
export const FOUR_STRATEGY_REPORT_FORMAT = 'phase4-c-four-strategy-v7';

export const FOUR_STRATEGIES = [
  { id: 'weak_first_hit', label: 'First-match retrieval' },
  { id: 'strong_rule_based', label: 'Relationship-priority retrieval' },
  { id: 'scope_aware', label: 'Match the task and project' },
  { id: 'temporal_importance', label: 'Consider time and importance' },
] as const;

export type FourStrategyId = typeof FOUR_STRATEGIES[number]['id'];

export interface FourStrategyAccuracy {
  correct: number;
  total: number;
  accuracy_percent: number | null;
}

export interface FourStrategyRepetition extends FourStrategyAccuracy {
  repetition: number;
}

export interface FourStrategyCategory extends FourStrategyAccuracy {
  category: string;
}

export interface FourStrategyResult extends FourStrategyAccuracy {
  id: FourStrategyId;
  label: string;
  per_repetition: FourStrategyRepetition[];
  categories: FourStrategyCategory[];
}

export interface FourStrategyPairwise {
  left: FourStrategyId;
  right: FourStrategyId;
  left_only: number;
  right_only: number;
  both: number;
  neither: number;
  total: number;
  left_accuracy_percent: number | null;
  right_accuracy_percent: number | null;
  difference_pp: number | null;
}

export interface FourStrategyReport {
  format: typeof FOUR_STRATEGY_REPORT_FORMAT;
  study_id: string;
  generated_at: string;
  protocol_id: string;
  protocol_sha256: string;
  run_sha256: string;
  source_revision: string;
  collection_status: string;
  collection_complete?: boolean;
  complete_for_decision: boolean;
  pacing_status?: string;
  pacing_addendum_sha256?: string;
  recommended_strategy: FourStrategyId | 'no_clear_winner';
  decision_rule: string;
  case_count: number;
  repetitions: number;
  total_target_answers: number;
  total_usable_grades: number;
  estimated_cost_usd: number | null;
  usage_based_cost_estimate_usd: number | null;
  request_dispatches: number;
  strategies: FourStrategyResult[];
  pairwise: FourStrategyPairwise[];
  limitations: string[];
}

type PageState = 'loading' | 'empty' | 'ready' | 'error';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const isText = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0;
const isCount = (value: unknown): value is number => Number.isInteger(value) && (value as number) >= 0;
const isPercent = (value: unknown): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= 0 && value <= 100;
const isMoney = (value: unknown): value is number | null => value === null
  || (typeof value === 'number' && Number.isFinite(value) && value >= 0);
const isHash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/i.test(value);

function approximatelyEqual(left: number, right: number): boolean {
  // Reports may round percentages to one decimal place.
  return Math.abs(left - right) <= 0.11;
}

function validAccuracy(value: unknown): value is FourStrategyAccuracy {
  if (!isRecord(value) || !isCount(value.correct) || !isCount(value.total) || value.correct > value.total) return false;
  if (value.accuracy_percent !== null && !isPercent(value.accuracy_percent)) return false;
  if (value.total === 0) return value.accuracy_percent === null;
  return typeof value.accuracy_percent === 'number'
    && approximatelyEqual(value.accuracy_percent, value.correct * 100 / value.total);
}

function validStrategy(value: unknown, repetitions: number, caseCount: number): value is FourStrategyResult {
  if (!isRecord(value) || !validAccuracy(value) || !isText(value.label)
      || !FOUR_STRATEGIES.some(strategy => strategy.id === value.id && strategy.label === value.label)
      || !Array.isArray(value.per_repetition) || value.per_repetition.length !== repetitions
      || !Array.isArray(value.categories)) return false;
  const seenRepetitions = new Set<number>();
  let repeatedCorrect = 0;
  let repeatedTotal = 0;
  for (const repetition of value.per_repetition) {
    if (!isRecord(repetition) || !Number.isInteger(repetition.repetition)
        || (repetition.repetition as number) < 1 || (repetition.repetition as number) > repetitions
        || seenRepetitions.has(repetition.repetition as number) || !validAccuracy(repetition)
        || repetition.total > caseCount) return false;
    seenRepetitions.add(repetition.repetition as number);
    repeatedCorrect += repetition.correct;
    repeatedTotal += repetition.total;
  }
  if (repeatedCorrect !== value.correct || repeatedTotal !== value.total) return false;
  return value.categories.every(category => isRecord(category) && isText(category.category)
    && validAccuracy(category));
}

function validPairwise(value: unknown, ids: Set<string>): value is FourStrategyPairwise {
  if (!isRecord(value) || !ids.has(String(value.left)) || !ids.has(String(value.right)) || value.left === value.right
      || !isCount(value.left_only) || !isCount(value.right_only) || !isCount(value.both)
      || !isCount(value.neither) || !isCount(value.total)) return false;
  if (value.left_only + value.right_only + value.both + value.neither !== value.total) return false;
  const expectedLeft = value.total ? (value.left_only + value.both) * 100 / value.total : null;
  const expectedRight = value.total ? (value.right_only + value.both) * 100 / value.total : null;
  const expectedDifference = expectedLeft === null || expectedRight === null ? null : expectedLeft - expectedRight;
  for (const [key, expected] of [
    ['left_accuracy_percent', expectedLeft], ['right_accuracy_percent', expectedRight], ['difference_pp', expectedDifference],
  ] as const) {
    const reported = value[key];
    const validReported = key === 'difference_pp'
      ? typeof reported === 'number' && Number.isFinite(reported) && Math.abs(reported) <= 100
      : isPercent(reported);
    if (expected === null ? reported !== null : !validReported || !approximatelyEqual(reported as number, expected)) return false;
  }
  return true;
}

export function isFourStrategyReport(value: unknown): value is FourStrategyReport {
  if (!isRecord(value) || value.format !== FOUR_STRATEGY_REPORT_FORMAT
      || !isText(value.study_id) || !isText(value.generated_at) || !Number.isFinite(Date.parse(value.generated_at))
      || !isText(value.protocol_id) || !isHash(value.protocol_sha256) || !isHash(value.run_sha256)
      || !isText(value.source_revision) || !isText(value.collection_status)
      || (value.collection_complete !== undefined && typeof value.collection_complete !== 'boolean')
      || (value.pacing_status !== undefined && !isText(value.pacing_status))
      || (value.pacing_addendum_sha256 !== undefined && !isHash(value.pacing_addendum_sha256))
      || typeof value.complete_for_decision !== 'boolean' || !isText(value.decision_rule)
      || !(FOUR_STRATEGIES.some(strategy => strategy.id === value.recommended_strategy) || value.recommended_strategy === 'no_clear_winner')
      || (!value.complete_for_decision && value.recommended_strategy !== 'no_clear_winner')
      || !Number.isInteger(value.case_count) || (value.case_count as number) < 1
      || !Number.isInteger(value.repetitions) || (value.repetitions as number) < 1
      || !isCount(value.total_target_answers) || !isCount(value.total_usable_grades)
      || value.total_usable_grades > value.total_target_answers
      || value.total_target_answers > (value.case_count as number) * (value.repetitions as number) * FOUR_STRATEGIES.length
      || !isMoney(value.estimated_cost_usd) || !isMoney(value.usage_based_cost_estimate_usd)
      || !isCount(value.request_dispatches) || !Array.isArray(value.strategies) || value.strategies.length !== FOUR_STRATEGIES.length
      || !Array.isArray(value.pairwise) || !Array.isArray(value.limitations)
      || !value.limitations.every(isText)) return false;

  const ids = new Set<string>();
  for (const strategy of value.strategies) {
    if (!validStrategy(strategy, value.repetitions as number, value.case_count as number) || ids.has(strategy.id)) return false;
    ids.add(strategy.id);
  }
  if (FOUR_STRATEGIES.some(strategy => !ids.has(strategy.id))) return false;
  if (value.strategies.reduce((sum, strategy) => sum + strategy.total, 0) !== value.total_usable_grades) return false;

  const pairs = new Set<string>();
  for (const pair of value.pairwise) {
    if (!validPairwise(pair, ids)) return false;
    const identity = [pair.left, pair.right].sort().join('|');
    if (pairs.has(identity)) return false;
    pairs.add(identity);
  }
  return true;
}

function accuracyText(correct: number, total: number, accuracy: number | null): string {
  return `${correct}/${total}${accuracy === null ? '' : ` · ${accuracy.toFixed(1)}%`}`;
}

function moneyText(value: number | null): string {
  return value === null ? 'Not reported' : `US$${value.toFixed(3)}`;
}

function repeatSummary(strategy: FourStrategyResult): string {
  const usable = strategy.per_repetition.map(repetition => repetition.accuracy_percent).filter((value): value is number => value !== null);
  if (!usable.length) return 'Repeat summary: no usable grades';
  const mean = usable.reduce((sum, value) => sum + value, 0) / usable.length;
  const range = `${Math.min(...usable).toFixed(1)}–${Math.max(...usable).toFixed(1)}%`;
  const sd = Math.sqrt(usable.reduce((sum, value) => sum + (value - mean) ** 2, 0) / usable.length);
  return `Repeat mean ${mean.toFixed(1)}% · range ${range} · population SD ${sd.toFixed(1)} pp`;
}

function strategyName(id: FourStrategyId | 'no_clear_winner'): string {
  return id === 'no_clear_winner' ? 'No clear winner' : FOUR_STRATEGIES.find(strategy => strategy.id === id)?.label ?? 'No clear winner';
}

type StrategyRow = FourStrategyResult;
type RepetitionRow = FourStrategyRepetition & { key: string; strategy: string };
type CategoryRow = FourStrategyCategory & { key: string; strategy: string };
type PairRow = FourStrategyPairwise & { key: string; left_label: string; right_label: string };

function rowsFor(report: FourStrategyReport) {
  const labels = Object.fromEntries(report.strategies.map(strategy => [strategy.id, strategy.label])) as Record<FourStrategyId, string>;
  return {
    strategies: [...report.strategies].sort((left, right) =>
      FOUR_STRATEGIES.findIndex(item => item.id === left.id) - FOUR_STRATEGIES.findIndex(item => item.id === right.id)),
    repetitions: report.strategies.flatMap(strategy => strategy.per_repetition.map(item => ({
      ...item, key: `${strategy.id}:${item.repetition}`, strategy: strategy.label,
    }))).sort((left, right) => left.repetition - right.repetition
      || FOUR_STRATEGIES.findIndex(item => item.label === left.strategy) - FOUR_STRATEGIES.findIndex(item => item.label === right.strategy)),
    categories: report.strategies.flatMap(strategy => strategy.categories.map(item => ({
      ...item, key: `${strategy.id}:${item.category}`, strategy: strategy.label,
    }))),
    pairwise: report.pairwise.map((item, index) => ({
      ...item, key: `${item.left}:${item.right}:${index}`,
      left_label: labels[item.left], right_label: labels[item.right],
    })),
  };
}

function FourStrategyTables({ report, compact = false }: { report: FourStrategyReport; compact?: boolean }) {
  const rows = rowsFor(report);
  const collectionStatus = report.collection_status.trim().toLowerCase();
  const collectionFinished = report.collection_complete
    ?? ['complete', 'completed', 'complete_automatic_collection'].includes(collectionStatus);
  const strategyColumns: ColumnsType<StrategyRow> = [
    { title: 'Retrieval strategy', dataIndex: 'label' },
    { title: 'Correct / usable grades', render: (_, row) => `${row.correct}/${row.total}` },
    { title: 'Pooled accuracy', render: (_, row) => row.accuracy_percent === null ? 'Not available' : `${row.accuracy_percent.toFixed(1)}%` },
  ];
  const repetitionColumns: ColumnsType<RepetitionRow> = [
    { title: 'Repetition', dataIndex: 'repetition' },
    { title: 'Retrieval strategy', dataIndex: 'strategy' },
    { title: 'Correct / usable grades', render: (_, row) => `${row.correct}/${row.total}` },
    { title: 'Accuracy', render: (_, row) => row.accuracy_percent === null ? 'Not available' : `${row.accuracy_percent.toFixed(1)}%` },
  ];
  const categoryColumns: ColumnsType<CategoryRow> = [
    { title: 'Retrieval strategy', dataIndex: 'strategy' },
    { title: 'Question category', dataIndex: 'category' },
    { title: 'Correct / usable grades', render: (_, row) => `${row.correct}/${row.total}` },
    { title: 'Accuracy', render: (_, row) => row.accuracy_percent === null ? 'Not available' : `${row.accuracy_percent.toFixed(1)}%` },
  ];
  const pairColumns: ColumnsType<PairRow> = [
    { title: 'Paired strategies', render: (_, row) => `${row.left_label} vs ${row.right_label}` },
    { title: 'Left only', dataIndex: 'left_only' },
    { title: 'Right only', dataIndex: 'right_only' },
    { title: 'Both correct', dataIndex: 'both' },
    { title: 'Neither correct', dataIndex: 'neither' },
    { title: 'Comparable answers', dataIndex: 'total' },
    { title: 'Left accuracy', render: (_, row) => row.left_accuracy_percent === null ? 'Not available' : `${row.left_accuracy_percent.toFixed(1)}%` },
    { title: 'Right accuracy', render: (_, row) => row.right_accuracy_percent === null ? 'Not available' : `${row.right_accuracy_percent.toFixed(1)}%` },
    { title: 'Difference · left minus right', render: (_, row) => row.difference_pp === null ? 'Not available' : `${row.difference_pp > 0 ? '+' : ''}${row.difference_pp.toFixed(1)} pp` },
  ];

  return <>
    {report.complete_for_decision
      ? <Alert type="info" showIcon title={report.recommended_strategy === 'no_clear_winner' ? 'Collection complete · no clear winner' : `Collection complete · decision rule selects ${strategyName(report.recommended_strategy)}`} description="This v7 follow-up is an exploratory supplement, separate from the frozen Proposal A/B/C results. The complete status only means the predeclared collection finished; it does not establish Auditor validity or real-world value." />
      : collectionFinished
        ? <Alert type="warning" showIcon title="Collection complete · timing unverified · no winner" description={`All ${report.total_target_answers} target answers and ${report.total_usable_grades} usable grades are retained across ${report.case_count} cases. Because protocol timing could not be verified, show these results descriptively and do not select a strategy winner. See the limitations for the timing caveat.`} />
        : <Alert type="warning" showIcon title="Partial collection · no winner can be declared" description={`The saved run stopped at “${report.collection_status}”. It includes ${report.total_target_answers} target answers and ${report.total_usable_grades} usable grades across ${report.case_count} planned cases. This is an incomplete exploratory supplement, not a final comparison.`} />}

    <section aria-label="Four-strategy pooled results" style={{ marginTop: 18 }}>
      <h3>Overall results</h3>
      <p>Separate target answers from saved usable grades: {report.case_count} cases × {report.repetitions} repeats per strategy, {report.total_target_answers} target answers and {report.total_usable_grades} usable automatic grades. Percentages below pool correct grades over usable grades. Repeated runs are not independent cases.</p>
      <figure aria-label="Four-strategy accuracy chart" style={{ margin: '1rem 0 1.4rem', maxWidth: 900 }}>
        {rows.strategies.map(strategy => <div key={strategy.id} className="four-strategy-result-row" style={{ alignItems: 'center', gap: 12, margin: '0.65rem 0' }}>
          <span>{strategy.label}</span>
          <div role="img" aria-label={`${strategy.label}: ${strategy.accuracy_percent === null ? 'accuracy unavailable' : `${strategy.accuracy_percent.toFixed(1)} percent`}, ${strategy.correct} of ${strategy.total} usable grades`} style={{ height: 16, borderRadius: 8, overflow: 'hidden', background: '#e8edf2' }}>
            {strategy.accuracy_percent !== null && <span style={{ display: 'block', height: '100%', width: `${strategy.accuracy_percent}%`, background: '#167d93', borderRadius: 8 }} />}
          </div>
          <span><strong>{accuracyText(strategy.correct, strategy.total, strategy.accuracy_percent)}</strong><br /><small>{repeatSummary(strategy)}</small></span>
        </div>)}
        <figcaption><small>Bars show pooled accuracy; repeat mean, range, and population SD summarize per-repeat percentages where grades are available.</small></figcaption>
      </figure>
    </section>
    <RepetitionTrendChart report={report} />
    {!compact && <details>
      <summary>Detailed repeat, paired-case, category and provenance tables</summary>
      <Table<StrategyRow> rowKey="id" pagination={false} dataSource={rows.strategies} columns={strategyColumns} scroll={{ x: 620 }} />
      <section aria-label="Results by repetition" style={{ marginTop: 18 }}>
        <h3>Results by repetition</h3>
        <Table<RepetitionRow> rowKey="key" pagination={false} size="small" dataSource={rows.repetitions} columns={repetitionColumns} scroll={{ x: 700 }} />
      </section>
      <section aria-label="Paired outcomes" style={{ marginTop: 18 }}>
        <h3>Paired outcomes</h3>
        <p>“Left only” and “right only” are answers correct under just one strategy. “Both” and “neither” are correct or incorrect under both strategies.</p>
        {rows.pairwise.length
          ? <Table<PairRow> rowKey="key" pagination={false} size="small" dataSource={rows.pairwise} columns={pairColumns} scroll={{ x: 1200 }} />
          : <p>No matched pairwise evidence was included in the report.</p>}
      </section>
      {rows.categories.length > 0 && <section aria-label="Results by question category" style={{ marginTop: 18 }}>
        <h3>Results by question category</h3>
        <p>Category scores are descriptive; small category denominators should not be read as independent confirmation.</p>
        <Table<CategoryRow> rowKey="key" pagination={false} size="small" dataSource={rows.categories} columns={categoryColumns} scroll={{ x: 800 }} />
      </section>}
      <section aria-label="Protocol and run provenance" style={{ marginTop: 18 }}>
        <h3>Protocol and run provenance</h3>
        <Descriptions bordered size="small" column={1}>
          <Descriptions.Item label="Study">{report.study_id}</Descriptions.Item>
          <Descriptions.Item label="Collection status">{report.collection_status}</Descriptions.Item>
          <Descriptions.Item label="Collection complete">{collectionFinished ? 'Yes' : 'No'}</Descriptions.Item>
          <Descriptions.Item label="Complete for decision">{report.complete_for_decision ? 'Yes' : 'No'}</Descriptions.Item>
          {report.pacing_status && <Descriptions.Item label="Pacing evidence">{report.pacing_status}</Descriptions.Item>}
          {report.pacing_addendum_sha256 && <Descriptions.Item label="Pacing addendum SHA-256"><code>{report.pacing_addendum_sha256}</code></Descriptions.Item>}
          <Descriptions.Item label="Protocol">{report.protocol_id}</Descriptions.Item>
          <Descriptions.Item label="Protocol SHA-256"><code>{report.protocol_sha256}</code></Descriptions.Item>
          <Descriptions.Item label="Run SHA-256"><code>{report.run_sha256}</code></Descriptions.Item>
          <Descriptions.Item label="Report generated"><time dateTime={report.generated_at}>{new Date(report.generated_at).toLocaleString()}</time></Descriptions.Item>
        </Descriptions>
      </section>
    </details>}
    {!compact && <details style={{ marginTop: 12 }}>
      <summary>Exploratory limitations</summary>
      <p>{report.decision_rule}</p>
      {report.limitations.length
        ? <ul>{report.limitations.map((limitation, index) => <li key={`${index}:${limitation}`}>{limitation}</li>)}</ul>
        : <p>No limitations were supplied in the report.</p>}
    </details>}
    {compact && <p><small>Exploratory automatic results; the repeated answers reuse the same cases. Timing could not be verified. <a href="/expanded-c">View study details</a>.</small></p>}
  </>;
}

function RepetitionTrendChart({ report }: { report: FourStrategyReport }) {
  const data = Array.from({ length: report.repetitions }, (_, index) => {
    const repetition = index + 1;
    const row: Record<string, number | string | null> = { repetition: `Repeat ${repetition}` };
    report.strategies.forEach(strategy => {
      row[strategy.id] = strategy.per_repetition.find(item => item.repetition === repetition)?.accuracy_percent ?? null;
    });
    return row;
  });
  const summary = report.strategies.map(strategy =>
    `${strategy.label}: ${strategy.per_repetition.map(item => item.accuracy_percent === null ? 'missing' : `${item.accuracy_percent.toFixed(1)}%`).join(', ')}`,
  ).join('; ');
  return <section aria-label="Four-strategy repeat trend" style={{ marginTop: 12 }}>
    <h3>Accuracy by repetition</h3>
    <p>Each point is one repeat; missing grades remain gaps.</p>
    <figure aria-label={`Four-strategy repetition line chart. ${summary}`}>
      <div role="img" aria-label={`Line chart of repeat accuracy from 0 to 100 percent. ${summary}.`}>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 2 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="repetition" />
            <YAxis domain={[0, 100]} tickFormatter={value => `${value}%`} />
            <Tooltip formatter={value => value == null ? 'No usable grade' : `${Number(value).toFixed(1)}%`} />
            <Legend />
            {FOUR_STRATEGIES.map((strategy, index) => <Line
              key={strategy.id} type="monotone" dataKey={strategy.id}
              name={strategy.label} stroke={['#486a9b', '#2d8b78', '#c08335', '#785aa6'][index]}
              strokeWidth={2} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false}
            />)}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption><small>Repeated observations are not independent cases. Pooled accuracy remains the primary summary.</small></figcaption>
    </figure>
  </section>;
}

export function FourStrategyComparisonSection({ compact = false }: { compact?: boolean } = {}) {
  const [report, setReport] = useState<FourStrategyReport | null>(null);
  const [state, setState] = useState<PageState>('loading');
  const [error, setError] = useState('');
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setState('loading');
    setError('');
    try {
      const response = await fetch(FOUR_STRATEGY_REPORT_PATH, { cache: 'no-store' });
      if (response.status === 404) {
        if (currentRequest === requestId.current) { setReport(null); setState('empty'); }
        return;
      }
      if (!response.ok) throw new Error(`Report request failed (${response.status}).`);
      const text = await response.text();
      if (!text.trim() || /^\s*</.test(text)) {
        if (currentRequest === requestId.current) { setReport(null); setState('empty'); }
        return;
      }
      let value: unknown;
      try { value = JSON.parse(text); }
      catch { throw new Error('The four-strategy report is not valid JSON.'); }
      if (!isFourStrategyReport(value)) throw new Error(`The four-strategy report does not match the required ${FOUR_STRATEGY_REPORT_FORMAT} contract.`);
      if (currentRequest === requestId.current) { setReport(value); setState('ready'); }
    } catch (cause) {
      if (currentRequest === requestId.current) {
        setReport(null);
        setError(cause instanceof Error ? cause.message : 'The four-strategy report could not be loaded.');
        setState('error');
      }
    }
  }, []);

  useEffect(() => {
    void load();
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') void load();
    };
    window.addEventListener('focus', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      window.removeEventListener('focus', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
      requestId.current += 1;
    };
  }, [load]);

  const pageState = state === 'ready' && report ? <FourStrategyTables report={report} compact={compact} />
    : state === 'loading' ? <section role="status" aria-label="Loading four-strategy report"><Skeleton active paragraph={{ rows: 4 }} /></section>
        : state === 'empty' ? <section className="empty" role="status"><b>The v7 four-strategy report is not published yet</b><p>The current frozen A/B/C results remain available above. This Experiment C extension will appear here after its aggregate evidence file is published.</p></section>
        : <Alert role="alert" type="error" showIcon title="Four-strategy report could not be loaded" description={error} />;

  return <section id="four-strategy-comparison" aria-label="Four-strategy comparison">
    <Card title={<span>Experiment C · Four-strategy comparison <Tag color="gold">Exploratory supplement</Tag></span>}
      extra={<Button onClick={() => void load()} loading={state === 'loading'}>Refresh supplement</Button>}>
      {pageState}
    </Card>
  </section>;
}

export function FourStrategyComparisonPage() {
  return <main className="page"><FourStrategyComparisonSection /></main>;
}
