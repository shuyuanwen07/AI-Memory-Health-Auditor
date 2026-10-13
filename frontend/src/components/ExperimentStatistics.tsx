import { UIPanel, UISummary, UITable } from './ui';
import type { AuditResult, Dimension } from '../types/domain';
import { failureCountLabel } from '../services/display';

export type ExperimentStatisticsRun = {
  colour?: string;
  /** A human-readable label for this individual audit execution. */
  label: string;
  /** Runs with the same group label are treated as repeated experimental conditions. */
  groupLabel?: string;
  /** Stable condition identity; display names alone may be reused for different settings. */
  groupKey?: string;
  result: AuditResult;
};

type DimensionDefinition = { key: Dimension; label: string };

const dimensions: DimensionDefinition[] = [
  { key: 'accuracy', label: 'Accuracy' },
  { key: 'freshness', label: 'Freshness' },
  { key: 'conflict_resolution', label: 'Conflict Resolution' },
  { key: 'appropriate_use', label: 'Appropriate Use' },
];

export type DimensionAggregate = {
  dimension: Dimension;
  label: string;
  average: number | null;
  passed: number;
  total: number;
  measuredRuns: number;
  failures: number;
  uncertainCount: number;
  excludedCount?: number;
};

export type ExperimentGroupStatistics = {
  colour?: string;
  label: string;
  runs: number;
  overallMeasuredRuns: number;
  overallAverage: number | null;
  overallStandardDeviation: number | null;
  testsPassed: number;
  testsTotal: number;
  uncertainCount: number;
  unassessedCount: number;
  excludedEvidenceCount: number;
  failureCount: number;
  measuredDimensionRuns: number;
  totalDimensionRuns: number;
  dimensions: DimensionAggregate[];
};

