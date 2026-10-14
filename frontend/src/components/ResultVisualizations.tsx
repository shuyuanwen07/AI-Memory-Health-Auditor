import { UICard, UIAlert, UIPanel, UISummary } from './ui';
import { failureCountLabel } from '../services/display';
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
import { comparisonColours } from '../services/chartColours';
import type { AuditResult, Dimension } from '../types/domain';
import { calculateExperimentStatistics, type ExperimentStatisticsRun } from './ExperimentStatistics';

type DimensionDefinition = { key: Dimension; label: string };

const dimensions: DimensionDefinition[] = [
  { key: 'accuracy', label: 'Accuracy' },
  { key: 'freshness', label: 'Freshness' },
  { key: 'conflict_resolution', label: 'Conflict Resolution' },
  { key: 'appropriate_use', label: 'Appropriate Use' },
];

const colours = comparisonColours;

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
function RadarAxisLabel({x=0,y=0,textAnchor='middle',payload}: {x?:number;y?:number;textAnchor?:'start'|'middle'|'end';payload?:{value?:string}}) {
  const words=(payload?.value??'').split(' ');
  return <text x={x} y={y} textAnchor={textAnchor} fill="#34495e" fontSize={12}>
    {words.map((word,index)=><tspan key={index} x={x} dy={index===0?(words.length>1?-3:4):14}>{word}</tspan>)}
  </text>;
}

function conditionLabelLines(label: string) {
  return label.split(' · ').flatMap(part => {
    const lines: string[] = [];
    let line = '';
    for (const word of part.split(/\s+/)) {
      if (line && `${line} ${word}`.length > 28) {
        lines.push(line);
        line = word;
      } else line = line ? `${line} ${word}` : word;
    }
    if (line) lines.push(line);
    return lines;
  });
}

function ConditionAxisLabel({x=0,y=0,payload}: {x?:number;y?:number;payload?:{value?:string}}) {
  const lines = conditionLabelLines(payload?.value ?? '');
  return <text x={x} y={y} textAnchor="end" fill="#34495e" fontSize={12}>
    <title>{payload?.value}</title>
    {lines.map((line,index)=><tspan key={index} x={x} dy={index===0?4-(lines.length-1)*7:14}>{line}</tspan>)}
  </text>;
}

