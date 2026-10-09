import { saveBlob } from '../services/download';
import { UIButton } from './ui';
import { useId, useRef, useState } from 'react';
import type { AuditComparison, Dimension } from '../types/domain';

const abilities: { key: Dimension; label: string; short: string }[] = [
  { key: 'accuracy', label: 'Accuracy', short: 'Accuracy' },
  { key: 'freshness', label: 'Freshness', short: 'Freshness' },
  { key: 'conflict_resolution', label: 'Conflict resolution', short: 'Conflict resolution' },
  { key: 'appropriate_use', label: 'Appropriate use', short: 'Appropriate use' },
];
const beforeColour = '#627eab';
const afterColour = '#138572';
const percentage = (value: number | null) => value === null ? 'Not scored' : `${Number(value.toFixed(1))}%`;
const difference = (value: number | null) => value === null ? 'No comparison' : `${value > 0 ? '+' : ''}${Number(value.toFixed(1))} pp`;

export function comparisonChartRows(data: AuditComparison, shared: boolean) {
  return abilities.map(ability => {
    const pairs = data.paired_tests.filter(test => test.dimension === ability.key);
    const left = data.before.result.dimensions.find(item => item.dimension === ability.key);
    const right = data.after.result.dimensions.find(item => item.dimension === ability.key);
    const beforeTotal = shared ? pairs.length : left?.total ?? 0;
    const afterTotal = shared ? pairs.length : right?.total ?? 0;
    const beforePassed = shared ? pairs.filter(test => test.before.passed).length : left?.passed ?? 0;
    const afterPassed = shared ? pairs.filter(test => test.after.passed).length : right?.passed ?? 0;
    const before = beforeTotal ? beforePassed / beforeTotal * 100 : null;
    const after = afterTotal ? afterPassed / afterTotal * 100 : null;
    return { ...ability, before, after, beforeTotal, afterTotal, beforePassed, afterPassed,
      delta: before === null || after === null || !shared ? null : after - before };
  });
}

