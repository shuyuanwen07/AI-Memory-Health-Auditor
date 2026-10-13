import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test } from 'vitest';
import { ResearchValidityChart } from './ResearchValidityChart';
import type { BinaryClassificationMetrics, ResearchValidityReport } from '../types/domain';

const metric: BinaryClassificationMetrics = { labelled_cases: 10, true_positives: 0, false_positives: 2, true_negatives: 5, false_negatives: 3, precision: 0, recall: 0, f1: 0, accuracy: 50, false_positive_rate: 28.6, cohens_kappa: -0.32 };
const missing = { ...metric, labelled_cases: 0, true_positives: 0, false_positives: 0, true_negatives: 0, false_negatives: 0, precision: null, recall: null, f1: null, accuracy: null, false_positive_rate: null, cohens_kappa: null };
const report: ResearchValidityReport = { dataset_id: 'hidden-fixture', dataset_version: 'v1', conversations: 2, extraction: metric, relationship: missing, test_validity: metric, evaluator: metric };

test('distinguishes genuine zero scores from missing observations in the chart alternative', () => {
  render(<ResearchValidityChart report={report} />);
  expect(screen.getByRole('img', { name: /Memory Extraction: Precision 0%, Recall 0%, F1 0%; 10 labelled cases/ })).toBeInTheDocument();
  expect(screen.getByRole('img', { name: /Relationship Classification: Precision Not measured, Recall Not measured, F1 Not measured; 0 labelled cases/ })).toBeInTheDocument();
  expect(screen.getByText('N/A · Not measured; no zero score is implied.')).toBeInTheDocument();
  expect(screen.queryByText('hidden-fixture')).not.toBeInTheDocument();
});

test('preserves confusion counts and negative kappa separately from percentage bars', async () => {
  const user = userEvent.setup();
  render(<ResearchValidityChart report={report} />);
  await user.click(screen.getByRole('button', { name: 'Agreement, error counts & score definitions' }));
  expect(await screen.findByRole('columnheader', { name: 'False negatives' })).toBeInTheDocument();
  expect(screen.getAllByRole('cell', { name: '-0.32' })).toHaveLength(3);
  expect(screen.getAllByRole('cell', { name: '28.6%' })).toHaveLength(3);
  expect(screen.getByRole('row', { name: 'Memory Extraction 10 0 2 5 3 50% 28.6% -0.32' })).toBeInTheDocument();
});

test('distinguishes perfect failure detection from wrong and absent categories', () => {
  render(<ResearchValidityChart report={{...report,evaluator:{...metric,recall:100},
    failure_classification:{reference_failures:2,correct:0,wrong_category:1,unclassified:1,
      missed:0,uncertain:0,missing:0,accuracy_all_reference_failures:0,accuracy_detected_failures:0}}} />);
  expect(screen.getByRole('img',{name:/Behaviour Evaluator:.*Recall 100%/})).toBeInTheDocument();
  expect(screen.getByRole('img',{name:/Failure classification outcomes: Correct category 0, Wrong category 1, No category 1/})).toBeInTheDocument();
  expect(screen.getByText(/detected-failure accuracy 0% · all-reference accuracy 0%/)).toBeInTheDocument();
});

test('does not turn missing classification evidence into a complete accuracy score', () => {
  render(<ResearchValidityChart report={{...report,
    failure_classification:{reference_failures:2,correct:1,wrong_category:0,unclassified:0,
      missed:0,uncertain:0,missing:1,accuracy_all_reference_failures:null,accuracy_detected_failures:100}}} />);
  expect(screen.getByText(/detected-failure accuracy 100% · all-reference accuracy Not measured/)).toBeInTheDocument();
  expect(screen.getByRole('img',{name:/Missing result 1; 2 reference failures/})).toBeInTheDocument();
});

test('keeps legacy and zero-reference category evidence visibly unmeasured', () => {
  const {rerender}=render(<ResearchValidityChart report={report} />);
  expect(screen.getByText('Failure-category assessment: Not recorded in this result.')).toBeInTheDocument();
  rerender(<ResearchValidityChart report={{...report,
    failure_classification:{reference_failures:0,correct:0,wrong_category:0,unclassified:0,
      missed:0,uncertain:0,missing:0,accuracy_all_reference_failures:null,accuracy_detected_failures:null}}} />);
  expect(screen.getByText('Not measured · no labelled reference failures.')).toBeInTheDocument();
  expect(screen.queryByRole('img',{name:/Failure classification outcomes/})).not.toBeInTheDocument();
});

test('contrasts decided-answer recall with full-reference recall without hiding uncertain outcomes', () => {
  render(<ResearchValidityChart report={{...report,evaluator:{...metric,recall:100},failure_detection:{reference_failures:2,detected:1,missed:0,uncertain:1,missing:0,recall_all_reference_failures:50}}} />);
  expect(screen.getByRole('img',{name:/Failure recall: Decided answers only 100%; All reference failures 50%/})).toBeInTheDocument();
  expect(screen.getByText('1 detected · 0 missed · 1 uncertain · 0 missing')).toBeInTheDocument();
});

test('missing and absent reference evidence never imply a zero or complete recall', () => {
  const {rerender}=render(<ResearchValidityChart report={{...report,evaluator:{...metric,recall:100},failure_detection:{reference_failures:2,detected:1,missed:0,uncertain:0,missing:1,recall_all_reference_failures:null}}} />);
  expect(screen.getByRole('img',{name:/Failure recall: Decided answers only 100%; All reference failures Not measured/})).toBeInTheDocument();
  rerender(<ResearchValidityChart report={report} />);
  expect(screen.getByText('Full-reference failure recall: Not recorded in this result.')).toBeInTheDocument();
  rerender(<ResearchValidityChart report={{...report,evaluator:missing,failure_detection:{reference_failures:0,detected:0,missed:0,uncertain:0,missing:0,recall_all_reference_failures:null}}} />);
  expect(screen.getByRole('img',{name:/Decided answers only Not measured; All reference failures Not measured/})).toBeInTheDocument();
});
