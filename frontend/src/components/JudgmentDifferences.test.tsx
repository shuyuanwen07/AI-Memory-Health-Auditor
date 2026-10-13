import {render,screen} from '@testing-library/react';
import {JudgmentDifferences,judgmentDifferencePairs} from './JudgmentDifferences';
import type {AuditResult,EvaluationReviewItem} from '../types/domain';
const result=(id:string):AuditResult=>({run_id:id,overall_score:null,tests_passed:0,tests_total:0,uncertain_count:1,dimensions:[],failures:[]});
const row=(passed:boolean|null,text:string):EvaluationReviewItem=>({test:{test_id:'t',run_id:'r',dimension:'accuracy',prompt:'What is current?',expected_behavior:'Current fact.',supporting_memory_ids:[],generator_version:'v'},response:{response_id:'a',test_id:'t',run_id:'r',response_text:text,model:'Qwen',temperature:0,created_at:''},automated:{evaluation_id:'e',test_id:'t',response_id:'a',passed,reason:'Evidence check.',evidence_memory_ids:[],evaluator:'v'},human_review:null,human_reviews:[]});
const runs=[{label:'Qwen · Weak · Model tests + rule review',result:result('rule')},{label:'Qwen · Weak · Model tests + hybrid review',result:result('hybrid')}];
test('shows original automated outcomes and explicitly distinguishes separate answers',()=>{
  const reviews={rule:[row(false,'Old fact.')],hybrid:[row(null,'Current fact.')]};
  render(<JudgmentDifferences runs={runs} reviews={reviews} ready />);
  expect(screen.getByRole('img',{name:/rule review: 0 pass, 1 fail, 0 awaiting review/})).toBeTruthy();
  expect(screen.getByRole('img',{name:/hybrid review: 0 pass, 0 fail, 1 awaiting review/})).toBeTruthy();
  expect(screen.getByText(/Answer text differs; this case is not a controlled/)).toBeTruthy();
  expect(screen.getByText('Old fact.')).toBeTruthy();expect(screen.getAllByText('Current fact.')).toHaveLength(2);
});
test('does not pair different target conditions, questions, or repeated ambiguous questions',()=>{
  expect(judgmentDifferencePairs(runs,{rule:[row(false,'x'),row(false,'y')],hybrid:[row(true,'z')]})).toEqual([]);
  expect(judgmentDifferencePairs([runs[0],{...runs[1],label:'Other model · Weak · Model tests + hybrid review'}],{rule:[row(false,'x')],hybrid:[row(true,'y')]})).toEqual([]);
  expect(judgmentDifferencePairs(runs,{rule:[row(false,'x')],hybrid:[{...row(true,'x'),test:{...row(true,'x').test,expected_behavior:'Different reference'}}]})).toEqual([]);
});
test('human reference labels do not rewrite the original distribution or imply independent accuracy',()=>{
  const label={review_id:'h',evaluation_id:'e',human_passed:true,reviewer_label:'A',review_role:'reference' as const,based_on_review_ids:[],created_at:'',updated_at:''};
  render(<JudgmentDifferences runs={runs} reviews={{rule:[{...row(false,'x'),human_review:label}],hybrid:[row(null,'x')]}} ready />);
  expect(screen.getByRole('img',{name:/rule review: 0 pass, 1 fail/})).toBeTruthy();
  expect(screen.getByText(/Answer text matches, but these are separate executions/)).toBeTruthy();
  expect(screen.getByRole('button',{name:'Human Review Cross-check'})).toBeTruthy();
});

test('repeated trials pair by immutable source receipt rather than question text',()=>{
  const original=(id:string)=>({...row(false,'x'),response:{...row(false,'x').response,response_id:id,run_id:'rule'}});
  const reused=(id:string)=>({...row(true,'x'),response:{...row(true,'x').response,response_id:`copy-${id}`,run_id:'hybrid',execution_metadata:{request_attempts:0,response_source:"shared_target_answer",shared_source_response_id:id,shared_source_run_id:'rule'}}});
  const pairs=judgmentDifferencePairs(runs,{rule:[original('r1'),original('r2')],hybrid:[reused('r2'),reused('r1')]});
  expect(pairs.map(pair=>pair.rule.response.response_id)).toEqual(['r2','r1']);
  expect(judgmentDifferencePairs(runs,{rule:[original('r1')],hybrid:[reused('missing')]})).toEqual([]);
});
