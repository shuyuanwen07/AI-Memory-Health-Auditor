import { Alert, Card } from 'antd';
import compactData from '../data/compactFinalDashboard.json';
import experimentAHistoricalMetrics from '../data/experimentAHistoricalMetrics.json';
import { Bar, BarChart, CartesianGrid, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { DynamicA, useDynamicStudies } from './DynamicStudies';
import { useEffect, useState } from 'react';
import type { BenchmarkPlan } from './BenchmarkExecutionPlan';

type DynamicStudyData = ReturnType<typeof useDynamicStudies>['data'];

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
type QuestionSlotCounts = {planned_slots:number;saved:number;valid:number;invalid:number;unresolved:number;missing:number};
type QuestionExecutionCheck = {planned:40;answers:number;assessments:number;status:'complete'|'partial';basis:'automatic'};
type TenSceneRetest = QuestionSlotCounts & {histories:10;review_status:'ai_preliminary'|'human_confirmed';source_unchanged:true;baseline:QuestionSlotCounts;evidence_path:string;revised_questions?:number;execution_check?:unknown;confirmed_relationships?:unknown;unresolved_relationships?:unknown};
function tenSceneRelationships(value:TenSceneRetest) {
  const {confirmed_relationships:confirmed,unresolved_relationships:unresolved}=value;
  if(typeof confirmed!=='number' || typeof unresolved!=='number'
    || !Number.isInteger(confirmed) || !Number.isInteger(unresolved)
    || confirmed<0 || unresolved<0 || confirmed+unresolved!==32)return null;
  return {confirmed,unresolved};
}
function isQuestionExecutionCheck(value:unknown):value is QuestionExecutionCheck {
  if(!object(value))return false;
  const {planned,answers,assessments,status,basis}=value;
  return planned===40 && basis==='automatic' && (status==='complete' || status==='partial')
    && typeof answers==='number' && Number.isInteger(answers) && answers>=0 && answers<=planned
    && typeof assessments==='number' && Number.isInteger(assessments) && assessments>=0 && assessments<=answers
    && (status!=='complete' || (answers===planned && assessments===planned));
}
function isQuestionSlotCounts(value:unknown):value is QuestionSlotCounts {
  if(!object(value))return false;
  const keys=['planned_slots','saved','valid','invalid','unresolved','missing'] as const;
  if(!keys.every(k=>Number.isInteger(value[k]) && (value[k] as number)>=0))return false;
  const v=value as unknown as QuestionSlotCounts;
  return v.valid+v.invalid+v.unresolved===v.saved && v.saved+v.missing===v.planned_slots;
}
function isTenSceneRetest(value:unknown):value is TenSceneRetest {
  if(!object(value))return false;
  const {baseline,histories,source_unchanged,review_status,evidence_path,revised_questions}=value;
  if(!isQuestionSlotCounts(value) || !isQuestionSlotCounts(baseline))return false;
  return histories===10 && value.planned_slots===40 && source_unchanged===true
    && (review_status==='ai_preliminary' || review_status==='human_confirmed')
    && typeof evidence_path==='string' && evidence_path.trim().length>0
    && (revised_questions===undefined || (typeof revised_questions==='number' && Number.isInteger(revised_questions) && revised_questions>=0 && revised_questions<=value.saved))
    && baseline.planned_slots===40 && baseline.saved===28 && baseline.valid===14
    && baseline.invalid===14 && baseline.unresolved===0 && baseline.missing===12;
}
function tenSceneEvidenceHref(value:string) {
  return (/^\/(?!\/)/.test(value) && !value.includes('\\')) || /^https:\/\//i.test(value) ? value : '/research-results';
}
function QuestionSlotBar({label,counts}:{label:string;counts:QuestionSlotCounts}) {
  return <div className="scope-replay-row"><span>{label}</span>
    <div className="scope-replay-track" role="img" aria-label={`${label}: ${counts.valid} valid, ${counts.invalid} invalid, ${counts.unresolved} unresolved, ${counts.missing} not generated, out of ${counts.planned_slots} planned`}>
      <i className="scope-accepted" style={{width:`${pct(counts.valid,counts.planned_slots)}%`}}/>
      <i className="scope-rejected" style={{width:`${pct(counts.invalid,counts.planned_slots)}%`}}/>
      <i className="scope-pending" style={{width:`${pct(counts.unresolved,counts.planned_slots)}%`}}/>
      <i style={{width:`${pct(counts.missing,counts.planned_slots)}%`,background:'#e8edf2'}}/>
    </div>
    <small><b>{counts.valid}/{counts.planned_slots} valid</b> · {counts.invalid} invalid · {counts.unresolved} unresolved · {counts.missing} not generated</small>
  </div>;
}
export function AstraCapacitySummary({refreshToken=0}:{refreshToken?:number}) {
  const [r,setResult]=useState<{cases:number;before:{passed:number;answered:number;planned:number};after:{passed:number;answered:number;planned:number;missing:number}}|null>(null);
  useEffect(()=>{let active=true;const refresh=()=>fetch('/reports/c-astra-capacity-development-v1.json',{cache:'no-store'}).then(v=>v.ok?v.json():null).then(v=>{
    const valid=(x:{passed:number;answered:number;planned:number}|undefined)=>x && [x.passed,x.answered,x.planned].every(n=>Number.isInteger(n)&&n>=0) && x.passed<=x.answered && x.answered<=x.planned;
    if(active && v?.format==='c-astra-capacity-development-v1' && v.review_status==='human_confirmed' && Number.isInteger(v.cases) && v.cases>0 && valid(v.before) && valid(v.after) && Number.isInteger(v.after.missing) && v.after.missing===v.after.planned-v.after.answered)setResult(v);
  }).catch(()=>{});void refresh();const timer=window.setInterval(()=>void refresh(),30000);return()=>{active=false;window.clearInterval(timer);};},[refreshToken]);
  if(!r)return null;
  return <p className="compact-note" aria-label="Astra capacity development comparison">Separate Astra development check · {r.cases} cases: capacity 50, {r.before.passed}/{r.before.answered} passed; capacity 500, {r.after.passed}/{r.after.answered} passed and {r.after.missing} request incomplete. Human-checked AI reviews; selected development cases, separate from the benchmark plan. <a href="/research-results">Evidence and limits →</a></p>;
}
export function AstraExtractionReview({refreshToken=0}:{refreshToken?:number}) {
  const [result,setResult]=useState<{histories:number;counts:Record<string,Record<string,number>>}|null>(null);
  useEffect(()=>{let active=true; const refresh=()=>fetch('/reports/ac1-astra-four-source-v1.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(v=>{
    const names=['candidates','reference_facts','extracted_relationships','reference_relationships'];
    if(active && v?.review_status==='human_confirmed' && Number.isInteger(v.histories) && v.histories>0 && names.every(n=>object(v.counts?.[n]) && Object.values(v.counts[n]).every(x=>Number.isInteger(x) && (x as number)>=0))) setResult(v);
  }).catch(()=>{}); void refresh();const timer=window.setInterval(()=>void refresh(),30000);return ()=>{active=false;window.clearInterval(timer);};},[refreshToken]);
  if(!result)return null;
  const rows=[{label:'Source-supported candidates',key:'candidates',success:'supported'}, {label:'Fully covered reference records',key:'reference_facts',success:'full'}, {label:'Correct extracted relationships',key:'extracted_relationships',success:'correct'}, {label:'Covered reference relationships',key:'reference_relationships',success:'full'}];
  return <figure className="scope-replay" aria-label="Astra extraction source review"><figcaption>AC1 · Astra source-only extraction</figcaption>
    {rows.map(row=>{const counts=result.counts[row.key], total=Object.values(counts).reduce((a,b)=>a+b,0),good=counts[row.success]??0; return <div className="scope-replay-row" key={row.key}><span>{row.label}</span><div className="scope-replay-track"><i className="scope-accepted" style={{width:`${pct(good,total)}%`}}/></div><small>{display(good,total)}</small></div>;})}
    <p className="compact-note">{result.histories} related synthetic histories · human-checked AI reviews. Records may combine several facts; not strict atomic recall.</p>
  </figure>;
}
export function AstraDiverseQuestions({refreshToken=0}:{refreshToken?:number}) {
  const [r,setResult]=useState<{planned_histories:number;completed_histories:number;planned_question_slots:number;saved_questions:number;all_valid:number;invalid:number;uncertain:number;guard_development?:{invalid_rejected:number;total_invalid:number;valid_accepted:number;total_valid:number};guard_retest?:{histories:number;completed:number;planned_slots:number;generated:number};repair_retest?:{histories:number;completed:number;planned_slots:number;generated:number;review_call_failed_histories:number};latest_repair_retest?:{histories:number;planned_slots:number;generated:number;ai_valid:number;human_review:string};ten_scene_retest?:unknown}|null>(null);
  useEffect(()=>{let active=true;const refresh=()=>fetch('/reports/ac2-astra-ten-source-v1.json',{cache:'no-store'}).then(v=>v.ok?v.json():null).then(v=>{
    const keys=['planned_histories','completed_histories','planned_question_slots','saved_questions','all_valid','invalid','uncertain'];
    if(active && v?.review_status==='human_confirmed' && keys.every(k=>Number.isInteger(v[k]) && v[k]>=0) && v.all_valid+v.invalid+v.uncertain===v.saved_questions && v.saved_questions<=v.planned_question_slots && v.completed_histories<=v.planned_histories) setResult(v);
  }).catch(()=>{});void refresh();const timer=window.setInterval(()=>void refresh(),30000);return ()=>{active=false;window.clearInterval(timer);};},[refreshToken]);
  if(!r)return null;
  if(isTenSceneRetest(r.ten_scene_retest)) {
    const latest=r.ten_scene_retest;
    const human=latest.review_status==='human_confirmed';
    const relationships=tenSceneRelationships(latest);
    return <figure className="scope-replay" aria-label="AC2 ten-scene product-flow retest"><figcaption>AC2 · Ten-scene retest</figcaption>
      <div className="scope-replay-legend"><span><i className="scope-accepted"/>Valid</span><span><i className="scope-rejected"/>Invalid</span><span><i className="scope-pending"/>Unresolved</span><span><i style={{background:'#e8edf2'}}/>Not generated</span></div>
      <QuestionSlotBar label="Original · human checked" counts={latest.baseline}/>
      <QuestionSlotBar label={human?'Latest · human checked':'Latest · AI preliminary'} counts={latest}/>
      <p className="compact-note">10 unchanged histories · 40 planned questions per arm. {human?'Human-confirmed AI-assisted reviews.':'Two independent AI reviews; human confirmation pending.'}{latest.revised_questions===2?' Includes two post-review regenerations.':latest.revised_questions?` Includes ${latest.revised_questions} post-review regenerations.`:''} Related development histories. <a href={tenSceneEvidenceHref(latest.evidence_path)}>Retest evidence →</a></p>
      {relationships && <p className="compact-note" aria-label="AC2 relationship review counts">Relationships: {relationships.confirmed} confirmed · {relationships.unresolved} unresolved.</p>}
      {isQuestionExecutionCheck(latest.execution_check) && <p className="compact-note" aria-label="AC2 question execution check">Execution check: {latest.execution_check.answers}/{latest.execution_check.planned} answered · {latest.execution_check.assessments}/{latest.execution_check.planned} automatically assessed.</p>}
    </figure>;
  }
  const missing=r.planned_question_slots-r.saved_questions;
  return <figure className="scope-replay" aria-label="Astra diverse-history product question review"><figcaption>AC2 · Diverse-history product-flow check</figcaption>
    {r.ten_scene_retest!==undefined && <p className="compact-note" role="alert">Latest ten-scene comparison unavailable: counts or study metadata do not match. Showing the retained earlier study.</p>}
    <div className="scope-replay-row"><span>Planned questions <b>{r.planned_question_slots}</b></span><div className="scope-replay-track" role="img" aria-label={`${r.all_valid} valid, ${r.invalid} invalid, ${r.uncertain} unresolved, ${missing} not generated`}><i className="scope-accepted" style={{width:`${pct(r.all_valid,r.planned_question_slots)}%`}}/><i className="scope-rejected" style={{width:`${pct(r.invalid,r.planned_question_slots)}%`}}/><i className="scope-pending" style={{width:`${pct(r.uncertain,r.planned_question_slots)}%`}}/></div><small>{r.all_valid} valid · {r.invalid} invalid · {r.uncertain} unresolved · {missing} not generated</small></div>
    <p className="compact-note">{r.completed_histories}/{r.planned_histories} histories produced questions. Human-checked AI reviews · related synthetic sources; operator confirmation was simulated.</p>
    {r.latest_repair_retest && <p className="compact-note" aria-label="Latest generation repair retest">Latest revised-source retest: {r.latest_repair_retest.generated}/{r.latest_repair_retest.planned_slots} saved · two AI reviews: {r.latest_repair_retest.ai_valid} valid · {r.latest_repair_retest.human_review==='confirmed'?'human confirmed':'human confirmation pending'}. {r.latest_repair_retest.histories} development history; not a repeat of the ten-history study.</p>}
  </figure>;
}
export function AstraPolicyReview({refreshToken=0,data}:{refreshToken?:number;data?:DynamicStudyData}) {
  const [r,setResult]=useState<{status:string;experiment_ids?:string[];source_created_at?:string;saved_answers:number;planned_answers:number;not_completed:number;complete_paired_only:Record<string,{saved:number;pass:number;fail:number;unresolved:number}>}|null>(null);
  useEffect(()=>{let active=true;const refresh=()=>fetch('/reports/b-astra-four-strategy-v1.json',{cache:'no-store'}).then(v=>v.ok?v.json():null).then(v=>{
    const keys=['weak_first_hit','strong_rule_based','scope_aware','temporal_importance'];
    if(active && v?.format==='b-astra-four-strategy-ai-review-v1' && keys.every(k=>{const q=v.complete_paired_only?.[k];return q && ['saved','pass','fail','unresolved'].every(f=>Number.isInteger(q[f]) && q[f]>=0) && q.pass+q.fail+q.unresolved===q.saved;}))setResult(v);
  }).catch(()=>{});void refresh();const timer=window.setInterval(()=>void refresh(),30000);return()=>{active=false;window.clearInterval(timer);};},[refreshToken]);
  if(!r)return null;
  const current=data?.b;
  const showLive=current && Array.isArray(r.experiment_ids) && typeof r.source_created_at==='string'
    && !r.experiment_ids.includes(current.experiment.experiment_id)
    && Date.parse(current.experiment.created_at)>Date.parse(r.source_created_at);
  if(showLive && data) return <CompactLivePolicy data={data}/>;
  const names:Record<string,string>={weak_first_hit:'First-match retrieval',strong_rule_based:'Relationship-priority retrieval',scope_aware:'Match the task and project',temporal_importance:'Consider time and importance'};
  return <figure className="scope-replay" aria-label="Astra four-strategy paired review"><figcaption>Latest Astra · Four strategies</figcaption>{Object.entries(names).map(([k,label])=>{const q=r.complete_paired_only[k];return <div className="scope-replay-row" key={k}><span>{label}</span><div className="scope-replay-track"><i className="scope-accepted" style={{width:`${pct(q.pass,q.saved)}%`}}/></div><small>{display(q.pass,q.saved)} pass · {q.unresolved} unresolved</small></div>;})}<p className="compact-note">{r.status==='human_confirmed'?'User-reported independent human checks of AI-assisted reviews.':'Two independent AI reviews; human confirmation pending.'} Three paired histories · one run each. {r.saved_answers}/{r.planned_answers} answers saved overall; {r.not_completed} missing. Incomplete fourth history excluded.</p></figure>;
}
const POLICY_NAMES:Record<string,string>={weak_first_hit:'First-match retrieval',strong_rule_based:'Relationship-priority retrieval',scope_aware:'Match the task and project',temporal_importance:'Consider time and importance'};

