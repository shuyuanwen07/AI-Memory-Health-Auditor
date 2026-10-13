import { useId } from 'react';
import { modelDisplayName } from '../services/display';
import { comparisonColours } from '../services/chartColours';
import type {AssessorComparisonBatch} from '../types/domain';

const colours=comparisonColours;
const format=(value:number)=>value.toLocaleString('en-US',{maximumSignificantDigits:4,
  notation:value!==0&&(value>=1e6||value<1e-6)?'scientific':'standard'});
function nameLines(name:string){
  const lines:string[]=[];let current='';
  for(const word of name.split(' ')){
    if(current&&current.length+word.length+1>20){lines.push(current);current=word;}
    else current=current?`${current} ${word}`:word;
  }
  if(current)lines.push(current);
  return lines.length>3?[...lines.slice(0,2),`${lines[2].slice(0,17)}…`]:lines;
}
type Row={name:string;value:number|null;coverage:string;colour:string};
export function OperationChart({title,unit,rows,subject='assessor'}:{title:string;unit:string;rows:Row[];subject?:string}){
  const titleId=useId();const descriptionId=useId();
  const known=rows.flatMap(row=>row.value===null?[]:[row.value]);
  const maximum=Math.max(0,...known);
  const scale=maximum>0?(Number.isFinite(maximum*1.2)?maximum*1.2:maximum):1;
  const width=Math.max(360,rows.length*145+65);
  const step=(width-65)/Math.max(rows.length,1);
  return <figure className="research-validity-chart">
    <h3>{title}</h3>
    <div role="region" aria-label={`${title} chart`} tabIndex={0} style={{overflowX:'auto'}}>
      <svg viewBox={`0 0 ${width} 330`} style={{width:'100%',minWidth:width}} role="img" aria-labelledby={titleId} aria-describedby={descriptionId}>
        <title id={titleId}>{title} by {subject}</title>
        <desc id={descriptionId}>{rows.map(row=>`${row.name}: ${row.value===null?'Not recorded':`${format(row.value)} ${unit}`}; ${row.coverage}`).join('; ')}</desc>
        {known.length>0&&(maximum>0?[0,0.5,1]:[0]).map(fraction=><g key={fraction}><line x1={55} x2={width-10} y1={240-fraction*180} y2={240-fraction*180} stroke="#dbe4ea"/><text x={48} y={244-fraction*180} textAnchor="end" fontSize={11}>{format(scale*fraction)}</text></g>)}
        {rows.map((row,index)=>{
          const x=55+step*(index+.5);const height=row.value===null?0:row.value/scale*180;
          return <g key={row.name}><title>{row.name}: {row.value===null?'Not recorded':`${format(row.value)} ${unit}`} · {row.coverage}</title>
            {row.value===null?<text x={x} y={228} textAnchor="middle" fill="#627481" fontSize={12}>Not recorded</text>:<>
              {row.value===0?<circle cx={x} cy={240} r={3} fill={row.colour}/>:<rect x={x-22} y={240-height} width={44} height={height} fill={row.colour} rx={3}/>}
              <text x={x} y={230-height} textAnchor="middle" fontSize={12}>{format(row.value)} {unit}</text></>}
            {nameLines(row.name).map((word,line)=><text key={line} x={x} y={262+line*14} textAnchor="middle" fontSize={11}>{word}</text>)}
            <text x={x} y={310} textAnchor="middle" fontSize={11} fill="#536b7e">{row.coverage}</text>
          </g>;
        })}
      </svg>
    </div>
    {rows.length>2&&<small>Scroll horizontally to compare all models on smaller screens.</small>}
  </figure>;
}

export function AssessorOperationCharts({entries}:{entries:AssessorComparisonBatch['entries']}){
  const rows=entries.map((entry,index)=>({name:entry.selection.evaluator_provider==='rule_based'?'Rules':modelDisplayName(entry.selection.evaluator_model??'Selected model'),
    observation:entry.observations,colour:colours[index%colours.length]}));
  return <section aria-label="Recorded assessor time and cost"><h2>Time & reported cost</h2>
    <div className="reliability-legend">{rows.map(row=><span key={row.name}><i style={{background:row.colour}}/>{row.name}</span>)}</div>
    <div className="visual-grid">
      <OperationChart title="Average recorded review time" unit="s" rows={rows.map(row=>({name:row.name,colour:row.colour,
        value:row.observation?.mean_elapsed_ms==null?null:row.observation.mean_elapsed_ms/1000,
        coverage:row.observation?`${row.observation.timed_answers}/${row.observation.expected_answers} timed`:'No receipts'}))}/>
      <OperationChart title="Reported OpenRouter credits" unit="credits" rows={rows.map(row=>({name:row.name,colour:row.colour,
        value:row.observation?.observed_cost_credits??null,
        coverage:row.observation?`${row.observation.cost_reported_answers}/${row.observation.expected_answers} reported${row.observation.complete_cost_coverage?'':' · partial'}`:'No receipts'}))}/>
    </div>
    <p>Time includes retries and validation. Credits cover reported replies, not a full invoice. Compare coverage before comparing amounts.</p>
  </section>;
}
