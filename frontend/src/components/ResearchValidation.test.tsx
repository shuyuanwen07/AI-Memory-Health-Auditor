import { selectUIOption } from './ui/testHelpers';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ResearchValidation } from './ResearchValidation';

const apiMocks = vi.hoisted(() => ({
  validateAnnotationDataset: vi.fn(), researchValidity: vi.fn(), validateBenchmark: vi.fn(),
  runBenchmark: vi.fn(), analysePilot: vi.fn(), createFormalSyntheticMatrix: vi.fn(), execute: vi.fn(), evaluate: vi.fn(), getAudit: vi.fn(), retry: vi.fn(),
}));
vi.mock('../services/api', () => ({ api: apiMocks }));

const dataset = { dataset_id: 'labels-v1', dataset_version: '1.0.0' };
const predictions = { dataset_id: 'labels-v1', dataset_version: '1.0.0', evaluator_predictions: [] };
const pilot = { pilot_id: 'pilot-v1', dataset_id: 'labels-v1', dataset_version: '1.0.0', authorised_for_research: true };

beforeEach(() => {
  sessionStorage.clear();
  apiMocks.getAudit.mockReset();
  apiMocks.retry.mockReset();
  apiMocks.execute.mockReset();
  apiMocks.evaluate.mockReset();
  apiMocks.validateAnnotationDataset.mockResolvedValue({ dataset_id: 'labels-v1', dataset_version: '1.0.0', fingerprint_sha256: 'abc123', conversations: 2, gold_memories: 8, gold_relationships: 2, gold_tests: 4, gold_evaluations: 4, created_at: '2026-01-01T00:00:00Z', validation_status: 'valid' });
  apiMocks.researchValidity.mockResolvedValue({ dataset_id: 'labels-v1', dataset_version: '1.0.0', conversations: 2, extraction: { labelled_cases: 8, true_positives: 6, false_positives: 1, true_negatives: 0, false_negatives: 2, precision: 85.7, recall: 75, f1: 80, accuracy: 75, false_positive_rate: null, cohens_kappa: .6 }, relationship: { labelled_cases: 2, true_positives: 1, false_positives: 0, true_negatives: 0, false_negatives: 1, precision: 100, recall: 50, f1: 66.7, accuracy: 50, false_positive_rate: null, cohens_kappa: .2 }, test_validity: { labelled_cases: 4, true_positives: 4, false_positives: 0, true_negatives: 0, false_negatives: 0, precision: 100, recall: 100, f1: 100, accuracy: 100, false_positive_rate: null, cohens_kappa: 1 }, evaluator: { labelled_cases: 4, true_positives: 3, false_positives: 1, true_negatives: 0, false_negatives: 0, precision: 75, recall: 100, f1: 85.7, accuracy: 75, false_positive_rate: null, cohens_kappa: .5 } });
  apiMocks.validateBenchmark.mockResolvedValue({ report: { benchmark_family: 'locomo', adapter_version: 'local-compatible-v1', cases_imported: 2, case_ids: ['B1', 'B2'], dimension_hints: ['accuracy'], source_format: 'local', notice: 'Local validation only.' }, cases: [] });
  apiMocks.runBenchmark.mockResolvedValue({ metadata: { benchmark_family: 'locomo', run_id: 'LOCAL-RUN-1', runner_version: 'local-v1', source_fingerprint_sha256: 'fingerprint', source_label: 'benchmark.json', memory_strategy: 'scope_aware', notice: 'Local baseline only.' }, cases: [{ case_id: 'B1', category: 'knowledge-update', dimension: 'freshness', question: 'What is current?', response_text: 'PostgreSQL', passed: true, evaluation_reason: 'matched', retrieved_memory_ids: ['B1-MEM-2'] }], categories: [], dimensions: [], tests_passed: 1, tests_total: 1, overall_percentage: 100 });
  apiMocks.analysePilot.mockResolvedValue({ pilot_id: 'pilot-v1', dataset_id: 'labels-v1', dataset_version: '1.0.0', fingerprint_sha256: 'pilot-hash', annotator_ids: ['A', 'B'], minimum_paired_items_per_task: 5, minimum_kappa: .6, overall: { task: null, declared_items: 5, annotator_a_labelled: 5, annotator_b_labelled: 5, paired_items: 5, adjudicated_items: 5, agreement_count: 4, disagreement_count: 1, percent_agreement: 80, cohens_kappa: .7, kappa_applicable: true, disagreements_adjudicated: 1, unresolved_disagreements: 0 }, by_task: [{ task: 'test_validity', declared_items: 5, annotator_a_labelled: 5, annotator_b_labelled: 5, paired_items: 5, adjudicated_items: 5, agreement_count: 4, disagreement_count: 1, percent_agreement: 80, cohens_kappa: .7, kappa_applicable: true, disagreements_adjudicated: 1, unresolved_disagreements: 0 }], ready_for_formal_evaluation: true, blocking_reasons: [], retention: 'request_scoped_not_persisted' });
  apiMocks.createFormalSyntheticMatrix.mockResolvedValue({ dataset_id: 'labels-v1', dataset_version: '1.0.0', dataset_fingerprint_sha256: 'hash', pilot_id: 'pilot-v1', condition_count: 2, scenario_count: 1, total_audit_runs: 2, total_target_calls: 8, scenarios: [{ source_conversation_id: 'S1', experiment_id: 'EXP1', run_ids: ['RUN1', 'RUN2'], test_count: 4 }], notice: 'Frozen.' });
});

