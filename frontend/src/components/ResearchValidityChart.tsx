import { useId } from 'react';
import { Collapse, Progress } from 'antd';
import { UITable } from './ui';
import type { ResearchValidityReport } from '../types/domain';

const measures = [
  { key: 'precision', label: 'Precision', colour: '#087ea4' },
  { key: 'recall', label: 'Recall', colour: '#16806a' },
  { key: 'f1', label: 'F1', colour: '#b7791f' },
] as const;
const caseCount = (value: number) => `${value} labelled case${value === 1 ? '' : 's'}`;
const percent = (value: number | null) => value === null ? 'Not measured' : `${Number(value.toFixed(1))}%`;

function ReferenceRecallChart({report}:{report:ResearchValidityReport}) {
  const result=report.failure_detection;
  if (!result) return <p>Full-reference failure recall: Not recorded in this result.</p>;
  const rows=[
    {label:'Decided answers only',value:report.evaluator.recall,colour:'#087ea4'},
    {label:'All reference failures',value:result.recall_all_reference_failures,colour:'#16806a'},
  ];
  return <section aria-label="Failure detection coverage">
    <h3>Are all failures being found?</h3>
    <div role="img" aria-label={`Failure recall: ${rows.map(row=>`${row.label} ${percent(row.value)}`).join('; ')}. Detected ${result.detected}, missed ${result.missed}, uncertain ${result.uncertain}, missing ${result.missing}; ${result.reference_failures} reference failures.`}>
      {rows.map(row=><div key={row.label} style={{marginBottom:12}}>
        <div style={{display:'flex',justifyContent:'space-between',gap:12}}><span>{row.label}</span><b>{percent(row.value)}</b></div>
        {row.value !== null && <Progress percent={row.value} showInfo={false} strokeColor={row.colour} />}
      </div>)}
    </div>
    <p>{result.detected} detected · {result.missed} missed · {result.uncertain} uncertain · {result.missing} missing</p>
    <small>All-reference recall counts uncertain answers as failures not found. Missing results prevent a complete score. A zero denominator is not measured. False positives are shown separately below.</small>
  </section>;
}

function FailureClassificationChart({report}:{report:ResearchValidityReport}) {
  const result=report.failure_classification;
  if (!result) return <p>Failure-category assessment: Not recorded in this result.</p>;
  const buckets=[
    {key:'correct',label:'Correct category',colour:'#16806a'},
    {key:'wrong_category',label:'Wrong category',colour:'#c43b4b'},
    {key:'unclassified',label:'No category',colour:'#b7791f'},
    {key:'missed',label:'Missed failure',colour:'#9154a7'},
    {key:'uncertain',label:'Uncertain',colour:'#087ea4'},
    {key:'missing',label:'Missing result',colour:'#718096'},
  ] as const;
  return <section aria-label="Failure-category assessment">
    <h3>Are failure categories correct?</h3>
    <p>{result.reference_failures} reference failures · detected-failure accuracy {percent(result.accuracy_detected_failures)} · all-reference accuracy {percent(result.accuracy_all_reference_failures)}</p>
    {result.reference_failures ? <div role="img" aria-label={`Failure classification outcomes: ${buckets.map(bucket=>`${bucket.label} ${result[bucket.key]}`).join(', ')}; ${result.reference_failures} reference failures.`}>
      {buckets.map(bucket=><div key={bucket.key} style={{display:'grid',gridTemplateColumns:'minmax(100px, 130px) minmax(80px, 1fr) 24px',gap:8,alignItems:'center',marginBottom:8}}>
        <span>{bucket.label}</span>
        <Progress percent={100*result[bucket.key]/result.reference_failures} showInfo={false} strokeColor={bucket.colour} />
        <span>{result[bucket.key]}</span>
      </div>)}
    </div> : <p>Not measured · no labelled reference failures.</p>}
    <small>Counts cover reference failures only. Detecting a failure does not establish its category. All-reference accuracy needs every failure result submitted; missed and uncertain outcomes count as unsuccessful classifications. False positives remain in the detection chart.</small>
  </section>;
}

