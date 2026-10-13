import '@testing-library/jest-dom/vitest';
import { render,screen,cleanup,waitFor,fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi,it,expect,beforeEach } from 'vitest';
import { ValidationWorkbench } from './ValidationWorkbench';
import { defaultTargetProfile } from './TargetProfileEditor';
import { api } from '../services/api';
vi.mock('../services/api',()=>({api:{diagnosis:vi.fn(),runDiagnosticAgent:vi.fn(),validationHistories:vi.fn(),repairExperiment:vi.fn(),generate:vi.fn(),testReview:vi.fn(),methodComparison:vi.fn(),methodComparisonResults:vi.fn(),freezeMethodComparisonInventory:vi.fn(),freezeMethodComparisonDiscoveryMapping:vi.fn(),interventions:vi.fn(),followUp:vi.fn(),getAudit:vi.fn(),results:vi.fn(),execute:vi.fn(),evaluate:vi.fn(),retry:vi.fn(),reviewTest:vi.fn(),reviewTestHumanValidity:vi.fn(),regenerateTest:vi.fn()}}));
beforeEach(()=>{cleanup();sessionStorage.clear();vi.clearAllMocks();});
it('requires review of the rule-generated fixed-template draft before freezing and generating Experiment A',async()=>{
  vi.mocked(api.diagnosis).mockResolvedValue({cases:[],suggested_profile:defaultTargetProfile,notice:'Synthetic smoke only.',paired_probes:{complete_groups:0,recall_use_gaps:0}});
  vi.mocked(api.validationHistories).mockResolvedValue([]);
  const questions=['accuracy','freshness','conflict_resolution','appropriate_use'].map((dimension,index)=>({
    template_id:`FT${index+1}`,dimension,prompt:`Rule draft question ${index+1}`,expected_behavior:`Expected ${index+1}`,
    supporting_memory_ids:[`M00${index+1}`],source_message_ids:[`SYN00${index+1}`],test_type:'direct',
  }));
  const template={schema_version:'mha-experiment-a-inventory-v1',comparison_id:'cmp-a',release_id:'inventory-v1',
    source_fingerprint_sha256:'a'.repeat(64),annotation_mode:'synthetic_smoke',reviewers:['Reviewer A','Reviewer B'],defects:[],
    fixed_template_release_id:'fixed-v1',fixed_template_reviewers:['Template reviewer'],
    fixed_template_draft_generator_version:'fixed-template-v2',fixed_template_draft_fingerprint_sha256:'b'.repeat(64),
    fixed_template_review_confirmed:false,fixed_template_questions:questions};
  vi.mocked(api.methodComparison).mockResolvedValue({experiment_id:'exp-a',comparison_id:'cmp-a',study_role:'audit_method_comparison',
    test_budget:4,runs:[{run_id:'direct',label:'Direct'},{run_id:'fixed',label:'Fixed template'},{run_id:'contextual',label:'Contextual'}],
    inventory_template:template,notice:'Review this synthetic draft.'} as Awaited<ReturnType<typeof api.methodComparison>>);
  vi.mocked(api.freezeMethodComparisonInventory).mockResolvedValue({comparison_id:'cmp-a',inventory_fingerprint_sha256:'c'.repeat(64),defect_count:0,fixed_template_question_count:4,fixed_template_release_id:'fixed-v1',status:'frozen'});
  vi.mocked(api.generate).mockResolvedValue([]);
  const validReviewedRuns=new Set<string>();
  vi.mocked(api.testReview).mockImplementation(async runId=>({run_id:runId,canonical_run_id:runId,tests:[{
    test_id:`${runId}-question`,run_id:runId,dimension:'accuracy',prompt:`Question for ${runId}?`,expected_behavior:'The source-supported answer.',
    supporting_memory_ids:['M001'],generator_version:'human-reviewed-fixed-template-v1',quality_status:'accepted',grounding_status:'grounded',
    human_validity_status:validReviewedRuns.has(runId)?'accepted':null,
    human_validity_reviewer:validReviewedRuns.has(runId)?'Researcher A':null,
  } as import('../types/domain').TestCase]}));
  vi.mocked(api.reviewTestHumanValidity).mockImplementation(async(runId,testId,decision,reviewer,note)=>{
    if(decision==='accepted')validReviewedRuns.add(runId);
    return {test_id:testId,run_id:runId,human_validity_status:decision,human_validity_reviewer:reviewer,human_validity_note:note} as import('../types/domain').TestCase;
  });

  render(<ValidationWorkbench runId="source-a"/>);
  await userEvent.click(screen.getByRole('button',{name:'Inspect diagnosis'}));
  await userEvent.click(await screen.findByRole('button',{name:'Prepare audit-method comparison'}));
  expect(await screen.findByText(/drafted once by the deterministic rule generator from confirmed memories/)).toBeInTheDocument();
  const editor=screen.getByRole('textbox',{name:'Frozen failure inventory and fixed templates JSON'});
  const edited={...template,fixed_template_questions:questions.map((question,index)=>index===0?{...question,prompt:'Edited after researcher review'}:question)};
  fireEvent.change(editor,{target:{value:JSON.stringify(edited,null,2)}});
  const freezeButton=screen.getByRole('button',{name:'Freeze reviewed release and generate three question sets'});
  expect(freezeButton).toBeDisabled();
  await userEvent.click(screen.getByRole('checkbox',{name:/I reviewed the rule-generated draft/}));
  expect(freezeButton).toBeEnabled();
  await userEvent.click(freezeButton);

  await waitFor(()=>expect(api.freezeMethodComparisonInventory).toHaveBeenCalledOnce());
  const frozenPayload=vi.mocked(api.freezeMethodComparisonInventory).mock.calls[0][1] as typeof edited;
  expect(frozenPayload.fixed_template_review_confirmed).toBe(true);
  expect(frozenPayload.fixed_template_questions[0].prompt).toBe('Edited after researcher review');
  await waitFor(()=>expect(api.generate).toHaveBeenCalledTimes(3));
  expect(await screen.findByText(/Source inventory and researcher-reviewed templates frozen/)).toBeInTheDocument();
  const executeButton=screen.getByRole('button',{name:'Run prepared conditions'});
  expect(executeButton).toBeDisabled();
  await userEvent.type(screen.getByRole('textbox',{name:'Human validity reviewer pseudonym'}),'Researcher A');
  await userEvent.click(screen.getByRole('button',{name:'Confirm valid'}));
  await waitFor(()=>expect(api.reviewTestHumanValidity).toHaveBeenCalledWith('direct','direct-question','accepted','Researcher A',undefined));
  expect(executeButton).toBeDisabled();
  const selector=screen.getByRole('combobox',{name:'Condition suite to review'});
  await userEvent.click(selector);
  await userEvent.click(await screen.findByRole('option',{name:'Fixed template'}));
  await userEvent.click(screen.getByRole('button',{name:'Confirm valid'}));
  await userEvent.click(selector);
  await userEvent.click(await screen.findByRole('option',{name:'Contextual'}));
  await userEvent.click(screen.getByRole('button',{name:'Confirm valid'}));
  await waitFor(()=>expect(api.reviewTestHumanValidity).toHaveBeenCalledTimes(3));
  expect(executeButton).toBeEnabled();
});
it('shows the post-run model synthesis with its evidence limits and model identity',async()=>{
  vi.mocked(api.diagnosis).mockResolvedValue({cases:[{test_id:'T001',question:'Which database is current?',dimension:'freshness',automated_passed:false,response:'MySQL',assessment:'Old value.',layer:'input_delivery_review',explanation:'Inspect final input assembly.',supporting_memory_ids:['M001'],supporting_source_count:1,stored_source_coverage:1,sent_source_coverage:0}],suggested_profile:defaultTargetProfile,notice:'Hypothesis only.',paired_probes:{complete_groups:0,recall_use_gaps:0}});
  vi.mocked(api.validationHistories).mockResolvedValue([]);
  vi.mocked(api.runDiagnosticAgent).mockResolvedValue({run_id:'diagnostic',diagnosis_version:'v1',execution_id:'AGT001',model:'qwen3:1.7b',reported_model:'qwen3:1.7b',diagnostic_agent:{version:'post-run-diagnostic-agent-v1',summary:'The supplied evidence points to an input-delivery review.',findings:[{test_id:'T001',focus:'input_delivery',evidence_memory_ids:['M001'],summary:'The exact fact was selected but absent from the final input.',next_check:'Inspect the recorded memory input receipt.',model_confidence:0.7}],notice:'Exploratory model synthesis only.'}});
  render(<ValidationWorkbench runId="diagnostic"/>);
  await userEvent.click(screen.getByRole('button',{name:'Inspect diagnosis'}));
  await userEvent.click(await screen.findByRole('button',{name:'Ask diagnostic Agent to review these hypotheses'}));
  expect(await screen.findByText(/Model: qwen3:1\.7b/)).toBeInTheDocument();
  expect(screen.getByText(/Evidence record: AGT001/)).toBeInTheDocument();
  expect(screen.getByText('The exact fact was selected but absent from the final input.')).toBeInTheDocument();
  expect(screen.getByText(/confidence is an uncalibrated estimate/)).toBeInTheDocument();
});
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
  expect(screen.getByText(/0 recorded exclusions by context limits · 0 recorded exclusions by profile filters/)).toBeInTheDocument();
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
  expect(screen.getByText(/Reference memories are listed in this explanation/)).toBeInTheDocument();
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
  const condition=(run_id:string,label:string,attempts:number|null,unknown_attempt_records:number)=>({run_id,label,suite_mode:'fixed_template',status:'COMPLETED',test_budget:3,planned_call_cap:3,actual_target_call_attempts:attempts,completed_answers:1,unknown_attempt_records,test_count:1,valid_test_count:1,human_validity_accepted_count:1,human_validity_reviewed_count:1,human_validity_pending_count:0,human_validity_acceptance_rate:1,valid_test_dimensions:['accuracy'],human_confirmed_failure_categories:[],human_confirmed_distinct_findings:0,automated_failures:0,category_coverage:{covered_dimensions:1,total_dimensions:4,value:0.25,status:'measured'},response_level:{independently_labelled_responses:0,unresolved_or_single_reviewer_labels:0,true_positives:0,false_negatives:0,false_positives:0,true_negatives:0,failure_detection_recall:null,false_positive_rate:null,status:'partial_or_awaiting_independent_labels'},failure_discovery_rate:{discovered_distinct_failures:null,known_distinct_failures:null,value:null,undiscovered_failure_ids:null,status:'inventory_missing_or_inconsistent'},discovery_mapping:{status:'awaiting_researcher_mapping',release_id:null,reviewer_pseudonym:null,fingerprint_sha256:null,mapped_response_count:0,total_response_count:1,entries:[]}});
  vi.mocked(api.methodComparisonResults).mockResolvedValue({comparison_id:'cmp',source_run_id:'source',source_fingerprint_sha256:'a'.repeat(64),inventory:{status:'missing_or_inconsistent',release_id:null,fingerprint_sha256:null,distinct_failure_count:null,reviewers:null,authorship_verified:false,fixed_template_release_id:null,fixed_template_reviewers:null,fixed_template_question_count:null,fixed_template_draft_generator_version:null,fixed_template_draft_fingerprint_sha256:null,fixed_template_final_fingerprint_sha256:null,fixed_template_review_confirmed:false,fixed_template_review_identity_verified:false,defects:[]},planned_test_budgets_equal:true,target_and_evaluation_settings_match:true,realised_call_attempts_equal:null,conditions:[condition('retry','Retried method',3,0),condition('unknown','Historical method',null,1)],notice:'Saved answers do not certify equal realised budgets.'});
  render(<ValidationWorkbench runId="method-budget"/>);
  await userEvent.click(screen.getByRole('button',{name:'Inspect diagnosis'}));
  await userEvent.click(await screen.findByRole('button',{name:'Inspect confirmed method findings'}));
  expect(await screen.findByRole('columnheader',{name:'Recorded target attempts'})).toBeInTheDocument();
  expect(screen.getByText('Not recorded')).toBeInTheDocument();
  expect(screen.getByRole('columnheader',{name:'Failure Detection Recall'})).toBeInTheDocument();
  expect(screen.getByRole('columnheader',{name:'Human validity review'})).toBeInTheDocument();
  expect(screen.getAllByText(/1\/1 accepted · 0 pending/).length).toBeGreaterThan(0);
  expect(screen.getByText('Saved answers do not certify equal realised budgets.')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Download Experiment A results (JSON)'})).toBeInTheDocument();
});