export function ScoreRadarChart({ result }: { result: AuditResult }) {
  const chartData = dimensions.map(({ key, label }) => ({
    dimension: label,
    score: dimensionScore(result, key),
    tested: dimensionScore(result, key) !== null,
    excluded: result.dimensions.find(dimension=>dimension.dimension===key)?.excluded_evidence_count??0,
    uncertain: (result.dimensions.find(dimension => dimension.dimension === key)?.uncertain_count ?? 0) > 0,
  }));
  const summary = chartData.map(({ dimension, score, tested, uncertain, excluded }) => `${dimension}: ${tested ? percentage(score) : excluded>0?'Evidence unavailable':uncertain ? 'Awaiting review' : 'Not tested'}${excluded>0?`, ${excluded} excluded for unavailable evidence`:''}`).join('; ');
  const captionId = `radar-caption-${result.run_id}`;

  return <section className="visual-report-card radar-card" aria-label="Memory Health profile">
    <div><h2>Memory Health Profile</h2></div>
    <figure aria-label={`Memory Health profile. ${summary}`} aria-describedby={captionId}>
      <div className="radar-chart" role="img" aria-label={`Radar chart: ${summary}`}>
        <ResponsiveContainer width="100%" height={320}>
          <RadarChart data={chartData} outerRadius="58%" margin={{ top: 22, right: 24, bottom: 22, left: 24 }}>
            <PolarGrid stroke="#c7d6e4" />
            <PolarAngleAxis dataKey="dimension" tick={<RadarAxisLabel/>} />
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
  const allGroups = rawGroups.map((group, index) => ({
      condition: displayLabels[index],
      fullCondition: group.label,
      overall: group.overallAverage,
      standardDeviation: group.overallStandardDeviation,
      colour: group.colour ?? colours[index % colours.length],
      runs: group.runs,
      scoredRuns: group.overallMeasuredRuns,
      decided: group.testsTotal,
      pending: group.uncertainCount,
      unassessed: group.unassessedCount,
      excluded: group.excludedEvidenceCount,
    }));
  const groups = allGroups.filter((group): group is typeof group & {overall: number} => group.overall !== null);
  const sampleSummary = (group: (typeof allGroups)[number]) => `n=${group.scoredRuns} scored run${group.scoredRuns === 1 ? '' : 's'}; ${group.decided} decided answer${group.decided === 1 ? '' : 's'}${group.pending ? `; ${group.pending} awaiting review` : ''}${group.unassessed ? `; ${group.unassessed} unassessed` : ''}${group.excluded ? `; ${group.excluded} evidence unavailable` : ''}`;
  const summary = allGroups.map((group) => `${group.fullCondition}: ${group.overall === null ? 'Not measured' : `${percentage(group.overall)} tested-ability average`} · ${sampleSummary(group)}${group.runs > 1 && group.standardDeviation === null ? ` · variation not measured (${group.scoredRuns} scored ${group.scoredRuns === 1 ? 'run' : 'runs'})` : group.standardDeviation !== null ? ` (± ${number(group.standardDeviation)} pp population SD)` : ''}`).join('; ');
  const rowHeight = Math.max(58, ...groups.map(group => conditionLabelLines(group.condition).length * 14 + 20));

  return <UICard className="visual-report-card">
    <h2>Tested Ability Average by Condition</h2>
    <figure className="wide-chart" aria-label={`Tested ability average comparison. ${summary}`} aria-describedby={captionId}>
      <div className="condition-score-chart" role="img" aria-label={`Horizontal bar chart. ${summary}`}>
        <ResponsiveContainer width="100%" height={Math.max(220, groups.length * rowHeight + 72)}>
          <BarChart data={groups} layout="vertical" margin={{ top: 12, right: 70, bottom: 12, left: 18 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#d8e2ea" horizontal={false} />
            <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fill: '#63788a', fontSize: 12 }} />
            <YAxis type="category" dataKey="condition" width={210} interval={0} tick={<ConditionAxisLabel/>} />
            <Tooltip formatter={(value, _name, item) => {
              const deviation = item.payload?.standardDeviation;
              const variation = item.payload?.runs > 1 ? typeof deviation === 'number' ? ` (± ${number(deviation)} pp population SD)` : ` · variation not measured (${item.payload?.scoredRuns} scored ${item.payload?.scoredRuns === 1 ? 'run' : 'runs'})` : '';
              const sample = ` · ${sampleSummary(item.payload)}`;
              return [`${percentage(Number(value))}${sample}${variation}`, 'Tested ability average'];
            }} />
            <Bar dataKey="overall" name="Tested ability average" radius={[0, 5, 5, 0]}>
              {groups.map((group) => <Cell key={group.condition} fill={group.colour} />)}
              <ErrorBar dataKey="standardDeviation" direction="x" width={5} stroke="#283b4c" />
              <LabelList dataKey="overall" position="right" formatter={(value) => percentage(Number(value))} fill="#34495e" fontSize={12} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="chart-review-coverage">{allGroups.map(group=><li key={group.fullCondition}>{group.fullCondition}: {group.overall === null ? 'Overall not measured · ' : ''}{sampleSummary(group)}{group.runs > 1 && group.standardDeviation === null ? ` · variation not measured (${group.scoredRuns} scored ${group.scoredRuns === 1 ? 'run' : 'runs'})` : ''}</li>)}</ul>
      <figcaption id={captionId}>Each bar is the mean tested-ability average across scored runs (0–100%). Error bars show population standard deviation across available run scores, in percentage points (pp), not a confidence interval. The chart lists the scored-run sample size and decided, pending, unassessed, or evidence-unavailable answer counts for each condition. Untested abilities and uncertain judgments are excluded; different coverage can change averages. An overall Memory Health score requires all four abilities.</figcaption>
    </figure>
  </UICard>;
}

function VerticalDimensionColumns({ chartData, series, formatValue }: {
  chartData: Array<Record<string, string | number | null>>;
  series: MetricSeries[];
  formatValue: (value: number | null, row: Record<string, string | number | null>, item: MetricSeries) => string;
}) {
  return <>
    <div className="chart-legend">{series.map(item => <span key={item.key} title={item.label}><i style={{backgroundColor:item.colour}} />{item.displayLabel}</span>)}</div>
    <div className="dimension-columns" style={{minWidth: Math.max(series.length === 1 ? 360 : 520, series.length * 150)}}>
      <div className="dimension-y-axis" aria-hidden="true">{[100,75,50,25,0].map(value => <span key={value} style={{bottom:`${value}%`}}>{value}%</span>)}</div>
      <div className="dimension-column-plot">
        <div className="dimension-grid-lines" aria-hidden="true">{[0,25,50,75,100].map(value => <span key={value} style={{bottom:`${value}%`}} />)}</div>
        {chartData.map(row => <div className="dimension-column-group" key={String(row.dimension)}>
          <div className="dimension-column-bars">{series.map(item => {
            const raw = row[item.key];
            const value = typeof raw === 'number' ? raw : null;
            const label = formatValue(value,row,item);
            return <div className="dimension-column-slot" key={item.key} title={`${row.dimension} · ${item.label}: ${label}`}>
              {value === null ? <span className="dimension-column-missing">{label}</span> : <div className="dimension-column" style={{height:`${Math.max(0,Math.min(100,value))}%`,backgroundColor:item.colour}}><strong>{label}</strong></div>}
            </div>;
          })}</div>
          <b className="dimension-column-label">{row.dimension}</b>
        </div>)}
      </div>
    </div>
  </>;
}