/** Fixed percentage axis; missing observations are never plotted as zero. */
export function ComparisonVisualizations({ data }: { data: AuditComparison }) {
  const [shared, setShared] = useState(true);
  const svg = useRef<SVGSVGElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const rows = comparisonChartRows(data, shared);
  const available = rows.some(row => row.before !== null || row.after !== null);
  const exportChart = () => {
    if (!svg.current) return;
    const content = new XMLSerializer().serializeToString(svg.current);
    saveBlob(new Blob([content], { type: 'image/svg+xml;charset=utf-8' }), 'memory-before-after.svg');
  };
  return <section className="comparison-visuals" aria-label="Memory improvement charts">
    <div className="comparison-chart-heading"><div><p className="eyebrow">MEMORY ABILITIES</p><h2>Before and after, side by side</h2>
      <p>Compare each ability on the same 0–100% scale.</p></div>
      <div className="comparison-chart-controls" aria-label="Chart question scope">
        <UIButton type="button" className={`secondary ${shared ? 'selected' : ''}`} aria-pressed={shared} onClick={() => setShared(true)}>Shared questions</UIButton>
        <UIButton type="button" className={`secondary ${!shared ? 'selected' : ''}`} aria-pressed={!shared} onClick={() => setShared(false)}>Full test suites</UIButton>
      </div></div>
    {!shared && <p className="trace-note">Full suites can contain different questions or assessment standards. These historical scores are descriptive only. Use comparable shared questions to assess changes.</p>}
    {available ? <figure className="comparison-chart-figure">
      <div className="comparison-chart-scroll"><svg ref={svg} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 420" fontFamily="Arial, sans-serif" role="img" aria-labelledby={`${titleId} ${descriptionId}`}>
        <title id={titleId}>Memory ability pass rates before and after improvement</title>
        <desc id={descriptionId}>{rows.map(row => `${row.label}: before ${percentage(row.before)} (${row.beforePassed}/${row.beforeTotal}), after ${percentage(row.after)} (${row.afterPassed}/${row.afterTotal}), change ${difference(row.delta)}.`).join(' ')}</desc>
        <rect width="880" height="420" fill="#ffffff" />
        <text x="58" y="26" fill="#20354d" fontSize="16" fontWeight="700">Memory ability comparison · {shared ? 'shared questions' : 'full suites'}</text>
        <text x="58" y="48" fill="#63758a" fontSize="12">Before: {data.before.run.model} · {data.before.run.memory_strategy?.replaceAll('_', ' ')}</text>
        <text x="58" y="68" fill="#63758a" fontSize="12">After: {data.after.run.model} · {data.after.run.memory_strategy?.replaceAll('_', ' ')}</text>
        <rect x="616" y="18" width="12" height="12" rx="3" fill={beforeColour} /><text x="635" y="28" fill="#44556a" fontSize="12">Before</text>
        <rect x="723" y="18" width="12" height="12" rx="3" fill={afterColour} /><text x="742" y="28" fill="#44556a" fontSize="12">After</text>
        {[0, 25, 50, 75, 100].map(tick => {
          const y = 312 - tick * 2.12;
          return <g key={tick}><line x1="58" x2="855" y1={y} y2={y} stroke="#e6ecf2" strokeDasharray={tick === 0 ? undefined : '4 4'} />
            <text x="46" y={y + 4} textAnchor="end" fill="#697b8f" fontSize="11">{tick}%</text></g>;
        })}
        {rows.map((row, index) => {
          const center = 156 + index * 199;
          return <g key={row.key}>
            {(['before', 'after'] as const).map((side, sideIndex) => {
              const value = row[side]; const x = center - 57 + sideIndex * 61;
              const passed = side === 'before' ? row.beforePassed : row.afterPassed;
              const total = side === 'before' ? row.beforeTotal : row.afterTotal;
              const colour = side === 'before' ? beforeColour : afterColour;
              const height = value === null ? 0 : value * 2.12;
              return <g key={side}><title>{row.label} · {side}: {percentage(value)} · {passed}/{total} passed</title>
                {value !== null && <rect x={x} y={312 - height - (value === 0 ? 2 : 0)} width="52" height={value === 0 ? 2 : height} rx={value === 0 ? 0 : 5} fill={colour} />}
                <text x={x + 26} y={value === null ? 296 : 302 - height} textAnchor="middle" fill={colour} fontSize={value === null ? 10 : 14} fontWeight="700">{percentage(value)}</text>
                <text x={x + 26} y="334" textAnchor="middle" fill="#697b8f" fontSize="11">{total ? `${passed}/${total}` : '—'}</text>
              </g>;
            })}
            <text x={center} y="359" textAnchor="middle" fill="#34475d" fontSize="13" fontWeight="600">{row.short}</text>
            <text x={center} y="385" textAnchor="middle" fill={row.delta === null || row.delta === 0 ? '#697b8f' : row.delta > 0 ? '#0c7864' : '#b34444'} fontSize="14" fontWeight="700">{difference(row.delta)}</text>
          </g>;
        })}
        <text x="58" y="411" fill="#697b8f" fontSize="11">Pass rate · counts shown as passed/tested · pp = percentage points · automated assessments</text>
      </svg></div>
      <figcaption><span>{shared ? `${data.paired_tests.length} identical questions` : 'All questions in each audit'} · Counts below the bars show passed / tested. An untested ability has no bar.</span>
        <UIButton type="button" className="secondary" onClick={exportChart}>Save chart (SVG)</UIButton></figcaption>
    </figure> : <p className="empty">No shared questions to chart. Choose full test suites to view each audit separately.</p>}
    <div className="comparison-change-strip" aria-label="Shared question outcomes">
      <div className="comparison-change-track" aria-hidden="true">{([
        ['fixed', '#138572'], ['regressed', '#be5252'], ['still_failed', '#c68b31'], ['still_passed', '#91a6bb'],
      ] as const).map(([key, colour]) => data.counts[key] > 0 && <span key={key} style={{ flex: data.counts[key], backgroundColor: colour }} />)}</div>
      <p><b>{data.counts.fixed}</b> fixed <span>·</span> <b>{data.counts.regressed}</b> regressed <span>·</span> <b>{data.counts.still_failed + data.counts.still_passed}</b> unchanged <small>on shared questions</small></p>
    </div>
  </section>;
}
