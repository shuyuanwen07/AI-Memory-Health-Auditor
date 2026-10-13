import {UIActionLink} from './ui';
import type {PairedComparison} from '../types/domain';

const outcomes = [
  {key:'both_passed',label:'Passed in both',colour:'#16806a'},
  {key:'candidate_only_passed',label:'Only setting 2 passed',colour:'#087ea4'},
  {key:'reference_only_passed',label:'Only setting 1 passed',colour:'#b7791f'},
  {key:'both_failed',label:'Failed in both',colour:'#b94848'},
] as const;

export function PairedOutcomeOverview({comparisons,labelForRun}:{comparisons:PairedComparison[];labelForRun:(id:string,fallback:string)=>string}) {
  const comparable = comparisons.filter(pair=>pair.shared_tests>0);
  if(!comparable.length)return null;
  return <section className="paired-outcome-overview" aria-label="Comparable answer changes">
    <h3>Changes on shared questions</h3>
    <p>Matching questions and review standards. Counts include only comparable, decided answers.</p>
    <div className="paired-outcome-legend">{outcomes.map(item=><span key={item.key}><i style={{backgroundColor:item.colour}} aria-hidden="true"/>{item.label}</span>)}</div>
    <div className="paired-outcome-grid">{comparable.map(pair=>{
      const first=labelForRun(pair.reference_run_id,pair.reference_label);
      const second=labelForRun(pair.candidate_run_id,pair.candidate_label);
      const firstPassed=pair.both_passed+pair.reference_only_passed;
      const secondPassed=pair.both_passed+pair.candidate_only_passed;
      const summary=outcomes.map(item=>`${item.label}: ${pair[item.key]}`).join('; ');
      const query=new URLSearchParams({before:pair.reference_run_id,after:pair.candidate_run_id});
      return <article key={`${pair.reference_run_id}:${pair.candidate_run_id}`}>
        <p><b>Setting 1:</b> {first}<br/><b>Setting 2:</b> {second}</p>
        <strong>{firstPassed}/{pair.shared_tests} → {secondPassed}/{pair.shared_tests} passed</strong>
        <div className="paired-outcome-bar" role="img" aria-label={`${first} versus ${second}. ${summary}`}>
          {outcomes.map(item=>pair[item.key]>0&&<span key={item.key} style={{width:`${pair[item.key]*100/pair.shared_tests}%`,backgroundColor:item.colour}} title={`${item.label}: ${pair[item.key]}`}>{pair[item.key]}</span>)}
        </div>
        <small>{pair.shared_question_count==null?`${pair.shared_tests} comparable answers · shared question total not recorded`:`${pair.shared_tests} of ${pair.shared_question_count} shared questions compared`}</small>
        <UIActionLink href={`/compare?${query}`}>Inspect these two settings</UIActionLink>
      </article>;
    })}</div>
    {comparable.length<comparisons.length&&<small>{comparisons.length-comparable.length} other pairings have no comparable decided answers and are omitted.</small>}
    <small>These pairings reuse results; they are not independent samples or evidence of general superiority.</small>
  </section>;
}