/** Percentage measures share one scale; agreement and raw counts remain separate. */
export function ResearchValidityChart({ report }: { report: ResearchValidityReport }) {
  const titleId = useId();
  const descriptionId = useId();
  const rows = [
    { label: 'Memory Extraction', lines: ['Memory', 'Extraction'], metrics: report.extraction },
    { label: 'Relationship Classification', lines: ['Relationship', 'Classification'], metrics: report.relationship },
    { label: 'Test Validity', lines: ['Test', 'Validity'], metrics: report.test_validity },
    { label: 'Behaviour Evaluator', lines: ['Behaviour', 'Evaluator'], metrics: report.evaluator },
  ];
  return <figure className="research-validity-chart">
    <div className="reliability-legend">{measures.map(measure => <span key={measure.key}><i style={{ background: measure.colour }} />{measure.label}</span>)}</div>
    <small className="validity-scroll-hint">Scroll horizontally to compare stages.</small>
    <div style={{ overflowX: 'auto' }} tabIndex={0} role="region" aria-label="Scrollable auditor validity chart">
      <svg viewBox="0 0 820 375" style={{ width: '100%', minWidth: 650 }} role="img" aria-labelledby={`${titleId} ${descriptionId}`}>
        <title id={titleId}>Auditor validity by stage</title>
        <desc id={descriptionId}>{rows.map(row => `${row.label}: ${measures.map(measure => `${measure.label} ${percent(row.metrics[measure.key])}`).join(', ')}; ${caseCount(row.metrics.labelled_cases)}.`).join(' ')}</desc>
        {[0, 25, 50, 75, 100].map(value => <g key={value}><line x1={55} x2={805} y1={280 - value * 2.3} y2={280 - value * 2.3} stroke="#dbe4ea" /><text x={45} y={285 - value * 2.3} textAnchor="end" fontSize={12} fill="#536b7e">{value}%</text></g>)}
        {rows.map((row, index) => {
          const centre = 145 + index * 190;
          return <g key={row.label}>{measures.map((measure, offset) => {
            const value = row.metrics[measure.key];
            const x = centre - 57 + offset * 40;
            return <g key={measure.key}>
              <title>{row.label} · {measure.label}: {percent(value)}</title>
              {value === null ? <text x={x + 16} y={265} textAnchor="middle" fontSize={11} fill="#536b7e">N/A</text> : <><rect x={x} y={280 - value * 2.3} width={32} height={value * 2.3} rx={3} fill={measure.colour} /><text x={x + 16} y={270 - value * 2.3} textAnchor="middle" fontSize={11} fill="#23475e">{percent(value)}</text></>}
            </g>;
          })}<text x={centre} y={305} textAnchor="middle" fontSize={13} fill="#23475e">{row.lines.map((line, i) => <tspan key={line} x={centre} dy={i ? 16 : 0}>{line}</tspan>)}</text><text x={centre} y={345} textAnchor="middle" fontSize={12} fill="#536b7e">{caseCount(row.metrics.labelled_cases)}</text></g>;
        })}
      </svg>
    </div>
    {rows.some(row => measures.some(measure => row.metrics[measure.key] === null)) && <p>N/A · Not measured; no zero score is implied.</p>}
    <ReferenceRecallChart report={report} />
    <FailureClassificationChart report={report} />
    <Collapse items={[{ key: 'counts', label: 'Agreement, error counts & score definitions', children: <>
      <p>Positive classes: matched memories, correct relationships, acceptable tests, and detected answer failures.</p>
      <p>Precision: correct positive findings / all positive findings. Recall: detected positives / reference positives. F1 balances both. κ measures agreement beyond chance on a −1 to 1 scale. False-positive rate is lower when better.</p>
      <div className="comparison-scroll"><UITable><thead><tr><th>Stage</th><th>Labelled</th><th>True positives</th><th>False positives</th><th>True negatives</th><th>False negatives</th><th>Accuracy</th><th>False-positive rate</th><th>Cohen’s κ</th></tr></thead><tbody>{rows.map(row => <tr key={row.label}><th scope="row">{row.label}</th><td>{row.metrics.labelled_cases}</td><td>{row.metrics.true_positives}</td><td>{row.metrics.false_positives}</td><td>{row.metrics.true_negatives}</td><td>{row.metrics.false_negatives}</td><td>{percent(row.metrics.accuracy)}</td><td>{percent(row.metrics.false_positive_rate)}</td><td>{row.metrics.cohens_kappa === null ? 'Not measured' : row.metrics.cohens_kappa.toFixed(2)}</td></tr>)}</tbody></UITable></div>
    </> }]} />
  </figure>;
}
