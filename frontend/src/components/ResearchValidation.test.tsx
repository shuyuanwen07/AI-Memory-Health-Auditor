import { selectUIOption } from './ui/testHelpers';
import { render, screen, waitFor, cleanup, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ResearchValidation } from './ResearchValidation';

const apiMocks = vi.hoisted(() => ({
  restoreFormalPlan:vi.fn(), savedFormalRuns:vi.fn(), audits: vi.fn(), validateAnnotationDataset: vi.fn(), researchValidity: vi.fn(), validateBenchmark: vi.fn(),
  runBenchmark: vi.fn(), analysePilot: vi.fn(), createFormalResearchMatrix: vi.fn(), createFormalSyntheticMatrix: vi.fn(), createExploratorySyntheticMatrix: vi.fn(), execute: vi.fn(), evaluate: vi.fn(), getAudit: vi.fn(), retry: vi.fn(),
}));
vi.mock('../services/api', () => ({ api: apiMocks }));
const downloadMocks = vi.hoisted(() => ({saveBlob: vi.fn()}));
vi.mock('../services/download', () => downloadMocks);

const dataset = { dataset_id: 'labels-v1', dataset_version: '1.0.0' };
const predictions = { dataset_id: 'labels-v1', dataset_version: '1.0.0', evaluator_predictions: [] };
const criteria={failure_detection_recall_min_percent:80,failure_classification_accuracy_min_percent:75,test_validity_min_percent:90,false_positive_rate_max_percent:10};
async function fillSuccessCriteria(user:ReturnType<typeof userEvent.setup>) {
  for (const [label,value] of [['Minimum failure recall (%)','80'],['Minimum classification accuracy (%)','75'],['Minimum test validity (%)','90'],['Maximum false-positive rate (%)','10']]) await user.type(screen.getByLabelText(label),value);
}
const pilot = { dataset_fingerprint_sha256:'a'.repeat(64), pilot_id: 'pilot-v1', dataset_id: 'labels-v1', dataset_version: '1.0.0', authorised_for_research: true };

beforeEach(() => {
  sessionStorage.clear();
  apiMocks.savedFormalRuns.mockResolvedValue({items:[],total:0,offset:0,limit:25});
  downloadMocks.saveBlob.mockClear();
  apiMocks.audits.mockResolvedValue([]);
  apiMocks.getAudit.mockReset();
  apiMocks.retry.mockReset();
  apiMocks.execute.mockReset();
  apiMocks.evaluate.mockReset();
  apiMocks.validateAnnotationDataset.mockResolvedValue({ dataset_id: 'labels-v1', dataset_version: '1.0.0', fingerprint_sha256: 'a'.repeat(64), conversations: 2, gold_memories: 8, gold_relationships: 2, gold_tests: 4, gold_evaluations: 4, created_at: '2026-01-01T00:00:00Z', validation_status: 'valid' });
  apiMocks.researchValidity.mockResolvedValue({ dataset_id: 'labels-v1', dataset_version: '1.0.0', conversations: 2, extraction: { labelled_cases: 8, true_positives: 6, false_positives: 1, true_negatives: 0, false_negatives: 2, precision: 85.7, recall: 75, f1: 80, accuracy: 75, false_positive_rate: null, cohens_kappa: .6 }, relationship: { labelled_cases: 2, true_positives: 1, false_positives: 0, true_negatives: 0, false_negatives: 1, precision: 100, recall: 50, f1: 66.7, accuracy: 50, false_positive_rate: null, cohens_kappa: .2 }, test_validity: { labelled_cases: 4, true_positives: 4, false_positives: 0, true_negatives: 0, false_negatives: 0, precision: 100, recall: 100, f1: 100, accuracy: 100, false_positive_rate: null, cohens_kappa: 1 }, evaluator: { labelled_cases: 4, true_positives: 3, false_positives: 1, true_negatives: 0, false_negatives: 0, precision: 75, recall: 100, f1: 85.7, accuracy: 75, false_positive_rate: null, cohens_kappa: .5 } });
  apiMocks.validateBenchmark.mockResolvedValue({ report: { benchmark_family: 'locomo', adapter_version: 'local-compatible-v1', cases_imported: 2, case_ids: ['B1', 'B2'], dimension_hints: ['accuracy'], source_format: 'local', notice: 'Local validation only.' }, cases: [] });
  apiMocks.runBenchmark.mockResolvedValue({ metadata: { benchmark_family: 'locomo', run_id: 'LOCAL-RUN-1', runner_version: 'local-v1', source_fingerprint_sha256: 'fingerprint', source_label: 'benchmark.json', memory_strategy: 'scope_aware', notice: 'Local baseline only.' }, cases: [{ case_id: 'B1', category: 'knowledge-update', dimension: 'freshness', question: 'What is current?', response_text: 'PostgreSQL', passed: true, evaluation_reason: 'matched', retrieved_memory_ids: ['B1-MEM-2'] }], categories: [], dimensions: [], tests_passed: 1, tests_total: 1, overall_percentage: 100 });
  apiMocks.analysePilot.mockResolvedValue({ pilot_id: 'pilot-v1', dataset_id: 'labels-v1', dataset_version: '1.0.0', fingerprint_sha256: 'pilot-hash', annotator_ids: ['A', 'B'], minimum_paired_items_per_task: 5, minimum_kappa: .6, overall: { task: null, declared_items: 5, annotator_a_labelled: 5, annotator_b_labelled: 5, paired_items: 5, adjudicated_items: 5, agreement_count: 4, disagreement_count: 1, percent_agreement: 80, cohens_kappa: .7, kappa_applicable: true, disagreements_adjudicated: 1, unresolved_disagreements: 0 }, by_task: [{ task: 'test_validity', declared_items: 5, annotator_a_labelled: 5, annotator_b_labelled: 5, paired_items: 5, adjudicated_items: 5, agreement_count: 4, disagreement_count: 1, percent_agreement: 80, cohens_kappa: .7, kappa_applicable: true, disagreements_adjudicated: 1, unresolved_disagreements: 0 }], ready_for_formal_evaluation: true, blocking_reasons: [], retention: 'request_scoped_not_persisted' });
  apiMocks.createFormalSyntheticMatrix.mockResolvedValue({ dataset_id: 'labels-v1', dataset_version: '1.0.0', dataset_fingerprint_sha256: 'hash', pilot_id: 'pilot-v1', condition_count: 2, scenario_count: 1, repetition_count:3, total_audit_runs: 6, total_target_calls: 24, scenarios: [{ source_conversation_id: 'S1', experiment_id: 'EXP1', run_ids: ['RUN1', 'RUN2', 'RUN3','RUN4','RUN5','RUN6'], test_count: 4 }], notice: 'Frozen.', acceptance_protocol:{format:'formal-acceptance-protocol-v1',study_mode:'formal_experiment_b',frozen_at:'2026-10-12T00:00:00Z',criteria,dataset_fingerprint_sha256:'hash',runtime_source_sha256:'source',notice:'Test fixture only.'} });
  apiMocks.createExploratorySyntheticMatrix.mockResolvedValue({ dataset_id: 'labels-v1', dataset_version: '1.0.0', dataset_fingerprint_sha256: 'hash', pilot_id: 'pilot-v1', condition_count: 2, scenario_count: 1, repetition_count:1, total_audit_runs: 2, total_target_calls: 8, scenarios: [{ source_conversation_id: 'S1', experiment_id: 'EXP1', run_ids: ['RUN1', 'RUN2'], test_count: 4 }], notice: 'Exploratory fixture.', acceptance_protocol:{format:'formal-acceptance-protocol-v1',study_mode:'exploratory',frozen_at:'2026-10-12T00:00:00Z',criteria,dataset_fingerprint_sha256:'hash',runtime_source_sha256:'source',notice:'Test fixture only.'} });
});

