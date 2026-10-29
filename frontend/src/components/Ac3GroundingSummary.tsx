import { useEffect, useState } from 'react';
import { Card, Tag } from 'antd';
import { AC3_PRIMARY_STUDY_SHA, isReviewedAc3Primary } from './Ac3HeldoutResults';
import { api } from '../services/api';

type Summary = {
  format: 'ac3-grounding-summary-v1'; snapshot_confirmed_at_utc: string;
  questions: number; agreed_valid: number; agreed_invalid: number; disagreed: number; missing_or_uncertain: number;
  protocol_frozen: false; held_out_results_available: false; thresholds_accepted: true; threshold_status: 'selected_not_frozen'; review_process: string;
  revision: { histories_changed: number; affected_question_contexts: number; review_complete: true; source_sha256: string;
    questions: number; agreed_valid: number; review_note: string };
  expansion: { reviewed_histories: number; new_histories: number; proposed_histories: number;
    reviewed_questions: number; new_questions: number; proposed_questions: number; new_review_complete: true;
    v5_unchanged_new_histories: number; v6_revised_histories: number; pending_histories: number; pending_questions: number;
    v5_reviewed_additional_histories: number; v5_review_note: string; v6_review_note: string;
    v7_pending_questions: number; semantic_qualification: string; pending_fact_relationship_count: number; v8_review_note: string;
    unresolved_edge_status: 'unresolved_not_written_as_confirmed' };
};
type FrozenStatus = { format: 'ac3-frozen-protocol-status-v1'; primary_histories: number; primary_questions: number;
  repeat_histories: number; repeat_questions: number; primary_sha256: string; repeat_sha256: string };

function isFrozenStatus(value: unknown): value is FrozenStatus {
  if (!value || typeof value !== 'object') return false;
  const x = value as FrozenStatus;
  return x.format === 'ac3-frozen-protocol-status-v1' && x.primary_histories === 30 && x.primary_questions === 120
    && x.repeat_histories === 10 && x.repeat_questions === 40 && /^[a-f0-9]{64}$/.test(x.primary_sha256)
    && /^[a-f0-9]{64}$/.test(x.repeat_sha256);
}

function isSummary(value: unknown): value is Summary {
  if (!value || typeof value !== 'object') return false;
  const x = value as Record<string, unknown>;
  const names = ['questions', 'agreed_valid', 'agreed_invalid', 'disagreed', 'missing_or_uncertain'] as const;
  if (x.format !== 'ac3-grounding-summary-v1' || x.protocol_frozen !== false || x.held_out_results_available !== false || x.thresholds_accepted !== true || x.threshold_status !== 'selected_not_frozen'
    || typeof x.snapshot_confirmed_at_utc !== 'string' || typeof x.review_process !== 'string'
    || !names.every(name => typeof x[name] === 'number' && Number.isInteger(x[name]) && (x[name] as number) >= 0)) return false;
  if (!x.revision || typeof x.revision !== 'object') return false;
  const revision = x.revision as Record<string, unknown>;
  if (revision.review_complete !== true || !Number.isInteger(revision.histories_changed)
    || !Number.isInteger(revision.affected_question_contexts) || (revision.histories_changed as number) < 1
    || (revision.affected_question_contexts as number) < 1 || typeof revision.source_sha256 !== 'string'
    || !Number.isInteger(revision.questions) || revision.questions !== x.questions || revision.agreed_valid !== revision.questions
    || typeof revision.review_note !== 'string') return false;
  if (!x.expansion || typeof x.expansion !== 'object') return false;
  const e = x.expansion as Record<string, unknown>;
  if (!['reviewed_histories', 'new_histories', 'proposed_histories', 'reviewed_questions', 'new_questions', 'proposed_questions', 'v5_unchanged_new_histories', 'v6_revised_histories', 'pending_histories', 'pending_questions', 'v5_reviewed_additional_histories', 'v7_pending_questions']
    .every(k => Number.isInteger(e[k]) && (e[k] as number) >= 0) || e.new_review_complete !== true
    || (e.reviewed_histories as number) + (e.pending_histories as number) !== e.proposed_histories
    || (e.reviewed_questions as number) + (e.pending_questions as number) !== e.proposed_questions
    || (e.v5_unchanged_new_histories as number) + (e.v6_revised_histories as number) !== e.new_histories
    || e.pending_questions !== e.v7_pending_questions || typeof e.v5_review_note !== 'string'
    || typeof e.v6_review_note !== 'string' || typeof e.semantic_qualification !== 'string'
    || e.pending_fact_relationship_count !== 0 || e.unresolved_edge_status !== 'unresolved_not_written_as_confirmed'
    || typeof e.v8_review_note !== 'string') return false;
  return (x.questions as number) > 0 && (x.agreed_valid as number) + (x.agreed_invalid as number)
    + (x.disagreed as number) + (x.missing_or_uncertain as number) === x.questions;
}