function CompactLivePolicy({data}:{data:DynamicStudyData}) {
  const group=data.b;
  if(!group)return null;
  const rows=group.conditions.filter(c=>c.memory_strategy in POLICY_NAMES);
  const human=rows.every(c=>(data.bHuman[c.condition_id]?.reviewed??0)>0);
  const missing=rows.reduce((n,c)=>n+Math.max(0,c.planned_runs-c.completed_runs),0);
  return <figure className="scope-replay" aria-label="Latest saved four-strategy results"><figcaption>{group.experiment.label}</figcaption>
    {rows.map(c=>{const ref=data.bHuman[c.condition_id];const passed=human?ref.passed:c.tests_passed,decided=human?ref.decided:c.tests_total;
      const unresolved=human?ref.unresolved:c.dimensions.reduce((n,d)=>n+(d.uncertain_count??0),0);
      return <div className="scope-replay-row" key={c.condition_id}><span>{POLICY_NAMES[c.memory_strategy]}</span><div className="scope-replay-track"><i className="scope-accepted" style={{width:`${pct(passed,decided)}%`}}/></div><small>{decided?display(passed,decided):'No agreed answers'} · {unresolved} unresolved{human?` · ${Math.max(0,c.tests_total-ref.reviewed)} unreviewed`:''}</small></div>;
    })}
    <p className="compact-note">{human?'Independent human-review consensus; declared identities are not authenticated.':'Automatic saved assessments; human review incomplete.'} {rows[0]?.model} · {missing} planned runs incomplete. Repeated answers reuse cases. <a href={`/experiments/${group.experiment.experiment_id}`}>Source group →</a></p>
  </figure>;
}

