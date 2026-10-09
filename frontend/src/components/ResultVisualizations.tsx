import { UICard, UIAlert } from './ui';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ErrorBar,
  LabelList,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useId } from 'react';
import type { AuditResult, Dimension } from '../types/domain';
import { calculateExperimentStatistics, type ExperimentStatisticsRun } from './ExperimentStatistics';

type DimensionDefinition = { key: Dimension; label: string };

const dimensions: DimensionDefinition[] = [
  { key: 'accuracy', label: 'Accuracy' },
  { key: 'freshness', label: 'Freshness' },
  { key: 'conflict_resolution', label: 'Conflict Resolution' },
  { key: 'appropriate_use', label: 'Appropriate Use' },
];

const colours = ['#087ea4', '#16806a', '#b7791f', '#7952b3', '#b94848', '#3566a9'];

function percentage(value: number | null | undefined) {
  return value === null || value === undefined
    ? 'Not tested'
    : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

function number(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

/**
 * Keep plot axes and legends readable when a condition includes a provider and
 * a dotted model identifier. Full provenance remains in the accessible chart
 * summary and the condition table. If two labels end in the same strategy,
 * retain the full label to avoid a misleading legend collision.
 */
function displayConditionLabels(groups: Array<{ label: string }>) {
  const shortLabels = groups.map((group) => {
    const parts = group.label.split(' · ');
    return parts[parts.length - 1]?.trim() || group.label;
  });
  const counts = new Map<string, number>();
  shortLabels.forEach((label) => counts.set(label, (counts.get(label) ?? 0) + 1));
  const candidates = groups.map((group, index) => {
    if (counts.get(shortLabels[index]) === 1) return shortLabels[index];
    const parts = group.label.split(' · ');
    return parts.length >= 3 ? parts.slice(-2).join(' · ') : group.label;
  });
  return candidates.map((label, index) => candidates.filter((item) => item === label).length === 1 ? label : groups[index].label);
}

function dimensionScore(result: AuditResult, dimension: Dimension) {
  return result.dimensions.find((item) => item.dimension === dimension)?.percentage ?? null;
}

type MetricSeries = {
  key: string;
  label: string;
  displayLabel: string;
  colour: string;
};

/**
 * A responsive grouped bar view built from ordinary HTML instead of a
 * chart-library categorical layout. Recharts is retained for the radar and
 * single-series comparison charts, but its grouped categorical bars can
 * calculate incorrect rectangle geometry in some browser/layout combinations.
 */
function GroupedMetricRows({
  chartData,
  series,
  maximum,
  formatValue,
}: {
  chartData: Array<Record<string, string | number | null>>;
  series: MetricSeries[];
  maximum: number;
  formatValue: (value: number | null, row: Record<string, string | number | null>, series: MetricSeries) => string;
}) {
  return <div className="metric-chart-rows">
    {chartData.map((row) => <section className="metric-chart-row" key={String(row.dimension)}>
      <h3>{row.dimension}</h3>
      <div className="metric-chart-bars">
        {series.map((item) => {
          const rawValue = row[item.key];
          const value = typeof rawValue === 'number' ? rawValue : null;
          const width = value === null ? 0 : Math.max(0, Math.min(100, (value / maximum) * 100));
          return <div className="metric-bar-entry" key={item.key} title={item.label}>
            <div className="metric-bar-meta">
              <span><i aria-hidden="true" style={{ backgroundColor: item.colour }} />{item.displayLabel}</span>
              <strong>{formatValue(value, row, item)}</strong>
            </div>
            <div className="metric-bar-track" aria-hidden="true">
              <span className="metric-bar-fill" style={{ width: `${width}%`, backgroundColor: item.colour }} />
            </div>
          </div>;
        })}
      </div>
    </section>)}
  </div>;
}

/** A Recharts profile of one audit condition, with the exact values in its caption. */
export function ScoreRadarChart({ result }: { result: AuditResult }) {
  const chartData = dimensions.map(({ key, label }) => ({
    dimension: label,
    score: dimensionScore(result, key),
    tested: dimensionScore(result, key) !== null,
    uncertain: (result.dimensions.find(dimension => dimension.dimension === key)?.uncertain_count ?? 0) > 0,
  }));
  const summary = chartData.map(({ dimension, score, tested, uncertain }) => `${dimension}: ${tested ? percentage(score) : uncertain ? 'Awaiting review' : 'Not tested'}`).join('; ');
  const captionId = `radar-caption-${result.run_id}`;

  return <section className="visual-report-card radar-card" aria-label="Memory Health profile">
    <div><h2>Memory Health Profile</h2></div>
    <figure aria-label={`Memory Health profile. ${summary}`} aria-describedby={captionId}>
      <div className="radar-chart" role="img" aria-label={`Radar chart: ${summary}`}>
        <ResponsiveContainer width="100%" height={320}>
          <RadarChart data={chartData} outerRadius="68%" margin={{ top: 22, right: 24, bottom: 22, left: 24 }}>
            <PolarGrid stroke="#c7d6e4" />
            <PolarAngleAxis dataKey="dimension" tick={{ fill: '#34495e', fontSize: 12 }} />
            <PolarRadiusAxis angle={90} domain={[0, 100]} tickCount={5} tick={{ fill: '#63788a', fontSize: 11 }} />
            <Radar name="Memory Health" dataKey="score" connectNulls={false} stroke="#087ea4" fill="#087ea4" fillOpacity={0.3} />
            <Tooltip formatter={(value) => value == null ? 'Not scored' : percentage(typeof value === 'number' ? value : Number(value))} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <figcaption id={captionId}>{summary}</figcaption>
    </figure>
  </section>;
}

function OverallBarChart({ runs, captionId }: { runs: ExperimentStatisticsRun[]; captionId: string }) {
  const rawGroups = calculateExperimentStatistics(runs);
  const displayLabels = displayConditionLabels(rawGroups);
  const groups = rawGroups.map((group, index) => ({
      condition: displayLabels[index],
      fullCondition: group.label,
      overall: group.overallAverage ?? 0,
      standardDeviation: group.overallStandardDeviation ?? 0,
      colour: colours[index % colours.length],
      runs: group.runs,
      decided: group.testsTotal,
      pending: group.uncertainCount,
    })).filter((group, index) => rawGroups[index].overallAverage !== null);
  const summary = groups.map((group) => `${group.fullCondition}: ${percentage(group.overall)}${group.pending ? ` · ${group.decided} decided, ${group.pending} awaiting review` : ''}${group.runs > 1 ? ` (± ${number(group.standardDeviation)}%)` : ''}`).join('; ');

  return <UICard className="visual-report-card">
    <h2>Tested Ability Average by Condition</h2>
    <figure className="wide-chart" aria-label={`Tested ability average comparison. ${summary}`} aria-describedby={captionId}>
      <div role="img" aria-label={`Horizontal bar chart. ${summary}`}>
        <ResponsiveContainer width="100%" height={Math.max(220, groups.length * 58 + 72)}>
          <BarChart data={groups} layout="vertical" margin={{ top: 12, right: 70, bottom: 12, left: 18 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#d8e2ea" horizontal={false} />
            <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fill: '#63788a', fontSize: 12 }} />
            <YAxis type="category" dataKey="condition" width={210} tick={{ fill: '#34495e', fontSize: 12 }} />
            <Tooltip formatter={(value, _name, item) => {
              const deviation = Number(item.payload?.standardDeviation ?? 0);
              return [`${percentage(Number(value))}${deviation > 0 ? ` (± ${number(deviation)}%)` : ''}`, 'Tested ability average'];
            }} />
            <Bar dataKey="overall" name="Tested ability average" radius={[0, 5, 5, 0]}>
              {groups.map((group) => <Cell key={group.condition} fill={group.colour} />)}
              <ErrorBar dataKey="standardDeviation" direction="x" width={5} stroke="#283b4c" />
              <LabelList dataKey="overall" position="right" formatter={(value) => percentage(Number(value))} fill="#34495e" fontSize={12} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {groups.some(group=>group.pending>0)&&<ul className="chart-review-coverage">{groups.map(group=><li key={group.fullCondition}>{group.fullCondition}: {group.decided} / {group.decided + group.pending} answers decided · {group.pending} awaiting review</li>)}</ul>}
      <figcaption id={captionId}>Conditions are grouped by the same model and memory strategy. Untested abilities and uncertain judgments are excluded; differing coverage can change averages. A formal overall score requires all four abilities.</figcaption>
    </figure>
  </UICard>;
}

function DimensionBarChart({ runs, captionId }: { runs: ExperimentStatisticsRun[]; captionId: string }) {
  const groups = calculateExperimentStatistics(runs);
  // Recharts treats a dot in a string `dataKey` as a nested object path.
  // Provider/model labels commonly contain dots (for example qwen3:1.7b),
  // so never use a human-readable condition name as the data key.
  const displayLabels = displayConditionLabels(groups);
  const series: Array<MetricSeries & { group: (typeof groups)[number] }> = groups.map((group, index) => ({ key: `condition_${index}`, label: group.label, displayLabel: displayLabels[index], colour: colours[index % colours.length], group }));
  const chartData = dimensions.map((dimension) => {
    const row: Record<string, string | number | null> = { dimension: dimension.label };
    series.forEach((item) => {
      const score = item.group.dimensions.find((score) => score.dimension === dimension.key);
      row[item.key] = score?.average ?? null;
      row[item.key + '_pending'] = score?.uncertainCount ?? 0;
    });
    return row;
  });
  const statusValue = (value: number | null, row: Record<string, string | number | null>, item: MetricSeries) => value === null && Number(row[item.key + '_pending']) > 0 ? 'Awaiting review' : percentage(value);
  const summary = chartData.map((row) => `${row.dimension}: ${series.map((item) => `${item.label} ${statusValue(row[item.key] as number | null, row, item)}`).join(', ')}`).join('; ');

  return <UICard className="visual-report-card">
    <h2>Dimension Comparison</h2>
    <figure className="wide-chart" aria-label={`Dimension comparison. ${summary}`} aria-describedby={captionId}>
      <div role="img" aria-label={`Grouped bar chart. ${summary}`}>
        <GroupedMetricRows chartData={chartData} series={series} maximum={100} formatValue={statusValue} />
      </div>
      <figcaption id={captionId}>Scores are percentages. A missing bar has no definitive score. Awaiting review means answers were executed but judgment is pending.</figcaption>
    </figure>
  </UICard>;
}

function FailureDistributionChart({ runs, captionId }: { runs: ExperimentStatisticsRun[]; captionId: string }) {
  const groups = calculateExperimentStatistics(runs);
  const displayLabels = displayConditionLabels(groups);
  const series: Array<MetricSeries & { group: (typeof groups)[number] }> = groups.map((group, index) => ({ key: `condition_${index}`, label: group.label, displayLabel: displayLabels[index], colour: colours[index % colours.length], group }));
  const chartData = dimensions.map((dimension) => {
    const row: Record<string, string | number | null> = { dimension: dimension.label };
    series.forEach((item) => {
      row[item.key] = item.group.dimensions.find((score) => score.dimension === dimension.key)?.failures ?? null;
    });
    return row;
  });
  const summary = chartData.map((row) => `${row.dimension}: ${series.map((item) => `${item.label} ${row[item.key] === null ? 'not tested' : row[item.key]}`).join(', ')}`).join('; ');
  const maximum = Math.max(1, ...chartData.flatMap((row) => series.map((item) => typeof row[item.key] === 'number' ? row[item.key] as number : 0)));

  return <UICard className="visual-report-card">
    <h2>Detected Failure Distribution</h2>
    <figure className="wide-chart" aria-label={`Detected failure distribution. ${summary}`} aria-describedby={captionId}>
      <div role="img" aria-label={`Grouped failure bar chart. ${summary}`}>
        <GroupedMetricRows chartData={chartData} series={series} maximum={maximum} formatValue={(value) => value === null ? 'Not scored' : `${number(value)} failure${value === 1 ? '' : 's'}`} />
      </div>
      <figcaption id={captionId}>Failure counts aggregate all completed runs in each condition; more repeated runs can increase the count.</figcaption>
    </figure>
  </UICard>;
}

/** Visual companion to the tables: values remain available in the tables beneath each chart. */
export function ComparisonVisualizations({ runs }: { runs: ExperimentStatisticsRun[] }) {
  const idPrefix = useId().replace(/:/g, '');
  if (!runs.length) return null;
  const awaiting = runs.reduce((sum, run) => sum + (run.result.uncertain_count ?? 0), 0);
  return <section className="comparison-visualizations" aria-label="Visual comparison charts">
    <div className="visual-heading"><h2>Visual Comparison</h2>
    {awaiting > 0 && <UIAlert role="status"><b>{awaiting} answers await review</b><p>Charts include decided answers only. A 100% average or zero detected failures does not mean all executed answers passed.</p></UIAlert>}</div>
    <div className="visual-grid"><OverallBarChart runs={runs} captionId={`${idPrefix}-overall-caption`} /><DimensionBarChart runs={runs} captionId={`${idPrefix}-dimension-caption`} /><FailureDistributionChart runs={runs} captionId={`${idPrefix}-failure-caption`} /></div>
  </section>;
}
