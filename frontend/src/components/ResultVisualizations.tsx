import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ErrorBar,
  LabelList,
  Legend,
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

function dimensionScore(result: AuditResult, dimension: Dimension) {
  return result.dimensions.find((item) => item.dimension === dimension)?.percentage ?? null;
}

/** A Recharts profile of one audit condition, with the exact values in its caption. */
export function ScoreRadarChart({ result }: { result: AuditResult }) {
  const chartData = dimensions.map(({ key, label }) => ({
    dimension: label,
    score: dimensionScore(result, key) ?? 0,
    tested: dimensionScore(result, key) !== null,
  }));
  const summary = chartData.map(({ dimension, score, tested }) => `${dimension}: ${tested ? percentage(score) : 'Not tested'}`).join('; ');
  const captionId = `radar-caption-${result.run_id}`;

  return <section className="visual-report-card radar-card" aria-label="Memory Health profile">
    <div><h2>Memory Health Profile</h2><p>The four dimensions make strengths and weak spots visible at a glance.</p></div>
    <figure aria-label={`Memory Health profile. ${summary}`} aria-describedby={captionId}>
      <div className="radar-chart" role="img" aria-label={`Radar chart: ${summary}`}>
        <ResponsiveContainer width="100%" height={320}>
          <RadarChart data={chartData} outerRadius="68%" margin={{ top: 22, right: 24, bottom: 22, left: 24 }}>
            <PolarGrid stroke="#c7d6e4" />
            <PolarAngleAxis dataKey="dimension" tick={{ fill: '#34495e', fontSize: 12 }} />
            <PolarRadiusAxis angle={90} domain={[0, 100]} tickCount={5} tick={{ fill: '#63788a', fontSize: 11 }} />
            <Radar name="Memory Health" dataKey="score" stroke="#087ea4" fill="#087ea4" fillOpacity={0.3} />
            <Tooltip formatter={(value) => percentage(typeof value === 'number' ? value : Number(value))} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <figcaption id={captionId}>{summary}</figcaption>
    </figure>
  </section>;
}

function OverallBarChart({ runs }: { runs: ExperimentStatisticsRun[] }) {
  const groups = calculateExperimentStatistics(runs)
    .filter((group) => group.overallAverage !== null)
    .map((group, index) => ({
      condition: group.label,
      overall: group.overallAverage ?? 0,
      standardDeviation: group.overallStandardDeviation ?? 0,
      colour: colours[index % colours.length],
      runs: group.runs,
    }));
  const captionId = 'overall-comparison-caption';
  const summary = groups.map((group) => `${group.condition}: ${percentage(group.overall)}${group.runs > 1 ? ` (± ${number(group.standardDeviation)}%)` : ''}`).join('; ');

  return <article className="visual-report-card">
    <h2>Overall Memory Health by Condition</h2><p>Higher is better. Whiskers show ± one standard deviation when a condition was repeated.</p>
    <figure className="wide-chart" aria-label={`Overall Memory Health comparison. ${summary}`} aria-describedby={captionId}>
      <div role="img" aria-label={`Horizontal bar chart. ${summary}`}>
        <ResponsiveContainer width="100%" height={Math.max(220, groups.length * 58 + 72)}>
          <BarChart data={groups} layout="vertical" margin={{ top: 12, right: 70, bottom: 12, left: 18 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#d8e2ea" horizontal={false} />
            <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fill: '#63788a', fontSize: 12 }} />
            <YAxis type="category" dataKey="condition" width={150} tick={{ fill: '#34495e', fontSize: 12 }} />
            <Tooltip formatter={(value, _name, item) => {
              const deviation = Number(item.payload?.standardDeviation ?? 0);
              return [`${percentage(Number(value))}${deviation > 0 ? ` (± ${number(deviation)}%)` : ''}`, 'Overall score'];
            }} />
            <Bar dataKey="overall" name="Overall score" radius={[0, 5, 5, 0]}>
              {groups.map((group) => <Cell key={group.condition} fill={group.colour} />)}
              <ErrorBar dataKey="standardDeviation" direction="x" width={5} stroke="#283b4c" />
              <LabelList dataKey="overall" position="right" formatter={(value) => percentage(Number(value))} fill="#34495e" fontSize={12} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption id={captionId}>Conditions are grouped by the same model and memory strategy. Untested scores are excluded.</figcaption>
    </figure>
  </article>;
}

