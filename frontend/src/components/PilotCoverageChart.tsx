import { useId } from 'react';
import type { PilotAgreementMetrics, PilotTask } from '../types/domain';

const tasks: { key: PilotTask; label: string; lines: string[] }[] = [
  { key: 'memory_inclusion', label: 'Memory review', lines: ['Memory', 'review'] },
  { key: 'relationship_type', label: 'Relationships', lines: ['Relationships'] },
  { key: 'test_validity', label: 'Question validity', lines: ['Question', 'validity'] },
  { key: 'evaluator_verdict', label: 'Answer decisions', lines: ['Answer', 'decisions'] },
  { key: 'failure_dimension', label: 'Failure categories', lines: ['Failure', 'categories'] },
];
const series = [
  { key: 'annotator_a_labelled', label: 'Reviewer 1', colour: '#087ea4' },
  { key: 'annotator_b_labelled', label: 'Reviewer 2', colour: '#16806a' },
  { key: 'adjudicated_items', label: 'Reference decisions', colour: '#b7791f' },
] as const;

/** Review completion only; coverage is not assessment accuracy or model health. */
export function PilotCoverageChart({ metrics }: { metrics: PilotAgreementMetrics[] }) {
  const titleId = useId();
  const descriptionId = useId();
  const rows = tasks.map(task => ({ ...task, metric: metrics.find(metric => metric.task === task.key) }));
  const valueLabel = (row: typeof rows[number], key: typeof series[number]['key']) => {
    const metric = row.metric;
    return metric && metric.declared_items > 0
      ? `${metric[key]} / ${metric.declared_items} (${Math.round(metric[key] / metric.declared_items * 100)}%)`
      : 'No items declared';
  };
  return <figure className="research-validity-chart">
    <div className="reliability-legend">{series.map(item => <span key={item.key}><i style={{ background: item.colour }} />{item.label}</span>)}</div>
    <div style={{ overflowX: 'auto' }} tabIndex={0} role="region" aria-label="Scrollable review coverage chart">
      <svg viewBox="0 0 880 355" style={{ width: '100%', minWidth: 720 }} role="img" aria-labelledby={`${titleId} ${descriptionId}`}>
        <title id={titleId}>Review completion by task</title>
        <desc id={descriptionId}>{rows.map(row => `${row.label}: ${series.map(item => `${item.label} ${valueLabel(row, item.key)}`).join(', ')}.`).join(' ')}</desc>
        {[0, 25, 50, 75, 100].map(value => <g key={value}><line x1={55} x2={865} y1={265 - value * 2.1} y2={265 - value * 2.1} stroke="#dbe4ea" /><text x={45} y={270 - value * 2.1} textAnchor="end" fontSize={12} fill="#536b7e">{value}%</text></g>)}
        {rows.map((row, index) => {
          const centre = 140 + index * 160;
          const metric = row.metric;
          return <g key={row.key}>
            {metric && metric.declared_items > 0 ? series.map((item, offset) => {
              const value = metric[item.key] / metric.declared_items * 100;
              const x = centre - 51 + offset * 35;
              return <g key={item.key}><title>{row.label} · {item.label}: {valueLabel(row, item.key)}</title><rect x={x} y={265 - value * 2.1} width={28} height={value * 2.1} rx={3} fill={item.colour} /><text x={x + 14} y={255 - value * 2.1} textAnchor="middle" fontSize={11} fill="#23475e">{Math.round(value)}%</text></g>;
            }) : <text x={centre} y={250} textAnchor="middle" fontSize={12} fill="#536b7e">No items</text>}
            <text x={centre} y={290} textAnchor="middle" fontSize={13} fill="#23475e">{row.lines.map((line, i) => <tspan key={line} x={centre} dy={i ? 16 : 0}>{line}</tspan>)}</text>
            <text x={centre} y={335} textAnchor="middle" fontSize={12} fill="#536b7e">{metric && metric.declared_items > 0 ? `${metric.declared_items} items` : 'Not measured'}</text>
          </g>;
        })}
      </svg>
    </div>
    <figcaption>Completion of declared items, not accuracy. Full coverage does not prove independent review. Scroll to compare tasks; exact counts and agreement are available below.</figcaption>
  </figure>;
}