export function CompactBenchmarkResults({plan,strategies}:{plan:BenchmarkPlan|null;strategies:Strategy[]}) {
  const completed=plan?Object.values(plan.executions).filter(e=>e.status==='COMPLETED' && e.dashboard_summary):[];
  if(!plan || !completed.length) return <figure className="scope-replay" aria-label="Reviewed LongMemEval historical strategy results"><figcaption>Reviewed historical benchmark subset</figcaption>
    {strategies.map(row=><div className="scope-replay-row" key={row.id}><span>{row.label}</span><div className="scope-replay-track"><i className="scope-accepted" style={{width:`${pct(row.c_pass,row.c_decided)}%`}}/></div><small>{display(row.c_pass,row.c_decided)} pass · {row.c_uncertain} unresolved</small></div>)}
    <p className="compact-note">30 selected cases × 3 repeats · {strategies[0].c_total} answers per strategy. {strategies.reduce((n,row)=>n+row.c_uncertain,0)} unresolved excluded from decided rates; repeats reuse cases. A separate model and study from B.</p>
  </figure>;
  const human=completed.some(e=>(e.human_reviews?.at(-1)?.reviewers.length??0)>=2);
  const totals=new Map<string,{passed:number;decided:number;total:number;unresolved:number}>();
  for(const execution of completed) {
    const reviewers=execution.human_reviews?.at(-1)?.reviewers??[];
    for(const condition of execution.dashboard_summary!.conditions) {
      const row=totals.get(condition.strategy)??{passed:0,decided:0,total:0,unresolved:0};row.total+=condition.total;
      if(human) {
        if(!condition.case_ids || condition.case_ids.length!==condition.total) row.unresolved+=condition.total;
        else {
          for(const id of condition.case_ids) {
            const labels=reviewers.map(r=>r.judgments.find(j=>j.strategy===condition.strategy && j.case_id===id)?.verdict);
            if(labels.length>=2 && labels.every(v=>v && v===labels[0] && v!=='uncertain')) {row.decided++;if(labels[0]==='pass')row.passed++;}
            else row.unresolved++;
          }
        }
      } else {row.passed+=condition.matched;row.decided+=condition.total;}
      totals.set(condition.strategy,row);
    }
  }
  const planned=plan.protocol?.trials?.length??Object.keys(plan.executions).length;
  const model=plan.protocol?.benchmark?.configuration?.model;
  const cases=plan.protocol?.benchmark?.case_ids?.length;
  return <figure className="scope-replay" aria-label="Latest saved benchmark plan results"><figcaption>{human?'Human-review consensus':'Automatic lexical match'} · completed trials combined</figcaption>
    {[...totals].map(([key,row])=><div className="scope-replay-row" key={key}><span>{POLICY_NAMES[key]??key}</span><div className="scope-replay-track"><i className="scope-accepted" style={{width:`${pct(row.passed,row.decided)}%`}}/></div><small>{row.decided?display(row.passed,row.decided):'Not measured'}{human?` · ${row.decided}/${row.total} agreed · ${row.unresolved} unresolved or unreviewed`:''}</small></div>)}
    <p className="compact-note">{cases?`${cases} selected cases · `:''}{completed.length}/{planned} planned trials complete · {Math.max(0,planned-completed.length)} incomplete. {typeof model==='string'?model:'Saved benchmark model'} · repeats reuse cases. {human?'Reviewer independence is declared.':'Lexical match is not a human or official benchmark score.'} <a href="/experiments">Plan evidence →</a></p>
  </figure>;
}