test('runs an authorised selected local benchmark and shows its results', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await selectUIOption(user, 'Benchmark family', 'LoCoMo');
  await user.upload(screen.getByLabelText('Local benchmark JSON'), new File([JSON.stringify([{ id: 'B1' }])], 'benchmark.json', { type: 'application/json' }));
  await user.click(screen.getByRole('button', { name: 'Validate Benchmark Input' }));
  await waitFor(() => expect(apiMocks.validateBenchmark).toHaveBeenCalledWith('locomo', [{ id: 'B1' }]));
  expect(screen.getByText('LoCoMo-compatible input validated')).not.toBeNull();
  await selectUIOption(user, 'Benchmark memory strategy', 'Scope-aware retrieval');
  await user.click(screen.getByLabelText('Benchmark source authorisation'));
  await user.click(screen.getByRole('button', { name: 'Run Local Baseline' }));
  await waitFor(() => expect(apiMocks.runBenchmark).toHaveBeenCalledWith('locomo', [{ id: 'B1' }], 'benchmark.json', 'scope_aware'));
  expect(screen.getByText('LoCoMo local baseline completed')).not.toBeNull();
  expect(screen.getByText('Case 1')).not.toBeNull();
  expect(screen.getByText('1 record')).not.toBeNull();
  expect(screen.queryByText('B1-MEM-2')).toBeNull();
});

test('analyses a pilot package and displays readiness, coverage and agreement', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.upload(screen.getByLabelText('Pilot package JSON'), new File([JSON.stringify(pilot)], 'pilot.json', { type: 'application/json' }));
  await user.click(screen.getByRole('button', { name: 'Analyse Pilot Package' }));
  await waitFor(() => expect(apiMocks.analysePilot).toHaveBeenCalledWith(pilot));
  expect(screen.getByText('Ready for formal evaluation')).not.toBeNull();
  expect(screen.getAllByText('test validity')).not.toHaveLength(0);
  expect(screen.getByText('Overall κ 0.70')).not.toBeNull();
});

test('creates a formal synthetic matrix only after the matching ready pilot and confirmation', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File([JSON.stringify(dataset)], 'labels.json', { type: 'application/json' }));
  await user.upload(screen.getByLabelText('Pilot package JSON'), new File([JSON.stringify(pilot)], 'pilot.json', { type: 'application/json' }));
  await user.click(screen.getByRole('button', { name: 'Analyse Pilot Package' }));
  await user.click(screen.getByLabelText('Synthetic data confirmation'));
  await user.click(screen.getByRole('button', { name: 'Create Formal Matrix' }));
  await waitFor(() => expect(apiMocks.createFormalSyntheticMatrix).toHaveBeenCalled());
  expect(screen.getByText('Formal synthetic matrix created')).not.toBeNull();
  expect(screen.getByRole('button', { name: 'Run 2 Conditions' })).not.toBeNull();
});

test('validates imported research labels and displays all four validity cards', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File([JSON.stringify(dataset)], 'labels.json', { type: 'application/json' }));
  await user.upload(screen.getByLabelText('Prediction set JSON'), new File([JSON.stringify(predictions)], 'predictions.json', { type: 'application/json' }));
  await user.click(screen.getByRole('button', { name: 'Validate Research Files' }));
  await waitFor(() => expect(apiMocks.researchValidity).toHaveBeenCalledWith(dataset, predictions));
  expect(screen.getByText('Annotation dataset validated')).not.toBeNull();
  expect(screen.getByText('Memory Extraction')).not.toBeNull();
  expect(screen.getByText('Relationship Classification')).not.toBeNull();
  expect(screen.getByText('Test Validity')).not.toBeNull();
  expect(screen.getByText('Behaviour Evaluator')).not.toBeNull();
});