it('requires a researcher mapping for every saved method response and freezes its release',async()=>{
  vi.mocked(api.diagnosis).mockResolvedValue({cases:[],suggested_profile:defaultTargetProfile,notice:'Hypothesis only.',paired_probes:{complete_groups:0,recall_use_gaps:0}});
  vi.mocked(api.validationHistories).mockResolvedValue([]);
  const entry={response_id:'RESP001',test_id:'TEST001',question:'Which database is current?',response:'PostgreSQL is current.',human_passed:false,defect_ids:[]};
  const report=(status:'awaiting_researcher_mapping'|'frozen')=>({comparison_id:'cmp-map',source_run_id:'source',source_fingerprint_sha256:'a'.repeat(64),
    inventory:{status:'frozen',release_id:'inventory-v1',fingerprint_sha256:'b'.repeat(64),distinct_failure_count:1,reviewers:['A','B'],authorship_verified:false,
      fixed_template_release_id:'templates-v1',fixed_template_reviewers:['C'],fixed_template_question_count:3,fixed_template_draft_generator_version:'fixed-template-v2',
      fixed_template_draft_fingerprint_sha256:'c'.repeat(64),fixed_template_final_fingerprint_sha256:'d'.repeat(64),fixed_template_review_confirmed:true,
      fixed_template_review_identity_verified:false,defects:[{defect_id:'D001',dimension:'freshness',explanation:'The current project database changed to PostgreSQL.'}]},
    planned_test_budgets_equal:true,target_and_evaluation_settings_match:true,realised_call_attempts_equal:true,
    conditions:[{run_id:'RUN001',label:'Fixed templates',suite_mode:'fixed_template',status:'COMPLETED',test_budget:3,planned_call_cap:3,
      actual_target_call_attempts:3,completed_answers:1,unknown_attempt_records:0,test_count:1,valid_test_count:1,valid_test_dimensions:['freshness'],
      human_confirmed_failure_categories:['freshness'],human_confirmed_distinct_findings:1,automated_failures:1,
      human_validity_accepted_count:1,human_validity_reviewed_count:1,human_validity_pending_count:0,human_validity_acceptance_rate:1,
      category_coverage:{covered_dimensions:1,total_dimensions:4,value:0.25,status:'measured'},
      response_level:{independently_labelled_responses:1,unresolved_or_single_reviewer_labels:0,true_positives:1,false_negatives:0,false_positives:0,true_negatives:0,failure_detection_recall:1,false_positive_rate:null,status:'measured'},
      failure_discovery_rate:{discovered_distinct_failures:status==='frozen'?1:null,known_distinct_failures:1,value:status==='frozen'?1:null,undiscovered_failure_ids:status==='frozen'?[]:null,status:status==='frozen'?'measured':'awaiting_researcher_mapping'},
      discovery_mapping:{status,release_id:status==='frozen'?'map-v1':null,reviewer_pseudonym:status==='frozen'?'Researcher R':null,fingerprint_sha256:status==='frozen'?'e'.repeat(64):null,mapped_response_count:status==='frozen'?1:0,total_response_count:1,
        entries:[{...entry,defect_ids:status==='frozen'?['D001']:[]}]} }],notice:'Mapping is human-reviewed.'}) as Awaited<ReturnType<typeof api.methodComparisonResults>>;
  vi.mocked(api.methodComparisonResults).mockResolvedValueOnce(report('awaiting_researcher_mapping')).mockResolvedValueOnce(report('frozen'));
  vi.mocked(api.freezeMethodComparisonDiscoveryMapping).mockResolvedValue({comparison_id:'cmp-map',run_id:'RUN001',mapping_fingerprint_sha256:'e'.repeat(64),status:'frozen',mapped_response_count:1});
  render(<ValidationWorkbench runId="source"/>);
  await userEvent.click(screen.getByRole('button',{name:'Inspect diagnosis'}));
  await userEvent.click(await screen.findByRole('button',{name:'Inspect confirmed method findings'}));
  expect(await screen.findByText(/Failure Discovery Rate: awaiting_researcher_mapping/)).toBeInTheDocument();
  await userEvent.clear(screen.getByRole('textbox',{name:'Fixed templates mapping release ID'}));
  await userEvent.type(screen.getByRole('textbox',{name:'Fixed templates mapping release ID'}),'map-v1');
  await userEvent.type(screen.getByRole('textbox',{name:'Fixed templates mapping reviewer pseudonym'}),'Researcher R');
  await userEvent.click(screen.getByRole('combobox',{name:'Defects found in response RESP001'}));
  await userEvent.click(await screen.findByText('D001 · freshness'));
  await userEvent.click(screen.getByRole('checkbox',{name:/I reviewed every response-to-defect link/}));
  await userEvent.click(screen.getByRole('button',{name:'Freeze response-to-defect mapping'}));
  await waitFor(()=>expect(api.freezeMethodComparisonDiscoveryMapping).toHaveBeenCalledWith('RUN001',expect.objectContaining({
    comparison_id:'cmp-map',inventory_fingerprint_sha256:'b'.repeat(64),mapping_release_id:'map-v1',reviewer_pseudonym:'Researcher R',completed_by_human:true,
    entries:[{response_id:'RESP001',test_id:'TEST001',defect_ids:['D001']}],
  })));
  expect(await screen.findByText(/Mapping frozen · map-v1 · 1\/1 responses/)).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Download Experiment A results (JSON)'})).toBeInTheDocument();
});


