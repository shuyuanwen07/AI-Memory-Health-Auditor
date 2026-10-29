import {render,screen} from '@testing-library/react';
import {PairedOutcomeOverview} from './PairedOutcomeOverview';
import type {PairedComparison} from '../types/domain';

const pair:PairedComparison={reference_run_id:'PRIVATE-WEAK',candidate_run_id:'PRIVATE-STRONG',reference_label:'weak',candidate_label:'strong',shared_tests:4,shared_question_count:4,both_passed:0,both_failed:1,reference_only_passed:0,candidate_only_passed:3,candidate_delta_percentage_points:75,candidate_delta_confidence_interval_low:null,candidate_delta_confidence_interval_high:null,two_sided_sign_test_p_value:null};
const name=(_id:string,fallback:string)=>fallback==='weak'?'First-match retrieval · Rule review':'Match the task and project · Rule review';

test('shows compatible strategy changes without presenting incompatible judge comparisons as improvement',()=>{
 render(<PairedOutcomeOverview comparisons={[pair,{...pair,candidate_run_id:'OTHER-JUDGE',shared_tests:0,candidate_only_passed:0,both_failed:0,excluded_assessment_count:4,candidate_delta_percentage_points:null}]} labelForRun={name}/>);
 expect(screen.getAllByRole('img')).toHaveLength(1);
 expect(screen.getByRole('img')).toHaveAccessibleName(/Only setting 2 passed: 3.*Failed in both: 1/);
 expect(screen.getByText('0/4 → 3/4 passed')).toBeInTheDocument();
 expect(screen.getByText(/1 other pairings have no comparable decided answers/)).toBeInTheDocument();
 expect(screen.getByRole('link',{name:'Inspect these two settings'})).toHaveAttribute('href','/compare?before=PRIVATE-WEAK&after=PRIVATE-STRONG');
 expect(screen.queryByText(/PRIVATE-|OTHER-JUDGE/)).not.toBeInTheDocument();
 expect(screen.getByText(/not independent samples/)).toBeInTheDocument();
});

test('keeps missing or uncertain shared answers outside the chart denominator and states coverage',()=>{
 render(<PairedOutcomeOverview comparisons={[{...pair,shared_question_count:7,excluded_uncertain_count:2,excluded_assessment_count:1}]} labelForRun={name}/>);
 expect(screen.getByText('4 of 7 shared questions compared')).toBeInTheDocument();
 expect(screen.getByText('0/4 → 3/4 passed')).toBeInTheDocument();
 expect(screen.queryByText(/0\/7|3\/7/)).not.toBeInTheDocument();
});

test('does not display a zero-change result when no answers can be fairly paired',()=>{
 const {container}=render(<PairedOutcomeOverview comparisons={[{...pair,shared_tests:0,candidate_delta_percentage_points:null}]} labelForRun={name}/>);
 expect(container).toBeEmptyDOMElement();
});
