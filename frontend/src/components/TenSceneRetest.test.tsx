import { act, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { AstraDiverseQuestions } from './CompactExperimentResults';

// Fixtures exercise incomplete and provisional outcomes; they are not study data.
const baseline={planned_slots:40,saved:28,valid:14,invalid:14,unresolved:0,missing:12};
const retest=()=>({histories:10,planned_slots:40,saved:36,valid:31,invalid:2,unresolved:3,missing:4,
  review_status:'ai_preliminary',source_unchanged:true,baseline:{...baseline},evidence_path:'/research-results',revised_questions:2});
const report=(latest:unknown)=>({review_status:'human_confirmed',planned_histories:10,completed_histories:7,
  planned_question_slots:40,saved_questions:28,all_valid:14,invalid:14,uncertain:0,
  latest_repair_retest:{histories:1,planned_slots:4,generated:4,ai_valid:4,human_review:'confirmed'},
  ...(latest===undefined?{}:{ten_scene_retest:latest})});
function fetchReport(latest:unknown) {
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>report(latest)})));
}
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers();});

it('compares the original and latest forty planned slots without treating missing questions as reviewed',async()=>{
  fetchReport(retest());render(<AstraDiverseQuestions/>);
  expect(await screen.findByLabelText('AC2 ten-scene product-flow retest')).toBeInTheDocument();
  expect(screen.getByRole('img',{name:'Original · human checked: 14 valid, 14 invalid, 0 unresolved, 12 not generated, out of 40 planned'})).toBeInTheDocument();
  expect(screen.getByRole('img',{name:'Latest · AI preliminary: 31 valid, 2 invalid, 3 unresolved, 4 not generated, out of 40 planned'})).toBeInTheDocument();
  expect(screen.getByText('31/40 valid')).toBeInTheDocument();
  expect(screen.getByText(/Two independent AI reviews; human confirmation pending/)).toBeInTheDocument();
  expect(screen.getByText(/Includes two post-review regenerations/)).toBeInTheDocument();
  expect(screen.queryByLabelText('Latest generation repair retest')).not.toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Retest evidence →'})).toHaveAttribute('href','/research-results');
});

it('retains the legacy ten-history and single-source results when no full retest has been published',async()=>{
  fetchReport(undefined);render(<AstraDiverseQuestions/>);
  expect(await screen.findByText('14 valid · 14 invalid · 0 unresolved · 12 not generated')).toBeInTheDocument();
  expect(screen.getByLabelText('Latest generation repair retest')).toHaveTextContent('4/4 saved');
  expect(screen.queryByLabelText('AC2 ten-scene product-flow retest')).not.toBeInTheDocument();
});

it.each([
  ['unaccounted saved questions',{...retest(),saved:37}],
  ['missing slots counted incorrectly',{...retest(),missing:3}],
  ['a substituted source set',{...retest(),source_unchanged:false}],
  ['a different number of histories',{...retest(),histories:4}],
  ['a changed historical baseline',{...retest(),baseline:{...baseline,valid:15,invalid:13}}],
  ['an unknown review status',{...retest(),review_status:'approved'}],
  ['negative outcome counts',{...retest(),valid:33,invalid:-1,unresolved:4}],
  ['more revised questions than saved slots',{...retest(),revised_questions:41}],
])('does not present %s as the ten-scene comparison',async(_,invalid)=>{
  fetchReport(invalid);render(<AstraDiverseQuestions/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Latest ten-scene comparison unavailable');
  expect(screen.queryByLabelText('AC2 ten-scene product-flow retest')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Astra diverse-history product question review')).toBeInTheDocument();
});

it('refreshes counts and switches from AI preliminary to human confirmation when new reviewed data arrives',async()=>{
  vi.useFakeTimers();let current=report(retest());
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>current})));
  await act(async()=>{render(<AstraDiverseQuestions/>);});
  expect(screen.getByText(/human confirmation pending/)).toBeInTheDocument();
  current=report({...retest(),saved:40,valid:36,invalid:4,unresolved:0,missing:0,review_status:'human_confirmed'});
  await act(async()=>{await vi.advanceTimersByTimeAsync(30000);});
  expect(screen.getByText('36/40 valid')).toBeInTheDocument();
  expect(screen.getByRole('img',{name:'Latest · human checked: 36 valid, 4 invalid, 0 unresolved, 0 not generated, out of 40 planned'})).toBeInTheDocument();
  expect(screen.getByText(/Human-confirmed AI-assisted reviews/)).toBeInTheDocument();
  expect(screen.queryByText(/human confirmation pending/)).not.toBeInTheDocument();
});

