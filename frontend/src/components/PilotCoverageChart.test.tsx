import { render, screen } from '@testing-library/react';
import { test, expect } from 'vitest';
import { PilotCoverageChart } from './PilotCoverageChart';
import type { PilotAgreementMetrics } from '../types/domain';

const metric: PilotAgreementMetrics = { task: 'test_validity', declared_items: 4, annotator_a_labelled: 4, annotator_b_labelled: 2, paired_items: 2, adjudicated_items: 0, agreement_count: 2, disagreement_count: 0, percent_agreement: 100, cohens_kappa: null, kappa_applicable: false, disagreements_adjudicated: 0, unresolved_disagreements: 0 };

test('shows actual coverage rather than agreement as bar heights', () => {
  const { container } = render(<PilotCoverageChart metrics={[metric]} />);
  expect(screen.getByRole('img', {name: /Question validity: Reviewer 1 4 \/ 4 \(100%\), Reviewer 2 2 \/ 4 \(50%\), Reference decisions 0 \/ 4 \(0%\)/})).toBeInTheDocument();
  expect(Array.from(container.querySelectorAll('rect')).map(bar => Number(bar.getAttribute('height')))).toEqual([210, 105, 0]);
  expect(new Set(Array.from(container.querySelectorAll('rect')).map(bar => bar.getAttribute('fill'))).size).toBe(3);
  expect(screen.getByText(/Completion of declared items, not accuracy/)).toBeInTheDocument();
});

test('keeps missing tasks and zero-denominator tasks unmeasured, distinct from zero coverage', () => {
  const { container } = render(<PilotCoverageChart metrics={[{ ...metric, declared_items: 0, annotator_a_labelled: 0, annotator_b_labelled: 0, paired_items: 0 }]} />);
  expect(screen.getByRole('img', {name: /Question validity: Reviewer 1 No items declared/})).toBeInTheDocument();
  expect(screen.getByRole('img', {name: /Memory review: Reviewer 1 No items declared/})).toBeInTheDocument();
  expect(container.querySelectorAll('rect')).toHaveLength(0);
  expect(screen.getAllByText('Not measured')).toHaveLength(5);
});