test('requires a local source and consent before a benchmark can run', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  expect((screen.getByRole('button', { name: 'Run Local Baseline' }) as HTMLButtonElement).disabled).toBe(true);
  await user.upload(screen.getByLabelText('Local benchmark JSON'), new File(['not json'], 'broken.json', { type: 'application/json' }));
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('not valid JSON'));
});


test('shows actual blank review coverage without exposing dataset hashes', async () => {
  const user = userEvent.setup();
  const hash = 'a'.repeat(64);
  const empty = {task:null,declared_items:174,annotator_a_labelled:0,annotator_b_labelled:0,paired_items:0,adjudicated_items:0,agreement_count:0,disagreement_count:0,percent_agreement:null,cohens_kappa:null,kappa_applicable:false,disagreements_adjudicated:0,unresolved_disagreements:0};
  apiMocks.analysePilot.mockResolvedValue({dataset_version:hash,overall:empty,by_task:[],ready_for_formal_evaluation:false,blocking_reasons:['Both reviewers must label all items.']});
  render(<ResearchValidation />);
  await user.upload(screen.getByLabelText('Pilot package JSON'),new File([JSON.stringify(pilot)],'blank.json',{type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Analyse Pilot Package'}));
  expect(await screen.findByText('Evidence-bound dataset release · 0 of 174 items labelled by both reviewers')).toBeTruthy();
  expect(screen.queryByText(new RegExp(hash))).toBeNull();
  expect(screen.queryByText(/two independent reviewers/)).toBeNull();
  expect(screen.getByRole('button',{name:'Create Formal Matrix'})).toBeDisabled();
});

test('shows missing and uncertain prediction coverage instead of implying complete assessment', async () => {
  const user = userEvent.setup();
  const metric = {labelled_cases:0,precision:null,recall:null,f1:null,accuracy:null,false_positive_rate:null,cohens_kappa:null};
  apiMocks.researchValidity.mockResolvedValue({dataset_id:'labels-v1',dataset_version:'1.0.0',conversations:1,extraction:metric,relationship:metric,test_validity:metric,evaluator:metric,test_assessment_coverage:{expected:5,submitted:0,decided:0,missing:5,abstained:0},evaluator_coverage:{expected:5,submitted:1,decided:0,missing:4,abstained:1}});
  render(<ResearchValidation />);
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File([JSON.stringify(dataset)],'labels.json',{type:'application/json'}));
  await user.upload(screen.getByLabelText('Prediction set JSON'), new File([JSON.stringify(predictions)],'empty.json',{type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Validate Research Files'}));
  expect(await screen.findByText('Question assessments: 0 / 5 decided · 5 missing · 0 uncertain')).not.toBeNull();
  expect(screen.getByText('Answer judgments: 0 / 5 decided · 4 missing · 1 uncertain')).not.toBeNull();
  expect(screen.queryByText(/Accuracy 60%/)).toBeNull();
});

test('creates two models under one selected memory strategy with identical frozen settings', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File([JSON.stringify(dataset)], 'labels.json', { type:'application/json' }));
  await user.upload(screen.getByLabelText('Pilot package JSON'), new File([JSON.stringify(pilot)], 'pilot.json', { type:'application/json' }));
  await user.click(screen.getByRole('button', {name:'Analyse Pilot Package'}));
  const models = screen.getByLabelText('Formal matrix target model');
  await user.clear(models);
  await user.type(models, 'qwen/small\nqwen/large');
  for (const label of ['no memory','full context','weak first hit','strong rule based','strong score based','temporal importance']) {
    await user.click(screen.getByRole('checkbox',{name:label}));
  }
  await user.click(screen.getByLabelText('Synthetic data confirmation'));
  await user.click(screen.getByRole('button',{name:'Create Formal Matrix'}));
  await waitFor(()=>expect(apiMocks.createFormalSyntheticMatrix).toHaveBeenCalled());
  const conditions = apiMocks.createFormalSyntheticMatrix.mock.calls[0][0].conditions;
  expect(conditions).toHaveLength(2);
  expect(conditions.map((value: {model:string})=>value.model)).toEqual(['qwen/small','qwen/large']);
  expect(conditions.every((value:{memory_strategy:string;temperature:number})=>value.memory_strategy==='scope_aware'&&value.temperature===0)).toBe(true);
});


async function prepareFormalMatrixUi() {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File([JSON.stringify(dataset)], 'labels.json', {type:'application/json'}));
  await user.upload(screen.getByLabelText('Pilot package JSON'), new File([JSON.stringify(pilot)], 'pilot.json', {type:'application/json'}));
  await user.click(screen.getByRole('button',{name:'Analyse Pilot Package'}));
  await user.click(screen.getByLabelText('Synthetic data confirmation'));
  await user.click(screen.getByRole('button',{name:'Create Formal Matrix'}));
  return user;
}

test('resumes a formal matrix without executing completed or already answered conditions', async () => {
  const user = await prepareFormalMatrixUi();
  const states: Record<string,string> = {RUN1:'COMPLETED',RUN2:'TESTS_EXECUTED'};
  apiMocks.getAudit.mockImplementation(async(id:string)=>({run_id:id,status:states[id]}));
  apiMocks.execute.mockRejectedValue(new Error('Execution is frozen after answers were saved.'));
  apiMocks.evaluate.mockImplementation(async(id:string)=>{states[id]='COMPLETED';});
  await user.click(screen.getByRole('button',{name:'Run 2 Conditions'}));
  await waitFor(()=>expect(apiMocks.evaluate).toHaveBeenCalledWith('RUN2'));
  expect(apiMocks.execute).not.toHaveBeenCalled();
  expect(apiMocks.evaluate).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/Completed 2 controlled synthetic audit runs/)).toBeTruthy();
});


