import { useId } from 'react';

type Condition = {
  label: string;
  category_coverage: {covered_dimensions: number; total_dimensions: number; value: number | null};
  response_level: {true_positives: number; false_negatives: number; false_positives: number; true_negatives: number; failure_detection_recall: number | null; false_positive_rate: number | null};
  failure_discovery_rate: {discovered_distinct_failures: number | null; known_distinct_failures: number | null; value: number | null};
};
const colours = ['#087ea4', '#16806a', '#b7791f'];

function MetricFigure({conditions, title, value, counts, note}: {conditions: Condition[]; title: string; value: (condition: Condition) => number | null; counts: (condition: Condition) => string; note?: string}) {
  const id = useId();
  const width = 780;
  const plotLeft = 220;
  const plotWidth = 390;
  const height = Math.max(88, 38 * conditions.length + 44);
  return <figure className="research-validity-chart">
    <div role="region" aria-label={`Scrollable ${title} chart`} tabIndex={0} style={{overflowX:'auto'}}>
      <svg viewBox={`0 0 ${width} ${height}`} style={{width:'100%',minWidth:width}} role="img" aria-labelledby={`${id}-title ${id}-desc`}>
        <title id={`${id}-title`}>{title} by test method</title>
        <desc id={`${id}-desc`}>{conditions.map(condition=>`${condition.label}: ${value(condition)===null?'Not measured':`${(value(condition)!*100).toFixed(1)}%`}, ${counts(condition)}`).join('; ')}{note ? ` ${note}` : ''}</desc>
        {[0,25,50,75,100].map(tick=>{const x=plotLeft+plotWidth*tick/100;return <g key={tick}><line x1={x} x2={x} y1={18} y2={height-18} stroke="#dbe4ea"/><text x={x} y={height-3} textAnchor="middle" fontSize={11} fill="#536b7e">{tick}%</text></g>;})}
        {conditions.map((condition,index)=>{
          const y=28+index*38;const score=value(condition);
          return <g key={condition.label}><text x={plotLeft-10} y={y+13} textAnchor="end" fontSize={12} fill="#23475e">{condition.label}</text>
            {score===null?<text x={plotLeft+6} y={y+13} fontSize={12} fill="#536b7e">Not measured · {counts(condition)}</text>:<>
              <rect x={plotLeft} y={y} width={Math.max(score*plotWidth,score===0?1:0)} height={18} rx={3} fill={colours[index%colours.length]}/>
              <text x={plotLeft+plotWidth+12} y={y+13} fontSize={12} fill="#23475e">{(score*100).toFixed(1)}% · {counts(condition)}</text>
            </>}
          </g>;
        })}
      </svg>
    </div>
    <figcaption>{title}. Percentages use the displayed numerator/denominator; an unavailable denominator is shown as “Not measured,” never as zero.{note ? ` ${note}` : ''}</figcaption>
  </figure>;
}

export function ExperimentAMethodChart({conditions}: {conditions: Condition[]}) {
  return <div aria-label="Experiment A metric charts">
    <MetricFigure conditions={conditions} title="Category Coverage" value={condition=>condition.category_coverage.value} counts={condition=>`${condition.category_coverage.covered_dimensions}/${condition.category_coverage.total_dimensions} dimensions`} />
    <MetricFigure conditions={conditions} title="Response-level Failure Detection Recall" value={condition=>condition.response_level.failure_detection_recall} counts={condition=>`${condition.response_level.true_positives}/${condition.response_level.true_positives+condition.response_level.false_negatives} labelled failures`} />
    <MetricFigure conditions={conditions} title="Failure Discovery Rate" value={condition=>condition.failure_discovery_rate.value} counts={condition=>condition.failure_discovery_rate.discovered_distinct_failures===null||condition.failure_discovery_rate.known_distinct_failures===null?'distinct failures not measured':`${condition.failure_discovery_rate.discovered_distinct_failures}/${condition.failure_discovery_rate.known_distinct_failures} distinct failures`} note="Counts frozen defect IDs mapped by a researcher to responses marked Fail in the saved reference labels; mapping and reviewer identity are self-declared and not independently verified." />
    <MetricFigure conditions={conditions} title="False-positive Rate" value={condition=>condition.response_level.false_positive_rate} counts={condition=>`${condition.response_level.false_positives}/${condition.response_level.false_positives+condition.response_level.true_negatives} labelled passes`} />
  </div>;
}
