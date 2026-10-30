import { useEffect, useState } from 'react';
import { api } from '../services/api';
import { memoryStrategyLabel } from '../services/display';
import type { Experiment, ExperimentAnalytics, MemoryStrategy } from '../types/domain';
import type { BenchmarkPlan } from './BenchmarkExecutionPlan';

type MethodResult = Awaited<ReturnType<typeof api.methodComparisonResults>>;
type Analysis = Awaited<ReturnType<typeof api.listBenchmarkAnalyses>>[number];
type DynamicData = {a: MethodResult | null; b: ExperimentAnalytics | null; c: BenchmarkPlan | null; analysis:Analysis|null; errors: string[]};
const initial: DynamicData = {a:null,b:null,c:null,analysis:null,errors:[]};
const strategies = ['weak_first_hit','strong_rule_based','strong_score_based','scope_aware'];

export function useDynamicStudies() {
  const [data,setData] = useState<DynamicData>(initial);
  const [revision,setRevision] = useState(0);
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') setRevision(x=>x+1); };
    window.addEventListener('focus',refresh); document.addEventListener('visibilitychange',refresh);
    return () => { window.removeEventListener('focus',refresh); document.removeEventListener('visibilitychange',refresh); };
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
      let a:MethodResult|null=null;
      const seen=new Set<string>();
      for(const group of methodGroups) {
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
      const plans=plansResult.status==='fulfilled' ? plansResult.value : [];
      const c=plans.find(p=>Object.values(p.executions).some(v=>v.status==='COMPLETED' && v.dashboard_summary)) ?? null;
      if(active) setData({a,b,c,analysis:analysisResult.status==='fulfilled' ? analysisResult.value[0] ?? null : null,errors});
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
  if(!data.a) return null;
  return <div><h3>Latest saved A comparison</h3>
    {data.a.conditions.map(c=><Bar key={c.run_id} label={c.label} value={c.failure_discovery_rate.discovered_distinct_failures} total={c.failure_discovery_rate.known_distinct_failures} tag={c.failure_discovery_rate.status}/>)}
    <p className="compact-note">Distinct frozen defects found, with saved human mapping. Unmeasured stays unmeasured. <a href={`/audits/${data.a.source_run_id}`}>Source audit →</a></p>
  </div>;
}
export function DynamicBC({data}:{data:DynamicData}) {
  const summaries=data.c ? Object.entries(data.c.executions).filter(([,v])=>v.status==='COMPLETED' && v.dashboard_summary) : [];
  if(!data.b && !summaries.length && !data.analysis) return null;
  return <div><h3>Latest saved comparisons</h3>
    {data.b && <><b>B · saved four-strategy group</b>{data.b.conditions.filter(c=>strategies.includes(c.memory_strategy)).map(c=><Bar key={c.condition_id} label={memoryStrategyLabel(c.memory_strategy)} value={c.tests_passed} total={c.tests_total} tag={`${c.completed_runs}/${c.planned_runs} runs · ${c.dimensions.reduce((n,d)=>n+(d.uncertain_count??0),0)} uncertain · automatic scoring`}/>)}
      <p className="compact-note">{data.b.experiment.label} · model {data.b.conditions[0]?.model}. One experiment group; repeated answers are not independent. <a href={`/experiments/${data.b.experiment.experiment_id}`}>View group →</a></p></>}
    {data.c && summaries.map(([trial,entry])=><div key={trial}><b>C · {trial} · lexical match</b>{entry.dashboard_summary!.conditions.map(row=><Bar key={row.strategy} label={memoryStrategyLabel(row.strategy as MemoryStrategy)} value={row.matched} total={row.total}/>)}
      <p className="compact-note">Plan {data.c!.plan_id} · automatic lexical match, not human-validated accuracy. Raw replies are not saved here.</p></div>)}
    {data.analysis && <p className="compact-note">Latest C ranking analysis · {data.analysis.report.measured_trials}/{data.analysis.report.planned_trials} trials measured · agreement {data.analysis.report.ranking_agreement_percentage === null ? 'not measured' : `${data.analysis.report.ranking_agreement_percentage.toFixed(1)}%`} · {data.analysis.report.status} · plan {data.analysis.plan_id}. The analysis uses the supplied evaluations; human review is not inferred.</p>}
  </div>;
}
