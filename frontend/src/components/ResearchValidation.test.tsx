import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ResearchValidation } from './ResearchValidation';

const apiMocks = vi.hoisted(() => ({
  validateAnnotationDataset: vi.fn(), researchValidity: vi.fn(), validateBenchmark: vi.fn(),
  runBenchmark: vi.fn(), analysePilot: vi.fn(),
}));
vi.mock('../services/api', () => ({ api: apiMocks }));

const dataset = { dataset_id: 'labels-v1', dataset_version: '1.0.0' };
const predictions = { dataset_id: 'labels-v1', dataset_version: '1.0.0', evaluator_predictions: [] };
const pilot = { pilot_id: 'pilot-v1', dataset_id: 'labels-v1', dataset_version: '1.0.0', authorised_for_research: true };

beforeEach(() => {
  apiMocks.validateAnnotationDataset.mockResolvedValue({ dataset_id: 'labels-v1', dataset_version: '1.0.0', fingerprint_sha256: 'abc123', conversations: 2, gold_memories: 8, gold_relationships: 2, gold_tests: 4, gold_evaluations: 4, created_at: '2026-01-01T00:00:00Z', validation_status: 'valid' });
  apiMocks.researchValidity.mockResolvedValue({ dataset_id: 'labels-v1', dataset_version: '1.0.0', conversations: 2, extraction: { labelled_cases: 8, true_positives: 6, false_positives: 1, true_negatives: 0, false_negatives: 2, precision: 85.7, recall: 75, f1: 80, accuracy: 75, false_positive_rate: null, cohens_kappa: .6 }, relationship: { labelled_cases: 2, true_positives: 1, false_positives: 0, true_negatives: 0, false_negatives: 1, precision: 100, recall: 50, f1: 66.7, accuracy: 50, false_positive_rate: null, cohens_kappa: .2 }, test_validity: { labelled_cases: 4, true_positives: 4, false_positives: 0, true_negatives: 0, false_negatives: 0, precision: 100, recall: 100, f1: 100, accuracy: 100, false_positive_rate: null, cohens_kappa: 1 }, evaluator: { labelled_cases: 4, true_positives: 3, false_positives: 1, true_negatives: 0, false_negatives: 0, precision: 75, recall: 100, f1: 85.7, accuracy: 75, false_positive_rate: null, cohens_kappa: .5 } });
  apiMocks.validateBenchmark.mockResolvedValue({ report: { benchmark_family: 'locomo', adapter_version: 'local-compatible-v1', cases_imported: 2, case_ids: ['B1', 'B2'], dimension_hints: ['accuracy'], source_format: 'local', notice: 'Local validation only.' }, cases: [] });
  apiMocks.runBenchmark.mockResolvedValue({ metadata: { benchmark_family: 'locomo', run_id: 'LOCAL-RUN-1', runner_version: 'local-v1', source_fingerprint_sha256: 'fingerprint', source_label: 'benchmark.json', memory_strategy: 'scope_aware', notice: 'Local baseline only.' }, cases: [{ case_id: 'B1', category: 'knowledge-update', dimension: 'freshness', question: 'What is current?', response_text: 'PostgreSQL', passed: true, evaluation_reason: 'matched', retrieved_memory_ids: ['B1-MEM-2'] }], categories: [], dimensions: [], tests_passed: 1, tests_total: 1, overall_percentage: 100 });
  apiMocks.analysePilot.mockResolvedValue({ pilot_id: 'pilot-v1', dataset_id: 'labels-v1', dataset_version: '1.0.0', fingerprint_sha256: 'pilot-hash', annotator_ids: ['A', 'B'], minimum_paired_items_per_task: 5, minimum_kappa: .6, overall: { task: null, declared_items: 5, annotator_a_labelled: 5, annotator_b_labelled: 5, paired_items: 5, adjudicated_items: 5, agreement_count: 4, disagreement_count: 1, percent_agreement: 80, cohens_kappa: .7, kappa_applicable: true, disagreements_adjudicated: 1, unresolved_disagreements: 0 }, by_task: [{ task: 'test_validity', declared_items: 5, annotator_a_labelled: 5, annotator_b_labelled: 5, paired_items: 5, adjudicated_items: 5, agreement_count: 4, disagreement_count: 1, percent_agreement: 80, cohens_kappa: .7, kappa_applicable: true, disagreements_adjudicated: 1, unresolved_disagreements: 0 }], ready_for_formal_evaluation: true, blocking_reasons: [], retention: 'request_scoped_not_persisted' });
});

test('runs an authorised selected local benchmark and shows its results', async () => {
  const user = userEvent.setup(); render(<ResearchValidation />);
  await user.selectOptions(screen.getByLabelText('Benchmark family'), 'locomo');
  await user.upload(screen.getByLabelText('Local benchmark JSON'), new File([JSON.stringify([{ id: 'B1' }])], 'benchmark.json', { type: 'application/json' }));
  await user.click(screen.getByRole('button', { name: 'Validate Benchmark Input' }));
  await waitFor(() => expect(apiMocks.validateBenchmark).toHaveBeenCalledWith('locomo', [{ id: 'B1' }]));
  expect(screen.getByText('LoCoMo-compatible input validated')).not.toBeNull();
  await user.selectOptions(screen.getByLabelText('Benchmark memory strategy'), 'scope_aware');
  await user.click(screen.getByLabelText('Benchmark source authorisation'));
  await user.click(screen.getByRole('button', { name: 'Run Local Baseline' }));
  await waitFor(() => expect(apiMocks.runBenchmark).toHaveBeenCalledWith('locomo', [{ id: 'B1' }], 'benchmark.json', 'scope_aware'));
  expect(screen.getByText('LoCoMo local baseline completed')).not.toBeNull();
  expect(screen.getByText('B1-MEM-2')).not.toBeNull();
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
