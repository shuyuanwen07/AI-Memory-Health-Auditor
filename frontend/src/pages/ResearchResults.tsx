import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Skeleton, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ExperimentAMethodChart } from '../components/ExperimentAMethodChart';
import { FourStrategyComparisonSection } from '../components/FourStrategyComparison';
import { api } from '../services/api';
import { memoryStrategyLabel, modelDisplayName } from '../services/display';
import type { FormalStudySummary, SavedFormalRunOption } from '../types/domain';
import type { QualityReport } from './AuditorQuality';
import {
  EXPANDED_C_REPORT_PATH,
  isExpandedCReport,
  withLatestCReview,
  type ExpandedCAccuracy,
  type ExpandedCReport,
  type ExpandedCSegment,
} from './ExpandedCComparison';

type PageState = 'loading' | 'ready' | 'empty' | 'error';
type MethodResults = Awaited<ReturnType<typeof api.methodComparisonResults>>;
type MethodCondition = MethodResults['conditions'][number];
type FormalCondition = FormalStudySummary['conditions'][number];

const qualityMeasures = [
  ['Agreement with references', 'accuracy'],
  ['Failure precision', 'failure_precision'],
  ['Failure recall', 'failure_recall'],
  ['False positive rate', 'false_positive_rate'],
  ['Failure category accuracy', 'failure_classification_accuracy'],
] as const;

function percent(value: number | null | undefined, fractional = false) {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'Not measured';
  return `${(fractional ? value * 100 : value).toFixed(1)}%`;
}

function qualityMetricText(metric: QualityReport['accuracy'] | undefined) {
  if (!metric || metric.percentage === null) return 'Not measured';
  return `${metric.percentage.toFixed(1)}% · ${metric.numerator}/${metric.denominator}`;
}

function methodRate(value: number | null, numerator: number, denominator: number) {
  if (value === null || denominator === 0) return 'Not measured';
  return `${percent(value, true)} · ${numerator}/${denominator}`;
}

function accuracyText(value: ExpandedCAccuracy | null | undefined) {
  if (!value) return 'Not measured';
  if (typeof value.correct === 'number' && typeof value.total === 'number') {
    const rate = value.accuracy_percent ?? (value.total ? value.correct * 100 / value.total : null);
    return `${value.correct}/${value.total}${rate === null ? '' : ` · ${rate.toFixed(1)}%`}`;
  }
  return typeof value.accuracy_percent === 'number' ? `${value.accuracy_percent.toFixed(1)}% · counts unavailable` : 'Not measured';
}

function segmentCases(segment: ExpandedCSegment | null | undefined, fallback: number) {
  return typeof segment?.case_count === 'number' ? `${segment.case_count} cases` : `${fallback} cases planned`;
}

function winnerLabel(winner: string | null | undefined) {
  if (winner === 'strong_rule_based') return 'Relationship-priority ranked higher';
  if (winner === 'weak_first_hit') return 'First-match ranked higher';
  if (winner === 'tie' || winner === 'no_clear_winner') return 'No clear winner';
  return winner || 'Not recorded';
}

