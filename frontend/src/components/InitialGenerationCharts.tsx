import {useId} from 'react';
import {Tag} from 'antd';
import {comparisonColours} from '../services/chartColours';
import {generatorName} from './GeneratorQualityCharts';
import type {GeneratorComparisonBatch} from '../types/domain';

type Entry=GeneratorComparisonBatch['entries'][number];
function labelLines(label:string){
  const lines:string[]=[];let line='';
  for(const word of label.split(' ')){if(line&&line.length+word.length+1>20){lines.push(line);line=word;}else line=line?`${line} ${word}`:word;}
  if(line)lines.push(line);
  return lines.slice(0,3);
}
function InitialChart({entries,title,value}:{entries:Entry[];title:string;value:(entry:Entry)=>number|null}){
  const id=useId();const description=useId();const width=Math.max(360,entries.length*160+60);const step=(width-60)/Math.max(entries.length,1);
  return <figure><h3>{title}</h3><div role="region" aria-label={`${title} chart`} tabIndex={0} style={{overflowX:'auto'}}>
    <svg viewBox={`0 0 ${width} 320`} style={{width:'100%',minWidth:width}} role="img" aria-labelledby={id} aria-describedby={description}>
      <title id={id}>{title} by generator</title><desc id={description}>{entries.map(entry=>`${generatorName(entry)}: ${value(entry)===null?'Unknown':`${Number(value(entry)!.toFixed(1))}%`}`).join('; ')}</desc>
      {[0,50,100].map(percent=><g key={percent}><line x1={45} x2={width-10} y1={210-percent*1.5} y2={210-percent*1.5} stroke="#dbe4ea"/><text x={36} y={214-percent*1.5} textAnchor="end" fontSize={12}>{percent}%</text></g>)}
      {entries.map((entry,index)=>{const percent=value(entry);const x=45+step*(index+.5);const height=(percent??0)*1.5;return <g key={index}>
        <title>{generatorName(entry)} · {percent===null?'Unknown':`${Number(percent.toFixed(1))}%`}</title>
        {percent===null?<text x={x} y={198} textAnchor="middle" fontSize={12}>Unknown</text>:<>
          {percent>0?<rect x={x-20} y={210-height} width={40} height={height} fill={comparisonColours[index%comparisonColours.length]}/>:<circle cx={x} cy={210} r={3} fill={comparisonColours[index%comparisonColours.length]}/>}
          <text x={x} y={200-height} textAnchor="middle" fontSize={12}>{Number(percent.toFixed(1))}%</text></>}
        {labelLines(generatorName(entry)).map((line,index)=><text key={index} x={x} y={238+index*15} textAnchor="middle" fontSize={12}>{line}</text>)}
        <text x={x} y={300} textAnchor="middle" fontSize={11}>{entry.generation?.initial_candidates==null?'No initial data':`${entry.generation.initial_candidates} candidates`}</text>
      </g>;})}
    </svg>
  </div>{entries.length>2&&<small>Scroll horizontally to compare all models on smaller screens.</small>}</figure>;
}

export function InitialGenerationCharts({entries}:{entries:Entry[]}){
  return <section aria-label="Initial generation observations"><h2>Before automatic repairs</h2>
    <div className="visual-grid"><InitialChart entries={entries} title="Initial local-check pass rate" value={entry=>entry.generation?.initial_local_check_percentage??null}/>
      <InitialChart entries={entries} title="Initial answer-leak flags" value={entry=>entry.generation?.initial_leak_percentage??null}/></div>
    <div className="provider-grid">{entries.map((entry,index)=><div className="target" key={index}><strong>{generatorName(entry)}</strong>
      {entry.generation?<><span>{entry.generation.operation_count} generation operations · {entry.generation.repair_passes} automatic repair passes</span>
        {entry.generation.initial_suite_contract_valid===false&&<Tag color="red">Initial suite contract rejected</Tag>}
        {entry.generation.initial_status==='coverage_rejected'&&<Tag color="gold">Initial coverage incomplete</Tag>}
        {entry.generation.latest_status==='unfinished'&&<Tag color="gold">Unfinished generation operation</Tag>}
        {entry.generation.latest_status==='failed'&&<Tag color="red">Generation failed</Tag>}
        {entry.generation.latest_status==='not_saved'&&<Tag color="gold">Suite not saved</Tag>}</>:<span>No operation record</span>}
    </div>)}</div>
    <p>These are local checks on the first recorded candidates, not independent validity. Generation operations are not HTTP retry counts. Historical missing observations stay unknown.</p>
  </section>;
}
