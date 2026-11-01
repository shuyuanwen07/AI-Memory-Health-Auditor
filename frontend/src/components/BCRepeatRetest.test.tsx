import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { BCRepeatRetest, isBCRetestReport, type BCRetestReport } from './BCRepeatRetest';

function pending(): BCRetestReport {
  return { format: 'bc-astra-repeat-retest-v2', updated_at: '2026-11-01T12:30:00Z', provider: 'openai',
    model: 'gpt-6-astra', reasoning_effort: 'max', questions_per_strategy: 16, repetitions: 3,
    planned_per_strategy: 48, review_status: 'pending', studies: (['B', 'C'] as const).map(id => ({
      id, label: id === 'B' ? 'Synthetic histories' : 'LongMemEval Oracle', source_units: id === 'B' ? 4 : 16,
      conditions: ['weak_first_hit', 'strong_rule_based', 'scope_aware', 'temporal_importance'].map(strategy => ({
        strategy, planned: 48, saved: 0, errors: 0, remaining: 48, reviewed: 0, pass: null, fail: null,
        unresolved: null, repeats: [1, 2, 3].map(repeat => ({ repeat, saved: 0, pass: null })),
      })),
    })) };
}

describe('repeated B/C study display', () => {
  it('shows collection progress instead of zero scores before review', () => {
    const report = pending();
    expect(isBCRetestReport(report)).toBe(true);
    render(<BCRepeatRetest report={report}/>);
    expect(screen.getByRole('status')).toHaveTextContent('review pending');
    expect(screen.getAllByText('0/48 answered · review pending')).toHaveLength(8);
    expect(screen.queryByText(/0\/48 passed/)).not.toBeInTheDocument();
  });

  it('rejects mismatched denominators or fabricated reviewed counts', () => {
    const report = pending();
    report.studies[0].conditions[0].planned = 12;
    expect(isBCRetestReport(report)).toBe(false);
    report.studies[0].conditions[0].planned = 48;
    report.studies[0].conditions[0].reviewed = 1;
    report.studies[0].conditions[0].pass = 1;
    expect(isBCRetestReport(report)).toBe(false);
  });

  it('distinguishes a reviewed zero from a pending score', () => {
    const report = pending();
    report.review_status = 'ai_reviewed';
    const c = report.studies[0].conditions[0];
    Object.assign(c, { saved: 16, errors: 32, remaining: 0, reviewed: 16, pass: 0, fail: 15, unresolved: 1 });
    c.repeats[0] = { repeat: 1, saved: 16, pass: 0 };
    expect(isBCRetestReport(report)).toBe(true);
    render(<BCRepeatRetest report={report}/>);
    expect(screen.getByRole('status')).toHaveTextContent('human confirmation pending');
    expect(screen.getByText('0/48 passed · 1 unresolved')).toBeInTheDocument();
  });
});
