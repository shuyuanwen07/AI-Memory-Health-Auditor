import { useEffect, useState } from 'react';
import { api } from '../services/api';
import { memoryStrategyLabel } from '../services/display';
import type { Experiment, ExperimentAnalytics, MemoryStrategy } from '../types/domain';
import type { BenchmarkPlan } from './BenchmarkExecutionPlan';

type MethodResult = Awaited<ReturnType<typeof api.methodComparisonResults>>;
type Analysis = Awaited<ReturnType<typeof api.listBenchmarkAnalyses>>[number];
type HumanCount = {passed:number;decided:number;reviewed:number;unresolved:number};
type Campaign = {id:string; planned:number; scenarios:Array<{id:string; result:MethodResult; singleReviews?:Record<string,HumanCount>}>};
type DynamicData = {a: MethodResult | null; campaign:Campaign|null; b: ExperimentAnalytics | null; bHuman:Record<string,HumanCount>; c: BenchmarkPlan | null; analysis:Analysis|null; errors: string[]};
const initial: DynamicData = {a:null,campaign:null,b:null,bHuman:{},c:null,analysis:null,errors:[]};
const strategies = ['weak_first_hit','strong_rule_based','scope_aware','temporal_importance'];

export function useDynamicStudies() {
  const [data,setData] = useState<DynamicData>(initial);
  const [revision,setRevision] = useState(0);
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') setRevision(x=>x+1); };
    window.addEventListener('focus',refresh); document.addEventListener('visibilitychange',refresh);
    const interval=window.setInterval(refresh,30000);
    return () => { window.clearInterval(interval); window.removeEventListener('focus',refresh); document.removeEventListener('visibilitychange',refresh); };
  }, []);
  useEffect(() => {
    let active=true;
    async function load() {
      const errors:string[]=[];
      const [groupsResult,plansResult,analysisResult] = await Promise.allSettled([api.experimentGroups(),api.listBenchmarkPlans(),api.listBenchmarkAnalyses()]);
      const groups = groupsResult.status==='fulfilled' ? groupsResult.value : [];
      if (groupsResult.status==='rejected') errors.push('A and B experiments could not be loaded');
      if (plansResult.status==='rejected') errors.push('C benchmark plans could not be loaded');
      if (analysisResult.status==='rejected') errors.push('C benchmark analyses could not be loaded');
      const ordered=[...groups].sort((a,b)=>(b.completed_at??b.created_at).localeCompare(a.completed_at??a.created_at));
      const methodGroups=ordered.filter(g=>g.test_suite_metadata?.study_role==='audit_method_comparison' && g.test_suite_metadata.diagnostic_source_run_id && g.test_suite_metadata.method_comparison_id);
      const campaignMeta=methodGroups.find(g=>g.test_suite_metadata.method_campaign_id)?.test_suite_metadata;
      let campaign:Campaign|null=null;
      if(campaignMeta?.method_campaign_id && campaignMeta.method_campaign_planned_scenarios) {
        const selected=methodGroups.filter(g=>g.test_suite_metadata.method_campaign_id===campaignMeta.method_campaign_id);
        const unique=new Map(selected.map(g=>[g.test_suite_metadata.method_comparison_id!,g]));
        const results=await Promise.all([...unique.values()].map(async g=>{
          try {
            const result=await api.methodComparisonResults(g.test_suite_metadata.diagnostic_source_run_id!,g.test_suite_metadata.method_comparison_id!);
            const singleReviews:Record<string,HumanCount>={};
            await Promise.all(result.conditions.filter(c=>c.status==='COMPLETED').map(async c=>{
              try {
                const items=await api.evaluationReview(c.run_id);const count:HumanCount={passed:0,decided:0,reviewed:0,unresolved:0};
                for(const item of items) {
                  const refs=item.human_reviews.filter(r=>r.review_role==='reference').sort((a,b)=>`${b.updated_at}:${b.review_id}`.localeCompare(`${a.updated_at}:${a.review_id}`));
                  if(refs.length) {count.reviewed++;count.decided++;if(refs[0].human_passed)count.passed++;}
                }
                singleReviews[c.run_id]=count;
              } catch {errors.push(`Single-review results for ${g.test_suite_metadata.method_scenario_id} could not be loaded`);}
            }));
            return {id:g.test_suite_metadata.method_scenario_id!,result,singleReviews};
          }
          catch {errors.push(`A scenario ${g.test_suite_metadata.method_scenario_id} could not be loaded`);return null;}
        }));
        campaign={id:campaignMeta.method_campaign_id,planned:campaignMeta.method_campaign_planned_scenarios,scenarios:results.filter((x):x is NonNullable<typeof x>=>x!==null)};
      }
      let a:MethodResult|null=null;
      const seen=new Set<string>();
      for(const group of methodGroups.filter(g=>!g.test_suite_metadata.method_campaign_id)) {
        const id=group.test_suite_metadata.method_comparison_id!;
        if(seen.has(id)) continue; seen.add(id);
        try { const result=await api.methodComparisonResults(group.test_suite_metadata.diagnostic_source_run_id!,id);
          if(result.conditions.length===3 && result.conditions.every(c=>c.status==='COMPLETED')) {a=result;break;} }
        catch {errors.push(`A comparison ${id} could not be loaded`);}
      }
      let b:ExperimentAnalytics|null=null;
      for(const group of ordered.filter((g:Experiment)=>g.status==='COMPLETED' && g.test_suite_metadata?.study_role!=='audit_method_comparison')) {
        try {const report=await api.experimentResults(group.experiment_id);
          const matching=report.conditions.filter(c=>strategies.includes(c.memory_strategy));
          if(new Set(matching.map(c=>c.memory_strategy)).size===4 && matching.length===4 && matching.every(c=>c.completed_runs>0) && new Set(matching.map(c=>`${c.provider}:${c.model}`)).size===1) {b=report;break;}
        } catch {errors.push(`Experiment ${group.experiment_id} could not be loaded`);}
      }
      const bHuman:Record<string,HumanCount>={};
      if(b) {
        for(const condition of b.conditions.filter(c=>strategies.includes(c.memory_strategy))) {
          const count:HumanCount={passed:0,decided:0,reviewed:0,unresolved:0};
          try {
            for(const runId of condition.run_ids) {
              const items=await api.evaluationReview(runId);
              for(const item of items) {
                const latest=new Map<string,typeof item.human_reviews[number]>();
                for(const review of item.human_reviews) {
                  if(review.review_role!=='independent') continue;
                  const id=review.reviewer_label.trim().toLocaleLowerCase();
                  const old=latest.get(id);
                  if(id && (!old || `${review.updated_at}:${review.review_id}` > `${old.updated_at}:${old.review_id}`)) latest.set(id,review);
                }
                const reviews=[...latest.values()];
                if(reviews.length<2) continue;
                count.reviewed++;
                if(reviews.every(r=>r.human_passed===reviews[0].human_passed)) { count.decided++; if(reviews[0].human_passed) count.passed++; }
                else count.unresolved++;
              }
            }
            bHuman[condition.condition_id]=count;
          } catch { errors.push(`Human reviews for ${condition.label} could not be loaded`); }
        }
      }
      const plans=plansResult.status==='fulfilled' ? plansResult.value : [];
      const c=plans.find(p=>Object.values(p.executions).some(v=>v.status==='COMPLETED' && v.dashboard_summary)) ?? null;
      if(active) setData({a,campaign,b,bHuman,c,analysis:analysisResult.status==='fulfilled' ? analysisResult.value[0] ?? null : null,errors});
    }
    void load(); return ()=>{active=false;};
  },[revision]);
  return {data,refresh:()=>setRevision(x=>x+1)};
}