test('runs an authorised selected local benchmark and shows its results', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await selectUIOption(user, 'Benchmark family', 'LoCoMo');
  await user.upload(screen.getByLabelText('Local benchmark JSON'), new File([JSON.stringify([{ id: 'B1' }])], 'benchmark.json', { type: 'application/json' }));
  expect(apiMocks.validateBenchmark).not.toHaveBeenCalled();
  await user.click(screen.getByLabelText('Benchmark source authorisation'));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Validate Benchmark Input' })).toBeEnabled());
  await user.click(screen.getByRole('button', { name: 'Validate Benchmark Input' }));
  await waitFor(() => expect(apiMocks.validateBenchmark).toHaveBeenCalledWith('locomo', [{ id: 'B1' }], true));
  expect(screen.getByText('LoCoMo-compatible input validated')).not.toBeNull();
  await selectUIOption(user, 'Benchmark memory strategy', 'Match the task and project');
  await user.click(screen.getByRole('button', { name: 'Run Local Baseline' }));
  await waitFor(() => expect(apiMocks.runBenchmark).toHaveBeenCalledWith('locomo', [{ id: 'B1' }], true, 'benchmark.json', 'scope_aware'));
  expect(screen.getByText('LoCoMo local baseline completed')).not.toBeNull();
  expect(screen.getByText('Case 1')).not.toBeNull();
  expect(screen.getByText('1 record')).not.toBeNull();
  expect(screen.queryByText('B1-MEM-2')).toBeNull();
});

test('analyses a pilot package and displays readiness, coverage and agreement', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Pilot package JSON'), new File([JSON.stringify(pilot)], 'pilot.json', { type: 'application/json' }));
  await user.click(screen.getByRole('button', { name: 'Analyse Pilot Package' }));
  await waitFor(() => expect(apiMocks.analysePilot).toHaveBeenCalledWith(pilot,true));
  expect(screen.getByText('Pilot annotation checks passed')).not.toBeNull();
  expect(screen.getByRole('img', { name: /Review completion by task/ })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Exact review counts & agreement' }));
  expect(screen.getAllByText('test validity')).not.toHaveLength(0);
  expect(screen.getByText('Overall κ 0.70')).not.toBeNull();
});

test.each([
  ['AI-assisted synthetic engineering fixture','AI-assisted synthetic engineering fixture'],
  [undefined,'Not recorded'],
])('reference validation retains declared source without claiming human independence (%s)',async(source,expected)=>{
  const result=await apiMocks.validateAnnotationDataset();
  apiMocks.validateAnnotationDataset.mockResolvedValue({...result,data_origin:source});
  const user=userEvent.setup();render(<ResearchValidation/>);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'),new File([JSON.stringify(dataset)],'labels.json',{type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  expect(screen.getByText(`Declared source: ${expected}`)).toBeInTheDocument();
  expect(screen.getByText('Format and reference checks do not verify independent human review.')).toBeInTheDocument();
});

test('creates an explicitly exploratory matrix without a frozen Experiment B plan', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File([JSON.stringify(dataset)], 'labels.json', { type: 'application/json' }));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  await user.upload(screen.getByLabelText('Pilot package JSON'), new File([JSON.stringify(pilot)], 'pilot.json', { type: 'application/json' }));
  await user.click(screen.getByRole('button', { name: 'Analyse Pilot Package' }));
  await fillSuccessCriteria(user);
  await user.click(screen.getByLabelText('Synthetic data confirmation'));
  await user.click(screen.getByRole('button', { name: 'Create Exploratory Matrix' }));
  await waitFor(() => expect(apiMocks.createExploratorySyntheticMatrix).toHaveBeenCalled());
  expect(apiMocks.createExploratorySyntheticMatrix.mock.calls.at(-1)?.[0].repetitions).toBe(1);
  expect(apiMocks.createExploratorySyntheticMatrix.mock.calls.at(-1)?.[0].study_design).toBeUndefined();
  expect(apiMocks.createFormalSyntheticMatrix).not.toHaveBeenCalled();
  expect(screen.getByText('Exploratory synthetic matrix created')).not.toBeNull();
  expect(screen.getByRole('button', { name: 'Run 2 Experiments' })).not.toBeNull();
});

