import { UIAlert, UICard } from '../components/ui';
import { UIButton, UIInput, UISelect, UIOption, UIPanel, UISummary, UITable } from '../components/ui';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../services/api';
import { assessmentLabel, auditDisplayNames, friendlyText, processingLabel } from '../services/display';
import { ComparisonVisualizations, comparisonChartRows } from '../components/ComparisonVisualizations';
import type { AuditComparison as Comparison, AuditRun } from '../types/domain';

const labels = { fixed: 'Fixed', regressed: 'Regressed', still_failed: 'Still failing', still_passed: 'Still passing' };
const pretty = (value:string) => value.replaceAll('_', ' ');
const score = (value:number|null) => value == null ? 'Unmeasured' : `${value.toFixed(1)}%`;
const change = (value:number|null) => value == null ? 'Unmeasured' : `${value > 0 ? '+' : ''}${value.toFixed(1)} pp`;

export function AuditComparisonPage() {
  const [params, setParams] = useSearchParams();
  const [runs, setRuns] = useState<AuditRun[]>([]);
  const before = params.get('before') ?? '';
  const after = params.get('after') ?? '';
  const [data, setData] = useState<Comparison|null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const [auditSearch, setAuditSearch] = useState('');
  const presentation = params.get('view') === 'presentation';
  const setPresentation = (enabled:boolean) => {
    const next = new URLSearchParams(params);
    if (enabled) next.set('view', 'presentation'); else next.delete('view');
    setParams(next);
  };
  useEffect(() => {
    let active = true;
    api.audits().then(items => { if (active) setRuns(items); })
      .catch(() => { if (active) setError('Audit history could not be loaded.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    setData(null); setError(''); setFilter('all');
    if (!before || !after || before === after) { setBusy(false); return; }
    let active = true;
    setBusy(true);
    api.compareAudits(before, after).then(result => { if (active) setData(result); })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'Comparison unavailable.'); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [before, after]);
  const choose = (side:'before'|'after', value:string) => {
    const nextBefore = side === 'before' ? value : before;
    const nextAfter = side === 'after' ? value : after;
    const next = new URLSearchParams(params);
    if (nextBefore) next.set('before', nextBefore); else next.delete('before');
    if (nextAfter) next.set('after', nextAfter); else next.delete('after');
    setParams(next);
  };
  const displayNames = auditDisplayNames(runs);
  const visibleQuestions = data?.paired_tests.filter(item => filter === 'all' || item.outcome === filter) ?? [];
  const completedRuns = runs.filter(run => run.status === 'COMPLETED');
  const option = (run:AuditRun) => `${displayNames[run.run_id]} · ${run.model} · ${pretty(run.memory_strategy)} · ${new Date(run.created_at).toLocaleString()}`;
  const matchingRuns = completedRuns.filter(run => !auditSearch.trim() || option(run).toLowerCase().includes(auditSearch.trim().toLowerCase()));
  const selectorRuns = completedRuns.filter(run => run.run_id === before || run.run_id === after || matchingRuns.includes(run));
  return <section className="audit-comparison"><p className="eyebrow">BEFORE & AFTER</p><div className="comparison-title-row"><h1>Memory improvement results</h1><UIButton type="button" className="secondary" aria-pressed={presentation} onClick={() => setPresentation(!presentation)}>{presentation ? 'Exit presentation view' : 'Presentation view'}</UIButton></div>
    <div hidden={presentation}>
    <p className="comparison-intro">Compare saved tests before and after a change. Check the repaired failures and any regressions alongside the score.</p>
    <div className="comparison-picker-tools"><label>Find saved audits<UIInput aria-label="Find saved audits" placeholder="Search audit name, model or memory approach" value={auditSearch} onChange={event => setAuditSearch(event.target.value)} /></label>{auditSearch && <UIButton type="button" className="secondary" onClick={() => setAuditSearch('')}>Clear search</UIButton>}<UIButton type="button" className="secondary" disabled={!before || !after || before === after} onClick={() => { const next = new URLSearchParams(params); next.set('before', after); next.set('after', before); setParams(next); }}>Swap before &amp; after</UIButton></div><p className="trace-note" role="status">{matchingRuns.length} matching audits. Your selected audits stay available.</p>
    <div className="comparison-selectors">{(['before','after'] as const).map(side => <label key={side}>{side === 'before' ? 'Before improvement' : 'After improvement'}<UISelect aria-label={[(side === 'before' ? 'Before improvement' : 'After improvement')].join(' ')} value={side === 'before' ? before : after} onChange={event => choose(side,event.target.value)}><UIOption value="">Choose a completed audit</UIOption>{(side === "before" ? before : after) && !selectorRuns.some(run => run.run_id === (side === "before" ? before : after)) && <UIOption value={side === "before" ? before : after}>Selected audit · loading or unavailable</UIOption>}{selectorRuns.map(run => <UIOption key={run.run_id} value={run.run_id}>{option(run)}</UIOption>)}</UISelect></label>)}</div>
    </div>
    {loading && <p role="status">Loading saved audits…</p>}
    {!loading && completedRuns.length < 2 && <p className="empty">Complete at least two audits to compare results.</p>}
    {before && before === after && <UIAlert role="alert" className="alert">Choose two different audits.</UIAlert>}
    {busy && <p role="status">Loading comparison…</p>}
    {error && <UIAlert role="alert" className="alert">{error}</UIAlert>}
    {data && <>
      <section className={`comparison-takeaway ${!data.paired_tests.length || (data.counts.fixed === 0 && data.counts.regressed === 0) ? 'neutral' : data.counts.regressed > data.counts.fixed ? 'has-regressions' : ''}`} aria-label="Comparison takeaway"><p className="eyebrow">ON THE SAME QUESTIONS</p><h2>{!data.paired_tests.length ? 'A direct improvement comparison is not available' : data.counts.fixed > 0 ? `${data.counts.fixed} ${data.counts.fixed === 1 ? 'answer improved' : 'answers improved'}` : data.counts.regressed > 0 ? 'Some answers regressed' : 'No answers changed from fail to pass'}</h2><div className="takeaway-counts">{data.paired_tests.length > 0 ? <><span><b>{data.paired_tests.length}</b> shared questions</span><span><b>{data.counts.regressed}</b> regressions</span><span><b>{data.counts.still_failed}</b> still failing</span></> : <span>No comparable decided questions. Historical scores are descriptive only.</span>}</div><p>{data.before.run.model === data.after.run.model ? `Same model: ${data.before.run.model}` : `Models: ${data.before.run.model} → ${data.after.run.model}`} · Memory approach: {pretty(data.before.run.memory_strategy)} → {pretty(data.after.run.memory_strategy)}</p><small>Results are automatically assessed. A change in memory approach does not mean the model was trained.</small>{((data.before.result.uncertain_count ?? 0) + (data.after.result.uncertain_count ?? 0)) > 0 && <p role="note">Awaiting review: before {data.before.result.uncertain_count ?? 0}, after {data.after.result.uncertain_count ?? 0}. These answers are excluded from scores and paired outcomes; improvement and regression counts cover decided answers only.</p>}</section>
      {presentation && data.warnings.length > 0 && <p className="presentation-note" role="note">{data.warnings.map(friendlyText).join(' ')}</p>}
      {!presentation && data.warnings.length > 0 && <div className="comparison-caution" role="note"><b>Check before interpreting improvement</b><ul>{data.warnings.map(warning => <li key={warning}>{friendlyText(warning)}</li>)}</ul></div>}
      <div className="comparison-scorecards">{(['before','after'] as const).map(side => <UICard key={side}><span>{side === 'before' ? 'Before improvement' : 'After improvement'}</span><strong>{score(data[side].result.overall_score)}</strong><p>{data[side].result.tests_passed} / {data[side].result.tests_total} decided tests passed</p>{(data[side].result.uncertain_count ?? 0) > 0 && <p>{data[side].result.uncertain_count} {data[side].result.uncertain_count === 1 ? 'answer' : 'answers'} awaiting review · excluded from this score</p>}<small>{data[side].run.model} · {pretty(data[side].run.memory_strategy)}</small><a href={`/audits/${data[side].run.run_id}`}>Open full report →</a></UICard>)}<UICard className={`comparison-delta ${data.paired_delta_percentage_points == null || data.paired_delta_percentage_points === 0 ? 'neutral' : data.paired_delta_percentage_points < 0 ? 'negative' : 'positive'}`}><span>Change on shared questions</span><strong>{change(data.paired_delta_percentage_points)}</strong><p>{data.paired_tests.length} identical frozen questions</p><small>Percentage points in paired pass rate. Each score is an automated assessment.</small></UICard></div>
      {!!data.excluded_assessments?.length && <section role="note" aria-label="Assessment comparability"><h2>Assessment standards changed</h2><p>{data.excluded_assessments.length} shared questions are excluded from improvement statistics. Their original answers remain available below. Full-suite scores describe the original assessments and do not establish a performance gain.</p>{data.excluded_assessments.map((item, index) => <UIPanel key={index}><UISummary>{item.prompt}</UISummary><p>{item.reason}</p><p><b>Before · {item.before_passed ? 'Passed' : 'Failed'}:</b> {item.before_response}</p><p><b>After · {item.after_passed ? 'Passed' : 'Failed'}:</b> {item.after_response}</p></UIPanel>)}</section>}
      <ComparisonVisualizations data={data} />
      <div hidden={presentation}><UIPanel className="comparison-exact-values"><UISummary>View exact dimension scores</UISummary><div className="comparison-table-scroll"><UITable><thead><tr><th>Ability</th><th>Before</th><th>After</th><th>Change</th></tr></thead><tbody>{comparisonChartRows(data, true).map(row => <tr key={row.key}><th>{row.label}</th><td>{score(row.before)} <small>({row.beforePassed}/{row.beforeTotal})</small></td><td>{score(row.after)} <small>({row.afterPassed}/{row.afterTotal})</small></td><td>{change(row.delta)}</td></tr> )}</tbody></UITable></div><p className="trace-note">Dimension changes use only identical frozen questions with comparable decided assessments. Full-suite scores are shown separately and do not establish improvement.</p></UIPanel>
      <h2>What changed on the same questions?</h2><div className="comparison-outcomes">{Object.entries(labels).map(([key,label]) => <UIButton className={`secondary ${filter === key ? 'selected' : ''}`} aria-label={`${data.counts[key as keyof typeof labels]} ${label}`} aria-pressed={filter === key} key={key} onClick={() => setFilter(filter === key ? 'all' : key)}><strong>{data.counts[key as keyof typeof labels]}</strong>{label}</UIButton>)}</div>
      {filter !== 'all' && <UIButton className="secondary" onClick={() => setFilter('all')}>Show all shared questions</UIButton>}
      <div className="comparison-questions">{visibleQuestions.map(item => <UIPanel key={item.suite_test_id} className={`comparison-question ${item.outcome}`}><UISummary><span className="pill">{labels[item.outcome]}</span> {item.prompt}<small>{pretty(item.dimension)}</small></UISummary><p><b>Expected behaviour:</b> {item.expected_behavior}</p><div className="comparison-answers">{(['before','after'] as const).map(side => <UICard key={side}><h3>{side === 'before' ? 'Before' : 'After'} · {item[side].passed ? 'Passed' : 'Failed'}</h3><p>{item[side].response_text}</p><small>{friendlyText(item[side].reason)}</small><UIPanel><UISummary>Assessment source</UISummary>{assessmentLabel(item[side].evaluator)}</UIPanel></UICard>)}</div></UIPanel>)}</div>
      {data.paired_tests.length > 0 && visibleQuestions.length === 0 && <p className="empty" role="status">No shared questions are {labels[filter as keyof typeof labels]?.toLowerCase()}. Choose another outcome or show all shared questions.</p>}
      {!data.paired_tests.length && <p className="empty">There are no comparable decided questions. Use identical frozen questions and matching assessment standards to compare performance.</p>}
      <UIPanel className="audit-technical-details"><UISummary>Comparison settings</UISummary><p>{data.unpaired_before} unpaired questions before · {data.unpaired_after} after.</p>{data.setting_differences.length ? <ul>{data.setting_differences.map(item => <li key={item.field}>{item.label}: {item.field.endsWith('_id') || item.field.endsWith('_version') ? 'Changed between these audits' : `${processingLabel(String(item.before ?? 'unknown'))} → ${processingLabel(String(item.after ?? 'unknown'))}`} </li>)}</ul> : <p>The checked model, conversation, evaluator and memory storage settings match.</p>}<p>One comparison does not establish statistical significance. Repeat the experiment and independently review AI assessments before reporting a research conclusion.</p></UIPanel>
      </div>
    </>}
  </section>;
}
