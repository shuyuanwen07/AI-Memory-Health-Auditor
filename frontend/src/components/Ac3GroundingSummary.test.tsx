import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Ac3GroundingSummary } from './Ac3GroundingSummary';
import { api } from '../services/api';
import { AC3_PRIMARY_STUDY_SHA } from './Ac3HeldoutResults';

vi.mock('../services/api', () => ({ api: { ac3StudySummaries: vi.fn(async () => ({ studies: [] })) } }));

const summary = {
  format: 'ac3-grounding-summary-v1', snapshot_confirmed_at_utc: '2026-10-28T08:51:56Z',
  questions: 32, agreed_valid: 32, agreed_invalid: 0, disagreed: 0, missing_or_uncertain: 0,
  protocol_frozen: false, held_out_results_available: false, thresholds_accepted: true, threshold_status: 'selected_not_frozen', review_process: 'User confirmed independent reviews.',
  revision: { histories_changed: 8, affected_question_contexts: 8, review_complete: true, source_sha256: 'revision',
    questions: 32, agreed_valid: 32, review_note: 'User confirmed independent revised reviews.' },
  expansion: { reviewed_histories: 30, new_histories: 22, proposed_histories: 30,
    reviewed_questions: 120, new_questions: 88, proposed_questions: 120, new_review_complete: true,
    v5_unchanged_new_histories: 12, v6_revised_histories: 10, pending_histories: 0, pending_questions: 0,
    v5_reviewed_additional_histories: 22, v5_review_note: 'User-confirmed v5 review; 12 unchanged histories carried forward.',
    v6_review_note: 'User-confirmed v6 review.', v7_pending_questions: 0,
    semantic_qualification: 'H19 fact reviewed and original edge unresolved.', pending_fact_relationship_count: 0,
    unresolved_edge_status: 'unresolved_not_written_as_confirmed', v8_review_note: 'H19 fact and edge handling reviewed.' }
};
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.mocked(api.ac3StudySummaries).mockReset().mockResolvedValue({studies:[]}); });
it('displays question review separately from pending AC3 results', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => summary }));
  render(<Ac3GroundingSummary />);
  expect(await screen.findByText('120/120', { exact: true })).toBeInTheDocument();
  expect(screen.getByRole('img', { name: /Both valid 120/ })).toBeInTheDocument();
  expect(screen.getByText('Protocol not frozen')).toBeInTheDocument();
  expect(screen.getByText('Thresholds selected')).toBeInTheDocument();
  expect(screen.getByText('Results not yet available')).toBeInTheDocument();
  expect(screen.getByText('H19 fact and edge handling reviewed', { exact: true })).toBeInTheDocument();
  expect(screen.getByText(/Original edge unresolved/)).toBeInTheDocument();
  expect(screen.getByText(/proposed questions reviewed/)).toBeInTheDocument();
  expect(screen.getByText(/not an Auditor accuracy result/)).toBeInTheDocument();
});
it('rejects a revised source with incomplete human review', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...summary, revision: { ...summary.revision, review_complete: false } }) }));
  const { findByText } = render(<Ac3GroundingSummary />);
  await expect(findByText('AC3 · Question source review', {}, { timeout: 100 })).rejects.toThrow();
});
it('rejects malformed counts rather than presenting them', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...summary, agreed_valid: 33 }) }));
  const { findByText } = render(<Ac3GroundingSummary />);
  await expect(findByText('AC3 · Question source review', {}, { timeout: 100 })).rejects.toThrow();
});
it('shows the separately verified frozen primary and repeat protocols', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string) => ({ok:true,json:async () => url.includes('ac3-frozen-protocol')
    ? {format:'ac3-frozen-protocol-status-v1',primary_histories:30,primary_questions:120,repeat_histories:10,repeat_questions:40,
       primary_sha256:'a'.repeat(64),repeat_sha256:'b'.repeat(64)} : summary})));
  render(<Ac3GroundingSummary />);
  expect(await screen.findByText('Main and repeat protocols frozen')).toBeInTheDocument();
  expect(screen.getByText(/Main: 30 histories \/ 120 questions/)).toBeInTheDocument();
  expect(screen.queryByText('Protocol not frozen')).not.toBeInTheDocument();
  expect(screen.getByText('Results not yet available')).toBeInTheDocument();
});
it('retains source review and reports dynamically submitted primary results', async () => {
  const metric={metric:{numerator:1,denominator:1,value:1},threshold:.8,direction:'min',met_descriptively:true};
  const reviewed={format:'ac3-heldout-public-summary-v1',cases:120,histories:30,acceptance:'not_assessed',limitations:'Synthetic.',
    human_reference:{unresolved:0},automatic:{abstain_reference_fail:0,abstain_reference_pass:0},
    threshold_comparison_descriptive:{failure_detection_recall_min:metric,failure_classification_accuracy_min:metric,test_validity_min:metric,false_positive_rate_max:metric},
    source_sha256:{frozen:AC3_PRIMARY_STUDY_SHA,run:'a'.repeat(64),review_1:'b'.repeat(64),review_2:'c'.repeat(64)}};
  vi.mocked(api.ac3StudySummaries).mockResolvedValueOnce({studies:[{study_id:AC3_PRIMARY_STUDY_SHA,study_role:'primary_validation',summary:reviewed}]});
  vi.stubGlobal('fetch',vi.fn().mockImplementation(async (url:string)=>({ok:!url.includes('heldout-public'),json:async()=>summary})));
  render(<Ac3GroundingSummary />);
  expect(await screen.findByText('Reviewed results available below')).toBeInTheDocument();
  expect(screen.getByText('AC3 · Question source review')).toBeInTheDocument();
  expect(screen.queryByText('Results not yet available')).not.toBeInTheDocument();
});
