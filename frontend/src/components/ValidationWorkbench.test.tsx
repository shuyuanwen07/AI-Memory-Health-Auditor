import '@testing-library/jest-dom/vitest';
import { render,screen,cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi,it,expect,beforeEach } from 'vitest';
import { ValidationWorkbench } from './ValidationWorkbench';
import { defaultTargetProfile } from './TargetProfileEditor';
import { api } from '../services/api';
vi.mock('../services/api',()=>({api:{diagnosis:vi.fn(),validationHistories:vi.fn(),repairExperiment:vi.fn(),generate:vi.fn(),testReview:vi.fn(),methodComparison:vi.fn(),methodComparisonResults:vi.fn(),interventions:vi.fn(),followUp:vi.fn(),getAudit:vi.fn()}}));
beforeEach(()=>{cleanup();sessionStorage.clear();vi.clearAllMocks();});
it('reviews the answer as well as excluded history without silently selecting a repair',async()=>{
  vi.mocked(api.diagnosis).mockResolvedValue({cases:[{test_id:'history',question:'Which database is current?',dimension:'freshness',automated_passed:false,response:'Kotlin',assessment:'Wrong database.',layer:'answer_and_history_review',explanation:'Check the answer against the supplied newer fact; determine whether older history was necessary.',supporting_source_count:1,stored_source_coverage:1,sent_source_coverage:1}],suggested_profile:{...defaultTargetProfile,label:'Original full context'},suggested_memory_strategy:'full_context',source_memory_capacity:50,suggested_memory_capacity:50,notice:'Hypothesis, not causal proof.',paired_probes:{complete_groups:0,recall_use_gaps:0}});
  vi.mocked(api.validationHistories).mockResolvedValue([]);
  render(<ValidationWorkbench runId="history-context"/>);
  await userEvent.click(screen.getByRole('button',{name:'Inspect diagnosis'}));
  expect(await screen.findByText('Check answer & update context')).toBeInTheDocument();
  expect(screen.getByText(/Check the answer against the supplied newer fact/)).toBeInTheDocument();
  expect(screen.getByRole('textbox',{name:'Configuration name'})).toHaveValue('Original full context');
  expect(screen.getByRole('button',{name:'Prepare repair comparison'})).toBeDisabled();
});
it('distinguishes selected-but-unsupplied facts from retrieval gaps',async()=>{
  vi.mocked(api.diagnosis).mockResolvedValue({cases:[{test_id:'delivery',question:'Which database?',dimension:'freshness',automated_passed:false,response:'Unknown',assessment:'Missing value',layer:'input_delivery_review',explanation:'Inspect final input assembly.',supporting_source_count:1,stored_source_coverage:1,sent_source_coverage:0,input_delivery:{expected_fact_units:1,retrieved_fact_units:1,selected_not_supplied_fact_units:1,context_budget_excluded_fact_units:0,profile_filter_excluded_fact_units:0,notice:'Exact matches are proxies.'}}],suggested_profile:defaultTargetProfile,notice:'No causal proof.',paired_probes:{complete_groups:0,recall_use_gaps:0}});
  vi.mocked(api.validationHistories).mockResolvedValue([]);
  render(<ValidationWorkbench runId="delivery"/>);
  await userEvent.click(screen.getByRole('button',{name:'Inspect diagnosis'}));
  expect(await screen.findByText('Check input assembly')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button',{name:'Expand row'}));
  expect(screen.getByText(/1\/1 retrieved · 1 selected but not supplied/)).toBeInTheDocument();
  expect(screen.getByText('Exact matches are proxies.')).toBeInTheDocument();
});
it('shows review-first advice and preserves existing target instructions and strategy',async()=>{
  vi.mocked(api.diagnosis).mockResolvedValue({cases:[],suggested_profile:{...defaultTargetProfile,additional_instructions:'Keep existing customer boundaries.'},suggested_memory_strategy:'weak_first_hit',suggested_memory_capacity:7,
    repair_recommendation:{status:'requires_review',focus:'evidence_review',title:'Review the evidence before choosing a repair',rationale:'The current configuration is retained.',notice:'Independent validation is required.'},notice:'Hypothesis only.',paired_probes:{complete_groups:0,recall_use_gaps:0}});
  vi.mocked(api.validationHistories).mockResolvedValue([]);
  render(<ValidationWorkbench runId="uncertain-source"/>);
  await userEvent.click(screen.getByRole('button',{name:'Inspect diagnosis'}));
  expect(await screen.findByText('Review the evidence before choosing a repair')).toBeInTheDocument();
  expect(screen.getByRole('textbox',{name:'Additional target instructions'})).toHaveValue('Keep existing customer boundaries.');
  expect(screen.getByText('First matching memory')).toBeInTheDocument();
  expect(screen.queryByRole('spinbutton',{name:'Candidate memory capacity'})).not.toBeInTheDocument();
});
it('requires a repair rationale and sends general settings separately from test answers',async()=>{
  const user=userEvent.setup();
  vi.mocked(api.diagnosis).mockResolvedValue({cases:[],suggested_profile:{...defaultTargetProfile,label:'Diagnosis-guided configuration'},notice:'Hypothesis, not causal proof.',paired_probes:{complete_groups:2,recall_use_gaps:1}});
  vi.mocked(api.validationHistories).mockResolvedValue([]);
  vi.mocked(api.repairExperiment).mockResolvedValue({experiment_id:'group',runs:[{run_id:'pending',label:'Original'}],notice:'Diagnostic replay only.'});
  vi.mocked(api.generate).mockResolvedValue([]);
  vi.mocked(api.testReview).mockResolvedValue({run_id:'pending',canonical_run_id:'pending',tests:[]});
  render(<ValidationWorkbench runId="source"/>);
  await user.click(screen.getByRole('button',{name:'Inspect diagnosis'}));
  expect(await screen.findByRole('button',{name:'Prepare repair comparison'})).toBeDisabled();
  await user.type(screen.getByRole('textbox',{name:'Repair rationale'}),'Separate current project facts from old facts.');
  await user.click(screen.getByRole('button',{name:'Prepare repair comparison'}));
  expect(api.repairExperiment).toHaveBeenCalledWith('source',expect.objectContaining({targeted_profile:expect.objectContaining({label:'Diagnosis-guided configuration'}),diagnosis_note:'Separate current project facts from old facts.'}));
  expect(await screen.findByText('Diagnostic replay only.')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Run prepared conditions'})).toBeDisabled();
});

it('restores completed conditions and displays pending frozen questions without regeneration',async()=>{
  sessionStorage.setItem('mha-validation-plan-recovery',JSON.stringify({experiment_id:'group',runs:[{run_id:'done',label:'Original'},{run_id:'next',label:'Candidate'}],notice:'Candidate validation.'}));
  vi.mocked(api.getAudit).mockImplementation(async id=>({status:id==='done'?'COMPLETED':'TESTS_GENERATED'} as Awaited<ReturnType<typeof api.getAudit>>));
  vi.mocked(api.testReview).mockResolvedValue({run_id:'next',canonical_run_id:'done',tests:[{test_id:'question',prompt:'What is remembered?',quality_status:'accepted',dimension:'accuracy',expected_behavior:'A grounded fact.'} as import('../types/domain').TestCase]});
  const previous=vi.mocked(api.generate).mock.calls.length;
  render(<ValidationWorkbench runId="recovery"/>);
  await userEvent.setup().click(screen.getByRole('button',{name:'Restore saved experiment'}));
  expect(await screen.findByText('2 conditions · 1 completed')).toBeInTheDocument();
  expect(screen.getByText(/The shared questions are frozen/)).toBeInTheDocument();
  expect(await screen.findByRole('button',{name:/Continue \/ verify saved conditions/})).toBeEnabled();
  expect(screen.getByRole('button',{name:'Regenerate'})).toBeDisabled();
  expect(vi.mocked(api.generate).mock.calls.length).toBe(previous);
  sessionStorage.removeItem('mha-validation-plan-recovery');
});

it('a restored single-condition follow-up never offers a self-comparison', async()=>{
  sessionStorage.setItem('mha-validation-plan-single',JSON.stringify({experiment_id:'group',runs:[{run_id:'done',label:'Exploratory follow-up'}],notice:'Exploratory.'}));
  vi.mocked(api.getAudit).mockResolvedValue({status:'COMPLETED'} as Awaited<ReturnType<typeof api.getAudit>>);
  vi.mocked(api.testReview).mockResolvedValue({run_id:'done',canonical_run_id:'done',tests:[]});
  render(<ValidationWorkbench runId="single"/>);
  await userEvent.click(screen.getByRole('button',{name:'Restore saved experiment'}));
  expect(await screen.findByText('1 conditions · 1 completed')).toBeInTheDocument();
  expect(screen.queryByRole('link',{name:/Compare/})).toBeNull();
});

it('separates source overlap from fact correspondence and exposes the recorded text',async()=>{
  vi.mocked(api.diagnosis).mockResolvedValue({cases:[{
    test_id:'same-message',question:'Which database is current?',dimension:'freshness',automated_passed:false,
    response:'MySQL',assessment:'Old value. Evidence records: MABCDEF0123456789.',layer:'fact_correspondence_review',explanation:'Compare fact text before attribution.',
    supporting_source_count:1,stored_source_coverage:1,sent_source_coverage:1,
    fact_correspondence:{expected_fact_units:1,stored_fact_units:0,supplied_fact_units:0,
      facts:[{reference_label:'Supporting fact 1',reference_text:'Use PostgreSQL',stored_related_text:['Use MySQL'],supplied_related_text:['Use MySQL']}]},
  }],suggested_profile:defaultTargetProfile,notice:'Proxies are not causal proof.',paired_probes:{complete_groups:0,recall_use_gaps:0}});
  vi.mocked(api.validationHistories).mockResolvedValue([]);
  render(<ValidationWorkbench runId="facts"/>);
  await userEvent.click(screen.getByRole('button',{name:'Inspect diagnosis'}));
  expect(await screen.findByText('Check fact correspondence')).toBeInTheDocument();
  expect(screen.getByText('0/1 exact stored · 0/1 exact supplied')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button',{name:'Expand row'}));
  expect(screen.getByText(/Use PostgreSQL/)).toBeInTheDocument();
  expect(screen.queryByText(/MABCDEF0123456789/)).toBeNull();
  expect(screen.getByText(/Supporting memories were checked/)).toBeInTheDocument();
  expect(screen.getByText(/Actually supplied from related sources/)).toBeInTheDocument();
});

it('shows answer-time eviction and allows an explicit candidate-only capacity repair',async()=>{
  vi.mocked(api.diagnosis).mockResolvedValue({source_memory_capacity:1,suggested_memory_capacity:5,suggested_memory_strategy:'scope_aware',cases:[{
    test_id:'evicted',question:'Where do I live?',dimension:'accuracy',automated_passed:false,response:'Unknown',assessment:'Missing fact',
    layer:'retention_hypothesis',explanation:'Capacity excluded the supporting fact at answer time.',supporting_source_count:1,stored_source_coverage:1,sent_source_coverage:0,
    memory_availability:{expected_fact_units:1,observed_fact_units:1,eligible_fact_units:0,capacity_excluded_fact_units:1,facts:[{reference_label:'Supporting fact 1',reference_text:'I live in Bunbury',matching_record_eligibility:[{record_text:'I live in Bunbury',eligibility:'capacity_excluded'}]}]},
  }],suggested_profile:{...defaultTargetProfile,label:'Retention capacity candidate'},notice:'Hypothesis, not causal proof.',paired_probes:{complete_groups:0,recall_use_gaps:0}});
  vi.mocked(api.validationHistories).mockResolvedValue([]);
  vi.mocked(api.repairExperiment).mockResolvedValue({experiment_id:'capacity',runs:[{run_id:'pending',label:'Original'}],notice:'Replay only.'});
  vi.mocked(api.generate).mockResolvedValue([]);vi.mocked(api.testReview).mockResolvedValue({run_id:'pending',canonical_run_id:'pending',tests:[]});
  const user=userEvent.setup();render(<ValidationWorkbench runId="capacity"/>);await user.click(screen.getByRole('button',{name:'Inspect diagnosis'}));
  expect(await screen.findByText('Check retention capacity')).toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Expand row'}));expect(screen.getByText(/Removed by capacity limit/)).toBeInTheDocument();
  expect(screen.getByText(/Missing eligibility records remain unknown/)).toBeInTheDocument();
  await user.type(screen.getByRole('textbox',{name:'Repair rationale'}),'Increase capacity while keeping reader and retrieval unchanged.');
  const capacity=screen.getByRole('spinbutton',{name:'Candidate memory capacity'});expect(capacity).toHaveValue('5');
  await user.clear(capacity);expect(screen.getByRole('button',{name:'Prepare repair comparison'})).toBeDisabled();
  await user.type(capacity,'5');await user.click(screen.getByRole('button',{name:'Prepare repair comparison'}));
  expect(api.repairExperiment).toHaveBeenCalledWith('capacity',expect.objectContaining({targeted_memory_capacity:5,targeted_memory_strategy:'scope_aware'}));
});

it('recovers failed history loading without resetting the diagnosis or edited repair',async()=>{
  const user=userEvent.setup();
  vi.mocked(api.diagnosis).mockResolvedValue({cases:[],suggested_profile:{...defaultTargetProfile,label:'Initial candidate'},notice:'Hypothesis only.',paired_probes:{complete_groups:0,recall_use_gaps:0}});
  vi.mocked(api.validationHistories).mockRejectedValueOnce(new Error('History connection interrupted')).mockResolvedValueOnce([{conversation_id:'new-history',label:'New reviewed history'}]);
  render(<ValidationWorkbench runId="source"/>);
  await user.click(screen.getByRole('button',{name:'Inspect diagnosis'}));
  await screen.findByText('History connection interrupted');
  await user.clear(screen.getByRole('textbox',{name:'Configuration name'}));
  await user.type(screen.getByRole('textbox',{name:'Configuration name'}),'Preserved candidate');
  await user.click(screen.getByRole('button',{name:'Refresh reviewed histories'}));
  expect(api.diagnosis).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('textbox',{name:'Configuration name'})).toHaveValue('Preserved candidate');
  await user.click(screen.getByRole('combobox',{name:'Independent validation history'}));
  expect(await screen.findByText('New reviewed history')).toBeInTheDocument();
});


it('labels an intentional no-memory outcome and retains the reference configuration',async()=>{
  vi.mocked(api.diagnosis).mockResolvedValue({cases:[{test_id:'baseline',question:'Which city?',dimension:'accuracy',automated_passed:false,response:'Unknown',assessment:'No supplied fact',layer:'no_memory_reference',explanation:'Memory was intentionally disabled.',supporting_source_count:1,stored_source_coverage:1,sent_source_coverage:0}],suggested_profile:defaultTargetProfile,suggested_memory_strategy:'no_memory',repair_recommendation:{status:'baseline_reference',focus:'baseline_ablation',title:'Memory intentionally disabled for this baseline',rationale:'Keep original configuration.',notice:'A different condition is not proof of repair.'},notice:'Reference outcome.',paired_probes:{complete_groups:0,recall_use_gaps:0}});
  vi.mocked(api.validationHistories).mockResolvedValue([]);
  render(<ValidationWorkbench runId="no-memory"/>);
  await userEvent.click(screen.getByRole('button',{name:'Inspect diagnosis'}));
  expect(await screen.findByText('Memory disabled · baseline outcome')).toBeInTheDocument();
  expect(screen.getByText('Memory intentionally disabled for this baseline')).toBeInTheDocument();
  expect(screen.getByText('Supply no memories')).toBeInTheDocument();
});

it('separates saved answers from recorded retries and preserves unknown attempt evidence',async()=>{
  vi.mocked(api.diagnosis).mockResolvedValue({cases:[],suggested_profile:defaultTargetProfile,notice:'Hypothesis only.',paired_probes:{complete_groups:0,recall_use_gaps:0}});
  vi.mocked(api.validationHistories).mockResolvedValue([]);
  vi.mocked(api.methodComparisonResults).mockResolvedValue({conditions:[{run_id:'retry',label:'Retried method',actual_calls:3,completed_answers:1,unknown_attempt_records:0,resolved_labels:0,human_confirmed_distinct_findings:0},{run_id:'unknown',label:'Historical method',actual_calls:null,completed_answers:1,unknown_attempt_records:1,resolved_labels:0,human_confirmed_distinct_findings:0}],notice:'Saved answers do not certify equal realised budgets.'});
  render(<ValidationWorkbench runId="method-budget"/>);
  await userEvent.click(screen.getByRole('button',{name:'Inspect diagnosis'}));
  await userEvent.click(await screen.findByRole('button',{name:'Inspect confirmed method findings'}));
  expect(await screen.findByText('Recorded request attempts')).toBeInTheDocument();
  expect(screen.getByText('Not recorded')).toBeInTheDocument();
  expect(screen.getByText('Answers missing attempt evidence')).toBeInTheDocument();
  expect(screen.getByText('Saved answers do not certify equal realised budgets.')).toBeInTheDocument();
});
