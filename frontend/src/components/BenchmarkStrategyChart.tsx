import { useId } from 'react';

const colours = ['#087ea4', '#16806a', '#b7791f', '#7659a6'];
type Condition = {strategy: string; lexical_matches: number; total: number; percentage: number};

/** Compare one lexical proxy on one shared scale; absent cases are not zero. */
export function BenchmarkStrategyChart({conditions, label}: {conditions: Condition[]; label: (strategy: string) => string}) {
  const title = useId();
  const description = useId();
  const width = Math.max(360, conditions.length * 140 + 70);
  const step = (width - 70) / Math.max(conditions.length, 1);
  return <figure className="research-validity-chart">
    <div className="reliability-legend">{conditions.map((condition, index) => <span key={condition.strategy}><i style={{background: colours[index % colours.length]}}/><span>Strategy {index+1}: </span><b>{label(condition.strategy)} · {condition.lexical_matches}/{condition.total} lexical matches</b></span>)}</div>
    <div role="region" aria-label="Scrollable benchmark strategy chart" tabIndex={0} style={{overflowX:'auto'}}>
      <svg viewBox={`0 0 ${width} 340`} style={{width:'100%',minWidth:width}} role="img" aria-labelledby={`${title} ${description}`}>
        <title id={title}>Lexical reference match rates by memory strategy</title>
        <desc id={description}>{conditions.map(condition => `${label(condition.strategy)} ${condition.lexical_matches}/${condition.total} lexical matches, ${condition.total ? `${condition.percentage}%` : 'Not measured'}`).join('; ')}</desc>
        {[0,25,50,75,100].map(value => <g key={value}><line x1={55} x2={width-15} y1={270-value*2.2} y2={270-value*2.2} stroke="#dbe4ea"/><text x={45} y={274-value*2.2} textAnchor="end" fontSize={12} fill="#536b7e">{value}%</text></g>)}
        {conditions.map((condition,index) => {
          const centre=55+step*(index+.5);
          return <g key={condition.strategy}><title>{label(condition.strategy)}: {condition.total ? `${condition.percentage}%` : 'Not measured'}</title>
            {condition.total ? <><rect x={centre-23} y={270-condition.percentage*2.2} width={46} height={condition.percentage*2.2} rx={3} fill={colours[index%colours.length]}/><text x={centre} y={260-condition.percentage*2.2} textAnchor="middle" fontSize={13} fill="#23475e">{condition.percentage}%</text></> : <text x={centre} y={255} textAnchor="middle" fontSize={12} fill="#536b7e">Not measured</text>}
            <text x={centre} y={295} textAnchor="middle" fontSize={13} fill="#23475e">Strategy {index+1}</text><text x={centre} y={318} textAnchor="middle" fontSize={12} fill="#536b7e">{condition.total} {condition.total===1?'answer':'answers'}</text>
          </g>;
        })}
      </svg>
    </div>
    <figcaption>Same imported questions · lexical matching only. Scroll horizontally if needed; the legend identifies each strategy.</figcaption>
  </figure>;
}