function DimensionBarChart({ runs, captionId, singleSetting = false }: { runs: ExperimentStatisticsRun[]; captionId: string; singleSetting?: boolean }) {
  const groups = calculateExperimentStatistics(runs);
  // Recharts treats a dot in a string `dataKey` as a nested object path.
  // Provider/model labels commonly contain dots (for example qwen3:1.7b),
  // so never use a human-readable condition name as the data key.
  const displayLabels = displayConditionLabels(groups);
  const series: Array<MetricSeries & { group: (typeof groups)[number] }> = groups.map((group, index) => ({ key: `condition_${index}`, label: group.label, displayLabel: displayLabels[index], colour: group.colour ?? colours[index % colours.length], group }));
  const chartData = dimensions.map((dimension) => {
    const row: Record<string, string | number | null> = { dimension: dimension.label };
    series.forEach((item) => {
      const score = item.group.dimensions.find((score) => score.dimension === dimension.key);
      row[item.key] = score?.average ?? null;
      row[item.key + '_pending'] = score?.uncertainCount ?? 0;
      row[item.key + '_excluded'] = score?.excludedCount??0;
      row[item.key + '_total'] = score?.total ?? 0;
      row[item.key + '_runs'] = score?.measuredRuns ?? 0;
    });
    return row;
  });
  const statusValue = (value: number | null, row: Record<string, string | number | null>, item: MetricSeries) => {
    const total = Number(row[item.key + '_total']);
    const measuredRuns = Number(row[item.key + '_runs']);
    if (value === null) {
      const status = Number(row[item.key + '_excluded']) > 0
        ? 'Evidence unavailable'
        : Number(row[item.key + '_pending']) > 0 ? 'Awaiting review' : 'Not tested';
      const pending = Number(row[item.key + '_pending']);
      return `${status} · n=${total} decided answer${total === 1 ? '' : 's'}${pending > 0 ? ` · ${pending} awaiting review` : ''}`;
    }
    return `${percentage(value)} average · n=${total} decided answer${total === 1 ? '' : 's'} · ${measuredRuns} measured run${measuredRuns === 1 ? '' : 's'}`;
  };
  const summary = chartData.map((row) => `${row.dimension}: ${series.map((item) => `${item.label} ${statusValue(row[item.key] as number | null, row, item)}`).join(', ')}`).join('; ');

  return <UICard className="visual-report-card">
    <h2>{singleSetting ? 'Results by dimension' : 'Dimension Comparison'}</h2>
    <figure className="wide-chart" aria-label={`${singleSetting ? 'Dimension results' : 'Dimension comparison'}. ${summary}`} aria-describedby={captionId}>
      <small className="validity-scroll-hint">Scroll horizontally if any dimension is out of view.</small>
      <div role="region" aria-label="Scrollable dimension chart" tabIndex={0} style={{overflowX:'auto'}}>
        <div role="img" aria-label={`Grouped bar chart. ${summary}`}>
          <VerticalDimensionColumns chartData={chartData} series={series} formatValue={statusValue} />
        </div>
      </div>
      <figcaption id={captionId}>Scores are percentages averaged across measured runs. Each label reports the decided answer count (n) and number of measured runs. A missing bar has no definitive score; awaiting review means judgment is pending.</figcaption>
    </figure>
  </UICard>;
}

