import { memoryStrategyLabel, modelDisplayName } from '../services/display';
import { saveBlob } from '../services/download';
import { UIButton, UIPanel, UISummary } from './ui';
import { Input } from 'antd';
import { useId, useRef, useState } from 'react';
import type { AuditComparison, Dimension } from '../types/domain';

const abilities: { key: Dimension; label: string; short: string }[] = [
  { key: 'accuracy', label: 'Accuracy', short: 'Accuracy' },
  { key: 'freshness', label: 'Freshness', short: 'Freshness' },
  { key: 'conflict_resolution', label: 'Conflict resolution', short: 'Conflict resolution' },
  { key: 'appropriate_use', label: 'Appropriate use', short: 'Appropriate use' },
];
const beforeColour = '#627eab';
const afterColour = '#138572';
const percentage = (value: number | null) => value === null ? 'Not scored' : `${Number(value.toFixed(1))}%`;
const difference = (value: number | null) => value === null ? 'No comparison' : `${value > 0 ? '+' : ''}${Number(value.toFixed(1))} pp`;

export function isSavedAnswerComparison(data: AuditComparison | null) {
  return Boolean(data && [data.before.run, data.after.run].some(run =>
    run.reproducibility?.assessment_source_run_id || run.reproducibility?.shared_answer_source_run_id));
}

export function savedAnswerProvenanceNote(data: AuditComparison) {
  if (data.answer_provenance === 'different_saved_executions') return 'These answers come from different original target executions. Reassessment made no new target calls. Interpret differences using the original settings and matching assessment standards.';
  if (data.answer_provenance === 'same_saved_answers') return 'Both sides reuse the exact same original answers. Score changes describe assessment decisions, not target-model or memory improvement.';
  return 'Answer provenance is incomplete or mixed. These scores cannot establish whether differences come from assessment decisions or different original target answers.';
}

export function comparisonChartRows(data: AuditComparison, shared: boolean) {
  return abilities.map(ability => {
    const pairs = data.paired_tests.filter(test => test.dimension === ability.key);
    const left = data.before.result.dimensions.find(item => item.dimension === ability.key);
    const right = data.after.result.dimensions.find(item => item.dimension === ability.key);
    const beforeTotal = shared ? pairs.length : left?.total ?? 0;
    const afterTotal = shared ? pairs.length : right?.total ?? 0;
    const beforePassed = shared ? pairs.filter(test => test.before.passed).length : left?.passed ?? 0;
    const afterPassed = shared ? pairs.filter(test => test.after.passed).length : right?.passed ?? 0;
    const before = beforeTotal ? beforePassed / beforeTotal * 100 : null;
    const after = afterTotal ? afterPassed / afterTotal * 100 : null;
    return { ...ability, before, after, beforeTotal, afterTotal, beforePassed, afterPassed,
      delta: before === null || after === null || !shared ? null : after - before };
  });
}

