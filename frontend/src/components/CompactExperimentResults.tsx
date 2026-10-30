import { Alert, Card } from 'antd';
import compactData from '../data/compactFinalDashboard.json';
import { Bar, BarChart, CartesianGrid, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { DynamicA, DynamicBC, useDynamicStudies } from './DynamicStudies';
import { RetrievalImprovement, useRetrievalImprovement } from './RetrievalImprovement';

type Ratio = { numerator: number; denominator: number; value: number | null };
type AMethod = { label: string; detected: number; known: number };
type Strategy = { id: string; label: string; b_pass: number; b_decided: number; b_total: number; b_dimensions:Record<string,{passed:number;decided:number}>; c_pass: number; c_decided: number; c_total: number; c_uncertain: number };
type Extract = { reference_fact_id_matched_coverage: Ratio; reference_relationship_coverage: Ratio };
type QuestionArm = { generated: number; valid: number; invalid: number; missing_slots: number; gate_accepted_human_invalid: number };
type ScopeReplay = { human_invalid:number; invalid_after_rejected:number; invalid_after_pending:number; invalid_after_accepted:number;
  human_valid:number; valid_after_rejected:number; valid_after_pending:number; valid_after_accepted:number };
type ScopePilot = { histories:number; total:number; valid:number; valid_pending:number; invalid:number; invalid_rule_rejected:number; unresolved:number };
type SemanticPilot = { total:number; unresolved:number; parse_errors:number; invalid_invalid:number; invalid_uncertain:number; invalid_valid:number; valid_invalid:number; valid_uncertain:number; valid_valid:number };
type Prospective = { histories:number; generated_histories:number; failed_histories:number; questions:number;
  accepted:number; pending:number; ai_valid:number; ai_invalid:number; ai_unresolved:number;
  cross:Record<string,number> };
type ReviewedDimension = { dimension:string;label:string;total:number;valid:number;invalid:number;unresolved:number };
type Metrics = { failure_recall_conservative: Ratio; classification_accuracy_conservative: Ratio; false_positive_rate_decided: Ratio };
type Data = { format: 'compact-final-dashboard-v1'; sources: Record<string,{path:string;sha256:string}>;
  a: {histories:number;answers:number;methods:AMethod[]}; strategies:Strategy[]; b_example:{history:string;relationship_run_id:string;scope_run_id:string;development_original_pass:number;development_candidate_pass:number;development_current_original_pass:number;development_current_candidate_pass:number;development_total:number};
  c_reference:{cases:number;available_cases:number;agreement:{agreed_repetitions:number;total_repetitions:number}};
  ac1:{histories:number;partial:number;old:Extract;new:Extract;reviewed:{histories:number;facts:{full:number;partial:number;missing:number};relationships:{correct_type:number;partial:number}}};
  ac2:{histories:number;slots:number;baseline:QuestionArm;candidate:QuestionArm;scope_replay:ScopeReplay;scope_pilot:ScopePilot;semantic_pilot:SemanticPilot;prospective:Prospective;four_dimension_review:{histories:number;dimensions:ReviewedDimension[]};latest_development:{histories:number;saved_histories:number;valid:number;invalid:number;total:number}};
  ac3:{histories:number;answers:number;human_consensus:number;human_unresolved:number;old:Metrics;new:Metrics;detection_difference_interval:{lower:number;upper:number}} };
const pct=(n:number,d:number)=>d ? n/d*100 : 0;
const display=(n:number,d:number)=>`${n}/${d} · ${pct(n,d).toFixed(1)}%`;
const PAIRED_OLD='#9aaec2', PAIRED_NEW='#147e87';
const ratio=(x:Ratio)=>display(x.numerator,x.denominator);
const percentAxis = (v:number) => `${v}%`;
const object=(v:unknown):v is Record<string,unknown> => typeof v==='object' && v!==null && !Array.isArray(v);
function isCompactData(value:unknown):value is Data {
  if (!object(value)||value.format!=='compact-final-dashboard-v1'||!object(value.a)||!Array.isArray(value.a.methods)
      ||value.a.methods.length!==3||!Array.isArray(value.strategies)||value.strategies.length!==4
      ||!object(value.ac1)||!object(value.ac2)||!object(value.ac3)||!object(value.c_reference)||!object(value.b_example)
      ||typeof value.b_example.relationship_run_id!=='string'||typeof value.b_example.scope_run_id!=='string'
      ||typeof value.b_example.development_original_pass!=='number'||typeof value.b_example.development_candidate_pass!=='number'
      ||typeof value.b_example.development_current_original_pass!=='number'||typeof value.b_example.development_current_candidate_pass!=='number'||typeof value.b_example.development_total!=='number') return false;
  if (!value.strategies.every(s=>object(s)&&object(s.b_dimensions)&&['accuracy','freshness','conflict_resolution','appropriate_use'].every(k=>object(s.b_dimensions)&&object(s.b_dimensions[k])&&typeof s.b_dimensions[k].passed==='number'&&typeof s.b_dimensions[k].decided==='number'))) return false;
  return object(value.ac1.old)&&object(value.ac1.new)&&object(value.ac1.reviewed)&&object(value.ac2.baseline)&&object(value.ac2.candidate)&&object(value.ac2.scope_replay)&&object(value.ac2.scope_pilot)&&object(value.ac2.semantic_pilot)&&object(value.ac2.prospective)&&object(value.ac2.four_dimension_review)&&Array.isArray(value.ac2.four_dimension_review.dimensions)&&value.ac2.four_dimension_review.dimensions.length===4
    &&object(value.ac2.latest_development)&&typeof value.ac2.latest_development.valid==='number'&&typeof value.ac2.latest_development.invalid==='number'&&typeof value.ac2.latest_development.total==='number'
    &&object(value.ac3.old)&&object(value.ac3.new)&&object(value.ac3.detection_difference_interval)
    &&typeof value.ac3.detection_difference_interval.lower==='number'&&Number.isFinite(value.ac3.detection_difference_interval.lower)
    &&typeof value.ac3.detection_difference_interval.upper==='number'&&Number.isFinite(value.ac3.detection_difference_interval.upper)
    &&object(value.c_reference.agreement);
}

function FourDimensionReview({data}:{data:{histories:number;dimensions:ReviewedDimension[]}}) {
  return <figure className="scope-replay" aria-label="Four-dimension question review">
    <figcaption>Structured sources · four abilities</figcaption>
    {data.dimensions.map(row=><div className="scope-replay-row" key={row.dimension}>
      <span>{row.label}</span><div className="scope-replay-track" role="img" aria-label={`${row.label}: ${row.valid} agreed valid, ${row.invalid} agreed invalid, ${row.unresolved} unresolved out of ${row.total}`}>
        <i className="scope-accepted" style={{width:`${pct(row.valid,row.total)}%`}}/><i className="scope-rejected" style={{width:`${pct(row.invalid,row.total)}%`}}/><i className="scope-pending" style={{width:`${pct(row.unresolved,row.total)}%`}}/>
      </div><small>{row.valid}/{row.total} agreed valid{row.unresolved ? ` · ${row.unresolved} unresolved` : ''}</small>
    </div>)}
    <p className="compact-note">{data.histories} related synthetic histories · 32 questions. AI-assisted judgments were individually human-checked; human-review independence was not established.</p>
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

function BAbilityChart({strategies}:{strategies:Strategy[]}) {
  const dimensions=[['accuracy','Accuracy'],['freshness','Freshness'],['conflict_resolution','Conflict resolution'],['appropriate_use','Appropriate use']];
  const rows=dimensions.map(([key,name])=>({name,...Object.fromEntries(strategies.map(s=>[s.id,pct(s.b_dimensions[key].passed,s.b_dimensions[key].decided)]))}));
  const colours=['#718ba4','#147e87','#bd7735','#7254a2'];
  return <div className="compact-chart" role="img" aria-label="Experiment B pass rates by ability and memory strategy" style={{height:300}}>
    <ResponsiveContainer width="100%" height="100%"><BarChart data={rows} layout="vertical" margin={{top:0,right:12,bottom:0,left:0}}>
      <CartesianGrid strokeDasharray="3 3" horizontal={false}/><XAxis type="number" domain={[0,100]} tickFormatter={percentAxis}/>
      <YAxis type="category" dataKey="name" width={132} tick={{fontSize:12}}/><Tooltip formatter={(v)=>`${Number(v).toFixed(1)}%`}/><Legend/>
      {strategies.map((s,i)=><Bar key={s.id} dataKey={s.id} name={s.label} fill={colours[i]} radius={[0,4,4,0]}><LabelList dataKey={s.id} position="right" formatter={(value:unknown)=>value===0?'0%':''}/></Bar>)}
    </BarChart></ResponsiveContainer>
  </div>;
}

function ProspectiveChart({data}:{data:Prospective}) {
  const rows=[
    {label:'Executable',total:data.ai_valid,accepted:data.cross.valid_accepted,pending:data.cross.valid_pending},
    {label:'Not executable',total:data.ai_invalid,accepted:data.cross.invalid_accepted,pending:data.cross.invalid_pending},
    {label:'Unresolved',total:data.ai_unresolved,accepted:data.cross.unresolved_accepted,pending:data.cross.unresolved_pending},
  ];
  return <figure className="scope-replay" aria-label="Prospective AC2 question generation and reviewed judgments">
    <figcaption>New sources · AC2 generation</figcaption>
    <div className="scope-replay-row">
      <span>Histories <b>{data.histories}</b></span>
      <div className="scope-replay-track" role="img" aria-label={`${data.generated_histories} histories generated questions; ${data.failed_histories} histories did not`}>
        <i className="scope-accepted" style={{width:`${pct(data.generated_histories,data.histories)}%`}}/>
        <i className="scope-rejected" style={{width:`${pct(data.failed_histories,data.histories)}%`}}/>
      </div>
      <small>{data.generated_histories} generated · {data.failed_histories} no questions saved</small>
    </div>
    <p className="compact-note">{data.questions} saved questions · Accuracy only · {data.pending} pending · {data.accepted} accepted</p>
    <p className="scope-replay-subtitle">Reviewed judgments × scope check</p>
    {rows.map(row=><div className="scope-replay-row" key={row.label}>
      <span>{row.label} <b>{row.total}</b></span>
      <div className="scope-replay-track" role="img" aria-label={`${row.label}: ${row.accepted} accepted, ${row.pending} pending`}>
        <i className="scope-accepted" style={{width:`${pct(row.accepted,row.total)}%`}}/>
        <i className="scope-pending" style={{width:`${pct(row.pending,row.total)}%`}}/>
      </div>
      <small>{row.accepted} accepted · {row.pending} pending</small>
    </div>)}
    <div className="scope-replay-legend"><span><i className="scope-accepted"/>Accepted</span><span><i className="scope-pending"/>Pending review</span></div>
    <p className="compact-note">AI-assisted judgments were individually checked by humans, as reported by the user. Human-review independence was not established. Accepted is not proof of validity.</p>
  </figure>;
}

export function CompactExperimentResults() {
  const dynamic = useDynamicStudies();
  const retrieval = useRetrievalImprovement();
  if(!isCompactData(compactData))
    return <Alert role="alert" type="warning" showIcon title="Research results are unavailable" description="The source-bound dashboard data is invalid. Individual saved audits are still available below."/>;
  const data=compactData;
  const policy=data.strategies.map(s=>({name:s.label,old:pct(s.b_pass,s.b_decided),current:pct(s.c_pass,s.c_decided)}));
  const first=data.strategies.find(s=>s.id==='weak_first_hit');
  const relationship=data.strategies.find(s=>s.id==='strong_rule_based');
  const bKeys=['accuracy','freshness','conflict_resolution','appropriate_use'] as const;
  const bComparable=bKeys.filter(key=>first?.b_dimensions[key].decided && relationship?.b_dimensions[key].decided);
  const bHigher=bComparable.filter(key=>pct(relationship!.b_dimensions[key].passed,relationship!.b_dimensions[key].decided)>pct(first!.b_dimensions[key].passed,first!.b_dimensions[key].decided)).length;
  const bTied=bComparable.filter(key=>pct(relationship!.b_dimensions[key].passed,relationship!.b_dimensions[key].decided)===pct(first!.b_dimensions[key].passed,first!.b_dimensions[key].decided)).length;
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
      <div className="compact-intro"><h2>Experiment results</h2><p>Reviewed historical results and the latest compatible saved comparisons.</p><button type="button" onClick={()=>{dynamic.refresh();retrieval.refresh();}}>Refresh experiment results</button>{dynamic.data.errors.length>0 && <p role="alert">Some new results could not be loaded: {dynamic.data.errors.join('; ')}. Reviewed historical results remain available.</p>}{retrieval.error && <p role="alert">The retrieval comparison could not be loaded. Other results remain available.</p>}</div>
      <div className="compact-grid">
        <RetrievalImprovement data={retrieval.data}/>
        <Card title="A · Which audit method finds problems?" className="compact-a">
          <DynamicA data={dynamic.data}/><h3>Reviewed historical study</h3>
          <div className="compact-methods" role="img" aria-label="Predefined defects found by each audit method">
            {data.a.methods.map(m=><div className="compact-method" key={m.label}><span>{m.label}</span><div className="compact-track"><i style={{width:`${pct(m.detected,m.known)}%`}}/></div><strong>{m.detected}/{m.known}</strong></div>)}
          </div>
          <p className="compact-note">Each found the same 3 of 9 predefined defects. The expected method advantage was not observed.</p>
          <p className="compact-note">{data.a.histories} synthetic histories · {data.a.answers} answers · other failures fell outside the defect list.</p>
        </Card>
        <Card title="AC1 & AC2 · What changed?" className="compact-quality">
          <PairedChart data={measuresChart} oldName="Before" newName="After" height={190}/>
          <div className="compact-values"><div className="compact-value-header"><span>Measure</span><b>Before</b><b>After</b></div>{measures.map(x=><div key={x.name}><span>{x.name}</span><b>{ratio(x.old)}</b><b>{ratio(x.current)}</b></div>)}</div>
          <p className="compact-note">AC1: {data.ac1.histories} paired complete histories; {data.ac1.partial} partial runs excluded. ID matches may be partial, not strict recall or semantic accuracy.</p>
          <div className="scope-replay" aria-label="AC1 reviewed selected reference coverage">
            <p className="scope-replay-subtitle">AC1 · Selected reference review</p>
            {[
              {name:'Facts', full:data.ac1.reviewed.facts.full, partial:data.ac1.reviewed.facts.partial, missing:data.ac1.reviewed.facts.missing},
              {name:'Relationships', full:data.ac1.reviewed.relationships.correct_type, partial:data.ac1.reviewed.relationships.partial, missing:0},
            ].map(row=>{const total=row.full+row.partial+row.missing; return <div className="scope-replay-row" key={row.name}>
              <span>{row.name} <b>{total}</b></span>
              <div className="scope-replay-track" role="img" aria-label={`${row.name}: ${row.full} full or correct type, ${row.partial} partial, ${row.missing} missing`}>
                <i className="scope-accepted" style={{width:`${pct(row.full,total)}%`}}/><i className="scope-pending" style={{width:`${pct(row.partial,total)}%`}}/><i className="scope-rejected" style={{width:`${pct(row.missing,total)}%`}}/>
              </div><small>{row.full} full / correct · {row.partial} partial · {row.missing} missing</small>
            </div>})}
            <p className="compact-note">{data.ac1.reviewed.histories} complete histories; selected references are not exhaustive. Seven disagreements were adjudicated by the user.</p>
          </div>
          <p className="compact-note">AC2: {data.ac2.histories} histories; valid / generated questions. Includes the later two-person wording recheck: one question in each group changed to invalid. After: {data.ac2.candidate.invalid}/{data.ac2.candidate.generated} invalid; the gate accepted {data.ac2.candidate.gate_accepted_human_invalid} of them. Missing outputs are excluded.</p>
          <FourDimensionReview data={data.ac2.four_dimension_review}/>
          <figure className="scope-replay" aria-label="Latest AC2 development question review">
            <figcaption>Latest development · Accuracy questions</figcaption>
            <div className="scope-replay-row"><span>Reviewed questions</span><div className="scope-replay-track" role="img" aria-label={`${data.ac2.latest_development.valid} valid, ${data.ac2.latest_development.invalid} invalid`}>
              <i className="scope-accepted" style={{width:`${pct(data.ac2.latest_development.valid,data.ac2.latest_development.total)}%`}}/><i className="scope-rejected" style={{width:`${pct(data.ac2.latest_development.invalid,data.ac2.latest_development.total)}%`}}/>
            </div><small>{data.ac2.latest_development.valid} valid · {data.ac2.latest_development.invalid} invalid</small></div>
            <p className="compact-note">{data.ac2.latest_development.saved_histories}/{data.ac2.latest_development.histories} related synthetic histories saved questions; {data.ac2.latest_development.histories-data.ac2.latest_development.saved_histories} saved none. Two independent humans checked AI-assisted reviews, as reported by the user. Earlier AI opinions differed on one invalid-versus-valid judgment.</p>
          </figure>
          <ProspectiveChart data={data.ac2.prospective}/>
        </Card>
        <Card title="B & C · Four memory strategies" className="compact-policies">
          <DynamicBC data={dynamic.data}/><h3>Reviewed historical study</h3>
          <PairedChart data={policy} oldName="B · synthetic" newName="C · LongMemEval" labelWidth={162} height={230}/>
          <div className="compact-values"><div className="compact-value-header"><span>Strategy</span><b>B · synthetic</b><b>C · benchmark</b></div>{data.strategies.map(s=><div key={s.id}><span>{s.label}</span><b>{display(s.b_pass,s.b_decided)}</b><b>{display(s.c_pass,s.c_decided)}</b></div>)}</div>
          <p className="compact-note">B: 3 histories × 3 repeats, {data.strategies[0].b_total} answers per strategy. C: 30 selected cases × 3 repeats, {data.strategies[0].c_total} per strategy; {data.strategies.reduce((a,s)=>a+s.c_uncertain,0)} unresolved answers excluded from decided rates. Repeats are not independent cases.</p>
          <h3>B · Results by ability</h3>
          <BAbilityChart strategies={data.strategies}/>
          <p className="compact-note">B uses 3 related histories and 3 repeats. Relationship-priority is higher than First-match in {bHigher}/{bComparable.length} comparable abilities; {bTied} tied. Repeats are not independent cases.</p>
          <p className="compact-note">Example: Relationship-priority omitted the old database; Match the task and project retrieved both versions. Human reviewers failed the first answer, but the saved automatic judge passed both. <a href={`/audits/${data.b_example.relationship_run_id}`}>Inspect the first audit</a> · <a href={`/audits/${data.b_example.scope_run_id}`}>Inspect the comparison</a></p>
          <figure className="scope-replay" aria-label="Development retest of update history retrieval">
            <figcaption>New-source development retest</figcaption>
            {[
              {label:'Change history · original',value:data.b_example.development_original_pass},
              {label:'Change history · candidate',value:data.b_example.development_candidate_pass},
              {label:'Current value · original',value:data.b_example.development_current_original_pass},
              {label:'Current value · candidate',value:data.b_example.development_current_candidate_pass},
            ].map(item=><div className="scope-replay-row" key={item.label}>
              <span>{item.label}</span><div className="scope-replay-track"><i className="scope-accepted" style={{width:`${pct(item.value,data.b_example.development_total)}%`}}/></div>
              <small>{item.value}/{data.b_example.development_total} pass</small>
            </div>)}
            <p className="compact-note">Four similar synthetic histories · isolated candidate. Two independent humans checked AI-assisted reviews, as reported by the user; exposure to scores or other AI opinions was not established.</p>
          </figure>
          <p className="compact-note">Separate original Auditor / LongMemEval ranking check: same two-policy order in {data.c_reference.agreement.agreed_repetitions}/{data.c_reference.agreement.total_repetitions} repeats on {data.c_reference.cases}/{data.c_reference.available_cases} benchmark cases. It is not a four-strategy ranking agreement.</p>
        </Card>
        <Card title="Auditor · Before and after improvement" className="compact-auditor">
          <PairedChart data={scorer} oldName="Before" newName="After" height={190}/>
          <div className="compact-values"><div className="compact-value-header"><span>Measure</span><b>Before</b><b>After</b></div>{evalRows.map(x=><div key={x.key}><span>{x.name}</span><b>{ratio(data.ac3.old[x.key])}</b><b>{ratio(data.ac3.new[x.key])}</b></div>)}</div>
          <p className="compact-note">Same {data.ac3.answers} answers · {data.ac3.histories} synthetic histories · {data.ac3.human_consensus} human-consensus answers, {data.ac3.human_unresolved} disagreements. Old classification: 0/55 were classified, not 55 incorrect labels.</p>
          <p className="compact-note">Detection difference: history-resampling range {(100*data.ac3.detection_difference_interval.lower).toFixed(1)} to {(100*data.ac3.detection_difference_interval.upper).toFixed(1)} percentage points{data.ac3.detection_difference_interval.lower<=0 && data.ac3.detection_difference_interval.upper>=0 ? '; includes no improvement' : ''}. Descriptive for these histories.</p>
          <p className="compact-note">After is an optional reassessment, not the default evaluator. Thresholds were met on this sample; zero observed false positives does not establish zero population error.</p>
        </Card>
      </div>
      <p className="compact-evidence">Some studies used user-reported independent human reviews with AI assistance; reviewer identity and independence were not independently authenticated. Selected synthetic and benchmark subsets do not establish population-wide performance. <a href="/research-results">Research evidence and limitations →</a></p>
    </section>
  </>;
}