export function Ac3GroundingSummary() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [hasArchivedResults, setHasArchivedResults] = useState(false);
  const [hasDynamicResults, setHasDynamicResults] = useState(false);
  const [frozen, setFrozen] = useState<FrozenStatus | null>(null);
  useEffect(() => {
    let active = true;
    fetch('/reports/ac3-grounding-summary-v1.json', { cache: 'no-store' })
      .then(response => response.ok ? response.json() : null)
      .then(value => { if (active && isSummary(value)) setSummary(value); })
      .catch(() => { if (active) setSummary(null); });
    fetch('/reports/ac3-heldout-public-summary-v1.json', { cache: 'no-store' })
      .then(response => response.ok ? response.json() : null)
      .then(value => { if (active) setHasArchivedResults(isReviewedAc3Primary({study_id:AC3_PRIMARY_STUDY_SHA, study_role:'primary_validation', summary:value}, AC3_PRIMARY_STUDY_SHA)); })
      .catch(() => { if (active) setHasArchivedResults(false); });
    api.ac3StudySummaries()
      .then(value => { if (active) setHasDynamicResults(value.studies.some(item => isReviewedAc3Primary(item, AC3_PRIMARY_STUDY_SHA))); })
      .catch(() => undefined);
    fetch('/reports/ac3-frozen-protocol-status-v1.json', { cache: 'no-store' })
      .then(response => response.ok ? response.json() : null)
      .then(value => { if (active && isFrozenStatus(value)) setFrozen(value); })
      .catch(() => { if (active) setFrozen(null); });
    return () => { active = false; };
  }, []);
  if (!summary) return null;
  const hasHeldoutResults = hasArchivedResults || hasDynamicResults;
  const segments = [
    { name: 'Both valid', count: summary.expansion.reviewed_questions, color: '#23836f' },
    { name: 'Questions awaiting review', count: summary.expansion.pending_questions, color: '#b7c4c9' },
  ];
  return <Card title="AC3 · Question source review" style={{ marginTop: 16 }}>
    <p><strong>{summary.expansion.reviewed_questions}/{summary.expansion.proposed_questions}</strong> proposed questions reviewed · {summary.expansion.reviewed_histories} synthetic histories</p>
    <div role="img" aria-label={`Question source review: ${segments.map(item => `${item.name} ${item.count}`).join(', ')}`} style={{ display: 'flex', height: 20, width: '100%', borderRadius: 10, overflow: 'hidden', background: '#eee' }}>
      {segments.filter(item => item.count > 0).map(item => <span key={item.name} style={{ width: `${item.count / summary.expansion.proposed_questions * 100}%`, background: item.color }} />)}
    </div>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', marginTop: 8 }}>
      {segments.map(item => <span key={item.name}><span aria-hidden="true" style={{ color: item.color }}>●</span> {item.name}: {item.count}</span>)}
    </div>
    <p style={{ marginTop: 12 }}><Tag color="green">H19 fact and edge handling reviewed</Tag><Tag color="orange">Original edge unresolved</Tag><Tag color="green">Thresholds selected</Tag>{frozen ? <Tag color="green">Main and repeat protocols frozen</Tag> : <Tag color="orange">Protocol not frozen</Tag>}{hasHeldoutResults ? <Tag color="green">Reviewed results available below</Tag> : <Tag>Results not yet available</Tag>}</p>
    {frozen && <p>Main: {frozen.primary_histories} histories / {frozen.primary_questions} questions · Repeat: {frozen.repeat_histories} histories / {frozen.repeat_questions} questions</p>}
    <small>Question source review is not an Auditor accuracy result.</small>
    <details><summary>Review and source details</summary><p>{summary.expansion.semantic_qualification}</p><p>{summary.expansion.v8_review_note}</p><p>{summary.revision.review_note}</p><p>{summary.expansion.v5_review_note}</p><p>{summary.expansion.v6_review_note}</p><p>Original-version review: {summary.agreed_valid}/{summary.questions} valid. {summary.review_process}</p>{frozen && <p>Frozen protocol fingerprints: {frozen.primary_sha256.slice(0,12)}… / {frozen.repeat_sha256.slice(0,12)}…</p>}</details>
  </Card>;
}