test('a rounded agreement score cannot hide a below-threshold formal gate', async () => {
  const report = await apiMocks.analysePilot();
  const reason = "test_validity: Cohen's kappa 0.599691 is below the declared minimum 0.6; readiness uses the unrounded value.";
  apiMocks.analysePilot.mockResolvedValue({...report,
    overall: {...report.overall, cohens_kappa: 0.5996908809891808},
    ready_for_formal_evaluation: false, blocking_reasons: [reason]});
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File([JSON.stringify(dataset)], 'labels.json', {type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  await user.upload(screen.getByLabelText('Pilot package JSON'), new File([JSON.stringify(pilot)], 'pilot.json', {type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Analyse Pilot Package'}));
  await fillSuccessCriteria(user);
  await user.click(screen.getByLabelText('Synthetic data confirmation'));
  expect(screen.getByText('Overall κ 0.60')).toBeInTheDocument();
  expect(screen.getByText(/Required κ: 0.6.*readiness uses unrounded values/)).toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Required checks (1)'}));
  expect(screen.getByText(/test validity: Cohen's kappa 0.599691.*unrounded value/)).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Create Exploratory Matrix'})).toBeDisabled();
  expect(apiMocks.createFormalSyntheticMatrix).not.toHaveBeenCalled();
});

test('validates imported research labels and displays a consolidated chart for all four stages', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File([JSON.stringify(dataset)], 'labels.json', { type: 'application/json' }));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  await user.upload(screen.getByLabelText('Prediction set JSON'), new File([JSON.stringify(predictions)], 'predictions.json', { type: 'application/json' }));
  await user.click(screen.getByRole('button', { name: 'Validate Research Files' }));
  await waitFor(() => expect(apiMocks.researchValidity).toHaveBeenCalledWith(dataset, predictions,true));
  expect(screen.getByText('Annotation dataset validated')).not.toBeNull();
  expect(screen.getByRole('button', {name: 'Download metrics & provenance'})).toBeDisabled();
  expect(screen.getByRole('img', {name:/Auditor validity by stage.*Memory Extraction/})).not.toBeNull();
  expect(screen.getByRole('img', {name:/Relationship Classification/})).not.toBeNull();
  expect(screen.getByRole('img', {name:/Test Validity/})).not.toBeNull();
  expect(screen.getByRole('img', {name:/Behaviour Evaluator/})).not.toBeNull();
});

test('requires a local source and consent before a benchmark can run', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  expect((screen.getByRole('button', { name: 'Run Local Baseline' }) as HTMLButtonElement).disabled).toBe(true);
  await user.upload(screen.getByLabelText('Local benchmark JSON'), new File(['not json'], 'broken.json', { type: 'application/json' }));
  expect(apiMocks.validateBenchmark).not.toHaveBeenCalled();
  expect(screen.getByText(/selected file has not been read/i)).toBeInTheDocument();
  expect(screen.queryByText(/not valid JSON/i)).not.toBeInTheDocument();
  await user.click(screen.getByLabelText('Benchmark source authorisation'));
  await waitFor(() => expect(screen.getByText(/not valid JSON/i)).toBeInTheDocument());
});


test('shows actual blank review coverage without exposing dataset hashes', async () => {
  const user = userEvent.setup();
  const hash = 'a'.repeat(64);
  const empty = {task:null,declared_items:174,annotator_a_labelled:0,annotator_b_labelled:0,paired_items:0,adjudicated_items:0,agreement_count:0,disagreement_count:0,percent_agreement:null,cohens_kappa:null,kappa_applicable:false,disagreements_adjudicated:0,unresolved_disagreements:0};
  apiMocks.analysePilot.mockResolvedValue({dataset_version:hash,overall:empty,by_task:[],ready_for_formal_evaluation:false,blocking_reasons:['Both reviewers must label all items.']});
  render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Pilot package JSON'),new File([JSON.stringify(pilot)],'blank.json',{type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Analyse Pilot Package'}));
  expect(await screen.findByText('Evidence-bound dataset release · 0 of 174 items labelled by both reviewers')).toBeTruthy();
  expect(screen.queryByText(new RegExp(hash))).toBeNull();
  expect(screen.queryByText(/two independent reviewers/)).toBeNull();
  expect(screen.getByRole('button',{name:'Create Exploratory Matrix'})).toBeDisabled();
});

