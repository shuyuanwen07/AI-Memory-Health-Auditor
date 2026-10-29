import '@testing-library/jest-dom/vitest';
import { act,fireEvent,render,screen } from '@testing-library/react';
import { afterEach,it,expect,vi } from 'vitest';
import { AuditorQualityPage } from './AuditorQuality';
import { cleanup } from '@testing-library/react';
import { api } from '../services/api';
afterEach(()=>{cleanup();vi.clearAllMocks();});
vi.mock('../services/api',()=>({api:{auditorQuality:vi.fn()}}));
it('does not display fabricated reliability percentages without human labels',async()=>{
  const metric={percentage:null,numerator:0,denominator:0,interval_95:null};
  vi.mocked(api.auditorQuality).mockResolvedValue({evaluated:8,decided:8,uncertain:0,resolved_reference_count:0,double_reviewed_count:0,completed_runs:1,scenario_count:1,evidence_status:'not_calibrated',notice:'Human references required.',accuracy:metric,failure_precision:metric,failure_recall:metric,false_positive_rate:metric,review_coverage:metric,decided_reference_count:0,labelled_abstention_rate:metric,failure_classification_accuracy:metric,failure_detection_and_classification_recall:metric,review_queue:[]});
  render(<AuditorQualityPage/>);
  expect(await screen.findByText(/Independent reviews are needed before/)).toBeInTheDocument();
  expect(screen.getAllByText('Not measured')).toHaveLength(6);
  expect(screen.queryByText('100.0%')).toBeNull();
});

it('shows method errors and separates adjudicated references from ordinary references',async()=>{
  const metric={percentage:null,numerator:0,denominator:0,interval_95:null};
  const method={method:'hybrid',label:'Model tests + hybrid review',completed_runs:1,scenario_count:1,run_ids:['one'],evaluated:4,resolved_reference_count:4,adjudicated_reference_count:0,reference_only_count:4,accuracy:{...metric,percentage:25,numerator:1,denominator:3},failure_precision:metric,failure_recall_including_abstentions:metric,review_coverage:metric,labelled_abstention_rate:{...metric,percentage:25,numerator:1,denominator:4},confusion:{true_positive:1,true_negative:0,false_positive:1,false_negative:1},reviewed_difference_count:1,reviewed_examples:[{run_id:'reviewed',question:'Which database is current?',answer:'Old database.',automated_passed:true,human_passed:false,assessment_reason:'Lexical match.',review_note:'Source update was ignored.',review_role:'reference',kind:'missed_failure'}]};
  vi.mocked(api.auditorQuality).mockResolvedValue({evaluated:4,decided:3,uncertain:1,resolved_reference_count:4,double_reviewed_count:0,completed_runs:1,scenario_count:1,evidence_status:'human_references_available',notice:'Human references required.',accuracy:metric,failure_precision:metric,failure_recall:metric,false_positive_rate:metric,review_coverage:metric,decided_reference_count:3,labelled_abstention_rate:metric,failure_classification_accuracy:metric,failure_detection_and_classification_recall:metric,review_queue:[],by_method:[method],adjudicated_reference_count:0,reference_only_count:4,method_comparison_notice:'Different histories are not a controlled comparison.'});
  render(<AuditorQualityPage/>);
  expect(await screen.findByText('Where each audit method makes mistakes')).toBeInTheDocument();
  expect(screen.getByText('False alarms')).toBeInTheDocument();
  expect(screen.getByText('Missed failures')).toBeInTheDocument();
  expect(screen.getByText(/0 references adjudicated/)).toBeInTheDocument();
  expect(screen.getByText('Some answers have reference labels. Independent validation is still incomplete.')).toBeInTheDocument();
  expect(screen.getByText('Different histories are not a controlled comparison.')).toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Latest of 1 audits'})).toHaveAttribute('href','/audits/one');
  fireEvent.click(screen.getByRole('button',{name:'Inspect 1 cases'}));
  expect(await screen.findByText('Case 1 · Missed failure')).toBeInTheDocument();
  expect(screen.getByText('Source update was ignored.')).toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Inspect the full audit evidence →'})).toHaveAttribute('href','/audits/reviewed');
});
it('refreshes saved review evidence on return and ignores older responses',async()=>{
  const metric={percentage:null,numerator:0,denominator:0,interval_95:null};
  const base={evaluated:4,decided:4,uncertain:0,resolved_reference_count:0,double_reviewed_count:0,completed_runs:1,scenario_count:1,evidence_status:'not_calibrated',notice:'Human references required.',accuracy:metric,failure_precision:metric,failure_recall:metric,false_positive_rate:metric,review_coverage:metric,decided_reference_count:0,labelled_abstention_rate:metric,failure_classification_accuracy:metric,failure_detection_and_classification_recall:metric,review_queue:[]};
  let resolveOld!:(value:typeof base)=>void;
  vi.mocked(api.auditorQuality).mockReturnValueOnce(new Promise(resolve=>{resolveOld=resolve;})).mockResolvedValueOnce({...base,resolved_reference_count:2});
  render(<AuditorQualityPage/>);
  await act(async()=>{window.dispatchEvent(new Event('focus'));});
  expect(await screen.findByText('2/4 resolved references')).toBeInTheDocument();
  await act(async()=>{resolveOld(base);});
  expect(screen.getByText('2/4 resolved references')).toBeInTheDocument();
});