function average(values: number[]) {
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

/** Population standard deviation is sufficient for a compact repeated-run summary. */
function standardDeviation(values: number[]) {
  const mean = average(values);
  if (mean === null || values.length < 2) return null;
  return Math.sqrt(values.reduce((sum, value) => sum + ((value - mean) ** 2), 0) / values.length);
}

function resultDimension(result: AuditResult, dimension: Dimension) {
  return result.dimensions.find((item) => item.dimension === dimension);
}

/**
 * Aggregates completed audits by condition label. Missing/untested dimensions are
 * deliberately excluded from averages so they cannot silently become zero scores.
 */
export function calculateExperimentStatistics(runs: ExperimentStatisticsRun[]): ExperimentGroupStatistics[] {
  const groups = new Map<string, ExperimentStatisticsRun[]>();
  runs.forEach((run) => {
    const label = run.groupLabel?.trim() || run.label;
    const key = JSON.stringify([run.groupKey ? 'condition' : 'label', run.groupKey || label]);
    groups.set(key, [...(groups.get(key) ?? []), run]);
  });

  const labels = [...groups.values()].map(group => group[0].groupLabel?.trim() || group[0].label);
  return [...groups.values()].map((groupRuns, index) => {
    const originalLabel = labels[index];
    const label = labels.filter(item => item === originalLabel).length > 1
      ? `${originalLabel} · Setting ${index + 1}` : originalLabel;
    const overallScores = groupRuns.flatMap((run) => run.result.overall_score === null ? [] : [run.result.overall_score]);
    const dimensionTotals = dimensions.map(({ key, label: dimensionLabel }) => {
      const measured = groupRuns.flatMap((run) => {
        const score = resultDimension(run.result, key);
        return score?.percentage === null || score?.percentage === undefined ? [] : [score];
      });
      const failures = groupRuns.reduce((count, run) => count + run.result.failures.filter((failure) =>
        failure.test.dimension === key,
      ).length, 0);
      return {
        dimension: key,
        label: dimensionLabel,
        average: average(measured.map((item) => item.percentage as number)),
        passed: measured.reduce((sum, item) => sum + item.passed, 0),
        total: measured.reduce((sum, item) => sum + item.total, 0),
        measuredRuns: measured.length,
        failures,
        excludedCount: groupRuns.reduce((sum,run)=>sum+(resultDimension(run.result,key)?.excluded_evidence_count??0),0),
        uncertainCount: groupRuns.reduce((sum, run) => sum + (resultDimension(run.result, key)?.uncertain_count ?? 0), 0),
      };
    });

    return {
      label,
      colour:groupRuns[0].colour&&/^#[0-9a-f]{6}$/i.test(groupRuns[0].colour)&&groupRuns.every(run=>run.colour===groupRuns[0].colour)?groupRuns[0].colour:undefined,
      runs: groupRuns.length,
      overallMeasuredRuns: overallScores.length,
      overallAverage: average(overallScores),
      overallStandardDeviation: standardDeviation(overallScores),
      testsPassed: groupRuns.reduce((sum, run) => sum + run.result.tests_passed, 0),
      testsTotal: groupRuns.reduce((sum, run) => sum + run.result.tests_total, 0),
      uncertainCount: groupRuns.reduce((sum, run) => sum + (run.result.uncertain_count ?? 0), 0),
      unassessedCount: groupRuns.reduce((sum, run) => sum + (run.result.answers?.filter(answer => answer.outcome === 'unassessed').length ?? 0), 0),
      excludedEvidenceCount: groupRuns.reduce((sum, run) => sum + (run.result.excluded_evidence_count ?? 0), 0),
      failureCount: groupRuns.reduce((sum, run) => sum + run.result.failures.length, 0),
      measuredDimensionRuns: dimensionTotals.reduce((sum, item) => sum + item.measuredRuns, 0),
      totalDimensionRuns: groupRuns.length * dimensions.length,
      dimensions: dimensionTotals,
    };
  });
}

function percentage(value: number | null) {
  return value === null ? 'Not scored' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

function GroupDetail({ group }: { group: ExperimentGroupStatistics }) {
  const repeatRunMessage = group.runs < 2
    ? 'Repeat-run statistics are not available yet. Run this condition at least twice to assess variation.'
    : `Based on ${group.runs} repeated runs. Tested ability standard deviation: ${percentage(group.overallStandardDeviation)}.`;

  return <UIPanel className="experiment-group-detail">
    <UISummary>{group.label}: dimension averages and failures</UISummary>
    <p className="repeat-note">{repeatRunMessage}</p>
    <div className="comparison-scroll"><UITable>
      <thead><tr><th>Dimension</th><th>Average score</th><th>Passed tests</th><th>Measured runs</th><th>Failures</th></tr></thead>
      <tbody>{group.dimensions.map((dimension) => <tr key={dimension.dimension}>
        <th scope="row">{dimension.label}</th>
        <td>{dimension.average === null ? (dimension.excludedCount??0)>0?'Evidence unavailable':dimension.uncertainCount > 0 ? 'Awaiting review' : 'Not tested' : percentage(dimension.average)}{dimension.uncertainCount > 0 && <small> · {dimension.uncertainCount} awaiting review</small>}</td>
        <td>{dimension.total > 0 ? `${dimension.passed} / ${dimension.total}` : (dimension.excludedCount??0)>0?'Evidence unavailable':dimension.uncertainCount > 0 ? 'Awaiting review' : 'Not tested'}</td>
        <td>{dimension.measuredRuns} / {group.runs}</td>
        <td>{dimension.total===0&&(dimension.excludedCount??0)>0?'Evidence unavailable':failureCountLabel(dimension.total > 0 ? dimension.failures : null, dimension.uncertainCount)}</td>
      </tr>)}</tbody>
    </UITable></div>
    {group.failureCount === 0 && <p className="empty">{group.testsTotal > 0 ? 'No failures were detected among decided answers.' : 'No decided answers yet.'}{group.uncertainCount > 0 && ` ${group.uncertainCount} answers still await review.`}</p>}
  </UIPanel>;
}

/** A reusable research view for fair comparisons and repeated-run summaries. */
export function ExperimentStatistics({ runs }: { runs: ExperimentStatisticsRun[] }) {
  const groups = calculateExperimentStatistics(runs);
  if (!groups.length) return <section className="experiment-statistics" aria-label="Experiment statistics"><h2>Research Comparison</h2><p className="empty">No completed audit results are available for statistical comparison.</p></section>;

  const hasRepeatedCondition = groups.some((group) => group.runs >= 2);
  return <section className="experiment-statistics" aria-label="Experiment statistics">
    <h2>Research Comparison</h2>
    <p>Completed runs are grouped by experimental condition. Untested dimensions and uncertain judgments are excluded from score averages. Compare coverage alongside averages; a formal overall score requires all four dimensions.</p>
    {!hasRepeatedCondition && <p className="statistics-warning" role="status">Repeat-run statistics are not available yet. Complete at least two runs for the same condition to measure variation.</p>}
    <div className="comparison-scroll"><UITable>
      <thead><tr><th>Experimental condition</th><th>Runs</th><th>Tested ability average</th><th>Coverage</th><th>Passed / decided</th><th>Awaiting review</th><th>Failures</th></tr></thead>
      <tbody>{groups.map((group) => <tr key={group.label}>
        <th scope="row">{group.label}</th>
        <td>{group.runs}</td>
        <td><b>{percentage(group.overallAverage)}</b></td>
        <td>{group.measuredDimensionRuns} / {group.totalDimensionRuns} dimension-runs</td>
        <td>{group.testsPassed} / {group.testsTotal}</td>
        <td>{group.uncertainCount} / {group.testsTotal + group.uncertainCount} answers</td>
        <td>{group.failureCount}</td>
      </tr>)}</tbody>
    </UITable></div>
    <div className="experiment-group-details">{groups.map((group) => <GroupDetail key={group.label} group={group} />)}</div>
  </section>;
}