function Bar({label,value,total,tag}:{label:string;value:number|null;total:number|null;tag?:string}) {
  const p=value!==null && total!==null && total>0 ? value/total*100 : null;
  return <div className="compact-method"><span>{label}</span><div className="compact-track"><i style={{width:`${p??0}%`}}/></div><strong>{p===null?'Not measured':`${value}/${total} · ${p.toFixed(1)}%`}</strong>{tag && <small>{tag}</small>}</div>;
}
export function DynamicA({data}:{data:DynamicData}) {
  if(!data.a && !data.campaign) return null;
  return <div>{data.campaign && <CampaignResults campaign={data.campaign}/>}{data.a && <><h3>Latest saved A comparison</h3>
    <p className="compact-note">Human-reviewed answers by test method</p>
    <div className="a-review-legend"><span><i className="a-pass"/> Passed</span><span><i className="a-fail"/> Failed</span></div>
    {data.a.conditions.map(c=>{
      const review=c.response_level;
      const passed=review ? review.true_negatives + review.false_positives : 0;
      const failed=review ? review.true_positives + review.false_negatives : 0;
      const total=passed+failed;
      const mapping=c.discovery_mapping;
      const outside=mapping?.status==='frozen' ? mapping.entries.filter(e=>e.human_passed===false && e.defect_ids.length===0).length : null;
      const candidate=c.failure_discovery_rate;
      return <div className="a-review-row" key={c.run_id}>
        <div className="a-review-heading"><b>{c.label}</b><span>{total ? `${passed} passed · ${failed} failed` : 'Review unavailable'}</span></div>
        <div className="a-review-track" role="img" aria-label={`${c.label}: ${passed} passed and ${failed} failed`}><i className="a-pass" style={{width:`${total ? passed/total*100 : 0}%`}}/><i className="a-fail" style={{width:`${total ? failed/total*100 : 0}%`}}/></div>
        <small>{candidate.status==='measured' ? `${candidate.discovered_distinct_failures} of ${candidate.known_distinct_failures} candidate patterns matched` : 'Candidate patterns not measured'}{outside!==null && outside>0 ? ` · ${outside} failed ${outside===1?'answer':'answers'} outside the candidate list` : ''}{review?.unresolved_or_single_reviewer_labels ? ` · ${review.unresolved_or_single_reviewer_labels} awaiting agreement` : ''}</small>
      </div>;
    })}
    <p className="compact-note">Candidates are possible errors, not confirmed failures. No matches does not measure detection accuracy. <a href={`/audits/${data.a.source_run_id}`}>Source audit →</a></p></>}
  </div>;
}
const methodModes=[['direct_ground_truth','Direct questions'],['fixed_template','Fixed templates'],['contextual_indirect','Contextual/indirect Auditor tests']] as const;
function CampaignResults({campaign}:{campaign:Campaign}) {
  const complete=campaign.scenarios.filter(s=>s.result.conditions.length===3 && s.result.conditions.every(c=>c.status==='COMPLETED'));
  return <section aria-label="Multi-scenario A results"><h3>Multi-scenario A results</h3>
    <p className="compact-note">{complete.length}/{campaign.planned} scenarios complete · {campaign.scenarios.length} registered · {campaign.id}</p>
    <div className="a-review-legend"><span><i className="a-pass"/> Passed</span><span><i className="a-fail"/> Failed</span></div>
    {methodModes.map(([mode,label])=>{
      const conditions=complete.flatMap(s=>s.result.conditions.filter(c=>c.suite_mode===mode));
      const passed=conditions.reduce((n,c)=>n+c.response_level.true_negatives+c.response_level.false_positives,0);
      const failed=conditions.reduce((n,c)=>n+c.response_level.true_positives+c.response_level.false_negatives,0);
      const waiting=conditions.reduce((n,c)=>n+Math.max(0,c.completed_answers-c.response_level.independently_labelled_responses),0);
      const references=complete.flatMap(s=>s.result.conditions.filter(c=>c.suite_mode===mode).map(c=>s.singleReviews?.[c.run_id]).filter((v):v is HumanCount=>!!v));
      const singlePassed=references.reduce((n,r)=>n+r.passed,0), singleDecided=references.reduce((n,r)=>n+r.decided,0);
      const independentTotal=passed+failed; const useSingle=!independentTotal && singleDecided>0;
      const chartPassed=useSingle?singlePassed:passed, chartFailed=useSingle?singleDecided-singlePassed:failed, total=chartPassed+chartFailed;
      return <div className="a-review-row" key={mode}><div className="a-review-heading"><b>{label}</b><span>{total ? `${chartPassed} passed · ${chartFailed} failed` : 'Awaiting reviewed answers'}</span></div>
        <div className="a-review-track" role="img" aria-label={`${label}: ${chartPassed} passed and ${chartFailed} failed`}><i className="a-pass" style={{width:`${total?100*chartPassed/total:0}%`}}/><i className="a-fail" style={{width:`${total?100*chartFailed/total:0}%`}}/></div>
        <small>{useSingle ? 'Single human reference · ' : independentTotal ? 'Independent human agreement · ' : ''}{waiting} answers awaiting independent human agreement · {conditions.length} completed scenarios{!useSingle && singleDecided ? ` · Single human reference: ${singlePassed} passed / ${singleDecided} reviewed` : ''}</small></div>;
    })}
    <p className="compact-note">Counts use independently resolved human labels when available; otherwise they use explicitly labelled single-human references. Questions within a history are related; these are answer outcomes, not auditor detection accuracy.</p>
    <div className="a-scenario-list">{campaign.scenarios.map(s=><div key={s.result.comparison_id}><b>{s.id}</b><span>{s.result.conditions.every(c=>c.status==='COMPLETED') ? 'Complete' : 'In progress'} · {s.result.conditions.reduce((n,c)=>n+c.response_level.independently_labelled_responses,0)} reviewed answers</span><a href={`/audits/${s.result.source_run_id}`}>Source →</a></div>)}</div>
  </section>;
}
export function DynamicBC({data}:{data:DynamicData}) {
  const summaries=data.c ? Object.entries(data.c.executions).filter(([,v])=>v.status==='COMPLETED' && v.dashboard_summary) : [];
  if(!data.b && !summaries.length && !data.analysis) return null;
  return <div><h3>Latest saved comparisons</h3>
    {data.b && <><b>B · saved four-strategy group</b>{data.b.conditions.filter(c=>strategies.includes(c.memory_strategy)).map(c=><Bar key={c.condition_id} label={memoryStrategyLabel(c.memory_strategy)} value={c.tests_passed} total={c.tests_total} tag={`${c.completed_runs}/${c.planned_runs} runs · ${c.dimensions.reduce((n,d)=>n+(d.uncertain_count??0),0)} uncertain · automatic scoring`}/>)}
      {data.b.conditions.some(c=>data.bHuman[c.condition_id]?.reviewed>0) && <><b>Independent human-review consensus</b>{data.b.conditions.filter(c=>strategies.includes(c.memory_strategy)).map(c=><Bar key={`human-${c.condition_id}`} label={memoryStrategyLabel(c.memory_strategy)} value={data.bHuman[c.condition_id]?.passed??null} total={data.bHuman[c.condition_id]?.decided??null} tag={data.bHuman[c.condition_id] ? `${data.bHuman[c.condition_id].reviewed} reviewed by at least two · ${data.bHuman[c.condition_id].unresolved} disagreements excluded` : 'Review data unavailable'}/>)}</>}
      <p className="compact-note">{data.b.experiment.label} · model {data.b.conditions[0]?.model}. One experiment group; repeated answers are not independent. Reviewer pseudonyms and independence are not authenticated. <a href={`/experiments/${data.b.experiment.experiment_id}`}>View group →</a></p></>}
    {data.c && summaries.map(([trial,entry])=>{const review=entry.human_reviews?.at(-1); return <div key={trial}><b>C · {trial} · lexical match</b>{entry.dashboard_summary!.conditions.map(row=><Bar key={row.strategy} label={memoryStrategyLabel(row.strategy as MemoryStrategy)} value={row.matched} total={row.total}/>)}
      {review && <><b>Independent human-review consensus</b>{entry.dashboard_summary!.conditions.map(row=>{const [left,right]=review.reviewers;const a=new Map(left.judgments.filter(j=>j.strategy===row.strategy).map(j=>[j.case_id,j.verdict]));const b=new Map(right.judgments.filter(j=>j.strategy===row.strategy).map(j=>[j.case_id,j.verdict]));let pass=0,decided=0;for(const id of row.case_ids??[]){const x=a.get(id),y=b.get(id);if(x && x===y && x!=='uncertain'){decided++;if(x==='pass')pass++;}}return <Bar key={`human-${row.strategy}`} label={memoryStrategyLabel(row.strategy as MemoryStrategy)} value={pass} total={decided} tag={`${decided}/${row.total} agreed pass or fail; remaining cases unresolved or unreviewed`}/>;})}</>}
      <p className="compact-note">Plan {data.c!.plan_id} · lexical match is automatic. Human reviewer independence is declared, not authenticated. Raw replies are not saved here. <a href="/experiments">Import review in Research tools →</a></p></div>;})}
    {data.analysis && <p className="compact-note">Latest C ranking analysis · {data.analysis.report.measured_trials}/{data.analysis.report.planned_trials} trials measured · agreement {data.analysis.report.ranking_agreement_percentage === null ? 'not measured' : `${data.analysis.report.ranking_agreement_percentage.toFixed(1)}%`} · {data.analysis.report.status} · plan {data.analysis.plan_id}. The analysis uses the supplied evaluations; human review is not inferred.</p>}
  </div>;
}