function FailureDistributionChart({ runs, captionId }: { runs: ExperimentStatisticsRun[]; captionId: string }) {
  const groups = calculateExperimentStatistics(runs);
  const displayLabels = displayConditionLabels(groups);
  const series: Array<MetricSeries & { group: (typeof groups)[number] }> = groups.map((group, index) => ({ key: `condition_${index}`, label: group.label, displayLabel: displayLabels[index], colour: group.colour ?? colours[index % colours.length], group }));
  const chartData = dimensions.map((dimension) => {
    const row: Record<string, string | number | null> = { dimension: dimension.label };
    series.forEach((item) => {
      const score = item.group.dimensions.find((score) => score.dimension === dimension.key);
      row[item.key] = score && score.total > 0 ? score.failures : null;
      row[item.key + '_pending'] = score?.uncertainCount ?? 0;
      row[item.key + '_excluded'] = score?.excludedCount??0;
      row[item.key + '_total'] = score?.total ?? 0;
    });
    return row;
  });
  const statusValue = (value: number | null, row: Record<string, string | number | null>, item: MetricSeries) => {
    const total = Number(row[item.key + '_total']);
    const pending = Number(row[item.key + '_pending']);
    if (value === null) {
      const status = Number(row[item.key + '_excluded']) > 0
        ? 'Evidence unavailable'
        : failureCountLabel(null, pending);
      return `${status} · n=${total} decided answer${total === 1 ? '' : 's'}${pending > 0 ? ` · ${pending} awaiting review` : ''}`;
    }
    return `${failureCountLabel(value, pending)} · n=${total} decided answer${total === 1 ? '' : 's'}`;
  };
  const summary = chartData.map((row) => `${row.dimension}: ${series.map((item) => `${item.label} ${statusValue(typeof row[item.key] === 'number' ? row[item.key] as number : null, row, item)}`).join(', ')}`).join('; ');
  const maximum = Math.max(1, ...chartData.flatMap((row) => series.map((item) => typeof row[item.key] === 'number' ? row[item.key] as number : 0)));

  return <UICard className="visual-report-card">
    <h2>Failed Tests by Tested Ability</h2>
    <figure className="wide-chart" aria-label={`Detected failure distribution. ${summary}`} aria-describedby={captionId}>
      <div role="img" aria-label={`Grouped failure bar chart. ${summary}`}>
        <GroupedMetricRows chartData={chartData} series={series} maximum={maximum} formatValue={statusValue} />
      </div>
      <figcaption id={captionId}>Counts show which ability each failed question tested, not independently diagnosed error causes. Counts aggregate completed runs; more repeated runs can increase the count.</figcaption>
    </figure>
  </UICard>;
}

/** Visual companion to the tables: values remain available in the tables beneath each chart. */
export function ComparisonVisualizations({ runs, hideFailureChart = false, compact = false, singleSetting = false }: { runs: ExperimentStatisticsRun[]; hideFailureChart?: boolean; compact?: boolean; singleSetting?: boolean }) {
  const idPrefix = useId().replace(/:/g, '');
  if (!runs.length) return null;
  const scoredAbilities = new Set(runs.map(run=>run.result.dimensions
    .filter(dimension=>dimension.percentage!==null&&dimension.total>0)
    .map(dimension=>dimension.dimension).sort().join(',')));
  const coverageDiffers = scoredAbilities.size>1;
  const awaiting = runs.reduce((sum, run) => sum + (run.result.uncertain_count ?? 0), 0);
  return <section className="comparison-visualizations" aria-label={singleSetting ? 'Single-setting result charts' : 'Visual comparison charts'}>
    <div className="visual-heading"><h2>{singleSetting ? 'Single-setting results' : 'Visual Comparison'}</h2>
    {coverageDiffers&&<UIAlert role="status"><b>Different score coverage</b><p>These conditions have scores for different abilities, so their averages are not directly comparable. Compare matching dimensions and resolve uncertain answers before claiming an improvement.</p></UIAlert>}
    {awaiting > 0 && <UIAlert role="status"><b>{awaiting} answers await review</b><p>Charts include decided answers only. A 100% average or zero detected failures does not mean all executed answers passed.</p></UIAlert>}</div>
    {compact ? <><DimensionBarChart runs={runs} captionId={`${idPrefix}-dimension-caption`} singleSetting={singleSetting} /><UIPanel><UISummary>Average scores & failed-question counts</UISummary><div className="visual-grid"><OverallBarChart runs={runs} captionId={`${idPrefix}-overall-caption`} />{!hideFailureChart && <FailureDistributionChart runs={runs} captionId={`${idPrefix}-failure-caption`} />}</div></UIPanel></> : <div className="visual-grid"><OverallBarChart runs={runs} captionId={`${idPrefix}-overall-caption`} /><DimensionBarChart runs={runs} captionId={`${idPrefix}-dimension-caption`} singleSetting={singleSetting} />{!hideFailureChart && <FailureDistributionChart runs={runs} captionId={`${idPrefix}-failure-caption`} />}</div>}
  </section>;
}