test('shows missing and uncertain prediction coverage instead of implying complete assessment', async () => {
  const user = userEvent.setup();
  const metric = {labelled_cases:0,precision:null,recall:null,f1:null,accuracy:null,false_positive_rate:null,cohens_kappa:null};
  apiMocks.researchValidity.mockResolvedValue({dataset_id:'labels-v1',dataset_version:'1.0.0',conversations:1,extraction:metric,relationship:metric,test_validity:metric,evaluator:metric,test_assessment_coverage:{expected:5,submitted:0,decided:0,missing:5,abstained:0},evaluator_coverage:{expected:5,submitted:1,decided:0,missing:4,abstained:1}});
  render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File([JSON.stringify(dataset)],'labels.json',{type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  await user.upload(screen.getByLabelText('Prediction set JSON'), new File([JSON.stringify(predictions)],'empty.json',{type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  expect(await screen.findByText('Question assessments: 0 / 5 decided · 5 missing · 0 uncertain')).not.toBeNull();
  expect(screen.getByText('Answer judgments: 0 / 5 decided · 4 missing · 1 uncertain')).not.toBeNull();
  expect(screen.queryByText(/Accuracy 60%/)).toBeNull();
});

test('creates two models under one selected memory strategy with identical frozen settings', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File([JSON.stringify(dataset)], 'labels.json', { type:'application/json' }));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  await user.upload(screen.getByLabelText('Pilot package JSON'), new File([JSON.stringify(pilot)], 'pilot.json', { type:'application/json' }));
  await user.click(screen.getByRole('button', {name:'Analyse Pilot Package'}));
  const models = screen.getByLabelText('Formal matrix target model');
  await user.clear(models);
  await user.type(models, 'qwen/small\nqwen/large');
  for (const label of ['Supply no memories','Replay all retained memories','First-match retrieval','Relationship-priority retrieval','Rank memories by relevance','Consider time and importance']) {
    await user.click(screen.getByRole('checkbox',{name:label}));
  }
  await fillSuccessCriteria(user);
  await user.click(screen.getByLabelText('Synthetic data confirmation'));
  await user.click(screen.getByRole('button',{name:'Create Exploratory Matrix'}));
  await waitFor(()=>expect(apiMocks.createExploratorySyntheticMatrix).toHaveBeenCalled());
  const conditions = apiMocks.createExploratorySyntheticMatrix.mock.calls[0][0].conditions;
  expect(conditions).toHaveLength(2);
  expect(conditions.map((value: {model:string})=>value.model)).toEqual(['qwen/small','qwen/large']);
  expect(conditions.every((value:{memory_strategy:string;temperature:number})=>value.memory_strategy==='scope_aware'&&value.temperature===0)).toBe(true);
});


async function prepareFormalMatrixUi() {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File([JSON.stringify(dataset)], 'labels.json', {type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  await user.upload(screen.getByLabelText('Pilot package JSON'), new File([JSON.stringify(pilot)], 'pilot.json', {type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Analyse Pilot Package'}));
  await fillSuccessCriteria(user);
  await user.click(screen.getByLabelText('Synthetic data confirmation'));
  await user.click(screen.getByRole('button',{name:'Create Exploratory Matrix'}));
  return user;
}

async function prepareFormalStudyForm(targetRuntime:'Local Ollama'|'Deterministic rule-based baseline', researchSource=false) {
  const user=userEvent.setup();render(<ResearchValidation/>);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'),new File([JSON.stringify(researchSource?{...dataset,data_origin:'deidentified_research'}:dataset)],'labels.json',{type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  await user.upload(screen.getByLabelText('Pilot package JSON'),new File([JSON.stringify(pilot)],'pilot.json',{type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Analyse Pilot Package'}));
  await fillSuccessCriteria(user);
  if(researchSource){
    await user.upload(screen.getByLabelText('Source permission receipt JSON'),new File([JSON.stringify({release_id:'fixture-only',dataset_fingerprint_sha256:'a'.repeat(64),cloud_processing_authorised:false})],'permission.json',{type:'application/json'}));
    await user.click(screen.getByLabelText('Research data confirmation'));
  }else await user.click(screen.getByLabelText('Synthetic data confirmation'));
  await selectUIOption(user,'Formal matrix target runtime',targetRuntime);
  await user.click(screen.getByRole('checkbox',{name:'Run as formal Experiment B with a frozen analysis plan'}));
  for(const label of ['Supply no memories','Replay all retained memories','Rank memories by relevance','Match the task and project','Consider time and importance']) await user.click(screen.getByRole('checkbox',{name:label}));
  const development={dataset_id:'development-v1',dataset_version:'1.0.0',conversations:[]};
  await user.upload(screen.getByLabelText('Development annotation dataset JSON'),new File([JSON.stringify(development)],'development.json',{type:'application/json'}));
  fireEvent.change(screen.getByLabelText('Formal scene selection rule'),{target:{value:'Select every permitted history before inspecting any formal results; exclude none.'}});
  return user;
}

test('formal Experiment B requires three repetitions for a local model provider',async()=>{
  const user=await prepareFormalStudyForm('Local Ollama');
  const repeats=screen.getByLabelText('Runs per condition');
  expect(repeats).toHaveValue('3');
  await user.clear(repeats);await user.type(repeats,'1');
  expect(screen.getByRole('button',{name:'Create Formal Experiment B'})).toBeDisabled();
  expect(screen.getByText(/Formal Experiment B requires 3–5 runs per condition/)).toBeInTheDocument();
  await user.clear(repeats);await user.type(repeats,'3');
  expect(screen.getByRole('button',{name:'Create Formal Experiment B'})).toBeEnabled();
});

test('formal Experiment B also requires three runs for the deterministic baseline',async()=>{
  const user=await prepareFormalStudyForm('Deterministic rule-based baseline');
  expect(screen.getByLabelText('Runs per condition')).toHaveValue('3');
  const repeats=screen.getByLabelText('Runs per condition');
  await user.clear(repeats);await user.type(repeats,'1');
  expect(screen.getByRole('button',{name:'Create Formal Experiment B'})).toBeDisabled();
  await user.clear(repeats);await user.type(repeats,'3');
  await user.click(screen.getByRole('button',{name:'Create Formal Experiment B'}));
  await waitFor(()=>expect(apiMocks.createFormalSyntheticMatrix).toHaveBeenCalled());
  expect(apiMocks.createFormalSyntheticMatrix.mock.calls.at(-1)?.[0].repetitions).toBe(3);
});

test('resumes a formal matrix without executing completed or already answered conditions', async () => {
  const user = await prepareFormalMatrixUi();
  const states: Record<string,string> = {RUN1:'COMPLETED',RUN2:'TESTS_EXECUTED'};
  apiMocks.getAudit.mockImplementation(async(id:string)=>({run_id:id,status:states[id]}));
  apiMocks.execute.mockRejectedValue(new Error('Execution is frozen after answers were saved.'));
  apiMocks.evaluate.mockImplementation(async(id:string)=>{states[id]='COMPLETED';});
  await user.click(screen.getByRole('button',{name:'Run 2 Experiments'}));
  await waitFor(()=>expect(apiMocks.evaluate).toHaveBeenCalledWith('RUN2'));
  expect(apiMocks.execute).not.toHaveBeenCalled();
  expect(apiMocks.evaluate).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/Completed 2 controlled audit runs/)).toBeTruthy();
});


test('recovers a lost execution reply without another target execution', async () => {
  const user = await prepareFormalMatrixUi();
  const states: Record<string,string> = {RUN1:'COMPLETED',RUN2:'TESTS_GENERATED'};
  apiMocks.getAudit.mockImplementation(async(id:string)=>({run_id:id,status:states[id]}));
  apiMocks.execute.mockImplementation(async(id:string)=>{states[id]='TESTS_EXECUTED';throw new Error('Connection interrupted after answers saved.');});
  apiMocks.evaluate.mockImplementation(async(id:string)=>{states[id]='COMPLETED';});
  await user.click(screen.getByRole('button',{name:'Run 2 Experiments'}));
  await screen.findByText('Connection interrupted after answers saved.');
  await user.click(screen.getByRole('button',{name:'Run 2 Experiments'}));
  await screen.findByText(/Completed 2 controlled audit runs/);
  expect(apiMocks.execute).toHaveBeenCalledTimes(1);
  expect(apiMocks.evaluate).toHaveBeenCalledTimes(1);
});

test('keeps cancelled formal conditions terminal and does not announce a complete matrix', async () => {
  const user = await prepareFormalMatrixUi();
  apiMocks.getAudit.mockImplementation(async(id:string)=>({run_id:id,status:id==='RUN1'?'COMPLETED':'CANCELLED'}));
  await user.click(screen.getByRole('button',{name:'Run 2 Experiments'}));
  await screen.findByText(/A condition was cancelled/);
  expect(apiMocks.execute).not.toHaveBeenCalled();
  expect(apiMocks.evaluate).not.toHaveBeenCalled();
  expect(apiMocks.retry).not.toHaveBeenCalled();
  expect(screen.queryByText(/Completed 2 controlled audit runs/)).toBeNull();
});

test('restores only a safe matrix plan after remount and verifies saved completion', async () => {
  const user = await prepareFormalMatrixUi();
  const saved = sessionStorage.getItem('mha-formal-matrix-plan');
  expect(saved).toBeTruthy();
  expect(saved).not.toContain('annotators');
  expect(saved).not.toContain('gold_memories');
  cleanup();render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  apiMocks.getAudit.mockResolvedValue({status:'COMPLETED'});
  await user.click(screen.getByRole('button',{name:'Run 2 Experiments'}));
  await screen.findByText(/Completed 2 controlled audit runs/);
  expect(apiMocks.execute).not.toHaveBeenCalled();
  expect(apiMocks.evaluate).not.toHaveBeenCalled();
});


test('verifies the durable stage planner result after a failed condition is recovered', async () => {
  const user = await prepareFormalMatrixUi();
  const states: Record<string,string> = {RUN1:'COMPLETED',RUN2:'FAILED'};
  apiMocks.getAudit.mockImplementation(async(id:string)=>({run_id:id,status:states[id]}));
  apiMocks.retry.mockImplementation(async(id:string)=>{states[id]='COMPLETED';});
  await user.click(screen.getByRole('button',{name:'Run 2 Experiments'}));
  await screen.findByText(/Completed 2 controlled audit runs/);
  expect(apiMocks.retry).toHaveBeenCalledWith('RUN2');
  expect(apiMocks.execute).not.toHaveBeenCalled();
  expect(apiMocks.evaluate).not.toHaveBeenCalled();
});


test('exports bound metrics intact and removes the export when inputs change', async () => {
  const user = userEvent.setup();
  const report = {...await apiMocks.researchValidity(), metric_version:'research-count-metrics-v1', annotation_fingerprint_sha256:'a'.repeat(64), prediction_fingerprint_sha256:'b'.repeat(64), notice:'Synthetic contract fixture only; no independent human evidence.'};
  apiMocks.researchValidity.mockResolvedValue(report);
  apiMocks.researchValidity.mockClear();
  render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File([JSON.stringify(dataset)], 'labels.json', {type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  await user.upload(screen.getByLabelText('Prediction set JSON'), new File([JSON.stringify(predictions)], 'predictions.json', {type:'application/json'}));
  await user.click(screen.getByRole('button', {name:'Validate Research Files'}));
  const download = await screen.findByRole('button', {name:'Download metrics & provenance'});
  await user.click(download);
  expect(downloadMocks.saveBlob).toHaveBeenCalledWith(expect.any(Blob), 'auditor-validity-metrics.json');
  const contents = await new Promise<string>((resolve,reject) => {const reader = new FileReader();reader.onload = () => resolve(String(reader.result));reader.onerror = () => reject(reader.error);reader.readAsText(downloadMocks.saveBlob.mock.calls[0][0]);});
  expect(JSON.parse(contents)).toEqual(report);
  await user.upload(screen.getByLabelText('Prediction set JSON'), new File([JSON.stringify({...predictions, evaluator_predictions:[{passed:null}]})], 'changed.json', {type:'application/json'}));
  expect(screen.queryByRole('button', {name:'Download metrics & provenance'})).not.toBeInTheDocument();
});


test('formal creation remains blocked when a ready pilot belongs to different dataset content', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'),new File([JSON.stringify(dataset)],'labels.json',{type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  await user.upload(screen.getByLabelText('Pilot package JSON'),new File([JSON.stringify({...pilot,dataset_fingerprint_sha256:'b'.repeat(64)})],'stale-pilot.json',{type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Analyse Pilot Package'}));
  await fillSuccessCriteria(user);
  await user.click(screen.getByLabelText('Synthetic data confirmation'));
  expect(screen.getByRole('button',{name:'Create Exploratory Matrix'})).toBeDisabled();
  expect(screen.getByText(/pilot is not bound to the currently validated dataset/)).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Download dataset review receipt'})).toBeEnabled();
  expect(apiMocks.createFormalSyntheticMatrix).not.toHaveBeenCalled();
});


test('review receipt remains available when browser download does not produce a file', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'),new File([JSON.stringify(dataset)],'labels.json',{type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  await user.click(await screen.findByRole('button',{name:'Download dataset review receipt'}));
  const receipt = JSON.parse((screen.getByLabelText('Dataset review receipt JSON') as HTMLTextAreaElement).value);
  expect(receipt.dataset_fingerprint_sha256).toBe('a'.repeat(64));
  expect(receipt.dataset_id).toBe(dataset.dataset_id);
  expect(screen.getByLabelText('Dataset review receipt JSON')).toHaveAttribute('readonly');
  expect(apiMocks.createFormalSyntheticMatrix).not.toHaveBeenCalled();
});