async function loadExpandedC(): Promise<ExpandedCReport | null> {
  const response = await fetch(EXPANDED_C_REPORT_PATH, { cache: 'no-store' });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Experiment C report request failed (${response.status}).`);
  const body: unknown = await response.json();
  if (!isExpandedCReport(body)) throw new Error('The Experiment C report has an unsupported format.');
  return withLatestCReview(body);
}

export function ResearchResultsPage({ embedded = false }: { embedded?: boolean }) {
  const [loading, setLoading] = useState(true);
  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [methodResults, setMethodResults] = useState<MethodResults | null>(null);
  const [formalSummary, setFormalSummary] = useState<FormalStudySummary | null>(null);
  const [formalRun, setFormalRun] = useState<SavedFormalRunOption | null>(null);
  const [expandedC, setExpandedC] = useState<ExpandedCReport | null>(null);
  const [states, setStates] = useState<Record<string, PageState>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const refresh = useCallback(async () => {
    setLoading(true);
    setErrors({});
    setStates({ auditor: 'loading', method: 'loading', memory: 'loading', benchmark: 'loading' });

    const qualityTask = api.auditorQuality().then(value => {
      setQuality(value);
      setStates(current => ({ ...current, auditor: 'ready' }));
    }).catch(error => {
      setErrors(current => ({ ...current, auditor: error instanceof Error ? error.message : 'Auditor evidence could not be loaded.' }));
      setStates(current => ({ ...current, auditor: 'error' }));
    });

    const methodTask = api.experimentGroups().then(async groups => {
      const latest = groups
        .filter(group => group.test_suite_metadata.study_role === 'audit_method_comparison'
          && group.test_suite_metadata.diagnostic_source_run_id
          && group.test_suite_metadata.method_comparison_id)
        .sort((left, right) => right.created_at.localeCompare(left.created_at))[0];
      if (!latest) {
        setMethodResults(null);
        setStates(current => ({ ...current, method: 'empty' }));
        return;
      }
      const result = await api.methodComparisonResults(
        latest.test_suite_metadata.diagnostic_source_run_id!,
        latest.test_suite_metadata.method_comparison_id!,
      );
      setMethodResults(result);
      setStates(current => ({ ...current, method: 'ready' }));
    }).catch(error => {
      setErrors(current => ({ ...current, method: error instanceof Error ? error.message : 'Experiment A results could not be loaded.' }));
      setStates(current => ({ ...current, method: 'error' }));
    });

    const memoryTask = api.savedFormalRuns().then(async page => {
      const candidates = page.items.filter(item => item.study_mode === 'formal_experiment_b');
      const complete = candidates.find(item => item.status.toLowerCase() === 'completed');
      const selected = complete ?? candidates[0];
      if (!selected) {
        setFormalRun(null);
        setFormalSummary(null);
        setStates(current => ({ ...current, memory: 'empty' }));
        return;
      }
      const summary = await api.formalStudySummary(selected.run_id);
      setFormalRun(selected);
      setFormalSummary(summary);
      setStates(current => ({ ...current, memory: 'ready' }));
    }).catch(error => {
      setErrors(current => ({ ...current, memory: error instanceof Error ? error.message : 'Experiment B results could not be loaded.' }));
      setStates(current => ({ ...current, memory: 'error' }));
    });

    const benchmarkTask = loadExpandedC().then(value => {
      setExpandedC(value);
      setStates(current => ({ ...current, benchmark: value ? 'ready' : 'empty' }));
    }).catch(error => {
      setErrors(current => ({ ...current, benchmark: error instanceof Error ? error.message : 'Experiment C results could not be loaded.' }));
      setStates(current => ({ ...current, benchmark: 'error' }));
    });

    await Promise.all([qualityTask, methodTask, memoryTask, benchmarkTask]);
    setLoading(false);
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const methodColumns: ColumnsType<MethodCondition> = [
    { title: 'Test method', dataIndex: 'label' },
    { title: 'Valid questions', render: (_, row) => `${row.valid_test_count}/${row.test_count}` },
    { title: 'Failure recall', render: (_, row) => methodRate(row.response_level.failure_detection_recall, row.response_level.true_positives, row.response_level.true_positives + row.response_level.false_negatives) },
    { title: 'Distinct failures found', render: (_, row) => row.failure_discovery_rate.value === null ? `Not measured · ${row.failure_discovery_rate.status}` : `${percent(row.failure_discovery_rate.value, true)} · ${row.failure_discovery_rate.discovered_distinct_failures}/${row.failure_discovery_rate.known_distinct_failures}` },
    { title: 'False positive rate', render: (_, row) => methodRate(row.response_level.false_positive_rate, row.response_level.false_positives, row.response_level.false_positives + row.response_level.true_negatives) },
  ];

  const qualityRows = quality ? qualityMeasures.map(([label, key]) => ({
    key,
    label,
    result: qualityMetricText(quality[key]),
  })) : [];

  const formalRows = formalSummary?.conditions.map(condition => ({
    key: condition.condition_index,
    setting: `${memoryStrategyLabel(condition.memory_strategy)} · ${modelDisplayName(condition.model)}`,
    score: percent(condition.overall_memory_health?.mean_percent ?? condition.mean_percent),
    measured: `${condition.measured_histories}/${formalSummary.planned_histories} histories`,
    repeats: `${condition.completed_runs}/${condition.planned_runs} runs · ${condition.uncertain_runs} uncertain`,
  })) ?? [];

  const dimensionRows = formalSummary?.conditions.flatMap(condition => (condition.dimension_summaries ?? []).map(item => ({
    key: `${condition.condition_index}-${item.dimension}`,
    setting: memoryStrategyLabel(condition.memory_strategy),
    dimension: item.dimension.replaceAll('_', ' '),
    score: percent(item.mean_percent),
    coverage: `${item.measured_histories}/${formalSummary.planned_histories} histories`,
    uncertain: item.uncertain_runs,
  }))) ?? [];

  const cRows = expandedC ? [
    { key: 'baseline-v5', label: 'Existing v5 subset', cases: segmentCases(expandedC.baseline_v5, 14), weak: accuracyText(expandedC.baseline_v5.aggregate?.weak), strong: accuracyText(expandedC.baseline_v5.aggregate?.strong), winner: winnerLabel(expandedC.baseline_v5.winner) },
    { key: 'extension-v6', label: 'New v6 cases', cases: segmentCases(expandedC.extension_v6, 30), weak: accuracyText(expandedC.extension_v6?.aggregate?.weak), strong: accuracyText(expandedC.extension_v6?.aggregate?.strong), winner: winnerLabel(expandedC.extension_v6?.winner) },
  ] : [];

  const Page = embedded ? 'div' : 'main';
  return <Page className={embedded ? 'research-results-page embedded' : 'page research-results-page'}>
    <div className="page-heading">
      <div>
        <h1>Research results</h1>
        <p>Saved Proposal A, B and C outcomes, with Auditor validation kept separate from target-memory results. The four-strategy v7 study is shown as a separate exploratory supplement.</p>
      </div>
      <Button onClick={() => void refresh()} loading={loading}>Refresh results</Button>
    </div>

    <Alert style={{ marginBottom: 20 }} type="info" showIcon title="How to read the dashboard" description="A measures audit-test performance. B and C compare target-memory retrieval policies. Auditor reliability uses reference labels in its own panel; none of the target-policy scores is an Auditor-accuracy score." />

    <Card title="A · Which audit tests find failures?" extra={<a href={methodResults ? `/audits/${methodResults.source_run_id}` : '/history'}>Open source audit →</a>} style={{ marginBottom: 20 }}>
      {states.method === 'loading' && <Skeleton active paragraph={{ rows: 3 }} />}
      {states.method === 'error' && <Alert type="error" showIcon title="Experiment A could not be loaded" description={errors.method} />}
      {states.method === 'empty' && <Alert type="info" showIcon title="No saved proposal A comparison was found" description="Create or restore the three-condition comparison from a completed audit report. The separate Audit methods page compares a different set of evaluator workflows." />}
      {methodResults && <>
        <p>{methodResults.notice}</p>
        <p>Equal test caps: {methodResults.planned_test_budgets_equal ? 'yes' : 'no'} · Target and evaluator settings matched: {methodResults.target_and_evaluation_settings_match ? 'yes' : 'no'} · Frozen source defects: {methodResults.inventory.distinct_failure_count ?? 'not recorded'}</p>
        <ExperimentAMethodChart conditions={methodResults.conditions} />
        <Table<MethodCondition> rowKey="run_id" pagination={false} dataSource={methodResults.conditions} columns={methodColumns} scroll={{ x: 950 }} />
        <p><a href="/experiments">Open research validation tools →</a></p>
      </>}
    </Card>

    <Card title="Auditor reliability · comparison with reference labels" extra={<a href="/quality">Open detailed reliability page →</a>} style={{ marginBottom: 20 }}>
      {states.auditor === 'loading' && <Skeleton active paragraph={{ rows: 3 }} />}
      {states.auditor === 'error' && <Alert type="error" showIcon title="Auditor evidence could not be loaded" description={errors.auditor} />}
      {quality && <>
        <Alert type={quality.adjudicated_reference_count ? 'info' : 'warning'} showIcon title={quality.adjudicated_reference_count ? 'Some adjudicated references are available; check coverage and provenance.' : 'Independent, held-out Auditor validation is not established.'} description={quality.notice} />
        <p>{quality.resolved_reference_count}/{quality.evidence_integrity?.expected_questions ?? quality.evaluated} saved reference labels resolved · {quality.adjudicated_reference_count ?? 0} adjudicated · {quality.uncertain} uncertain · {quality.decided_reference_count} decided answers eligible for agreement metrics.</p>
        <Table rowKey="key" pagination={false} dataSource={qualityRows} columns={[
          { title: 'Measure', dataIndex: 'label' },
          { title: 'Result · numerator/denominator', dataIndex: 'result' },
        ]} />
        <p><small>Review identity and independence are reviewer attestations; the application does not verify them. “Not measured” means evidence is insufficient, not a zero score.</small></p>
      </>}
    </Card>

    <Card title="B · Target-memory control: do scores separate known policies?" extra={<a href="/experiments">Open experiment groups →</a>} style={{ marginBottom: 20 }}>
      {states.memory === 'loading' && <Skeleton active paragraph={{ rows: 3 }} />}
      {states.memory === 'error' && <Alert type="error" showIcon title="Experiment B could not be loaded" description={errors.memory} />}
      {states.memory === 'empty' && <Alert type="info" showIcon title="No saved formal Experiment B run was found" description="Exploratory memory-strategy comparisons remain available under Experiments; this summary only treats runs declared as formal B as proposal evidence." />}
      {formalSummary && formalRun && <>
        <p>Target-memory results, not Auditor accuracy. {formalSummary.planned_histories} planned histories · {formalSummary.repetitions_per_condition} repeats per setting · {formalRun.has_frozen_criteria ? 'frozen criteria recorded' : 'frozen criteria not verified'}.</p>
        <Table rowKey="key" pagination={false} dataSource={formalRows} columns={[
          { title: 'Target setting', dataIndex: 'setting' },
          { title: 'Overall memory health', dataIndex: 'score' },
          { title: 'Coverage', dataIndex: 'measured' },
          { title: 'Runs / uncertainty', dataIndex: 'repeats' },
        ]} />
        {dimensionRows.length > 0 && <>
          <h3>Scores by memory dimension</h3>
          <Table rowKey="key" size="small" pagination={false} dataSource={dimensionRows} columns={[
            { title: 'Setting', dataIndex: 'setting' },
            { title: 'Dimension', dataIndex: 'dimension' },
            { title: 'Score', dataIndex: 'score' },
            { title: 'History coverage', dataIndex: 'coverage' },
            { title: 'Uncertain runs', dataIndex: 'uncertain' },
          ]} />
        </>}
        <p><small>{formalSummary.notice}</small></p>
      </>}
    </Card>

    <Card title="C · Does LongMemEval give the same retrieval-strategy ordering?" extra={<a href="/expanded-c">Open expanded C details →</a>} style={{ marginBottom: 20 }}>
      <p><a href="/four-strategy-comparison">Open the separate four-strategy v7 supplement →</a></p>
      {states.benchmark === 'loading' && <Skeleton active paragraph={{ rows: 3 }} />}
      {states.benchmark === 'error' && <Alert type="error" showIcon title="Experiment C could not be loaded" description={errors.benchmark} />}
      {states.benchmark === 'empty' && <Alert type="info" showIcon title="No published Experiment C summary was found" description="The expanded C report will appear here when its aggregate evidence file is available." />}
      {expandedC && <>
        <Alert type="warning" showIcon title="Local benchmark-compatible comparison" description="These are target-memory results from selected cases, not Auditor accuracy or a full official benchmark result." />
        <Table rowKey="key" pagination={false} dataSource={cRows} columns={[
          { title: 'Case set', dataIndex: 'label' },
          { title: 'Coverage', dataIndex: 'cases' },
          { title: 'First-match retrieval', dataIndex: 'weak' },
          { title: 'Relationship-priority retrieval', dataIndex: 'strong' },
          { title: 'Within-set result', dataIndex: 'winner' },
        ]} scroll={{ x: 760 }} />
        <p>{expandedC.extension_v6?.repetitions ?? expandedC.baseline_v5.repetitions ?? 3} repeats per set · v6 human review: {expandedC.extension_v6?.human_review?.status ?? 'not recorded'} · Relationship-priority led in {expandedC.decision?.repeat_wins ?? 'not recorded'}/3 repeats.</p>
        {expandedC.limitations?.length ? <details><summary>Coverage and limitations</summary><ul>{expandedC.limitations.map(item => <li key={item}>{item}</li>)}</ul></details> : null}
      </>}
    </Card>

    <FourStrategyComparisonSection />

    <details style={{ marginTop: 18 }}><summary>Research limitations and review status</summary>
      <p>Automated assessments do not establish independent human agreement. Check each section’s denominators, frozen source/protocol records and pending review status before making a general claim.</p>
      <p><a href="/quality">Review Auditor labels and provenance →</a> · <a href="/history">Open audit history →</a></p>
    </details>
  </Page>;
}
