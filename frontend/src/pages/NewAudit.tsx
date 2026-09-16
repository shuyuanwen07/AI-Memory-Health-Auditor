import { lazy, Suspense, useEffect, useState } from 'react';
import { api } from '../services/api';
import type { AuditResult, ConversationInputMessage, Memory, MemoryMaintenancePolicy, MemoryReviewPatch, MemoryStrategy, ProviderOption, TargetMemoryWriterKind, TargetProvider, TestCase, TestSuiteMode } from '../types/domain';
import { StepIndicator } from '../components/StepIndicator';
import { ResultDashboard } from '../components/ResultDashboard';
import { ConversationStep } from '../components/ConversationStep';
import { GroundTruthReview } from '../components/GroundTruthReview';
import { ModelComparison } from '../components/ModelComparison';
import { ExperimentStatistics } from '../components/ExperimentStatistics';
import { TestSuiteReview } from '../components/TestSuiteReview';
import { TargetMemoryTrace } from '../components/TargetMemoryTrace';

const ComparisonVisualizations = lazy(() => import('../components/ResultVisualizations').then((module) => ({ default: module.ComparisonVisualizations })));

const sample = `[User] I used MySQL before, but the backend now uses PostgreSQL.\n[User] I generally prefer Python.\n[User] For the current ELEC5623 assignment, Java is required.\n[User] I am based in Sydney.\n[User] The assignment must use PostgreSQL rather than SQLite.`;
const DRAFT_KEY = 'mha-new-audit-draft-v1';

type ConversationDraft = { text?: string; importedMessages?: ConversationInputMessage[] | null; consent?: boolean };

function loadConversationDraft(): ConversationDraft {
  try {
    const saved = sessionStorage.getItem(DRAFT_KEY);
    return saved ? JSON.parse(saved) as ConversationDraft : {};
  } catch { return {}; }
}

type PreparedRun = { runId: string; label: string; groupLabel: string };
type CompletedRun = { label: string; groupLabel: string; result: AuditResult };
type FailedRun = { runId: string; label: string; detail: string };

const strategies: Array<{ value: MemoryStrategy; label: string; description: string }> = [
  { value: 'weak_first_hit', label: 'Weak First-Hit', description: 'Uses only the first related memory, without resolving updates or conflicts.' },
  { value: 'strong_rule_based', label: 'Strong Rule-Based', description: 'Prioritises contextual requirements, updates, stable facts and superseded records.' },
  { value: 'strong_score_based', label: 'Strong Score-Based', description: 'Ranks memories with transparent relevance, freshness and context weights.' },
  { value: 'scope_aware', label: 'Scope-Aware', description: 'Prioritises project requirements for task prompts and uses profile or preferences only when relevant.' },
  { value: 'temporal_importance', label: 'Temporal & Importance', description: 'Ranks source-message recency and durable task importance using a frozen, explainable relative chronology.' },
];