export function AstraComparison({refreshToken=0,mode='history'}:{refreshToken?:number;mode?:'history'|'writer'}) {
  const [result,setResult]=useState<{histories:number;scheduled_slots:number;baseline:{valid:number};astra:{valid:number};product_followup?:{histories:number;generated:number;review_status:string;reviewed_valid?:number;reviewed_invalid?:number;reviewed_unresolved?:number};end_to_end_smoke?:{histories:number;questions:number;automatic_passed:number;failure_categories_disputed:number;review_status:string;human_passed?:number;human_unclassified_failures?:number};retrieval_followup?:{histories:number;questions:number;before_pass:number;after_pass:number;review_status:string};writer_followup?:{histories:number;questions:number;before_pass:number;after_pass:number;review_status:string};writer_four_followup?:{histories:number;questions:number;before_pass:number;after_pass:number;review_status:string;improved:number;worsened:number}} | null>(null);
  useEffect(()=>{let active=true; const refresh=()=>fetch('/reports/ac2-astra-comparison-v1.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(value=>{
    if(active && value?.format==='ac2-astra-comparison-v1' && value.histories===30 && value.scheduled_slots===120
      && Number.isInteger(value.baseline?.valid) && Number.isInteger(value.astra?.valid)
      && value.baseline.valid>=0 && value.baseline.valid<=120 && value.astra.valid>=0 && value.astra.valid<=120) setResult(value);
  }).catch(()=>{}); void refresh(); const timer=window.setInterval(()=>void refresh(),30000); return ()=>{active=false;window.clearInterval(timer);};},[refreshToken]);
  if(!result)return null;
  if(mode==='writer') {
    const writer=result.writer_four_followup;
    if(!writer || writer.review_status!=='human_confirmed') return <p className="compact-note">Writer repair review is not available.</p>;
    return <figure className="scope-replay" aria-label="Four-history writer repair results"><figcaption>Missing venue records → structured memory writer</figcaption>
      {[{label:'Before',value:writer.before_pass},{label:'After',value:writer.after_pass}].map(row=><div className="scope-replay-row" key={row.label}><span>{row.label}</span><div className="scope-replay-track"><i className="scope-accepted" style={{width:`${pct(row.value,writer.questions)}%`}}/></div><small>{display(row.value,writer.questions)} passed</small></div>)}
      <p className="compact-note">{writer.improved} improved · {writer.worsened} worsened · {writer.questions} paired questions · {writer.histories} related synthetic histories. Human-checked AI reviews, as reported by the user; not held-out.</p>
    </figure>;
  }
  return <figure className="scope-replay" aria-label="AC2 Astra question generation comparison">
    <figcaption>AC2 · Question generation on the same histories</figcaption>
    {[{label:'Rule generator v36',valid:result.baseline.valid},{label:'GPT-6 Astra · max',valid:result.astra.valid}].map(row=><div className="scope-replay-row" key={row.label}>
      <span>{row.label}</span><div className="scope-replay-track"><i className="scope-accepted" style={{width:`${pct(row.valid,result.scheduled_slots)}%`}}/></div>
      <small>{display(row.valid,result.scheduled_slots)} valid</small>
    </div>)}
    <p className="compact-note">{result.histories} previously studied synthetic histories. The user reports two independent humans checked the AI-assisted Astra reviews; reviewer identity and exposure to AI judgments were not independently verified. Different generator and review procedures; not a model-only comparison or held-out result.</p>
    {result.product_followup?.review_status==='pending' && <p className="compact-note">New product-flow follow-up: {result.product_followup.generated} questions across {result.product_followup.histories} related synthetic histories · human validity review pending. This saved research snapshot is updated after review.</p>}
    {result.product_followup?.review_status==='human_confirmed' && <p className="compact-note">Product-flow follow-up: {result.product_followup.reviewed_valid}/{result.product_followup.generated} agreed valid · {result.product_followup.reviewed_invalid} invalid · {result.product_followup.reviewed_unresolved} unresolved. User-reported human checks of AI-assisted judgments; {result.product_followup.histories} related synthetic histories.</p>}
    {result.end_to_end_smoke?.review_status==='pending' && <p className="compact-note">Separate {result.end_to_end_smoke.histories}-history integration smoke: {result.end_to_end_smoke.automatic_passed}/{result.end_to_end_smoke.questions} automatically passed · {result.end_to_end_smoke.failure_categories_disputed} failure categories disputed and awaiting human review.</p>}
    {result.end_to_end_smoke?.review_status==='human_adjudicated' && <p className="compact-note">Separate {result.end_to_end_smoke.histories}-history integration smoke: {result.end_to_end_smoke.human_passed}/{result.end_to_end_smoke.questions} passed after user-reported adjudication · {result.end_to_end_smoke.human_unclassified_failures} failure unclassified. This was a shared review of an AI recommendation, not a blind review.</p>}
    {result.retrieval_followup?.review_status==='ai_only' && <p className="compact-note">Exploratory Astra retrieval retest: {result.retrieval_followup.before_pass}/{result.retrieval_followup.questions} → {result.retrieval_followup.after_pass}/{result.retrieval_followup.questions} passed in two AI reviews · human review pending. One previously studied synthetic history; not held-out evidence.</p>}
    {result.retrieval_followup?.review_status==='human_confirmed' && <p className="compact-note">Exploratory Astra retrieval retest: {result.retrieval_followup.before_pass}/{result.retrieval_followup.questions} → {result.retrieval_followup.after_pass}/{result.retrieval_followup.questions} passed. Two people independently checked AI-assisted reviews as reported by the user. One previously studied synthetic history; not held-out evidence.</p>}
    {result.writer_followup?.review_status==='ai_only' && <p className="compact-note">Exploratory Astra memory-writer retest: {result.writer_followup.before_pass}/{result.writer_followup.questions} → {result.writer_followup.after_pass}/{result.writer_followup.questions} passed in two AI reviews · human review pending. Same previously studied synthetic history.</p>}
    {result.writer_followup?.review_status==='human_confirmed' && <p className="compact-note">Exploratory Astra memory-writer retest: {result.writer_followup.before_pass}/{result.writer_followup.questions} → {result.writer_followup.after_pass}/{result.writer_followup.questions} passed. Two people independently checked AI-assisted reviews as reported by the user. Same previously studied synthetic history; not held-out evidence.</p>}
    {result.writer_four_followup?.review_status==='human_confirmed' && <p className="compact-note">Four-history writer comparison: {result.writer_four_followup.before_pass}/{result.writer_four_followup.questions} → {result.writer_four_followup.after_pass}/{result.writer_four_followup.questions} passed · {result.writer_four_followup.improved} improved · {result.writer_four_followup.worsened} worsened. User reports two independent people checked AI-assisted reviews. Related synthetic histories; not a population estimate.</p>}
  </figure>;
}
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