function DimensionBarChart({ runs }: { runs: ExperimentStatisticsRun[] }) {
  const groups = calculateExperimentStatistics(runs);
  const chartData = dimensions.map((dimension) => {
    const row: Record<string, string | number | null> = { dimension: dimension.label };
    groups.forEach((group) => {
      row[group.label] = group.dimensions.find((item) => item.dimension === dimension.key)?.average ?? null;
    });
    return row;
  });
  const captionId = 'dimension-comparison-caption';
  const summary = chartData.map((row) => `${row.dimension}: ${groups.map((group) => `${group.label} ${percentage(row[group.label] as number | null)}`).join(', ')}`).join('; ');

  return <article className="visual-report-card">
    <h2>Dimension Comparison</h2><p>Compare where each condition retrieves, updates, resolves and uses memory well.</p>
    <figure className="wide-chart" aria-label={`Dimension comparison. ${summary}`} aria-describedby={captionId}>
      <div role="img" aria-label={`Grouped bar chart. ${summary}`}>
        <ResponsiveContainer width="100%" height={350}>
          <BarChart data={chartData} margin={{ top: 24, right: 18, bottom: 10, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#d8e2ea" vertical={false} />
            <XAxis dataKey="dimension" tick={{ fill: '#34495e', fontSize: 12 }} />
            <YAxis domain={[0, 100]} unit="%" tick={{ fill: '#63788a', fontSize: 12 }} />
            <Tooltip formatter={(value) => percentage(value === null ? null : Number(value))} />
            <Legend />
            {groups.map((group, index) => <Bar key={group.label} dataKey={group.label} name={group.label} fill={colours[index % colours.length]} radius={[4, 4, 0, 0]} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption id={captionId}>Scores are percentages. A missing bar means that dimension was not tested for that condition.</figcaption>
    </figure>
  </article>;
}

function FailureDistributionChart({ runs }: { runs: ExperimentStatisticsRun[] }) {
  const groups = calculateExperimentStatistics(runs);
  const chartData = dimensions.map((dimension) => {
    const row: Record<string, string | number> = { dimension: dimension.label };
    groups.forEach((group) => {
      row[group.label] = group.dimensions.find((item) => item.dimension === dimension.key)?.failures ?? 0;
    });
    return row;
  });
  const captionId = 'failure-distribution-caption';
  const summary = chartData.map((row) => `${row.dimension}: ${groups.map((group) => `${group.label} ${row[group.label]}`).join(', ')}`).join('; ');

  return <article className="visual-report-card">
    <h2>Detected Failure Distribution</h2><p>Lower is better. This reveals the dimension creating the most memory-risk evidence.</p>
    <figure className="wide-chart" aria-label={`Detected failure distribution. ${summary}`} aria-describedby={captionId}>
      <div role="img" aria-label={`Grouped failure bar chart. ${summary}`}>
        <ResponsiveContainer width="100%" height={350}>
          <BarChart data={chartData} margin={{ top: 24, right: 18, bottom: 10, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#d8e2ea" vertical={false} />
            <XAxis dataKey="dimension" tick={{ fill: '#34495e', fontSize: 12 }} />
            <YAxis allowDecimals={false} tick={{ fill: '#63788a', fontSize: 12 }} />
            <Tooltip formatter={(value) => `${number(Number(value))} failures`} />
            <Legend />
            {groups.map((group, index) => <Bar key={group.label} dataKey={group.label} name={group.label} fill={colours[index % colours.length]} radius={[4, 4, 0, 0]} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption id={captionId}>Failure counts aggregate all completed runs in each condition; more repeated runs can increase the count.</figcaption>
    </figure>
  </article>;
}

/** Visual companion to the tables: values remain available in the tables beneath each chart. */
export function ComparisonVisualizations({ runs }: { runs: ExperimentStatisticsRun[] }) {
  if (!runs.length) return null;
  return <section className="comparison-visualizations" aria-label="Visual comparison charts">
    <div className="visual-heading"><h2>Visual Comparison</h2><p>All conditions use the shared ground truth and frozen test suite, so differences can be compared directly.</p></div>
    <div className="visual-grid"><OverallBarChart runs={runs} /><DimensionBarChart runs={runs} /><FailureDistributionChart runs={runs} /></div>
  </section>;
}
