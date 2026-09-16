import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ResearchValidation } from './ResearchValidation';

const apiMocks = vi.hoisted(() => ({
  validateAnnotationDataset: vi.fn(),
  researchValidity: vi.fn(),
  validateLongMemEval: vi.fn(),
}));

vi.mock('../services/api', () => ({ api: apiMocks }));

const dataset = { dataset_id: 'labels-v1', dataset_version: '1.0.0' };
const predictions = { dataset_id: 'labels-v1', dataset_version: '1.0.0', evaluator_predictions: [] };

beforeEach(() => {
  apiMocks.validateAnnotationDataset.mockResolvedValue({
    dataset_id: 'labels-v1', dataset_version: '1.0.0', fingerprint_sha256: 'abc123',
    conversations: 2, gold_memories: 8, gold_relationships: 2, gold_tests: 4, gold_evaluations: 4,
    created_at: '2026-01-01T00:00:00Z', validation_status: 'valid',
  });
  apiMocks.researchValidity.mockResolvedValue({
    dataset_id: 'labels-v1', dataset_version: '1.0.0', conversations: 2,
    extraction: { labelled_cases: 8, true_positives: 6, false_positives: 1, true_negatives: 0, false_negatives: 2, precision: 85.7, recall: 75, f1: 80, accuracy: 75, false_positive_rate: null, cohens_kappa: .6 },
    relationship: { labelled_cases: 2, true_positives: 1, false_positives: 0, true_negatives: 0, false_negatives: 1, precision: 100, recall: 50, f1: 66.7, accuracy: 50, false_positive_rate: null, cohens_kappa: .2 },
    test_validity: { labelled_cases: 4, true_positives: 4, false_positives: 0, true_negatives: 0, false_negatives: 0, precision: 100, recall: 100, f1: 100, accuracy: 100, false_positive_rate: null, cohens_kappa: 1 },
    evaluator: { labelled_cases: 4, true_positives: 3, false_positives: 1, true_negatives: 0, false_negatives: 0, precision: 75, recall: 100, f1: 85.7, accuracy: 75, false_positive_rate: null, cohens_kappa: .5 },
  });
  apiMocks.validateLongMemEval.mockResolvedValue({ report: { adapter_version: 'longmemeval-compatible-v1', cases_imported: 2, case_ids: ['B1', 'B2'], dimension_hints: ['accuracy'], source_format: 'local', notice: 'Local validation only.' }, cases: [] });
});

test('validates imported research files and displays all four validity cards', async () => {
  const user = userEvent.setup();
  render(<ResearchValidation />);
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File([JSON.stringify(dataset)], 'labels.json', { type: 'application/json' }));
  await user.upload(screen.getByLabelText('Prediction set JSON'), new File([JSON.stringify(predictions)], 'predictions.json', { type: 'application/json' }));
  await user.upload(screen.getByLabelText('LongMemEval-compatible JSON'), new File([JSON.stringify([{ id: 'B1' }])], 'benchmark.json', { type: 'application/json' }));
  await user.click(screen.getByRole('button', { name: 'Validate Research Files' }));
  await waitFor(() => expect(apiMocks.researchValidity).toHaveBeenCalledWith(dataset, predictions));
  expect(apiMocks.validateLongMemEval).toHaveBeenCalledWith([{ id: 'B1' }]);
  expect(screen.getByText('Annotation dataset validated')).not.toBeNull();
  expect(screen.getByText('Memory Extraction')).not.toBeNull();
  expect(screen.getByText('Relationship Classification')).not.toBeNull();
  expect(screen.getByText('Test Validity')).not.toBeNull();
  expect(screen.getByText('Behaviour Evaluator')).not.toBeNull();
  expect(screen.getByText('LongMemEval-compatible input validated')).not.toBeNull();
});

test('requires an annotation dataset before validation', async () => {
  const user = userEvent.setup();
  render(<ResearchValidation />);
  expect((screen.getByRole('button', { name: 'Validate Research Files' }) as HTMLButtonElement).disabled).toBe(true);
  await user.upload(screen.getByLabelText('Annotation dataset JSON'), new File(['not json'], 'broken.json', { type: 'application/json' }));
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('not valid JSON'));
});