it('uses the research page when a report supplies an unsafe evidence link',async()=>{
  fetchReport({...retest(),evidence_path:'javascript:alert(1)'});render(<AstraDiverseQuestions/>);
  expect(await screen.findByRole('link',{name:'Retest evidence →'})).toHaveAttribute('href','/research-results');
});

it('keeps all forty reviewed-valid questions separate from a partial technical execution check',async()=>{
  fetchReport({...retest(),saved:40,valid:40,invalid:0,unresolved:0,missing:0,review_status:'human_confirmed',
    execution_check:{planned:40,answers:20,assessments:12,status:'partial',basis:'automatic'}});
  render(<AstraDiverseQuestions/>);
  expect(await screen.findByText('40/40 valid')).toBeInTheDocument();
  expect(screen.getByLabelText('AC2 question execution check')).toHaveTextContent('Execution check: 20/40 answered · 12/40 automatically assessed.');
  expect(screen.queryByText(/100%|accuracy|passed/i)).not.toBeInTheDocument();
});

it('does not add a technical execution note when the optional receipt is absent',async()=>{
  fetchReport(retest());render(<AstraDiverseQuestions/>);
  await screen.findByLabelText('AC2 ten-scene product-flow retest');
  expect(screen.queryByLabelText('AC2 question execution check')).not.toBeInTheDocument();
});

it.each([
  {planned:40,answers:41,assessments:40,status:'partial',basis:'automatic'},
  {planned:40,answers:20,assessments:-1,status:'partial',basis:'automatic'},
  {planned:40,answers:20.5,assessments:12,status:'partial',basis:'automatic'},
  {planned:40,answers:20,assessments:12,status:'complete',basis:'automatic'},
  {planned:40,answers:20,assessments:21,status:'partial',basis:'automatic'},
])('ignores an inconsistent execution receipt without hiding question validity: %j',async execution_check=>{
  fetchReport({...retest(),saved:40,valid:40,invalid:0,unresolved:0,missing:0,execution_check});
  render(<AstraDiverseQuestions/>);
  expect(await screen.findByText('40/40 valid')).toBeInTheDocument();
  expect(screen.queryByLabelText('AC2 question execution check')).not.toBeInTheDocument();
});

it('shows complete answer and assessment coverage without turning it into a pass rate',async()=>{
  fetchReport({...retest(),execution_check:{planned:40,answers:40,assessments:40,status:'complete',basis:'automatic'}});
  render(<AstraDiverseQuestions/>);
  expect(await screen.findByLabelText('AC2 question execution check')).toHaveTextContent('Execution check: 40/40 answered · 40/40 automatically assessed.');
  expect(screen.getByText('31/40 valid')).toBeInTheDocument();
});

it('keeps unresolved relationships visible separately from all forty valid questions',async()=>{
  fetchReport({...retest(),saved:40,valid:40,invalid:0,unresolved:0,missing:0,review_status:'human_confirmed',
    confirmed_relationships:26,unresolved_relationships:6});
  render(<AstraDiverseQuestions/>);
  expect(await screen.findByText('40/40 valid')).toBeInTheDocument();
  expect(screen.getByLabelText('AC2 relationship review counts')).toHaveTextContent('Relationships: 26 confirmed · 6 unresolved.');
});

it.each([
  {confirmed_relationships:26},
  {confirmed_relationships:26,unresolved_relationships:5},
  {confirmed_relationships:-1,unresolved_relationships:33},
  {confirmed_relationships:26.5,unresolved_relationships:5.5},
])('omits missing or inconsistent relationship metadata without hiding the question review: %j',async counts=>{
  fetchReport({...retest(),...counts});render(<AstraDiverseQuestions/>);
  await screen.findByLabelText('AC2 ten-scene product-flow retest');
  expect(screen.queryByLabelText('AC2 relationship review counts')).not.toBeInTheDocument();
  expect(screen.getByText('31/40 valid')).toBeInTheDocument();
});