it('does not transfer a saved validation experiment into another audit',async()=>{
  sessionStorage.setItem('mha-validation-plan-first',JSON.stringify({experiment_id:'old-group',runs:[{run_id:'old-condition',label:'Original'}],notice:'Old audit only.'}));
  const view=render(<ValidationWorkbench runId="first"/>);
  expect(screen.getByRole('button',{name:'Restore saved experiment'})).toBeInTheDocument();
  view.rerender(<ValidationWorkbench runId="second"/>);
  expect(screen.queryByRole('button',{name:'Restore saved experiment'})).not.toBeInTheDocument();
  expect(sessionStorage.getItem('mha-validation-plan-second')).toBeNull();
});

it('ignores a malformed persisted plan without crashing the workbench',()=>{
  sessionStorage.setItem('mha-validation-plan-malformed',JSON.stringify({experiment_id:'broken',runs:null}));
  render(<ValidationWorkbench runId="malformed"/>);
  expect(screen.getByRole('button',{name:'Inspect diagnosis'})).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Restore saved experiment'})).not.toBeInTheDocument();
});


it('compares every saved repair condition without new execution or hiding the generic control',async()=>{
  const runs=[{run_id:'original',label:'Original configuration'},{run_id:'generic',label:'Generic instruction control'},{run_id:'targeted',label:'Targeted repair'}];
  sessionStorage.setItem('mha-validation-plan-three-controls',JSON.stringify({experiment_id:'group',runs,notice:'Exploratory only.'}));
  vi.mocked(api.getAudit).mockResolvedValue({status:'COMPLETED'} as Awaited<ReturnType<typeof api.getAudit>>);
  vi.mocked(api.testReview).mockResolvedValue({run_id:'original',canonical_run_id:'original',tests:[]});
  vi.mocked(api.results).mockImplementation(async id=>({run_id:id,overall_score:id==='targeted'?100:0,tests_passed:id==='targeted'?1:0,tests_total:1,dimensions:[{dimension:'accuracy',percentage:id==='targeted'?100:0,passed:id==='targeted'?1:0,total:1}],failures:[]}));
  render(<ValidationWorkbench runId="three-controls"/>);
  const user=userEvent.setup();
  await user.click(screen.getByRole('button',{name:'Restore saved experiment'}));
  expect(await screen.findByRole('button',{name:'Refresh condition comparison'})).toBeInTheDocument();
  const chart=await screen.findByLabelText(/Dimension comparison\./);
  expect(chart.getAttribute('aria-label')).toContain('Generic instruction control');
  expect(chart.getAttribute('aria-label')).toContain('Original configuration');
  expect(chart.getAttribute('aria-label')).toContain('Targeted repair');
  expect(api.results).toHaveBeenCalledTimes(3);
  expect(api.generate).not.toHaveBeenCalled();
});