/** Fixed percentage axis; missing observations are never plotted as zero. */
export function ComparisonVisualizations({ data }: { data: AuditComparison }) {
  const reassessment = isSavedAnswerComparison(data);
  const [shared, setShared] = useState(true);
  const [chartSource,setChartSource] = useState('');
  const [downloadNotice,setDownloadNotice] = useState('');
  const svg = useRef<SVGSVGElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const rows = comparisonChartRows(data, shared);
  const available = rows.some(row => row.before !== null || row.after !== null);
  const exportLimits = [
    ...(!shared ? ['Full suites may differ; these scores are descriptive only.'] : []),
    ...((data.excluded_assessments?.length ?? 0) > 0 ? ['Assessment standards differ; excluded questions cannot establish improvement.'] : []),
    ...((data.setting_differences?.length ?? 0) > 0 ? ['Configurations differ; this does not isolate one memory mechanism.'] : []),
  ];
  const chartHeight = 420 + exportLimits.length * 18;
  const exportRun = (side: 'before' | 'after') => {
    const run = data[side].run;
    const profile = run.target_memory_profile;
    // Keep verifiable settings, not source dialogue, answers or arbitrary metadata.
    return {run_id: run.run_id, model: run.model, provider: run.provider,
      memory_strategy: run.memory_strategy, target_configuration: run.target_configuration,
      temperature: run.temperature, random_seed: run.random_seed,
      evaluator_provider: run.evaluator_provider, evaluator_model: run.evaluator_model,
      memory_maintenance_policy: run.memory_maintenance_policy,
      configuration_fingerprint: run.reproducibility?.configuration_fingerprint ?? null,
      saved_source_sha256: run.reproducibility?.audit_runtime_signature?.source_sha256 ?? null,
      target_memory_capacity: run.target_memory_capacity, target_memory_writer: run.target_memory_writer,
      memory_profile: profile ? {version: profile.version, max_retrieved_records: profile.max_retrieved_records,
        context_character_budget: profile.context_character_budget, isolate_project_scope: profile.isolate_project_scope,
        prefer_current_state: profile.prefer_current_state, output_token_limit: profile.output_token_limit,
        custom_instructions_present: Boolean(profile.additional_instructions?.trim())} : null,
      assessment_source_run_id: run.reproducibility?.assessment_source_run_id ?? null,
      shared_answer_source_run_id: run.reproducibility?.shared_answer_source_run_id ?? null};
  };
  const chartMetadata = {
    format: 'audit-comparison-chart-v1', scope: shared ? 'comparable_shared_questions' : 'full_test_suites',
    answer_provenance: data.answer_provenance ?? (reassessment ? 'unknown_saved_answers' : 'target_executions'),
    assessment_status: 'automated; independent reliability is not established by this chart',
    before: exportRun('before'), after: exportRun('after'),
    coverage: {unchanged_shared_questions: data.shared_question_count ?? null,
      comparable_decided_questions: data.paired_tests.length,
      before_uncertain_answers: data.before.result.uncertain_count ?? null,
      after_uncertain_answers: data.after.result.uncertain_count ?? null},
    dimensions: rows, paired_outcomes: data.counts,
    saved_assessor_versions: [...new Set(data.paired_tests.flatMap(pair => [pair.before.evaluator, pair.after.evaluator]).filter(Boolean))],
    setting_differences: (data.setting_differences ?? []).map(difference =>
      ['target_memory_profile', 'intervention'].includes(difference.field)
        ? {field: difference.field, label: difference.label, changed: true, detail: 'Inspect the saved audit for full configuration.'}
        : difference), comparison_warnings: data.warnings ?? [],
  };
  const exportChart = () => {
    if (!svg.current) return;
    const exportRoot = svg.current.cloneNode(true) as SVGSVGElement;
    exportRoot.removeAttribute('xmlns'); // The XML serializer emits the root namespace.
    const content = new XMLSerializer().serializeToString(exportRoot);
    setChartSource(content);
    try {
      saveBlob(new Blob([content], { type: 'image/svg+xml;charset=utf-8' }), reassessment ? 'saved-answer-assessments.svg' : 'memory-before-after.svg');
      setDownloadNotice('Chart prepared. Your browser was asked to save it. If no file appears, copy the SVG source below.');
    } catch { setDownloadNotice('This browser could not start the download. Copy the SVG source below and save it as an .svg file.'); }
  };
  return <section className="comparison-visuals" aria-label={reassessment ? "Saved-answer assessment charts" : "Memory improvement charts"}>
    <div className="comparison-chart-heading"><div><p className="eyebrow">MEMORY ABILITIES</p><h2>{reassessment ? 'Saved-answer assessments, side by side' : 'Before and after, side by side'}</h2>
      <p>Compare each ability on the same 0–100% scale.</p></div>
      <div className="comparison-chart-controls" aria-label="Chart question scope">
        <UIButton type="button" className={`secondary ${shared ? 'selected' : ''}`} aria-pressed={shared} onClick={() => setShared(true)}>Shared questions</UIButton>
        <UIButton type="button" className={`secondary ${!shared ? 'selected' : ''}`} aria-pressed={!shared} onClick={() => setShared(false)}>Full test suites</UIButton>
      </div></div>
    {reassessment && <p role="note">{savedAnswerProvenanceNote(data)}</p>}
    {!shared && <p className="trace-note">Full suites can contain different questions or assessment standards. These historical scores are descriptive only. Use comparable shared questions to assess changes.</p>}
    {available ? <figure className="comparison-chart-figure">
      <div className="comparison-chart-scroll"><svg ref={svg} xmlns="http://www.w3.org/2000/svg" viewBox={`0 0 880 ${chartHeight}`} fontFamily="Arial, sans-serif" role="img" aria-labelledby={`${titleId} ${descriptionId}`}>
        <title id={titleId}>{reassessment ? 'Saved-answer assessment pass rates' : 'Memory ability pass rates before and after improvement'}</title>
        <desc id={descriptionId}>{rows.map(row => `${row.label}: before ${percentage(row.before)} (${row.beforePassed}/${row.beforeTotal}), after ${percentage(row.after)} (${row.afterPassed}/${row.afterTotal}), change ${difference(row.delta)}.`).join(' ')}</desc>
        <metadata>{JSON.stringify(chartMetadata)}</metadata>
        <rect width="880" height={chartHeight} fill="#ffffff" />
        <text x="58" y="26" fill="#20354d" fontSize="16" fontWeight="700">{reassessment ? 'Saved-answer assessments' : 'Memory ability comparison'} · {shared ? 'shared questions' : 'full suites'}</text>
        <text x="58" y="48" fill="#63758a" fontSize="12">Before: {modelDisplayName(data.before.run.model)} · {memoryStrategyLabel(data.before.run.memory_strategy)}</text>
        <text x="58" y="68" fill="#63758a" fontSize="12">After: {modelDisplayName(data.after.run.model)} · {memoryStrategyLabel(data.after.run.memory_strategy)}</text>
        <rect x="616" y="18" width="12" height="12" rx="3" fill={beforeColour} /><text x="635" y="28" fill="#44556a" fontSize="12">Before</text>
        <rect x="723" y="18" width="12" height="12" rx="3" fill={afterColour} /><text x="742" y="28" fill="#44556a" fontSize="12">After</text>
        {[0, 25, 50, 75, 100].map(tick => {
          const y = 312 - tick * 2.12;
          return <g key={tick}><line x1="58" x2="855" y1={y} y2={y} stroke="#e6ecf2" strokeDasharray={tick === 0 ? undefined : '4 4'} />
            <text x="46" y={y + 4} textAnchor="end" fill="#697b8f" fontSize="11">{tick}%</text></g>;
        })}
        {rows.map((row, index) => {
          const center = 156 + index * 199;
          return <g key={row.key}>
            {(['before', 'after'] as const).map((side, sideIndex) => {
              const value = row[side]; const x = center - 57 + sideIndex * 61;
              const passed = side === 'before' ? row.beforePassed : row.afterPassed;
              const total = side === 'before' ? row.beforeTotal : row.afterTotal;
              const colour = side === 'before' ? beforeColour : afterColour;
              const height = value === null ? 0 : value * 2.12;
              return <g key={side}><title>{row.label} · {side}: {percentage(value)} · {passed}/{total} passed</title>
                {value !== null && <rect x={x} y={312 - height - (value === 0 ? 2 : 0)} width="52" height={value === 0 ? 2 : height} rx={value === 0 ? 0 : 5} fill={colour} />}
                <text x={x + 26} y={value === null ? 296 : 302 - height} textAnchor="middle" fill={colour} fontSize={value === null ? 10 : 14} fontWeight="700">{percentage(value)}</text>
                <text x={x + 26} y="334" textAnchor="middle" fill="#697b8f" fontSize="11">{total ? `${passed}/${total}` : '—'}</text>
              </g>;
            })}
            <text x={center} y="359" textAnchor="middle" fill="#34475d" fontSize="13" fontWeight="600">{row.short}</text>
            <text x={center} y="385" textAnchor="middle" fill={row.delta === null || row.delta === 0 ? '#697b8f' : row.delta > 0 ? '#0c7864' : '#b34444'} fontSize="14" fontWeight="700">{difference(row.delta)}</text>
          </g>;
        })}
        <text x="58" y="411" fill="#697b8f" fontSize="11">{reassessment ? (data.answer_provenance === 'different_saved_executions' ? 'Different original executions · reassessed saved answers · passed/tested · pp = percentage points' : data.answer_provenance === 'same_saved_answers' ? 'Reused answers · assessment changes, not model improvement · passed/tested · pp = percentage points' : 'Saved answers · source relation unverified · passed/tested · pp = percentage points') : 'Pass rate · counts shown as passed/tested · pp = percentage points · automated assessments'}</text>
        {exportLimits.map((limit, index) => <text key={limit} x="58" y={429 + index * 18} fill="#83572d" fontSize="11">{limit}</text>)}
      </svg></div>
      <figcaption><span>{shared ? `${data.paired_tests.length} comparable decided questions` : 'All questions in each audit'} · Counts below the bars show passed / tested. An untested ability has no bar.</span>
        <UIButton type="button" className="secondary" onClick={exportChart}>Save chart (SVG)</UIButton></figcaption>
    </figure> : <p className="empty">No shared questions with comparable decided assessments can be charted. Choose full test suites to view each audit separately.</p>}
    {chartSource && <section aria-label="Chart download alternative"><p role="status">{downloadNotice}</p><UIPanel><UISummary>Last prepared chart source (SVG)</UISummary><Input.TextArea aria-label="Prepared chart SVG" value={chartSource} readOnly autoSize={{minRows:3,maxRows:6}}/></UIPanel></section>}
    {data.paired_tests.length > 0 && <div className="comparison-change-strip" aria-label="Shared question outcomes">
      <div className="comparison-change-track" aria-hidden="true">{([
        ['fixed', '#138572'], ['regressed', '#be5252'], ['still_failed', '#c68b31'], ['still_passed', '#91a6bb'],
      ] as const).map(([key, colour]) => data.counts[key] > 0 && <span key={key} style={{ flex: data.counts[key], backgroundColor: colour }} />)}</div>
      <p><b>{data.counts.fixed}</b> {reassessment ? 'fail → pass' : 'fixed'} <span>·</span> <b>{data.counts.regressed}</b> {reassessment ? 'pass → fail' : 'regressed'} <span>·</span> <b>{data.counts.still_failed + data.counts.still_passed}</b> unchanged <small>on comparable decided questions</small></p>
    </div>}
  </section>;
}
