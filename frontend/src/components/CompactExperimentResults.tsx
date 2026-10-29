import { Alert, Card } from 'antd';
import compactData from '../data/compactFinalDashboard.json';
import { Bar, BarChart, CartesianGrid, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

type Ratio = { numerator: number; denominator: number; value: number | null };
type AMethod = { label: string; detected: number; known: number };
type Strategy = { id: string; label: string; b_pass: number; b_decided: number; b_total: number; c_pass: number; c_decided: number; c_total: number; c_uncertain: number };
type Extract = { reference_fact_id_matched_coverage: Ratio; reference_relationship_coverage: Ratio };
type QuestionArm = { generated: number; valid: number; invalid: number; missing_slots: number; gate_accepted_human_invalid: number };
type ScopeReplay = { human_invalid:number; invalid_after_rejected:number; invalid_after_pending:number; invalid_after_accepted:number;
  human_valid:number; valid_after_rejected:number; valid_after_pending:number; valid_after_accepted:number };
type ScopePilot = { histories:number; total:number; valid:number; valid_pending:number; invalid:number; invalid_rule_rejected:number; unresolved:number };
type SemanticPilot = { total:number; unresolved:number; parse_errors:number; invalid_invalid:number; invalid_uncertain:number; invalid_valid:number; valid_invalid:number; valid_uncertain:number; valid_valid:number };
type Metrics = { failure_recall_conservative: Ratio; classification_accuracy_conservative: Ratio; false_positive_rate_decided: Ratio };
type Data = { format: 'compact-final-dashboard-v1'; sources: Record<string,{path:string;sha256:string}>;
  a: {histories:number;answers:number;methods:AMethod[]}; strategies:Strategy[];
  c_reference:{cases:number;available_cases:number;agreement:{agreed_repetitions:number;total_repetitions:number}};
  ac1:{histories:number;partial:number;old:Extract;new:Extract};
  ac2:{histories:number;slots:number;baseline:QuestionArm;candidate:QuestionArm;scope_replay:ScopeReplay;scope_pilot:ScopePilot;semantic_pilot:SemanticPilot};
  ac3:{histories:number;answers:number;human_consensus:number;human_unresolved:number;old:Metrics;new:Metrics} };
const pct=(n:number,d:number)=>d ? n/d*100 : 0;
const display=(n:number,d:number)=>`${n}/${d} · ${pct(n,d).toFixed(1)}%`;
const PAIRED_OLD='#9aaec2', PAIRED_NEW='#147e87';
const ratio=(x:Ratio)=>display(x.numerator,x.denominator);
const percentAxis = (v:number) => `${v}%`;
const object=(v:unknown):v is Record<string,unknown> => typeof v==='object' && v!==null && !Array.isArray(v);
function isCompactData(value:unknown):value is Data {
  if (!object(value)||value.format!=='compact-final-dashboard-v1'||!object(value.a)||!Array.isArray(value.a.methods)
      ||value.a.methods.length!==3||!Array.isArray(value.strategies)||value.strategies.length!==4
      ||!object(value.ac1)||!object(value.ac2)||!object(value.ac3)||!object(value.c_reference)) return false;
  return object(value.ac1.old)&&object(value.ac1.new)&&object(value.ac2.baseline)&&object(value.ac2.candidate)&&object(value.ac2.scope_replay)&&object(value.ac2.scope_pilot)&&object(value.ac2.semantic_pilot)
    &&object(value.ac3.old)&&object(value.ac3.new)&&object(value.c_reference.agreement);
}

function SemanticPilotChart({data}:{data:SemanticPilot}) {
  const rows=[
    {label:'Human-invalid',invalid:data.invalid_invalid,uncertain:data.invalid_uncertain,valid:data.invalid_valid},
    {label:'Human-valid',invalid:data.valid_invalid,uncertain:data.valid_uncertain,valid:data.valid_valid},
  ];
  return <figure className="scope-replay" aria-label="Semantic candidate model verdicts against human consensus">
    <figcaption>Semantic candidate · model verdicts</figcaption>
    {rows.map(r=>{const total=r.invalid+r.uncertain+r.valid; return <div className="scope-replay-row" key={r.label}>
      <span>{r.label} <b>{total}</b></span>
      <div className="scope-replay-track" role="img" aria-label={`${r.label}: model labelled ${r.invalid} invalid, ${r.uncertain} uncertain, ${r.valid} valid`}>
        <i className="scope-rejected" style={{width:`${pct(r.invalid,total)}%`}}/><i className="scope-pending" style={{width:`${pct(r.uncertain,total)}%`}}/><i className="scope-accepted" style={{width:`${pct(r.valid,total)}%`}}/>
      </div>
      <small>{r.invalid} invalid · {r.uncertain} uncertain · {r.valid} valid</small>
    </div>})}
    <div className="scope-replay-legend"><span><i className="scope-rejected"/>Model invalid</span><span><i className="scope-pending"/>Model uncertain</span><span><i className="scope-accepted"/>Model valid</span></div>
  </figure>;
}

function PairedChart({data, oldName, newName, labelWidth=138, height=190}: {data:Array<{name:string;old:number;current:number}>;oldName:string;newName:string;labelWidth?:number;height?:number}) {
  return <div className="compact-chart" role="img" aria-label={`${oldName} compared with ${newName}`} style={{height}}>
    <ResponsiveContainer width="100%" height="100%"><BarChart data={data} layout="vertical" margin={{top:0,right:12,bottom:0,left:0}}>
      <CartesianGrid strokeDasharray="3 3" horizontal={false}/><XAxis type="number" domain={[0,100]} tickFormatter={percentAxis}/>
      <YAxis type="category" dataKey="name" width={labelWidth} tick={{fontSize:12}}/><Tooltip formatter={(v)=>`${Number(v).toFixed(1)}%`}/><Legend/>
      <Bar dataKey="old" name={oldName} fill={PAIRED_OLD} radius={[0,4,4,0]}><LabelList dataKey="old" position="right" formatter={(value: unknown) => value === 0 ? '0%' : ''}/></Bar>
      <Bar dataKey="current" name={newName} fill={PAIRED_NEW} radius={[0,4,4,0]}><LabelList dataKey="current" position="right" formatter={(value: unknown) => value === 0 ? '0%' : ''}/></Bar>
    </BarChart></ResponsiveContainer>
  </div>;
}

function ScopeReplayChart({data}:{data:ScopeReplay}) {
  const rows=[
    {label:'Human-invalid',total:data.human_invalid,rejected:data.invalid_after_rejected,pending:data.invalid_after_pending,accepted:data.invalid_after_accepted},
    {label:'Human-valid',total:data.human_valid,rejected:data.valid_after_rejected,pending:data.valid_after_pending,accepted:data.valid_after_accepted},
  ];
  return <figure className="scope-replay" aria-label="Retrospective question-scope check results">
    <figcaption>AC2 scope check · retrospective replay</figcaption>
    {rows.map(r=><div className="scope-replay-row" key={r.label}>
      <span>{r.label} <b>{r.total}</b></span>
      <div className="scope-replay-track" role="img" aria-label={`${r.label}: ${r.rejected} rejected, ${r.pending} pending review, ${r.accepted} accepted`}>
        <i className="scope-rejected" style={{width:`${pct(r.rejected,r.total)}%`}}/>
        <i className="scope-pending" style={{width:`${pct(r.pending,r.total)}%`}}/>
        <i className="scope-accepted" style={{width:`${pct(r.accepted,r.total)}%`}}/>
      </div>
      <small>{r.rejected} rejected · {r.pending} pending · {r.accepted} accepted</small>
    </div>)}
    <div className="scope-replay-legend"><span><i className="scope-rejected"/>Rejected</span><span><i className="scope-pending"/>Pending</span><span><i className="scope-accepted"/>Accepted</span></div>
  </figure>;
}

function ScopePilotChart({data}:{data:ScopePilot}) {
  return <figure className="scope-replay" aria-label="Pilot question checks reconstructed after the study">
    <figcaption>AC2 pilot · reconstructed per-question checks</figcaption>
    <div className="scope-replay-row">
      <span>Human-valid <b>{data.valid}</b></span>
      <div className="scope-replay-track" role="img" aria-label={`Human-valid: ${data.valid_pending} newly pending, ${data.valid-data.valid_pending} accepted`}>
        <i className="scope-pending" style={{width:`${pct(data.valid_pending,data.valid)}%`}}/>
        <i className="scope-accepted" style={{width:`${pct(data.valid-data.valid_pending,data.valid)}%`}}/>
      </div>
      <small>{data.valid_pending} newly pending · {data.valid-data.valid_pending} accepted</small>
    </div>
    <div className="scope-replay-row">
      <span>Human-invalid <b>{data.invalid}</b></span>
      <div className="scope-replay-track" role="img" aria-label={`Human-invalid: ${data.invalid_rule_rejected} already rejected by the per-question rule`}>
        <i className="scope-rejected" style={{width:`${pct(data.invalid_rule_rejected,data.invalid)}%`}}/>
      </div>
      <small>{data.invalid_rule_rejected} already rejected by the rule · no additional invalid detected</small>
    </div>
    <div className="scope-replay-legend"><span><i className="scope-rejected"/>Rejected</span><span><i className="scope-pending"/>Pending</span><span><i className="scope-accepted"/>Accepted</span></div>
  </figure>;
}

export function CompactExperimentResults() {
  if(!isCompactData(compactData))
    return <Alert role="alert" type="warning" showIcon title="Research results are unavailable" description="The source-bound dashboard data is invalid. Individual saved audits are still available below."/>;
  const data=compactData;
  const policy=data.strategies.map(s=>({name:s.label,old:pct(s.b_pass,s.b_decided),current:pct(s.c_pass,s.c_decided)}));
  const evalRows=[
    {name:'Detect failures',key:'failure_recall_conservative' as const},
    {name:'Classify failures',key:'classification_accuracy_conservative' as const},
    {name:'False positives ↓',key:'false_positive_rate_decided' as const},
  ];
  const scorer=evalRows.map(x=>({name:x.name,old:100*(data.ac3.old[x.key].value??0),current:100*(data.ac3.new[x.key].value??0)}));
  const measures=[
    {name:'Fact ID matches',old:data.ac1.old.reference_fact_id_matched_coverage,current:data.ac1.new.reference_fact_id_matched_coverage},
    {name:'Relation matches',old:data.ac1.old.reference_relationship_coverage,current:data.ac1.new.reference_relationship_coverage},
    {name:'Valid questions',old:{numerator:data.ac2.baseline.valid,denominator:data.ac2.baseline.generated,value:null},current:{numerator:data.ac2.candidate.valid,denominator:data.ac2.candidate.generated,value:null}},
  ];
  const measuresChart=measures.map(x=>({name:x.name,old:pct(x.old.numerator,x.old.denominator),current:pct(x.current.numerator,x.current.denominator)}));
  return <>
    <section aria-label="Final experiment results" className="compact-results">
      <div className="compact-intro"><h2>Experiment results</h2><p>Three studies show what was found, how strategies compare, and whether the Auditor improves.</p></div>
      <div className="compact-grid">
        <Card title="A · Which audit method finds problems?" className="compact-a">
          <div className="compact-methods" role="img" aria-label="Predefined defects found by each audit method">
            {data.a.methods.map(m=><div className="compact-method" key={m.label}><span>{m.label}</span><div className="compact-track"><i style={{width:`${pct(m.detected,m.known)}%`}}/></div><strong>{m.detected}/{m.known}</strong></div>)}
          </div>
          <p className="compact-note">Each found the same 3 of 9 predefined defects. The expected method advantage was not observed.</p>
          <p className="compact-note">{data.a.histories} synthetic histories · {data.a.answers} answers · other failures fell outside the defect list.</p>
        </Card>
        <Card title="AC1 & AC2 · What changed?" className="compact-quality">
          <PairedChart data={measuresChart} oldName="Before" newName="After" height={190}/>
          <div className="compact-values"><div className="compact-value-header"><span>Measure</span><b>Before</b><b>After</b></div>{measures.map(x=><div key={x.name}><span>{x.name}</span><b>{ratio(x.old)}</b><b>{ratio(x.current)}</b></div>)}</div>
          <p className="compact-note">AC1: {data.ac1.histories} paired complete histories; {data.ac1.partial} partial runs excluded. ID matches may be partial, not strict recall or semantic accuracy. Human reviewers found six relationships valid; a later AI review offered a different interpretation. All data were subsequently human-reviewed as reported by the user; no new item-level ruling was supplied.</p>
          <p className="compact-note">AC2: {data.ac2.histories} histories; valid / generated questions. New: {data.ac2.candidate.invalid}/{data.ac2.candidate.generated} invalid; the gate accepted {data.ac2.candidate.gate_accepted_human_invalid} of them. Scheduled slots and missing outputs are not included in this denominator.</p>
          <ScopeReplayChart data={data.ac2.scope_replay}/>
          <p className="compact-note">On previously reviewed development questions, the new check adds 37/54 invalid questions to review; none were automatically accepted in this replay. It also sends 53/63 valid questions to review. High review effort; this is not independent validation or evidence of zero future errors.</p>
          <ScopePilotChart data={data.ac2.scope_pilot}/>
          <p className="compact-note">Separate pilot: {data.ac2.scope_pilot.histories} synthetic histories · {data.ac2.scope_pilot.total} questions · {data.ac2.scope_pilot.unresolved} unresolved excluded. Per-question rule and scope check reconstructed afterwards, not the full production workflow or independent population evidence.</p>
          <SemanticPilotChart data={data.ac2.semantic_pilot}/>
          <p className="compact-note">GPT-6 Luna assessed the same pilot; {data.ac2.semantic_pilot.parse_errors}/{data.ac2.semantic_pilot.total} responses could not be parsed and count as uncertain. Five human-unresolved items are excluded. The reconstructed per-question rule already rejected all 14 human-invalid questions; this candidate is not deployed and does not establish a safety improvement.</p>
        </Card>
        <Card title="B & C · Four memory strategies" className="compact-policies">
          <PairedChart data={policy} oldName="B · synthetic" newName="C · LongMemEval" labelWidth={162} height={230}/>
          <div className="compact-values"><div className="compact-value-header"><span>Strategy</span><b>B · synthetic</b><b>C · benchmark</b></div>{data.strategies.map(s=><div key={s.id}><span>{s.label}</span><b>{display(s.b_pass,s.b_decided)}</b><b>{display(s.c_pass,s.c_decided)}</b></div>)}</div>
          <p className="compact-note">B: 3 histories × 3 repeats, {data.strategies[0].b_total} answers per strategy. C: 30 selected cases × 3 repeats, {data.strategies[0].c_total} per strategy; {data.strategies.reduce((a,s)=>a+s.c_uncertain,0)} unresolved answers excluded from decided rates. Repeats are not independent cases.</p>
          <p className="compact-note">Separate original Auditor / LongMemEval ranking check: same two-policy order in {data.c_reference.agreement.agreed_repetitions}/{data.c_reference.agreement.total_repetitions} repeats on {data.c_reference.cases}/{data.c_reference.available_cases} benchmark cases. It is not a four-strategy ranking agreement.</p>
        </Card>
        <Card title="Auditor · Before and after improvement" className="compact-auditor">
          <PairedChart data={scorer} oldName="Before" newName="After" height={190}/>
          <div className="compact-values"><div className="compact-value-header"><span>Measure</span><b>Before</b><b>After</b></div>{evalRows.map(x=><div key={x.key}><span>{x.name}</span><b>{ratio(data.ac3.old[x.key])}</b><b>{ratio(data.ac3.new[x.key])}</b></div>)}</div>
          <p className="compact-note">Same {data.ac3.answers} answers · {data.ac3.histories} synthetic histories · {data.ac3.human_consensus} human-consensus answers, {data.ac3.human_unresolved} disagreements. Old classification: 0/55 were classified, not 55 incorrect labels.</p>
          <p className="compact-note">Observed thresholds were met on this sample; zero observed false positives does not establish zero population error.</p>
        </Card>
      </div>
      <p className="compact-evidence">Two independent human reviews were reported with AI assistance; reviewer identity and independence were not independently authenticated. Selected synthetic and benchmark subsets do not establish population-wide performance. <a href="/research-results">Research evidence and limitations →</a></p>
    </section>
  </>;
}
