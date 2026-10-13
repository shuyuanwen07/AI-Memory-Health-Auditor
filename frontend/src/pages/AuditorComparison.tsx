import { memoryStrategyLabel, modelDisplayName } from '../services/display';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../services/api';
import { UIButton, UIAlert, UIPanel, UISummary } from '../components/ui';
import { ReviewedMethodComparison } from '../components/ReviewedMethodComparison';
import { ResultDashboard } from '../components/ResultDashboard';
import type { ExperimentStatisticsRun } from '../components/ExperimentStatistics';
import type { Experiment, ExperimentAnalytics } from '../types/domain';

const methodLabels: Record<string, string> = {
  rules: 'Rule tests + rule review', model_generation: 'Model tests + rule review', hybrid: 'Model tests + hybrid review',
};


export function AuditorComparisonPage() {
  const [params] = useSearchParams();
  const selection = params.get('groups') ?? '';
  const [reports, setReports] = useState<ExperimentAnalytics[]>([]);
  const [saved, setSaved] = useState<Experiment[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const requestVersion = useRef(0);
  const load = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoading(true); setError(''); setReports([]);
    try {
      if (!selection) { const groups = await api.experimentGroups(); if (version === requestVersion.current) setSaved(groups); return; }
      const ids = [...new Set(selection.split(',').filter(Boolean))];
      if (ids.length !== 2) throw new Error('A complete three-method comparison contains two saved test groups.');
      const values = await Promise.all(ids.map(id => api.experimentResults(id)));
      if (version !== requestVersion.current) return;
      const identity = values[0].experiment.test_suite_configuration.auditor_comparison_id;
      if (!identity || values.some(value => !!value.experiment.test_suite_metadata?.study_role
          || value.experiment.test_suite_configuration.auditor_comparison_id !== identity
          || value.experiment.conversation_id !== values[0].experiment.conversation_id)
          || values.filter(value => value.experiment.test_suite_configuration.pipeline_provider === 'rule_based').length !== 1) {
        throw new Error('These test groups do not belong to the same saved audit-method comparison.');
      }
      setReports(values);
    } catch (cause) { if (version === requestVersion.current) setError(cause instanceof Error ? cause.message : 'The comparison could not be loaded.'); }
    finally { if (version === requestVersion.current) setLoading(false); }
  }, [selection]);
  useEffect(() => { void load(); return () => { requestVersion.current++; }; }, [load]);
  const batches = new Map<string, Experiment[]>();
  saved.forEach(experiment => {
    const id = experiment.test_suite_configuration.auditor_comparison_id;
    if (id && !experiment.test_suite_metadata?.study_role) batches.set(id, [...(batches.get(id) ?? []), experiment]);
  });
  const planned = reports.reduce((sum, report) => sum + report.runs.length, 0);
  const completed: ExperimentStatisticsRun[] = reports.flatMap(report => report.runs.flatMap(({ run, result }) => {
    if (!result) return [];
    const method = methodLabels[run.reproducibility?.auditor_method ?? ''] ?? 'Custom audit';
    const groupLabel = `${modelDisplayName(run.model)} · ${memoryStrategyLabel(run.memory_strategy)} · ${method}`;
    const condition = report.conditions?.find(item => item.run_ids.includes(run.run_id));
    const groupKey = condition?.condition_id ?? `unverified-run:${run.run_id}`;
    return [{ label: groupLabel, groupLabel, groupKey, result }];
  }));
  return <section className="page"><h1>Audit Method Comparison</h1>
    <p>Three methods, one reviewed ground truth and the same target settings. Each tested ability shows one bar per method.</p>
    <UIAlert role="status"><b>What the chart measures</b><p>Bars show automated target-answer pass rates, not auditor accuracy. The rule method has its own questions; the two model methods share a frozen suite and, in new comparisons, the same saved replies. Historical runs without sharing receipts remain exploratory. Review failure precision, recall, false positives and abstentions against independent labels before claiming a better auditor.</p></UIAlert>
    <p>Shared replies incur no second target request and are not independent samples. Target usage excludes test generation and semantic judging; copied-answer latency is not the evaluator runtime. Report provider cost as unknown when billing evidence is absent.</p>
    {loading && <p role="status">Loading saved comparison…</p>}
    {error && <UIAlert role="alert">{error}<UIButton onClick={() => void load()}>Retry loading comparison</UIButton></UIAlert>}
    {!selection && !loading && <><a href="/new-audit">Start a three-method comparison</a>{batches.size ? [...batches.values()].map((group, index) => <UIPanel key={group[0].experiment_id} open><UISummary>Comparison {index + 1} · {new Date(group[0].created_at).toLocaleString()}</UISummary>{group.length === 2 ? <a href={`/audit-methods?groups=${encodeURIComponent(group.map(item => item.experiment_id).join(','))}`}>Open three-method results</a> : <p>Preparation is incomplete. Check the saved groups in Experiments.</p>}</UIPanel>) : <p>No saved three-method comparisons yet.</p>}</>}
    {reports.length > 0 && <><p role="status">{completed.length} of {planned} planned runs completed.</p>
      {completed.length < planned && <UIAlert role="status">Incomplete comparison: unfinished and cancelled runs have no score. <a href="/history">Inspect saved runs</a></UIAlert>}
      {completed.length > 0 ? <><ReviewedMethodComparison runs={completed} />{completed.map((item, index) => <UIPanel key={item.result.run_id}><UISummary>{item.label} · Run {index + 1}</UISummary><ResultDashboard result={item.result} /></UIPanel>)}</> : <p>These groups have no completed scored answers yet.</p>}
    </>}
  </section>;
}