export function FourDimensionReview({data}:{data:{histories:number;dimensions:ReviewedDimension[]}}) {
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

export function BAbilityChart({strategies}:{strategies:Strategy[]}) {
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

export function ProspectiveChart({data}:{data:Prospective}) {
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
  const [researchRefresh,setResearchRefresh]=useState(0);
  if(!isCompactData(compactData))
    return <Alert role="alert" type="warning" showIcon title="Research results are unavailable" description="The source-bound dashboard data is invalid. Individual saved audits are still available below."/>;
  const data=compactData;
  const evalRows=[
    {name:'Detect failures',key:'failure_recall_conservative' as const},
    {name:'Classify failures',key:'classification_accuracy_conservative' as const},
    {name:'False positives ↓',key:'false_positive_rate_decided' as const},
  ];
  const scorer=evalRows.map(x=>({name:x.name,old:100*(data.ac3.old[x.key].value??0),current:100*(data.ac3.new[x.key].value??0)}));
  const hasCurrentA=!!(dynamic.data.campaign || dynamic.data.a);
  const latestA=dynamic.data.campaign ? {...dynamic.data,a:null} : dynamic.data;
  return <section aria-label="Final experiment results" className="compact-results compact-results-latest">
    <div className="compact-intro"><h2>Experiment results</h2><p>Latest studies · review status and missing results stay visible.</p><button type="button" onClick={()=>{dynamic.refresh();setResearchRefresh(n=>n+1);}}>Refresh experiment results</button>{dynamic.data.errors.length>0 && <p role="alert">Some live results could not be loaded. <a href="/experiments">Inspect experiment history →</a></p>}</div>
    <div className="compact-grid">
      <Card title="A · Audit methods" className="compact-a">
        {hasCurrentA ? <DynamicA data={latestA}/> : <>
          <div className="compact-methods" role="img" aria-label="Predefined defects found by each audit method">
            {data.a.methods.map(m=><div className="compact-method" key={m.label}><span>{m.label}</span><div className="compact-track"><i style={{width:`${pct(m.detected,m.known)}%`}}/></div><strong>{m.detected}/{m.known}</strong></div>)}
          </div>
          <p className="compact-note">Reviewed historical study: each method found 3/9 predefined defects and detected {experimentAHistoricalMetrics.methods[0].failure_recall.numerator}/{experimentAHistoricalMetrics.methods[0].failure_recall.denominator} labelled failures. No method advantage observed; three related histories.</p>
        </>}
      </Card>
      <Card title="AC1 & AC2 · Memory and question quality" className="compact-quality">
        <AstraExtractionReview refreshToken={researchRefresh}/>
        <AstraDiverseQuestions refreshToken={researchRefresh}/>
      </Card>
      <Card title="Tutor · Diagnose, repair, retest" className="compact-repair">
        <AstraComparison refreshToken={researchRefresh} mode="writer"/>
      </Card>
      <Card title="B · Four memory strategies" className="compact-policies">
        <AstraPolicyReview refreshToken={researchRefresh} data={dynamic.data}/>
      </Card>
      <Card title={dynamic.data.c ? 'C · Latest benchmark plan' : 'C · LongMemEval · GPT-6 Luna'} className="compact-benchmark">
        <CompactBenchmarkResults plan={dynamic.data.c} strategies={data.strategies}/>
        <AstraCapacitySummary refreshToken={researchRefresh}/>
      </Card>
      <Card title="AC3 · Auditor before and after" className="compact-auditor">
        <PairedChart data={scorer} oldName="Before" newName="After" height={190}/>
        <div className="compact-values"><div className="compact-value-header"><span>Measure</span><b>Before</b><b>After</b></div>{evalRows.map(x=><div key={x.key}><span>{x.name}</span><b>{ratio(data.ac3.old[x.key])}</b><b>{ratio(data.ac3.new[x.key])}</b></div>)}</div>
        <p className="compact-note">{data.ac3.human_consensus}/{data.ac3.answers} human-consensus answers · {data.ac3.histories} related synthetic histories · {data.ac3.human_unresolved} disagreements. Before: 0/55 failures classified. After is an optional reassessment.</p>
        <p className="compact-note">Detection difference range: {(100*data.ac3.detection_difference_interval.lower).toFixed(1)} to {(100*data.ac3.detection_difference_interval.upper).toFixed(1)} percentage points; includes no improvement. Zero observed false positives does not imply zero population error.</p>
      </Card>
    </div>
    <p className="compact-evidence">Human-review independence is user-reported; reviews used AI assistance. Selected synthetic and benchmark subsets do not establish population-wide performance. <a href="/research-results">Historical results, evidence and limitations →</a> · <a href="/experiments">All experiment records →</a></p>
  </section>;
}
