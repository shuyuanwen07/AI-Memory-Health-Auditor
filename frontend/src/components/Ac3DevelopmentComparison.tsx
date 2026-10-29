import { useEffect, useState } from 'react';
import { Card } from 'antd';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

type Metric = {numerator:number;denominator:number;percentage:number};
type Condition = {id:'hybrid'|'provider_only';label:string;metrics:Record<string,Metric>};
type Report = {format:'ac3-taxonomy-development-public-v1';conditions:Condition[];sample_size:120;
  independent_retest:false;formal_acceptance_established:false;limitations:string[]};
const record=(x:unknown):x is Record<string,unknown>=>!!x && typeof x==='object' && !Array.isArray(x);
const keys=['failure_recall_conservative','classification_accuracy_conservative','decided_coverage','false_positive_rate_decided'];
const pairedNames=['False positives corrected','False positives → uncertain','Failures newly detected','Detected failures → pass','Detected failures → uncertain'];
type Paired = {format:'ac3-paired-development-public-v1';cases:120;independent_retest:false;rows:{name:string;hybrid:number;provider:number}[]};

export function isPairedDevelopment(x:unknown):x is Paired {
  return record(x) && x.format==='ac3-paired-development-public-v1' && x.cases===120 && x.independent_retest===false
    && x.run_sha256==='46c3670eafb67a2f6e3a5e40b08e5a6fa2f126a7cbd5e1aad14752c389eafdb1'
    && Array.isArray(x.rows) && x.rows.length===pairedNames.length && x.rows.every((row:unknown,i:number)=>record(row)
      && row.name===pairedNames[i] && ['hybrid','provider'].every(k=>Number.isInteger(row[k]) && Number(row[k])>=0 && Number(row[k])<=120));
}

function PairedChanges() {
  const [data,setData]=useState<Paired|null>(null);
  useEffect(()=>{let active=true;fetch('/reports/ac3-paired-development-v1.json',{cache:'no-store'})
    .then(r=>r.ok?r.json():null).then(x=>{if(active&&isPairedDevelopment(x))setData(x);})
    .catch(()=>{if(active)setData(null);});return()=>{active=false;};},[]);
  if(!data)return null;
  return <section aria-label="Paired development changes">
    <h4>Same answers: changes from original</h4>
    <p>Counts, not new validation. Uncertain is not a correct verdict.</p>
    <div role="img" aria-label="Paired development changes from original judgments" style={{width:'100%',height:260}}>
      <ResponsiveContainer><BarChart data={data.rows} layout="vertical" margin={{left:12,right:12}}>
        <CartesianGrid strokeDasharray="3 3"/><XAxis type="number" allowDecimals={false}/><YAxis type="category" dataKey="name" width={180}/><Tooltip/><Legend/>
        <Bar dataKey="hybrid" name="Model + rule check" fill="#23836f"/><Bar dataKey="provider" name="Model judgment only" fill="#486a9b"/>
      </BarChart></ResponsiveContainer>
    </div>
    <table><thead><tr><th>Change</th><th>Model + rule check</th><th>Model judgment only</th></tr></thead><tbody>
      {data.rows.map(row=><tr key={row.name}><th scope="row">{row.name}</th><td>{row.hybrid}</td><td>{row.provider}</td></tr>)}
    </tbody></table>
  </section>;
}

export function isAc3DevelopmentReport(x:unknown):x is Report {
  if(!record(x)||x.format!=='ac3-taxonomy-development-public-v1'||x.sample_size!==120||x.independent_retest!==false
    ||x.formal_acceptance_established!==false||!Array.isArray(x.conditions)||x.conditions.length!==2
    ||!Array.isArray(x.limitations)||!x.limitations.every((v:unknown)=>typeof v==='string'))return false;
  const ids=x.conditions.map((v:unknown)=>record(v)?v.id:null);
  if(!ids.includes('hybrid')||!ids.includes('provider_only'))return false;
  return x.conditions.every((c:unknown)=>record(c)&&typeof c.label==='string'&&record(c.metrics)&&keys.every(key=>{
    const m=(c.metrics as Record<string,unknown>)[key];
    return record(m)&&typeof m.numerator==='number'&&Number.isInteger(m.numerator)&&m.numerator>=0
      &&typeof m.denominator==='number'&&Number.isInteger(m.denominator)&&m.denominator>0&&m.numerator<=m.denominator
      &&typeof m.percentage==='number'&&Number.isFinite(m.percentage)&&Math.abs(m.percentage-100*m.numerator/m.denominator)<0.11;
  }) && (c.metrics.failure_recall_conservative as Metric).denominator===80
     && (c.metrics.decided_coverage as Metric).denominator===120
     && (c.metrics.classification_accuracy_conservative as Metric).denominator===(c.metrics.failure_recall_conservative as Metric).numerator
     && (c.metrics.false_positive_rate_decided as Metric).denominator<=40);
}

export function Ac3DevelopmentComparison() {
  const [data,setData]=useState<Report|null>(null);
  useEffect(()=>{let active=true;fetch('/reports/ac3-taxonomy-development-v1.json',{cache:'no-store'})
    .then(r=>r.ok?r.json():null).then(x=>{if(active&&isAc3DevelopmentReport(x))setData(x);})
    .catch(()=>{if(active)setData(null);});return()=>{active=false;};},[]);
  if(!data)return null;
  const hybrid=data.conditions.find(x=>x.id==='hybrid')!,provider=data.conditions.find(x=>x.id==='provider_only')!;
  const rows=[['Failure recall','failure_recall_conservative'],['Failure classification','classification_accuracy_conservative'],['Decided coverage','decided_coverage']]
    .map(([name,key])=>({name,hybrid:hybrid.metrics[key].percentage,provider:provider.metrics[key].percentage}));
  const ratio=(c:Condition,key:string)=>{const m=c.metrics[key];return `${m.numerator}/${m.denominator} (${m.percentage.toFixed(1)}%)`;};
  const fp=(c:Condition)=>{const m=c.metrics.false_positive_rate_decided;return `${m.numerator}/${m.denominator}`;};
  return <Card title="AC3 · scoring repair development" style={{marginTop:16}}>
    <p><b>Development only</b> · 120 previously observed answers · independent retest pending</p>
    <div role="img" aria-label="Development scorer comparison across failure recall, classification and coverage" style={{width:'100%',height:260}}>
      <ResponsiveContainer><BarChart data={rows}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="name"/><YAxis domain={[0,100]} unit="%"/><Tooltip/><Legend/>
        <Bar dataKey="hybrid" name="Model + rule check" fill="#23836f"/><Bar dataKey="provider" name="Model judgment only" fill="#486a9b"/>
      </BarChart></ResponsiveContainer>
    </div>
    <table><thead><tr><th>Metric</th><th>Model + rule check</th><th>Model judgment only</th></tr></thead><tbody>
      {[['Failure recall','failure_recall_conservative'],['Failure classification','classification_accuracy_conservative'],['Decided coverage','decided_coverage']].map(([label,key])=>
        <tr key={key}><th scope="row">{label}</th><td>{ratio(hybrid,key)}</td><td>{ratio(provider,key)}</td></tr>)}
    </tbody></table>
    <p>Decided-case false positives: {fp(hybrid)} vs {fp(provider)}. Of 40 human-pass answers, {40-hybrid.metrics.false_positive_rate_decided.denominator} vs {40-provider.metrics.false_positive_rate_decided.denominator} were not decided and are excluded from these denominators.</p>
    <PairedChanges />
    <p><small>{data.limitations.join(' ')}</small></p>
  </Card>;
}