export function NewAudit() {
  const restoredDraft = loadConversationDraft();
  const [step, setStep] = useState(0);
  const [text, setText] = useState(restoredDraft.text || sample);
  const [importedMessages, setImportedMessages] = useState<ConversationInputMessage[] | null>(restoredDraft.importedMessages || null);
  const [consent, setConsent] = useState(Boolean(restoredDraft.consent));
  const [conversationId, setConversationId] = useState('');
  const [memories, setMemories] = useState<Memory[]>([]);
  const [selectedStrategies, setSelectedStrategies] = useState<MemoryStrategy[]>(['weak_first_hit']);
  const [targetProviders, setTargetProviders] = useState<TargetProvider[]>(['rule_based']);
  const [targetModels, setTargetModels] = useState<Partial<Record<TargetProvider, string>>>({});
  const [pipelineProvider, setPipelineProvider] = useState<TargetProvider>('rule_based');
  const [evaluatorProvider, setEvaluatorProvider] = useState<TargetProvider>('rule_based');
  const [providers, setProviders] = useState<ProviderOption[]>([]);
  const [budget, setBudget] = useState(8);
  const [repetitions, setRepetitions] = useState(1);
  const [suiteMode, setSuiteMode] = useState<TestSuiteMode>('behavioural');
  const [maintenancePolicy, setMaintenancePolicy] = useState<MemoryMaintenancePolicy>('update_aware_consolidation');
  const [targetMemoryCapacity, setTargetMemoryCapacity] = useState(50);
  const [targetMemoryWriter, setTargetMemoryWriter] = useState<TargetMemoryWriterKind>('rule_based');
  const [runs, setRuns] = useState<PreparedRun[]>([]);
  const [results, setResults] = useState<CompletedRun[]>([]);
  const [failedRuns, setFailedRuns] = useState<FailedRun[]>([]);
  const [reviewTests, setReviewTests] = useState<TestCase[] | null>(null);
  const [runningLabel, setRunningLabel] = useState('');
  const [runningRunId, setRunningRunId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { api.targetProviders().then(setProviders).catch(() => setProviders([])); }, []);
  useEffect(() => {
    if (step === 0) sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ text, importedMessages, consent }));
    else sessionStorage.removeItem(DRAFT_KEY);
  }, [consent, importedMessages, step, text]);

  const clearDraft = () => {
    sessionStorage.removeItem(DRAFT_KEY);
    setText(sample); setImportedMessages(null); setConsent(false); setError('');
  };

  const act = async (operation: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try { await operation(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Something went wrong.'); }
    finally { setBusy(false); }
  };

  const submitConversation = () => act(async () => {
    const conversation = await api.createConversation(true, text, importedMessages);
    setConversationId(conversation.conversation_id);
    setMemories(await api.extract(conversation.conversation_id));
    setStep(1);
  });

  const updateMemory = (memory: Memory, patch: MemoryReviewPatch) => act(async () => {
    const next = await api.updateMemory(memory.memory_id, patch);
    setMemories((items) => items.map((item) => item.memory_id === memory.memory_id ? next : item));
  });

  const addMemory = (canonicalValue: string) => act(async () => {
    const memory = await api.addMemory({ conversation_id: conversationId, canonical_value: canonicalValue });
    setMemories((items) => [...items, memory]);
  });

  const confirm = () => act(async () => {
    const confirmedIds = memories
      .filter((memory) => memory.status === 'confirmed' || memory.status === 'edited')
      .map((memory) => memory.memory_id);
    setMemories(await api.confirm(conversationId, confirmedIds));
    setStep(2);
  });

  const selectedTargets = providers.filter((item) => targetProviders.includes(item.provider));
  const selectedPipeline = providers.find((item) => item.provider === pipelineProvider);
  const selectedEvaluator = providers.find((item) => item.provider === evaluatorProvider);
  const toggleTarget = (option: ProviderOption) => {
    if (!option.configured) return;
    setTargetProviders((current) => current.includes(option.provider)
      ? (current.length === 1 ? current : current.filter((provider) => provider !== option.provider))
      : [...current, option.provider]);
  };
  const toggleStrategy = (strategy: MemoryStrategy) => setSelectedStrategies((current) => current.includes(strategy)
    ? (current.length === 1 ? current : current.filter((value) => value !== strategy))
    : [...current, strategy]);

  const start = () => act(async () => {
    const plan = selectedTargets.flatMap((provider) => selectedStrategies.flatMap((strategy) =>
      Array.from({ length: repetitions }, (_, index) => ({ provider, strategy, repetition: index + 1 }))));
    const experiment = await api.createExperiment({
      conversation_id: conversationId,
      label: `Memory strategy comparison ${new Date().toISOString()}`,
      test_suite_configuration: {
        test_budget: budget, random_seed: 42, prompt_template_version: 'rule-based-v1',
        pipeline_provider: pipelineProvider,
        pipeline_model: pipelineProvider === 'rule_based' ? 'rule-based-v2' : selectedPipeline?.default_model,
        suite_mode: suiteMode,
      },
    });
    const created = await Promise.all(plan.map(({ provider, strategy }) => api.createAudit({
      conversation_id: conversationId,
      experiment_id: experiment.experiment_id,
      target_configuration: strategy === 'weak_first_hit' ? 'weak' : 'strong',
      memory_strategy: strategy,
      memory_maintenance_policy: maintenancePolicy,
      target_memory_capacity: targetMemoryCapacity,
      target_memory_writer: targetMemoryWriter,
      provider: provider.provider,
      model: targetModels[provider.provider]?.trim() || provider.default_model,
      pipeline_provider: pipelineProvider,
      pipeline_model: pipelineProvider === 'rule_based' ? undefined : selectedPipeline?.default_model,
      evaluator_provider: evaluatorProvider,
      evaluator_model: evaluatorProvider === 'rule_based' ? undefined : selectedEvaluator?.default_model,
      temperature: 0,
      random_seed: 42,
      test_budget: budget,
      prompt_template_version: 'rule-based-v1',
    })));
    setRuns(created.map((run, index) => {
      const condition = plan[index];
      const strategyLabel = strategies.find((item) => item.value === condition.strategy)?.label ?? condition.strategy;
      const groupLabel = `${condition.provider.label} · ${strategyLabel}`;
      return { runId: run.run_id, groupLabel, label: repetitions > 1 ? `${groupLabel} · Run ${condition.repetition}` : groupLabel };
    }));
    setStep(3);
  });

  const prepareTests = () => act(async () => {
    if (!runs[0]) throw new Error('No audit condition was created.');
    setRunningLabel('Generating the shared test suite');
    await api.generate(runs[0].runId);
    setReviewTests((await api.testReview(runs[0].runId)).tests);
    setRunningLabel('');
  });

  const reviewTest = (test: TestCase, decision: 'accepted' | 'rejected') => act(async () => {
    if (!runs[0]) return;
    const changed = await api.reviewTest(runs[0].runId, test.test_id, decision);
    setReviewTests((items) => items?.map((item) => item.test_id === changed.test_id ? changed : item) ?? null);
  });
  const regenerateTest = (test: TestCase) => act(async () => {
    if (!runs[0]) return;
    const changed = await api.regenerateTest(runs[0].runId, test.test_id);
    setReviewTests((items) => items?.map((item) => item.test_id === changed.test_id ? changed : item) ?? null);
  });
  const readyForExecution = Boolean(reviewTests?.length) && reviewTests!.every((test) => test.quality_status === 'accepted');

  const runAudit = () => act(async () => {
    if (!readyForExecution) throw new Error('Generate and complete the shared test-suite review before running the audit.');
    const completed: CompletedRun[] = [];
    const failed: FailedRun[] = [];
    for (const run of runs) {
      setRunningLabel(run.label);
      setRunningRunId(run.runId);
      try {
        await api.execute(run.runId);
        await api.evaluate(run.runId);
        completed.push({ label: run.label, groupLabel: run.groupLabel, result: await api.results(run.runId) });
      } catch (cause) {
        failed.push({ runId: run.runId, label: run.label, detail: cause instanceof Error ? cause.message : 'This condition could not be completed.' });
      }
    }
    setRunningLabel(''); setRunningRunId('');
    setResults(completed);
    setFailedRuns(failed);
    if (!completed.length) throw new Error('No experimental conditions completed. Check the failed runs and retry them.');
    setStep(4);
  });

  const retryFailedRuns = () => act(async () => {
    const recovered: CompletedRun[] = [];
    const stillFailed: FailedRun[] = [];
    for (const failed of failedRuns) {
      setRunningLabel(failed.label); setRunningRunId(failed.runId);
      try {
        const audit = await api.retry(failed.runId);
        if (audit.status !== 'COMPLETED') throw new Error('The run is still incomplete. Check the provider configuration and try again.');
        const groupLabel = runs.find((run) => run.runId === failed.runId)?.groupLabel ?? failed.label;
        recovered.push({ label: failed.label, groupLabel, result: await api.results(failed.runId) });
      } catch (cause) {
        stillFailed.push({ ...failed, detail: cause instanceof Error ? cause.message : failed.detail });
      }
    }
    setRunningLabel(''); setRunningRunId('');
    setResults((current) => [...current, ...recovered]);
    setFailedRuns(stillFailed);
  });

  const cancelCurrentRun = () => act(async () => {
    if (!runningRunId) return;
    await api.cancel(runningRunId);
    setError('Cancellation requested. Completed responses were retained for recovery.');
  });

  return <main className="workflow">
    <StepIndicator current={step} />
    {error && <div role="alert" aria-live="assertive" className="alert">{error}</div>}
    {step === 0 && <ConversationStep text={text} consent={consent} busy={busy} onTextChange={(next) => { setText(next); setImportedMessages(null); }} onConsentChange={setConsent} onImport={(messages, previewText) => { setImportedMessages(messages); setText(previewText); }} onImportError={setError} onClearDraft={clearDraft} onContinue={submitConversation} />}
    {step === 1 && <GroundTruthReview memories={memories} busy={busy} onChange={updateMemory} onAddMemory={addMemory} onConfirm={confirm} />}
    {step === 2 && <section>
      <h1>Configure Memory Audit</h1>
      <p>Select one or more strategies and target models. Every condition receives the same confirmed ground truth and frozen test suite.</p>
      <h3>Controlled Memory Strategies</h3>
      <div className="target-grid">{strategies.map((item) => <label className={`target ${selectedStrategies.includes(item.value) ? 'selected' : ''}`} key={item.value}>
        <input type="checkbox" checked={selectedStrategies.includes(item.value)} onChange={() => toggleStrategy(item.value)} />
        <strong>{item.label}</strong><span>{item.description}</span>
      </label>)}</div>
      <h3>Target Models to Compare</h3>
      <div className="provider-grid">{providers.map((item) => <label className={`target ${targetProviders.includes(item.provider) ? 'selected' : ''}`} key={item.provider}>
        <input type="checkbox" checked={targetProviders.includes(item.provider)} disabled={!item.configured} onChange={() => toggleTarget(item)} />
        <strong>{item.label}</strong><span>{item.description}</span><small className={item.configured ? 'ready' : 'missing'}>{item.configured ? 'Available for comparison' : 'API key required'}</small>
      </label>)}</div>
      <p className="provider-note">API keys remain on the backend. Selecting several strategies with one model measures memory policy; selecting several models compares model and policy.</p>
      <div className="form-grid">
        <label>Test suite design<select value={suiteMode} onChange={(event) => setSuiteMode(event.target.value as TestSuiteMode)}><option value="behavioural">Behavioural tests</option><option value="direct_ground_truth">Direct Ground-Truth baseline</option><option value="fixed_template">Fixed-Template baseline</option></select><small>Frozen once and shared by every condition.</small></label>
        <label>Memory maintenance<select value={maintenancePolicy} onChange={(event) => setMaintenancePolicy(event.target.value as MemoryMaintenancePolicy)}><option value="update_aware_consolidation">Update-aware consolidation</option><option value="append_only">Append only</option></select><small>Controls how the target agent writes and updates its own memory store.</small></label>
        <label>Target memory capacity<input type="number" min="1" max="500" value={targetMemoryCapacity} onChange={(event) => setTargetMemoryCapacity(Math.max(1, Math.min(500, Number(event.target.value) || 1)))} /><small>Maximum retained records. Capacity pressure creates traceable evictions; conflicts are preserved.</small></label>
        <label>Target memory writer<select value={targetMemoryWriter} onChange={(event) => setTargetMemoryWriter(event.target.value as TargetMemoryWriterKind)}><option value="rule_based">Rule-based writer</option><option value="llm_structured" disabled={pipelineProvider === 'rule_based'}>Structured LLM writer</option></select><small>Frozen on every run. The structured writer requires a configured LLM pipeline.</small></label>
        <label>Memory extraction and test generation<select value={pipelineProvider} onChange={(event) => { const next = event.target.value as TargetProvider; setPipelineProvider(next); if (next === 'rule_based' && targetMemoryWriter === 'llm_structured') setTargetMemoryWriter('rule_based'); }}>{providers.map((item) => <option key={item.provider} value={item.provider}>{item.label}{item.configured ? '' : ' — key required'}</option>)}</select></label>
        <label>Behaviour evaluator<select value={evaluatorProvider} onChange={(event) => setEvaluatorProvider(event.target.value as TargetProvider)}>{providers.map((item) => <option key={item.provider} value={item.provider}>{item.label}{item.configured ? '' : ' — key required'}</option>)}</select></label>
        <label>Test budget<input type="number" min="1" max="100" value={budget} onChange={(event) => setBudget(Number(event.target.value))} /></label>
        <label>Repeated runs per condition<input type="number" min="1" max="10" value={repetitions} onChange={(event) => setRepetitions(Math.max(1, Math.min(10, Number(event.target.value) || 1)))} /></label>
        <label>Temperature<input value="0.0" readOnly /></label><label>Random seed<input value="42" readOnly /></label><label>Prompt-template version<input value="rule-based-v1" readOnly /></label>
      </div>
      {selectedTargets.length > 0 && <div className="form-grid model-overrides">{selectedTargets.map((provider) => <label key={provider.provider}>Target model for {provider.label}<input value={targetModels[provider.provider] ?? provider.default_model} onChange={(event) => setTargetModels((current) => ({ ...current, [provider.provider]: event.target.value }))} /><small>Record an explicit deployed model name for this comparison.</small></label>)}</div>}
      <h3>Audit Dimensions</h3><p className="dimensions">Accuracy · Freshness · Conflict Resolution · Appropriate Use</p>
      <button disabled={busy || selectedTargets.length === 0 || selectedStrategies.length === 0 || !selectedPipeline?.configured || !selectedEvaluator?.configured} onClick={start}>Start {selectedTargets.length * selectedStrategies.length * repetitions > 1 ? `${selectedTargets.length * selectedStrategies.length * repetitions}-Run Comparison` : 'Memory Audit'}</button>
    </section>}
    {step === 3 && <section className="running">
      <h1>Prepare Memory Audit</h1><p>{runs.length > 1 ? `${runs.length} conditions will use one shared test suite.` : 'Generate and review the test suite before executing the controlled audit.'}</p>
      {busy && runningLabel && <p className="running-model">Currently working: <b>{runningLabel}</b> <button type="button" className="secondary" onClick={cancelCurrentRun}>Cancel current run</button></p>}
      <ul className="progress"><li>Preparing confirmed ground truth <b>Complete</b></li><li>Generating shared behavioural tests <b>{reviewTests ? 'Complete' : busy ? 'In progress' : 'Waiting'}</b></li><li>Researcher test-suite review <b>{readyForExecution ? 'Complete' : reviewTests ? 'Action required' : 'Waiting'}</b></li><li>Initialising target AI <b>{readyForExecution ? 'Ready' : 'Waiting'}</b></li><li>Executing memory tests <b>Waiting</b></li><li>Evaluating responses <b>Waiting</b></li></ul>
      {!reviewTests ? <button disabled={busy} onClick={prepareTests}>{busy ? 'Generating Shared Test Suite…' : 'Generate Tests for Review'}</button> : <><TestSuiteReview tests={reviewTests} busy={busy} onReview={reviewTest} onRegenerate={regenerateTest} /><button disabled={busy || !readyForExecution} onClick={runAudit}>{busy ? `Running ${runningLabel || 'audit'}…` : runs.length > 1 ? 'Run Comparison & View Results' : 'Run Audit & View Results'}</button>{!readyForExecution && <p className="provider-note">Accept each pending test and regenerate rejected tests before execution.</p>}</>}
    </section>}
    {step === 4 && results.length > 0 && <section>
      <h1>{results.length > 1 ? 'Memory Health Model Comparison' : 'Memory Health Report'}</h1>
      {failedRuns.length > 0 && <div className="partial-run-warning"><b>{failedRuns.length} condition{failedRuns.length === 1 ? '' : 's'} did not complete.</b><ul>{failedRuns.map((run) => <li key={run.runId}>{run.label}: {run.detail}</li>)}</ul><button disabled={busy} onClick={retryFailedRuns}>{busy ? `Retrying ${runningLabel || 'run'}…` : 'Retry Failed Conditions'}</button></div>}
      {results.length > 1 && <><Suspense fallback={<p className="chart-loading" role="status">Loading visual comparison charts…</p>}><ComparisonVisualizations runs={results} /></Suspense><ModelComparison runs={results} /><ExperimentStatistics runs={results} /></>}
      {results.map((item) => <details className="individual-report" key={item.result.run_id} open={results.length === 1}><summary>{item.label} detailed report</summary><ResultDashboard result={item.result} /><TargetMemoryTrace runId={item.result.run_id} /></details>)}
      <button className="secondary" onClick={() => window.location.reload()}>Start New Audit</button>
    </section>}
  </main>;
}