it('searches reviewed histories by visible scenario text rather than internal identifiers',async()=>{
  vi.mocked(api.diagnosis).mockResolvedValue({cases:[],suggested_profile:defaultTargetProfile,notice:'Hypothesis only.',paired_probes:{complete_groups:0,recall_use_gaps:0}});
  vi.mocked(api.validationHistories).mockResolvedValue([{conversation_id:'opaque-one',label:'Cedar database changes · 11 Oct'},{conversation_id:'opaque-two',label:'Harbor meeting requirements · 12 Oct'}]);
  render(<ValidationWorkbench runId="search-history"/>);
  const user=userEvent.setup();
  await user.click(screen.getByRole('button',{name:'Inspect diagnosis'}));
  const picker=await screen.findByRole('combobox',{name:'Independent validation history'});
  await user.type(picker,'Harbor');
  expect(await screen.findByText('Harbor meeting requirements · 12 Oct')).toBeInTheDocument();
  expect(screen.queryByText('Cedar database changes · 11 Oct')).not.toBeInTheDocument();
  await user.clear(picker);
  await user.type(picker,'opaque-two');
  expect(await screen.findByText('No matching history. Try another phrase.')).toBeInTheDocument();
});

it('restores saved target answers for scoring without running the target again',async()=>{
  sessionStorage.setItem('mha-validation-plan-scoring',JSON.stringify({experiment_id:'group',runs:[{run_id:'saved-answers',label:'Candidate'}],notice:'Exploratory.'}));
  let status='TESTS_EXECUTED';
  vi.mocked(api.getAudit).mockImplementation(async()=>({status} as Awaited<ReturnType<typeof api.getAudit>>));
  vi.mocked(api.testReview).mockResolvedValue({run_id:'saved-answers',canonical_run_id:'saved-answers',tests:[{test_id:'question',prompt:'Which database is current?',quality_status:'accepted',dimension:'freshness',expected_behavior:'PostgreSQL.'} as import('../types/domain').TestCase]});
  vi.mocked(api.evaluate).mockImplementation(async()=>{status='COMPLETED';return []});
  vi.mocked(api.results).mockResolvedValue({run_id:'saved-answers',tests_passed:1,tests_total:1,overall_score:100,dimensions:[],failures:[]});
  render(<ValidationWorkbench runId="scoring"/>);
  const user=userEvent.setup();await user.click(screen.getByRole('button',{name:'Restore saved experiment'}));
  expect(await screen.findByText('Which database is current?')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Regenerate'})).toBeDisabled();
  await user.click(screen.getByRole('button',{name:/Run prepared conditions|Continue \/ verify saved conditions/}));
  expect(await screen.findByRole('link',{name:'View completed report'})).toBeInTheDocument();
  expect(api.evaluate).toHaveBeenCalledWith('saved-answers');
  expect(api.execute).not.toHaveBeenCalled();expect(api.generate).not.toHaveBeenCalled();
});

it('keeps the visible suite bound to its run when another suite fails to load',async()=>{
  sessionStorage.setItem('mha-validation-plan-switch',JSON.stringify({experiment_id:'group',runs:[{run_id:'original',label:'Original'},{run_id:'candidate',label:'Candidate'}],notice:'Exploratory.'}));
  vi.mocked(api.getAudit).mockResolvedValue({status:'TESTS_GENERATED'} as Awaited<ReturnType<typeof api.getAudit>>);
  vi.mocked(api.testReview).mockImplementation(async runId=>{
    if(runId==='candidate')throw new Error('Candidate suite unavailable');
    return {run_id:'original',canonical_run_id:'original',tests:[{test_id:'original-question',run_id:'original',prompt:'Which database is current?',quality_status:'accepted',dimension:'freshness',expected_behavior:'PostgreSQL.'} as import('../types/domain').TestCase]};
  });
  render(<ValidationWorkbench runId="switch"/>);const user=userEvent.setup();
  await user.click(screen.getByRole('button',{name:'Restore saved experiment'}));await screen.findByText('Which database is current?');
  await user.click(screen.getByRole('combobox',{name:'Condition suite to review'}));
  await user.click(screen.getByRole('option',{name:'Candidate'}));
  await screen.findByText('Candidate suite unavailable');
  expect(screen.getByRole('combobox',{name:'Condition suite to review'}).closest('.ant-select')).toHaveTextContent('Original');
  expect(screen.getByText('Which database is current?')).toBeInTheDocument();
});


it('shows question-saving progress without implying model execution and recovers after failure',async()=>{
  sessionStorage.setItem('mha-validation-plan-action',JSON.stringify({experiment_id:'group',runs:[{run_id:'candidate',label:'Candidate'}],notice:'Exploratory.'}));
  vi.mocked(api.getAudit).mockResolvedValue({status:'TESTS_GENERATED'} as Awaited<ReturnType<typeof api.getAudit>>);
  vi.mocked(api.testReview).mockResolvedValue({run_id:'candidate',canonical_run_id:'candidate',tests:[{test_id:'question',run_id:'candidate',supporting_memory_ids:['confirmed-fact'],generator_version:'rule-based-fixture',prompt:'Which database is current?',quality_status:'pending',dimension:'freshness',expected_behavior:'PostgreSQL.'} as import('../types/domain').TestCase]});
  let failSave!:(reason:Error)=>void;
  vi.mocked(api.reviewTest).mockImplementation(()=>new Promise((_,reject)=>{failSave=reject;}));
  render(<ValidationWorkbench runId="action"/>);const user=userEvent.setup();
  await user.click(screen.getByRole('button',{name:'Restore saved experiment'}));await screen.findByText('Which database is current?');
  await user.click(screen.getByRole('button',{name:'Accept'}));
  expect(await screen.findByText('Saving question decision…')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Run prepared conditions'})).not.toHaveClass('ant-btn-loading');
  expect(screen.getByRole('button',{name:'Run prepared conditions'})).toBeDisabled();
  failSave(new Error('Question decision could not be saved'));
  expect(await screen.findByText('Question decision could not be saved')).toBeInTheDocument();
  expect(screen.queryByText('Saving question decision…')).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Accept'})).toBeEnabled();
  expect(api.execute).not.toHaveBeenCalled();
});

it('shows execution progress only while running and restores controls on execution failure',async()=>{
  sessionStorage.setItem('mha-validation-plan-executing',JSON.stringify({experiment_id:'group',runs:[{run_id:'candidate',label:'Candidate'}],notice:'Exploratory.'}));
  vi.mocked(api.getAudit).mockResolvedValue({status:'TESTS_GENERATED'} as Awaited<ReturnType<typeof api.getAudit>>);
  vi.mocked(api.testReview).mockResolvedValue({run_id:'candidate',canonical_run_id:'candidate',tests:[{test_id:'question',prompt:'Which database is current?',quality_status:'accepted',dimension:'freshness',expected_behavior:'PostgreSQL.'} as import('../types/domain').TestCase]});
  let failExecution!:(reason:Error)=>void;
  vi.mocked(api.execute).mockImplementation(()=>new Promise((_,reject)=>{failExecution=reject;}));
  render(<ValidationWorkbench runId="executing"/>);const user=userEvent.setup();
  await user.click(screen.getByRole('button',{name:'Restore saved experiment'}));await screen.findByText('Which database is current?');
  await user.click(screen.getByRole('button',{name:'Run prepared conditions'}));
  expect(await screen.findByText('Executing prepared conditions…')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:/Run prepared conditions/})).toHaveClass('ant-btn-loading');
  failExecution(new Error('Target request failed'));
  expect(await screen.findByText('Target request failed')).toBeInTheDocument();
  expect(screen.queryByText('Executing prepared conditions…')).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Pause after current condition'})).not.toBeInTheDocument();
  await waitFor(()=>expect(screen.getByRole('button',{name:/Run prepared conditions/})).toBeEnabled());
});
