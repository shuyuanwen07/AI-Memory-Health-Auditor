import {useId} from 'react';
import {Progress,Tag} from 'antd';
import {comparisonColours} from '../services/chartColours';
import {modelDisplayName} from '../services/display';
import type {GeneratorComparisonBatch,Dimension} from '../types/domain';

export const generatorName=(entry:GeneratorComparisonBatch['entries'][number])=>entry.selection.provider==='rule_based'?'Rules':modelDisplayName(entry.selection.model??'Selected model');
const dimensions:Array<[Dimension,string]>=[['accuracy','Accuracy'],['freshness','Freshness'],['conflict_resolution','Conflict resolution'],['appropriate_use','Appropriate use']];

export function GeneratorQualityCharts({entries}:{entries:GeneratorComparisonBatch['entries']}){
  const title=useId();const description=useId();
  const maximum=Math.max(1,...entries.flatMap(entry=>Object.values(entry.quality.dimensions)));
  const width=Math.max(560,entries.length*200);const groupWidth=(width-60)/4;
  const barWidth=Math.min(28,groupWidth/(entries.length+1));
  return <section aria-label="Saved generated question checks"><h2>Saved question checks</h2>
    <div className="provider-grid">{entries.map((entry,index)=><div className="target" key={index}>
      <strong>{generatorName(entry)}</strong>
      <Progress percent={entry.quality.saved_questions?Math.round(entry.quality.accepted/entry.quality.saved_questions*100):0}
        format={()=>entry.quality.saved_questions?`${entry.quality.accepted}/${entry.quality.saved_questions} accepted`:'Not generated'}/>
      {entry.quality.saved_questions>0&&<div><Tag color="red">{entry.quality.rejected} rejected</Tag><Tag color="gold">{entry.quality.pending} pending</Tag></div>}
    </div>)}</div>
    <h3>Accepted question coverage</h3>
    <div className="reliability-legend">{entries.map((entry,index)=><span key={index}><i style={{background:comparisonColours[index%comparisonColours.length]}}/>{generatorName(entry)}</span>)}</div>
    <div role="region" aria-label="Scrollable question coverage chart" tabIndex={0} style={{overflowX:'auto'}}>
      <svg viewBox={`0 0 ${width} 300`} style={{width:'100%',minWidth:width}} role="img" aria-labelledby={title} aria-describedby={description}>
        <title id={title}>Accepted questions by ability and generator</title>
        <desc id={description}>{dimensions.map(([key,label])=>`${label}: ${entries.map(entry=>`${generatorName(entry)} ${entry.quality.saved_questions?`${entry.quality.dimensions[key]} accepted questions`:'not generated'}`).join(', ')}`).join('; ')}</desc>
        {Array.from({length:Math.min(maximum,4)+1},(_,index)=>Math.round(index*maximum/Math.min(maximum,4))).filter((value,index,all)=>all.indexOf(value)===index).map(value=><g key={value}>
          <line x1={45} x2={width-10} y1={225-value/maximum*160} y2={225-value/maximum*160} stroke="#dbe4ea"/>
          <text x={35} y={229-value/maximum*160} textAnchor="end" fontSize={12}>{value}</text>
        </g>)}
        {dimensions.map(([key,label],dimension)=>{
          const centre=45+groupWidth*(dimension+.5);
          return <g key={key}>{entries.map((entry,index)=>{
            const x=centre+(index-(entries.length-1)/2)*(barWidth+5);const count=entry.quality.dimensions[key];const height=count/maximum*160;
            return <g key={index}><title>{generatorName(entry)} · {label}: {entry.quality.saved_questions?`${count} accepted questions`:'Not generated'}</title>
              {entry.quality.saved_questions?(count>0?<rect x={x-barWidth/2} y={225-height} width={barWidth} height={height} fill={comparisonColours[index%comparisonColours.length]}/>:<circle cx={x} cy={225} r={2} fill={comparisonColours[index%comparisonColours.length]}/>):<text x={x} y={215} textAnchor="middle" fontSize={11}>—</text>}
              {entry.quality.saved_questions&&<text x={x} y={217-height} textAnchor="middle" fontSize={11}>{count}</text>}
            </g>;
          })}{label.split(' ').map((part,line)=><text key={line} x={centre} y={250+line*15} textAnchor="middle" fontSize={12}>{part}</text>)}</g>;
        })}
      </svg>
    </div>
    <p>Counts reflect current saved question decisions, including review changes. Missing suites are not zero-quality suites. Initial local checks are displayed separately where recorded.</p>
  </section>;
}