test('a late dataset validation cannot restore evidence after the source file changes', async () => {
  const originalReport = await apiMocks.validateAnnotationDataset();
  let resolveOld!: (value: unknown) => void;
  apiMocks.validateAnnotationDataset.mockImplementationOnce(() => new Promise(resolve => {resolveOld=resolve;}));
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'),new File([JSON.stringify(dataset)],'original.json',{type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'),new File([JSON.stringify({...dataset,dataset_version:'2.0.0'})],'replacement.json',{type:'application/json'}));
  await act(async()=>resolveOld(originalReport));
  expect(screen.queryByRole('button',{name:'Download dataset review receipt'})).toBeNull();
  expect(screen.queryByText('Annotation dataset validated')).toBeNull();
  expect(screen.getByRole('button',{name:'Create Exploratory Matrix'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Validate Research Files'})).toBeEnabled();
});

test('an invalid replacement file clears previously validated evidence', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File([JSON.stringify(dataset)], 'valid.json', {type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  expect(await screen.findByRole('button',{name:'Download dataset review receipt'})).not.toBeNull();
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File(['[]'], 'invalid.json', {type:'application/json'}));
  expect(screen.queryByRole('button',{name:'Download dataset review receipt'})).toBeNull();
  expect(screen.getByRole('button',{name:'Validate Research Files'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Create Exploratory Matrix'})).toBeDisabled();
});

test('late pilot analysis cannot restore readiness after its package changes', async () => {
  const report = await apiMocks.analysePilot();
  let resolveOld!: (value: unknown) => void;
  apiMocks.analysePilot.mockImplementationOnce(() => new Promise(resolve => {resolveOld=resolve;}));
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Pilot package JSON'), new File([JSON.stringify(pilot)], 'original.json', {type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Analyse Pilot Package'}));
  await user.upload(screen.getByLabelText('Pilot package JSON'), new File([JSON.stringify({...pilot,pilot_id:'replacement'})], 'replacement.json', {type:'application/json'}));
  await act(async()=>resolveOld(report));
  expect(screen.queryByText('Pilot annotation checks passed')).toBeNull();
  expect(screen.getByRole('button',{name:'Analyse Pilot Package'})).toBeEnabled();
  expect(screen.getByRole('button',{name:'Create Exploratory Matrix'})).toBeDisabled();
});

test('changing benchmark family ignores a pending validation from the old family', async () => {
  const report = await apiMocks.validateBenchmark();
  let resolveOld!: (value: unknown) => void;
  apiMocks.validateBenchmark.mockImplementationOnce(() => new Promise(resolve => {resolveOld=resolve;}));
  const user=userEvent.setup();render(<ResearchValidation/>);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Local benchmark JSON'),new File(['[{"id":"B1"}]'],'source.json',{type:'application/json'}));
  await user.click(screen.getByLabelText('Benchmark source authorisation'));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Validate Benchmark Input'})).toBeEnabled());
  await user.click(screen.getByRole('button',{name:'Validate Benchmark Input'}));
  await selectUIOption(user,'Benchmark family','BEAM');
  await act(async()=>resolveOld(report));
  expect(screen.queryByText('BEAM-compatible input validated')).toBeNull();
  expect(screen.getByRole('button',{name:'Validate Benchmark Input'})).toBeEnabled();
});

test('invalid benchmark replacement revokes the old source and authorisation', async () => {
  const user=userEvent.setup();render(<ResearchValidation/>);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Local benchmark JSON'),new File(['[{"id":"B1"}]'],'source.json',{type:'application/json'}));
  await user.click(screen.getByLabelText('Benchmark source authorisation'));
  await user.upload(screen.getByLabelText('Local benchmark JSON'),new File(['false'],'invalid.json',{type:'application/json'}));
  expect(screen.getByLabelText('Benchmark source authorisation')).not.toBeChecked();
  expect(screen.getByRole('button',{name:'Run Local Baseline'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Validate Benchmark Input'})).toBeDisabled();
});

test('changing benchmark strategy cannot restore a pending run for the old setting', async () => {
  const report=await apiMocks.runBenchmark();let resolveOld!: (value:unknown)=>void;
  apiMocks.runBenchmark.mockImplementationOnce(()=>new Promise(resolve=>{resolveOld=resolve;}));
  const user=userEvent.setup();render(<ResearchValidation/>);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Local benchmark JSON'),new File(['[{"id":"B1"}]'],'source.json',{type:'application/json'}));
  await user.click(screen.getByLabelText('Benchmark source authorisation'));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Run Local Baseline'})).toBeEnabled());
  await user.click(screen.getByRole('button',{name:'Run Local Baseline'}));
  await selectUIOption(user,'Benchmark memory strategy','Supply no memories');
  await act(async()=>resolveOld(report));
  expect(screen.queryByText('LongMemEval local baseline completed')).toBeNull();
  expect(screen.getByRole('button',{name:'Run Local Baseline'})).toBeEnabled();
});


test('formal creation requires explicit criteria and preserves the frozen receipt',async()=>{
  const user=userEvent.setup();render(<ResearchValidation/>);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'),new File([JSON.stringify(dataset)],'labels.json',{type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  await user.upload(screen.getByLabelText('Pilot package JSON'),new File([JSON.stringify(pilot)],'pilot.json',{type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Analyse Pilot Package'}));
  await user.click(screen.getByLabelText('Synthetic data confirmation'));
  expect(screen.getByRole('button',{name:'Create Exploratory Matrix'})).toBeDisabled();
  await fillSuccessCriteria(user);
  const recall=screen.getByLabelText('Minimum failure recall (%)');
  await user.clear(recall);await user.type(recall,'101');
  expect(screen.getByRole('button',{name:'Create Exploratory Matrix'})).toBeDisabled();
  await user.clear(recall);await user.type(recall,'80');
  await user.click(screen.getByRole('button',{name:'Create Exploratory Matrix'}));
  await waitFor(()=>expect(apiMocks.createExploratorySyntheticMatrix).toHaveBeenCalled());
  expect(apiMocks.createExploratorySyntheticMatrix.mock.calls.at(-1)?.[0].success_criteria).toEqual(criteria);
  await user.click(screen.getByRole('button',{name:'Saved success criteria'}));
  expect(screen.getByRole('row',{name:'Minimum test validity (%) 90%'})).toBeInTheDocument();
  await user.clear(screen.getByLabelText('Minimum test validity (%)'));await user.type(screen.getByLabelText('Minimum test validity (%)'),'0');
  expect(screen.getByRole('row',{name:'Minimum test validity (%) 90%'})).toBeInTheDocument();
  expect(apiMocks.execute).not.toHaveBeenCalled();
});

test('legacy saved plans without success criteria cannot collect new formal results',async()=>{
  const plan=await apiMocks.createExploratorySyntheticMatrix();delete plan.acceptance_protocol;
  sessionStorage.setItem('mha-formal-matrix-plan',JSON.stringify(plan));
  render(<ResearchValidation/>);
  expect(screen.getByText(/Success criteria: Not recorded for this saved plan/)).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Run 2 Experiments'})).toBeDisabled();
});


test('restores a server execution plan without files and locks running while recovery is pending',async()=>{
  const plan=await apiMocks.createExploratorySyntheticMatrix();apiMocks.createExploratorySyntheticMatrix.mockClear();
  sessionStorage.setItem('mha-formal-matrix-plan',JSON.stringify(plan));
  apiMocks.savedFormalRuns.mockResolvedValue({items:[{run_id:'RUN1',provider:'ollama',model:'qwen3:1.7b',memory_strategy:'scope_aware',created_at:'2026-10-12T00:00:00Z',has_frozen_criteria:true,status:'COMPLETED'}],total:1,offset:0,limit:25});
  let resolve!:(value:unknown)=>void;apiMocks.restoreFormalPlan.mockReturnValue(new Promise(r=>resolve=r));
  apiMocks.getAudit.mockResolvedValue({status:'COMPLETED'});
  const user=userEvent.setup();render(<ResearchValidation />);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Restore execution plan'})).toBeEnabled());
  await user.click(screen.getByRole('button',{name:'Restore execution plan'}));
  expect(screen.getByRole('button',{name:'Run 2 Experiments'})).toBeDisabled();
  expect(apiMocks.getAudit).not.toHaveBeenCalled();expect(apiMocks.execute).not.toHaveBeenCalled();
  resolve(plan);
  await waitFor(()=>expect(screen.getByRole('button',{name:'Run 2 Experiments'})).toBeEnabled());
  expect(screen.getByText(/Saved execution plan restored/)).toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Run 2 Experiments'}));
  await waitFor(()=>expect(screen.getByText(/Completed 2 controlled audit runs/)).toBeInTheDocument());
  expect(apiMocks.execute).not.toHaveBeenCalled();expect(apiMocks.evaluate).not.toHaveBeenCalled();
});


test('exploratory matrices retain bounded repeat counts and reject fractional or out-of-range input',async()=>{
  const user=await prepareFormalMatrixUi();apiMocks.createExploratorySyntheticMatrix.mockClear();
  const repeats=screen.getByLabelText('Runs per condition');
  for(const value of ['0','6','2.5','3x']){
    await user.clear(repeats);await user.paste(value);
    expect(screen.getByRole('button',{name:'Create Exploratory Matrix'})).toBeDisabled();
  }
  await user.clear(repeats);await user.type(repeats,'3');
  expect(screen.getByRole('button',{name:'Create Exploratory Matrix'})).toBeEnabled();
  await user.click(screen.getByRole('button',{name:'Create Exploratory Matrix'}));
  await waitFor(()=>expect(apiMocks.createExploratorySyntheticMatrix).toHaveBeenCalled());
  expect(apiMocks.createExploratorySyntheticMatrix.mock.calls.at(-1)?.[0].repetitions).toBe(3);
  expect(screen.getByText(/Repeats use the same reviewed questions/)).toBeInTheDocument();
});


test('exploratory matrices can optionally check a development split',async()=>{
  const user=await prepareFormalMatrixUi();apiMocks.createExploratorySyntheticMatrix.mockClear();
  await user.click(screen.getByRole('checkbox',{name:'Check for reused development histories'}));
  expect(screen.getByRole('button',{name:'Create Exploratory Matrix'})).toBeDisabled();
  const development={dataset_id:'dev-only',dataset_version:'1',conversations:[]};
  await user.upload(screen.getByLabelText('Development annotation dataset JSON'),new File([JSON.stringify(development)],'development.json',{type:'application/json'}));
  expect(screen.getByRole('button',{name:'Create Exploratory Matrix'})).toBeEnabled();
  await user.click(screen.getByRole('button',{name:'Create Exploratory Matrix'}));
  await waitFor(()=>expect(apiMocks.createExploratorySyntheticMatrix).toHaveBeenCalled());
  expect(apiMocks.createExploratorySyntheticMatrix.mock.calls.at(-1)?.[0].development_dataset).toEqual(development);
  await user.upload(screen.getByLabelText('Development annotation dataset JSON'),new File(['invalid-json'],'broken.json',{type:'application/json'}));
  expect(screen.getByRole('button',{name:'Create Exploratory Matrix'})).toBeDisabled();
});


test('analysis plan is blocked without a sampling rule and submitted before execution',async()=>{
  const user=await prepareFormalMatrixUi();apiMocks.createFormalSyntheticMatrix.mockClear();
  await user.click(screen.getByRole('checkbox',{name:'Run as formal Experiment B with a frozen analysis plan'}));
  for(const label of ['Supply no memories','Replay all retained memories','Rank memories by relevance','Match the task and project','Consider time and importance']) await user.click(screen.getByRole('checkbox',{name:label}));
  expect(screen.getByRole('checkbox',{name:'Check for reused development histories'})).toBeChecked();
  expect(screen.getByRole('button',{name:'Create Formal Experiment B'})).toBeDisabled();
  const development={dataset_id:'dev-fixture',dataset_version:'1',conversations:[]};
  await user.upload(screen.getByLabelText('Development annotation dataset JSON'),new File([JSON.stringify(development)],'dev.json',{type:'application/json'}));
  expect(screen.getByRole('button',{name:'Create Formal Experiment B'})).toBeDisabled();
  const rule='Use every permitted scene from the fixed inventory; exclude no scene after inspecting results.';
  fireEvent.change(screen.getByLabelText('Formal scene selection rule'),{target:{value:rule}});
  await user.click(screen.getByRole('button',{name:'Create Formal Experiment B'}));
  await waitFor(()=>expect(apiMocks.createFormalSyntheticMatrix).toHaveBeenCalled());
  expect(apiMocks.createFormalSyntheticMatrix.mock.calls.at(-1)?.[0].study_design).toEqual({sampling_rule:rule,primary_outcome:'overall_memory_health',analysis_unit:'source_history',incomplete_results:'report_without_imputing_scores'});
  expect(apiMocks.execute).not.toHaveBeenCalled();
});


test('research release requires storage confirmation and uses the dedicated formal route',async()=>{
  apiMocks.createFormalResearchMatrix.mockResolvedValue(await apiMocks.createFormalSyntheticMatrix());
  apiMocks.createFormalResearchMatrix.mockClear();
  const user=await prepareFormalStudyForm('Local Ollama',true);
  expect(screen.queryByLabelText('Synthetic data confirmation')).not.toBeInTheDocument();
  await user.click(screen.getByLabelText('Research data confirmation'));
  expect(screen.getByRole('button',{name:'Create Formal Experiment B'})).toBeDisabled();
  await user.click(screen.getByLabelText('Research data confirmation'));
  await user.click(screen.getByRole('button',{name:'Create Formal Experiment B'}));
  await waitFor(()=>expect(apiMocks.createFormalResearchMatrix).toHaveBeenCalledTimes(1));
  expect(apiMocks.createFormalResearchMatrix).toHaveBeenCalledWith(expect.objectContaining({
    synthetic_data_confirmation:false,label_prefix:'Reviewed research release',
    source_release:expect.objectContaining({release_id:'fixture-only',cloud_processing_authorised:false}),
    dataset:expect.objectContaining({data_origin:'deidentified_research'}),repetitions:3,
  }));
});


test('research source files stay unread before permission and clear on revocation', async () => {
  const user=userEvent.setup();
  render(<ResearchValidation/>);
  const read=vi.spyOn(FileReader.prototype,'readAsText');
  const input=screen.getByLabelText('Annotation dataset JSON');
  expect(input).toBeDisabled();
  expect(screen.getByLabelText('Pilot package JSON')).toBeDisabled();
  expect(screen.getByLabelText('Prediction set JSON')).toBeDisabled();
  const file=new File([JSON.stringify(dataset)],'source-labels.json',{type:'application/json'});
  fireEvent.change(input,{target:{files:[file]}});
  expect(read).not.toHaveBeenCalled();
  expect(apiMocks.validateAnnotationDataset).not.toHaveBeenCalled();
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'),file);
  await screen.findByText('source-labels.json');
  await waitFor(()=>expect(screen.getByRole('button',{name:'Validate Research Files'})).toBeEnabled());
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  expect(screen.getByLabelText('Annotation dataset JSON')).toBeDisabled();
  expect(screen.queryByText('source-labels.json')).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Validate Research Files'})).toBeDisabled();
  read.mockRestore();
});

test('permission revocation excludes a pending research validation response', async () => {
  const user=userEvent.setup();render(<ResearchValidation/>);
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await user.upload(screen.getByLabelText('Annotation dataset JSON'),new File([JSON.stringify(dataset)],'labels.json',{type:'application/json'}));
  let resolve:((value:unknown)=>void)|undefined;
  apiMocks.validateAnnotationDataset.mockImplementationOnce(()=>new Promise(done=>{resolve=done;}));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  await waitFor(()=>expect(resolve).toBeDefined());
  await user.click(screen.getByRole('checkbox',{name:'Research file source authorisation'}));
  await act(async()=>{resolve?.({dataset_id:'labels-v1',valid:true,scenario_count:1});});
  expect(screen.queryByText('Annotation dataset validated. Add predictions to calculate Auditor validity metrics.')).not.toBeInTheDocument();
  expect(apiMocks.researchValidity).not.toHaveBeenCalled();
  expect(screen.getByRole('button',{name:'Validate Research Files'})).toBeDisabled();
});