it('shows loading evidence and explains why reviewed uncertain answers cannot measure agreement',async()=>{
  const metric={percentage:null,numerator:0,denominator:0,interval_95:null};
  let resolve!:(value:Awaited<ReturnType<typeof api.auditorQuality>>)=>void;
  vi.mocked(api.auditorQuality).mockReturnValue(new Promise(done=>{resolve=done;}));
  render(<AuditorQualityPage/>);
  expect(screen.getByRole('status',{name:'Loading review evidence'})).toBeInTheDocument();
  await act(async()=>resolve({evaluated:2,decided:0,uncertain:2,resolved_reference_count:2,double_reviewed_count:0,completed_runs:1,scenario_count:1,evidence_status:'human_references_available',notice:'Saved reviews.',accuracy:metric,failure_precision:metric,failure_recall:metric,false_positive_rate:metric,review_coverage:metric,decided_reference_count:0,labelled_abstention_rate:{...metric,numerator:2,denominator:2,percentage:100},failure_classification_accuracy:metric,failure_detection_and_classification_recall:metric,review_queue:[{run_id:'private-run',model:'rule-based-target-ai',created_at:'2026-10-11T00:00:00Z',unreviewed:0,independent_pending:2,adjudication_pending:0}]}));
  expect(screen.queryByRole('status',{name:'Loading review evidence'})).not.toBeInTheDocument();
  expect(screen.getByText(/2 reviewed answers have an uncertain automated result/)).toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Go to independent reviews'})).toHaveAttribute('href','#independent-review-queue');
  expect(screen.getByRole('heading',{name:'Independent review queue'})).toHaveAttribute('id','independent-review-queue');
  expect(screen.queryByText('rule-based-target-ai',{exact:true})).toBeNull();
  expect(screen.queryByText('private-run')).not.toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Start blind review →'})).toHaveAttribute('href','/blind-review/private-run');
  expect(screen.queryByRole('columnheader',{name:/^Model$/})).toBeNull();
  expect(screen.queryByText('Local rule-based baseline',{exact:true})).toBeNull();
  expect(screen.getByText(/Share the direct blind-review link/)).toBeInTheDocument();
});

it('keeps zero, missing scores and per-measure denominators distinct in the consolidated chart',async()=>{
  const missing={percentage:null,numerator:0,denominator:0,interval_95:null};
  const zero={percentage:0,numerator:0,denominator:3,interval_95:[0,70] as [number,number]};
  vi.mocked(api.auditorQuality).mockResolvedValue({evaluated:5,decided:3,uncertain:2,resolved_reference_count:5,double_reviewed_count:0,completed_runs:1,scenario_count:1,evidence_status:'human_references_available',notice:'Different measures use different eligible references.',accuracy:zero,failure_precision:missing,failure_recall:{...zero,percentage:50,numerator:1,denominator:2},false_positive_rate:zero,review_coverage:missing,decided_reference_count:3,labelled_abstention_rate:{...missing,percentage:40,numerator:2,denominator:5},failure_classification_accuracy:missing,failure_detection_and_classification_recall:missing,review_queue:[]});
  render(<AuditorQualityPage/>);
  const chart=await screen.findByRole('img',{name:/Auditor reliability overview/});
  expect(chart).toHaveAccessibleDescription(/Reference agreement: 0.0%; 0 of 3 eligible reference labels/);
  expect(chart).toHaveAccessibleDescription(/Reference-supported failures: Not measured; 0 of 0 eligible reference labels/);
  expect(chart).toHaveAccessibleDescription(/Reference-labelled failures detected: 50.0%; 1 of 2 eligible reference labels/);
  expect(chart.querySelectorAll('rect')).toHaveLength(3);
  expect(screen.getByRole('region',{name:'Scrollable reliability overview'})).toHaveAttribute('tabindex','0');
  fireEvent.click(screen.getByText('Score definitions, intervals & evidence limits'));
  expect(screen.getAllByText(/95% descriptive interval: 0–70%/)).toHaveLength(3);
  expect(screen.getByText(/Saved reference labels may be assisted or non-independent/)).toBeInTheDocument();
  expect(screen.queryByText(/human-confirmed failures/i)).toBeNull();
});


it('shows excluded evidence separately without changing it into model failures',async()=>{
  const metric={percentage:null,numerator:0,denominator:0,interval_95:null};
  vi.mocked(api.auditorQuality).mockResolvedValue({evaluated:3,decided:3,uncertain:0,resolved_reference_count:3,double_reviewed_count:0,completed_runs:1,scenario_count:1,evidence_status:'human_references_available',notice:'Excluded evidence remains missing.',accuracy:metric,failure_precision:metric,failure_recall:metric,false_positive_rate:metric,review_coverage:{...metric,percentage:75,numerator:3,denominator:4},decided_reference_count:3,labelled_abstention_rate:metric,failure_classification_accuracy:metric,failure_detection_and_classification_recall:metric,review_queue:[],evidence_integrity:{expected_questions:4,eligible_questions:3,excluded_questions:1,discarded_review_labels:1,reasons:{multiple_assessments:1}}});
  render(<AuditorQualityPage/>);
  expect(await screen.findByRole('alert',{name:'Saved evidence integrity'})).toHaveTextContent('Some saved evidence could not be used');
  expect(screen.getByText(/3 of 4 saved questions/)).toBeInTheDocument();
  expect(screen.getByText('Conflicting assessments: 1')).toBeInTheDocument();
  expect(screen.getByText('3/4 resolved references')).toBeInTheDocument();
  expect(screen.queryByText('3/3 resolved references')).not.toBeInTheDocument();
  expect(screen.getByText(/Excluded records count as missing evidence/)).toBeInTheDocument();
});