test('recovers a lost execution reply without another target execution', async () => {
  const user = await prepareFormalMatrixUi();
  const states: Record<string,string> = {RUN1:'COMPLETED',RUN2:'TESTS_GENERATED'};
  apiMocks.getAudit.mockImplementation(async(id:string)=>({run_id:id,status:states[id]}));
  apiMocks.execute.mockImplementation(async(id:string)=>{states[id]='TESTS_EXECUTED';throw new Error('Connection interrupted after answers saved.');});
  apiMocks.evaluate.mockImplementation(async(id:string)=>{states[id]='COMPLETED';});
  await user.click(screen.getByRole('button',{name:'Run 2 Conditions'}));
  await screen.findByText('Connection interrupted after answers saved.');
  await user.click(screen.getByRole('button',{name:'Run 2 Conditions'}));
  await screen.findByText(/Completed 2 controlled synthetic audit runs/);
  expect(apiMocks.execute).toHaveBeenCalledTimes(1);
  expect(apiMocks.evaluate).toHaveBeenCalledTimes(1);
});

test('keeps cancelled formal conditions terminal and does not announce a complete matrix', async () => {
  const user = await prepareFormalMatrixUi();
  apiMocks.getAudit.mockImplementation(async(id:string)=>({run_id:id,status:id==='RUN1'?'COMPLETED':'CANCELLED'}));
  await user.click(screen.getByRole('button',{name:'Run 2 Conditions'}));
  await screen.findByText(/A condition was cancelled/);
  expect(apiMocks.execute).not.toHaveBeenCalled();
  expect(apiMocks.evaluate).not.toHaveBeenCalled();
  expect(apiMocks.retry).not.toHaveBeenCalled();
  expect(screen.queryByText(/Completed 2 controlled synthetic audit runs/)).toBeNull();
});

test('restores only a safe matrix plan after remount and verifies saved completion', async () => {
  const user = await prepareFormalMatrixUi();
  const saved = sessionStorage.getItem('mha-formal-matrix-plan');
  expect(saved).toBeTruthy();
  expect(saved).not.toContain('annotators');
  expect(saved).not.toContain('gold_memories');
  cleanup();render(<ResearchValidation />);
  apiMocks.getAudit.mockResolvedValue({status:'COMPLETED'});
  await user.click(screen.getByRole('button',{name:'Run 2 Conditions'}));
  await screen.findByText(/Completed 2 controlled synthetic audit runs/);
  expect(apiMocks.execute).not.toHaveBeenCalled();
  expect(apiMocks.evaluate).not.toHaveBeenCalled();
});


test('verifies the durable stage planner result after a failed condition is recovered', async () => {
  const user = await prepareFormalMatrixUi();
  const states: Record<string,string> = {RUN1:'COMPLETED',RUN2:'FAILED'};
  apiMocks.getAudit.mockImplementation(async(id:string)=>({run_id:id,status:states[id]}));
  apiMocks.retry.mockImplementation(async(id:string)=>{states[id]='COMPLETED';});
  await user.click(screen.getByRole('button',{name:'Run 2 Conditions'}));
  await screen.findByText(/Completed 2 controlled synthetic audit runs/);
  expect(apiMocks.retry).toHaveBeenCalledWith('RUN2');
  expect(apiMocks.execute).not.toHaveBeenCalled();
  expect(apiMocks.evaluate).not.toHaveBeenCalled();
});
