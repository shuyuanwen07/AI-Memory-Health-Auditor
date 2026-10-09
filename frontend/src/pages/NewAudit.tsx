import { ModelPicker } from '../components/ModelPicker';
import { TargetProfileEditor, defaultTargetProfile } from "../components/TargetProfileEditor";
import { UIAlert } from '../components/ui';
import { UISelect, UIOption, UIInput, UIButton, UIPanel, UISummary, UICheckbox } from '../components/ui';
import type { ConversationMessage } from '../types/domain';
import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import type { AuditResult, ConversationInputMessage, Memory, MemoryMaintenancePolicy, MemoryReviewPatch, MemoryStrategy, ProviderOption, TargetMemoryWriterKind, TargetProvider, TestCase, TestSuiteMode } from '../types/domain';
import { StepIndicator } from '../components/StepIndicator';
import { ResultDashboard } from '../components/ResultDashboard';
import { ConversationStep } from '../components/ConversationStep';
import { GroundTruthReview } from '../components/GroundTruthReview';
import { ModelComparison } from '../components/ModelComparison';
import { ExperimentStatistics } from '../components/ExperimentStatistics';
import { TestSuiteReview, hasDuplicateQuestions } from '../components/TestSuiteReview';
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
type CreationBatch = {
  experimentBody: Record<string, unknown>;
  experimentId?: string;
  conditions: Array<{ body: Record<string, unknown>; label: string; groupLabel: string; runId?: string }>;
};
type CompletedRun = { label: string; groupLabel: string; result: AuditResult };
type FailedRun = { runId: string; label: string; detail: string };

const strategies: Array<{ value: MemoryStrategy; label: string; description: string }> = [
  { value: 'no_memory', label: 'No Memory', description: 'Reference baseline that gives the target AI no retrieved long-term memory.' },
  { value: 'full_context', label: 'Full Context', description: 'Reference baseline that replays all active memories without ranking.' },
  { value: 'weak_first_hit', label: 'Weak First-Hit', description: 'Uses only the first related memory, without resolving updates or conflicts.' },
  { value: 'strong_rule_based', label: 'Strong Rule-Based', description: 'Prioritises contextual requirements, updates, stable facts and superseded records.' },
  { value: 'strong_score_based', label: 'Strong Score-Based', description: 'Ranks memories with transparent relevance, freshness and context weights.' },
  { value: 'scope_aware', label: 'Scope-Aware', description: 'Prioritises project requirements for task prompts and uses profile or preferences only when relevant.' },
  { value: 'temporal_importance', label: 'Temporal & Importance', description: 'Ranks source-message recency and durable task importance using a frozen, explainable relative chronology.' },
];

export function NewAudit() {
  const restoredDraft = loadConversationDraft();
  const [step, setStep] = useState(0);
  const [text, setText] = useState(restoredDraft.text ?? sample);
  const [sourceMessages, setSourceMessages] = useState<ConversationMessage[]>([]);
  const [importedMessages, setImportedMessages] = useState<ConversationInputMessage[] | null>(restoredDraft.importedMessages || null);
  const [consent, setConsent] = useState(Boolean(restoredDraft.consent));
  const [conversationId, setConversationId] = useState('');
  const [memories, setMemories] = useState<Memory[]>([]);
  const [selectedStrategies, setSelectedStrategies] = useState<MemoryStrategy[]>(['weak_first_hit']);
  const [targetProviders, setTargetProviders] = useState<TargetProvider[]>(['rule_based']);
  const [targetModels, setTargetModels] = useState<Partial<Record<TargetProvider, string>>>({});
  const [pipelineProvider, setPipelineProvider] = useState<TargetProvider>('rule_based');
  const [evaluatorProvider, setEvaluatorProvider] = useState<TargetProvider>('rule_based');
  const [pipelineModel, setPipelineModel] = useState<string | null>(null);
  const [evaluatorModel, setEvaluatorModel] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProviderOption[]>([]);
  const [budget, setBudget] = useState(8);
  const [repetitions, setRepetitions] = useState(1);
  const [suiteMode, setSuiteMode] = useState<TestSuiteMode>('behavioural');
  const [maintenancePolicy, setMaintenancePolicy] = useState<MemoryMaintenancePolicy>('update_aware_consolidation');
  const [targetMemoryCapacity, setTargetMemoryCapacity] = useState(50);
  const [targetMemoryWriter, setTargetMemoryWriter] = useState<TargetMemoryWriterKind>('rule_based');
  const [targetProfile, setTargetProfile] = useState(defaultTargetProfile);
  const [targetSystem, setTargetSystem] = useState('controlled-memory');
  const [systems, setSystems] = useState<Array<{value:string;label:string;configured:boolean}>>([]);
  const [runs, setRuns] = useState<PreparedRun[]>([]);
  const [experimentId, setExperimentId] = useState('');
  const creationBatch = useRef<CreationBatch | null>(null);
  const [creationPending, setCreationPending] = useState(false);
  const [results, setResults] = useState<CompletedRun[]>([]);
  const [failedRuns, setFailedRuns] = useState<FailedRun[]>([]);
  const [reviewTests, setReviewTests] = useState<TestCase[] | null>(null);
  const [runningLabel, setRunningLabel] = useState('');
  const [runningRunId, setRunningRunId] = useState('');
  const [runningStage, setRunningStage] = useState<'idle' | 'execute' | 'evaluate' | 'recover'>('idle');
  const [queueStopped, setQueueStopped] = useState(false);
  const [entireExperimentCancelled, setEntireExperimentCancelled] = useState(false);
  const cancellationRequested = useRef(false);
  const entireExperimentCancelledRef = useRef(false);
  const cancelledRunIds = useRef(new Set<string>());
  const completedRunIds = useRef(new Set<string>());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    (api.targetSystems?.() ?? Promise.resolve([])).then(setSystems).catch(()=>setSystems([]));
    api.targetProviders().then((items) => {
      const openRouter = items.find((item) => item.provider === 'openrouter');
      // Legacy providers stay readable in saved runs; new cloud calls use OpenRouter.
      setProviders(openRouter ? items.filter((item) => item.provider === 'openrouter' || item.provider === 'rule_based' || item.provider === 'ollama') : items);
      if (openRouter?.configured) {
        setTargetProviders(['openrouter']);
        setPipelineProvider('openrouter');
        setEvaluatorProvider('openrouter');
      }
    }).catch(() => setProviders([]));
  }, []);
  useEffect(() => {
    if (step === 0) sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ text, importedMessages, consent }));
    else sessionStorage.removeItem(DRAFT_KEY);
  }, [consent, importedMessages, step, text]);

  const clearDraft = () => {
    sessionStorage.removeItem(DRAFT_KEY);
    setText(''); setImportedMessages(null); setConsent(false); setError('');
  };

  const act = async (operation: () => Promise<void>, propagateError = false) => {
    setBusy(true);
    setError('');
    try { await operation(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Something went wrong.'); if (propagateError) throw cause; }
    finally { setBusy(false); }
  };

  const submitConversation = () => act(async () => {
    const conversation = await api.createConversation(true, text, importedMessages);
    setConversationId(conversation.conversation_id);
    setSourceMessages(conversation.messages ?? []);
    setMemories(await api.extract(conversation.conversation_id, pipelineProvider, pipelineProvider === 'rule_based' ? undefined : pipelineModel?.trim() || selectedPipeline?.default_pipeline_model || selectedPipeline?.default_model));
    setStep(1);
  });

  const updateMemory = (memory: Memory, patch: MemoryReviewPatch) => act(async () => {
    const next = await api.updateMemory(memory.memory_id, patch);
    setMemories((items) => items.map((item) => item.memory_id === memory.memory_id ? next : item));
  }, true);

  const addMemory = (canonicalValue: string, sourceMessageIds: string[] = []) => act(async () => {
    const memory = await api.addMemory({ conversation_id: conversationId, canonical_value: canonicalValue, source_message_ids: sourceMessageIds });
    setMemories((items) => [...items, memory]);
  }, true);

  const confirm = () => act(async () => {
    const confirmedIds = memories
      .filter((memory) => memory.status === 'confirmed' || memory.status === 'edited')
      .map((memory) => memory.memory_id);
    setMemories(await api.confirm(conversationId, confirmedIds));
    setStep(2);
  });

  const selectedTargets = providers.filter((item) => targetProviders.includes(item.provider));
  const selectedModels = selectedTargets.map((provider) => ({
    provider,
    models: provider.provider === 'rule_based' ? [provider.default_model] : [...new Set(
      (targetModels[provider.provider] ?? provider.default_model).split(/\r?\n/).map((name) => name.trim()).filter(Boolean),
    )],
  }));
  const conditionCount = selectedModels.reduce((total, item) => total + item.models.length, 0) * selectedStrategies.length * repetitions;
  const modelSelectionError = selectedModels.some((item) => item.models.length === 0)
    ? `Select at least one model for ${selectedModels.filter((item) => item.models.length === 0).map((item) => item.provider.label).join(', ')}, or deselect that service above.`
    : selectedModels.some((item) => item.models.length > 8)
      ? 'Select up to eight models per service.'
      : conditionCount > 64 ? 'This comparison exceeds 64 runs. Reduce models, strategies or repetitions.' : '';
  // Structured extraction/generation does not yet support Ollama;
  // the separate evaluator does support local semantic pre-review.
  const pipelineProviders = providers.filter((item) => item.provider !== 'ollama');
  const selectedPipeline = pipelineProviders.find((item) => item.provider === pipelineProvider);
  const evaluatorProviders = providers;
  const selectedEvaluator = evaluatorProviders.find((item) => item.provider === evaluatorProvider);
  const toggleTarget = (option: ProviderOption) => {
    if (!option.configured) return;
    // Re-enabling a service starts with its configured model, even if its
    // previous selection was cleared. Clearing an active picker stays explicit.
    if (!targetProviders.includes(option.provider) && !targetModels[option.provider]?.trim()) {
      setTargetModels((current) => ({ ...current, [option.provider]: option.default_model }));
    }
    setTargetProviders((current) => current.includes(option.provider)
      ? (current.length === 1 ? current : current.filter((provider) => provider !== option.provider))
      : [...current, option.provider]);
  };
  const toggleStrategy = (strategy: MemoryStrategy) => setSelectedStrategies((current) => current.includes(strategy)
    ? (current.length === 1 ? current : current.filter((value) => value !== strategy))
    : [...current, strategy]);

  const start = () => act(async () => {
    if (!creationBatch.current && modelSelectionError) throw new Error(modelSelectionError);
    const plan = selectedModels.flatMap(({ provider, models }) => models.flatMap((model) => selectedStrategies.flatMap((strategy) =>
      Array.from({ length: repetitions }, (_, index) => ({ provider, model, strategy, repetition: index + 1 })))));
    if (!creationBatch.current) {
        const experimentBody = {
          creation_request_key: crypto.randomUUID(),
          conversation_id: conversationId,
          label: `Memory strategy comparison ${new Date().toISOString()}`,
          test_suite_configuration: {
            test_budget: budget, random_seed: 42, prompt_template_version: 'rule-based-v4',
            pipeline_provider: pipelineProvider,
            pipeline_model: pipelineProvider === 'rule_based' ? 'rule-based-v2' : pipelineModel?.trim() || selectedPipeline?.default_pipeline_model || selectedPipeline?.default_model,
            evaluator_provider: evaluatorProvider,
            evaluator_model: evaluatorProvider === 'rule_based' ? 'rule-based-v4' : evaluatorModel?.trim() || selectedEvaluator?.default_evaluator_model || selectedEvaluator?.default_model,
            suite_mode: suiteMode,
          },
        };
        const conditions = plan.map(({ provider, model, strategy, repetition }) => {
          const strategyLabel = strategies.find((item) => item.value === strategy)?.label ?? strategy;
          const groupLabel = `${provider.label} · ${model} · ${strategyLabel}`;
          return { groupLabel, label: repetitions > 1 ? `${groupLabel} · Run ${repetition}` : groupLabel, body: {
          creation_request_key: crypto.randomUUID(),
          conversation_id: conversationId,
          target_configuration: strategy === 'weak_first_hit' ? 'weak' : 'strong',
          memory_strategy: strategy,
          memory_maintenance_policy: maintenancePolicy,
          target_memory_capacity: targetMemoryCapacity,
          target_memory_writer: targetMemoryWriter,
          target_memory_profile: structuredClone(targetProfile),
          target_system_adapter: targetSystem,
          provider: provider.provider,
          model,
          pipeline_provider: pipelineProvider,
          pipeline_model: pipelineProvider === 'rule_based' ? undefined : pipelineModel?.trim() || selectedPipeline?.default_pipeline_model || selectedPipeline?.default_model,
          evaluator_provider: evaluatorProvider,
          evaluator_model: evaluatorProvider === 'rule_based' ? undefined : evaluatorModel?.trim() || selectedEvaluator?.default_evaluator_model || selectedEvaluator?.default_model,
          temperature: 0,
          random_seed: 42,
          test_budget: budget,
          prompt_template_version: 'rule-based-v4',
          } };
        });
        creationBatch.current = { experimentBody, conditions };
        setCreationPending(true);
    }
    const batch = creationBatch.current;
    if (!batch.experimentId) {
      batch.experimentId = (await api.createExperiment(batch.experimentBody)).experiment_id;
    }
    setExperimentId(batch.experimentId);
    setQueueStopped(false);
    setEntireExperimentCancelled(false);
    cancellationRequested.current = false;
    entireExperimentCancelledRef.current = false;
    cancelledRunIds.current.clear();
    completedRunIds.current.clear();
    // Sequential creation preserves every acknowledged condition. Unknown outcomes
    // are retried with the same durable server key and frozen payload.
    for (const condition of batch.conditions) {
      if (!condition.runId) condition.runId = (await api.createAudit({ ...condition.body, experiment_id: batch.experimentId })).run_id;
    }
    setRuns(batch.conditions.map((condition) => ({
      runId: condition.runId!, label: condition.label, groupLabel: condition.groupLabel,
    })));
    setCreationPending(false);
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
  const remainingConditions = runs.filter((run) => !cancelledRunIds.current.has(run.runId) && !completedRunIds.current.has(run.runId));
  const readyForExecution = Boolean(reviewTests?.length) && !hasDuplicateQuestions(reviewTests!) && reviewTests!.every((test) => test.quality_status === 'accepted');

  const runAudit = (continueRemaining = false) => act(async () => {
    if (!readyForExecution) throw new Error('Generate and complete the shared test-suite review before running the audit.');
    if (queueStopped && !continueRemaining) throw new Error('This execution queue was cancelled. Continue remaining conditions or start a new audit.');
    if (entireExperimentCancelledRef.current) throw new Error('This experiment was cancelled and cannot be resumed. Start a new audit for a fresh comparison.');
    setQueueStopped(false);
    cancellationRequested.current = false;
    const completed: CompletedRun[] = [];
    const failed: FailedRun[] = [];
    for (const run of runs) {
      if (cancelledRunIds.current.has(run.runId) || completedRunIds.current.has(run.runId)) continue;
      setRunningLabel(run.label);
      setRunningRunId(run.runId);
      try {
        setRunningStage('execute');
        await api.execute(run.runId);
        setRunningStage('evaluate');
        await api.evaluate(run.runId);
        completed.push({ label: run.label, groupLabel: run.groupLabel, result: await api.results(run.runId) });
        completedRunIds.current.add(run.runId);
      } catch (cause) {
        if (cancellationRequested.current) break;
        failed.push({ runId: run.runId, label: run.label, detail: cause instanceof Error ? cause.message : 'This condition could not be completed.' });
      }
    }
    setRunningLabel(''); setRunningRunId(''); setRunningStage('idle');
    setResults((current) => [...current.filter((item) => !completed.some((next) => next.result.run_id === item.result.run_id)), ...completed]);
    setFailedRuns((current) => [...current.filter((item) => !failed.some((next) => next.runId === item.runId)), ...failed]);
    if (cancellationRequested.current) {
      setQueueStopped(true);
      setError(entireExperimentCancelledRef.current
        ? 'The entire comparison was cancelled. Completed conditions remain available in Audit History.'
        : runs.some((run) => !cancelledRunIds.current.has(run.runId) && !completedRunIds.current.has(run.runId))
          ? 'Execution was stopped. Continue the remaining conditions or cancel the rest of this comparison.'
          : 'Execution was stopped. No conditions remain to run. Saved evidence is available in Audit History.');
      return;
    }
    if (!completedRunIds.current.size) throw new Error('No experimental conditions completed. Check the failed runs and retry them.');
    setStep(4);
  });

  const retryFailedRuns = () => act(async () => {
    const recovered: CompletedRun[] = [];
    const stillFailed: FailedRun[] = [];
    for (const failed of failedRuns) {
      setRunningLabel(failed.label); setRunningRunId(failed.runId);
      try {
        setRunningStage('recover');
        const audit = await api.retry(failed.runId);
        if (audit.status !== 'COMPLETED') throw new Error('The run is still incomplete. Check the provider configuration and try again.');
        const groupLabel = runs.find((run) => run.runId === failed.runId)?.groupLabel ?? failed.label;
        recovered.push({ label: failed.label, groupLabel, result: await api.results(failed.runId) });
        completedRunIds.current.add(failed.runId);
      } catch (cause) {
        stillFailed.push({ ...failed, detail: cause instanceof Error ? cause.message : failed.detail });
      }
    }
    setRunningLabel(''); setRunningRunId(''); setRunningStage('idle');
    setResults((current) => [...current, ...recovered]);
    setFailedRuns(stillFailed);
  });

  const cancelCurrentRun = async () => {
    if (!runningRunId) return;
    try {
      cancellationRequested.current = true;
      cancelledRunIds.current.add(runningRunId);
      await api.cancel(runningRunId);
      setError('Cancellation requested. This condition will stop between provider calls, and the execution queue will stop.');
    } catch (cause) {
      cancellationRequested.current = false;
      cancelledRunIds.current.delete(runningRunId);
      setError(cause instanceof Error ? cause.message : 'The current run could not be cancelled.');
    }
  };

  const cancelExperiment = async () => {
    if (!experimentId) return;
    try {
      cancellationRequested.current = true;
      setEntireExperimentCancelled(true);
      entireExperimentCancelledRef.current = true;
      await api.cancelExperiment(experimentId);
      for (const run of runs) if (!completedRunIds.current.has(run.runId)) cancelledRunIds.current.add(run.runId);
      setError('The comparison was cancelled. Completed conditions remain available in Audit History.');
    } catch (cause) {
      cancellationRequested.current = false;
      setEntireExperimentCancelled(false);
      entireExperimentCancelledRef.current = false;
      setError(cause instanceof Error ? cause.message : 'The comparison could not be cancelled.');
    }
  };

  return <main className="workflow">
    <StepIndicator current={step} />
    {error && <UIAlert role="alert" aria-live="assertive" className="alert">{error}</UIAlert>}
    {step === 0 && <><label>Memory extraction service<UISelect aria-label={["Memory extraction service"].join(' ')} value={pipelineProvider} disabled={busy} onChange={(event) => { setPipelineProvider(event.target.value as TargetProvider); setPipelineModel(null); }}>{pipelineProviders.map((item) => <UIOption key={item.provider} value={item.provider} disabled={!item.configured}>{item.label}{item.configured ? '' : ' — unavailable'}</UIOption>)}</UISelect></label><p className="input-help">Choose the service that extracts candidate memories before review. Qwen can be selected separately as the AI being tested.</p>{pipelineProvider !== 'rule_based' && <label>Extraction model<ModelPicker label="Extraction model" provider={pipelineProvider} defaultModel={selectedPipeline?.default_pipeline_model ?? selectedPipeline?.default_model} value={pipelineModel ?? selectedPipeline?.default_pipeline_model ?? selectedPipeline?.default_model ?? ''} onChange={setPipelineModel} disabled={busy} /></label>}<ConversationStep text={text} consent={consent} busy={busy} onTextChange={(next) => { setText(next); setImportedMessages(null); }} onConsentChange={setConsent} onImport={(messages, previewText) => { setImportedMessages(messages); setText(previewText); }} onImportError={setError} onClearDraft={clearDraft} onContinue={submitConversation} /></>}
    {step === 1 && <GroundTruthReview sourceMessages={sourceMessages} memories={memories} busy={busy} onChange={updateMemory} onAddMemory={addMemory} onConfirm={confirm} />}
    {step === 2 && creationPending && <section>
      <h1>Continue Preparing Your Audit</h1>
      <p>Your original settings are preserved. Some records may already be saved; continuing reuses them and finishes the remaining conditions.</p>
      <p>{creationBatch.current?.conditions.filter((item) => item.runId).length ?? 0} of {creationBatch.current?.conditions.length ?? 0} conditions acknowledged. No model answers have been requested at this step.</p>
      <UIButton disabled={busy} onClick={start}>{busy ? 'Preparing Audit…' : 'Resume Audit Preparation'}</UIButton>
      <p>Keep this page open to resume this preparation. After closing it, check Audit History for saved records.</p>
      <a href="/history">Open Audit History</a>
    </section>}
    {step === 2 && !creationPending && <section>
      <h1>Configure Memory Audit</h1>
      <h3>Controlled Memory Strategies</h3>
      <div className="target-grid">{strategies.map((item) => <UICheckbox checked={selectedStrategies.includes(item.value)} onChange={() => toggleStrategy(item.value)} className={`target ${selectedStrategies.includes(item.value) ? 'selected' : ''}`} key={item.value}><strong>{item.label}</strong><span>{item.description}</span></UICheckbox>)}</div>
      <h3>Target Models to Compare</h3>
      <div className="provider-grid">{providers.map((item) => <UICheckbox checked={targetProviders.includes(item.provider)} disabled={!item.configured} onChange={() => toggleTarget(item)} className={`target ${targetProviders.includes(item.provider) ? 'selected' : ''}`} key={item.provider}><strong>{item.label}</strong><span>{item.description}</span><small className={item.configured ? 'ready' : 'missing'}>{item.configured ? 'Available for comparison' : 'API key required'}</small></UICheckbox>)}</div>
      <p className="provider-note">API keys remain on the backend. Selecting several strategies with one model measures memory policy; selecting several models compares model and policy.</p>
      <div className="form-grid">
        <label>Test suite design<UISelect aria-label={["Test suite design"].join(' ')} value={suiteMode} onChange={(event) => setSuiteMode(event.target.value as TestSuiteMode)}><UIOption value="paired_contextual">Paired recall &amp; task probes</UIOption><UIOption value="behavioural">Behavioural tests</UIOption><UIOption value="direct_ground_truth">Direct Ground-Truth baseline</UIOption><UIOption value="fixed_template">Fixed-Template baseline</UIOption></UISelect><small>Frozen once and shared by every condition. Paired probes need at least two calls; an odd budget leaves one call unused.</small></label>
        <label>Memory maintenance<UISelect aria-label={["Memory maintenance"].join(' ')} disabled={targetSystem==='external-http'} value={maintenancePolicy} onChange={(event) => setMaintenancePolicy(event.target.value as MemoryMaintenancePolicy)}><UIOption value="update_aware_consolidation">Update-aware consolidation</UIOption><UIOption value="append_only">Append only</UIOption></UISelect><small>Controls how the target agent writes and updates its own memory store.</small></label>
        <label>Target memory capacity<UIInput type="number" min="1" max="500" disabled={targetSystem==='external-http'} value={targetMemoryCapacity} onChange={(event) => setTargetMemoryCapacity(Math.max(1, Math.min(500, Math.trunc(Number(event.target.value)) || 1)))} /><small>Maximum retained records. Capacity pressure creates traceable evictions; conflicts are preserved.</small></label>
        <label>Target memory writer<UISelect aria-label={["Target memory writer"].join(' ')} disabled={targetSystem==='external-http'} value={targetMemoryWriter} onChange={(event) => setTargetMemoryWriter(event.target.value as TargetMemoryWriterKind)}><UIOption value="rule_based">Rule-based writer</UIOption><UIOption value="llm_structured" disabled={pipelineProvider === 'rule_based'}>Structured LLM writer</UIOption></UISelect><small>Frozen on every run. The structured writer requires a configured LLM pipeline.</small></label>
        <label>Test generation service<UISelect aria-label={["Test generation service"].join(' ')} value={pipelineProvider} onChange={(event) => { const next = event.target.value as TargetProvider; setPipelineProvider(next); setPipelineModel(null); if (next === 'rule_based' && targetMemoryWriter === 'llm_structured') setTargetMemoryWriter('rule_based'); }}>{pipelineProviders.map((item) => <UIOption key={item.provider} value={item.provider} disabled={!item.configured}>{item.label}{item.configured ? '' : ' — unavailable'}</UIOption>)}</UISelect></label>
        <label>Behaviour evaluator<UISelect aria-label={["Behaviour evaluator"].join(' ')} value={evaluatorProvider} onChange={(event) => { setEvaluatorProvider(event.target.value as TargetProvider); setEvaluatorModel(null); }}>{evaluatorProviders.map((item) => <UIOption key={item.provider} value={item.provider} disabled={!item.configured}>{item.label}{item.configured ? '' : ' — unavailable'}</UIOption>)}</UISelect></label>
        <label>Test budget<UIInput type="number" min="1" max="100" value={budget} onChange={(event) => setBudget(Math.max(1, Math.min(100, Math.trunc(Number(event.target.value)) || 1)))} /></label>
        <label>Repeated runs per condition<UIInput type="number" min="1" max="10" value={repetitions} onChange={(event) => setRepetitions(Math.max(1, Math.min(10, Math.trunc(Number(event.target.value)) || 1)))} /></label>
        <label>Temperature<UIInput value="0.0" readOnly /></label><label>Random seed<UIInput value="42" readOnly /></label>
      </div>
      {pipelineProvider !== 'rule_based' && <label>Test generation model<ModelPicker label="Test generation model" provider={pipelineProvider} defaultModel={selectedPipeline?.default_pipeline_model ?? selectedPipeline?.default_model} value={pipelineModel ?? selectedPipeline?.default_pipeline_model ?? selectedPipeline?.default_model ?? ''} onChange={setPipelineModel} /></label>}
      {evaluatorProvider === 'ollama' && <p className="input-help" role="note">Local semantic evaluation is AI pre-review, not independent human validation. Using the same model for answers and judging can share errors; check complete answers and explanations independently. Invalid judge replies remain awaiting review.</p>}
      {evaluatorProvider !== 'rule_based' && <label>Evaluator model<ModelPicker label="Evaluator model" provider={evaluatorProvider} defaultModel={selectedEvaluator?.default_evaluator_model ?? selectedEvaluator?.default_model} value={evaluatorModel ?? selectedEvaluator?.default_evaluator_model ?? selectedEvaluator?.default_model ?? ''} onChange={setEvaluatorModel} /></label>}
      {selectedTargets.length > 0 && <div className="form-grid model-overrides">{selectedTargets.map((provider) => <label key={provider.provider}>Target model for {provider.label}<ModelPicker label={`Target model for ${provider.label}`} provider={provider.provider} defaultModel={provider.default_model} multiple disabled={provider.provider === 'rule_based'} value={provider.provider === 'rule_based' ? provider.default_model : targetModels[provider.provider] ?? provider.default_model} onChange={(value) => setTargetModels((current) => ({ ...current, [provider.provider]: value }))} /><small>{provider.provider === 'rule_based' ? 'This deterministic baseline has one fixed identity.' : 'Search and select up to eight models to compare.'}</small></label>)}</div>}
      {modelSelectionError && <UIAlert role="alert">{modelSelectionError}</UIAlert>}
      <p role="status">{conditionCount} planned runs · up to {conditionCount * budget} answer requests before retries. All conditions share reviewed questions, memory settings and instructions; model names must be available on the selected service.</p>
      <label>System under test<UISelect aria-label="System under test" value={targetSystem} onChange={event=>setTargetSystem(event.target.value)}>{systems.length ? systems.map(system=><UIOption key={system.value} value={system.value} disabled={!system.configured}>{system.label}{system.configured?'':' — backend setup required'}</UIOption>) : <UIOption value="controlled-memory">Configurable memory system</UIOption>}</UISelect></label>
      {targetSystem==='external-http'&&<p>The independent service owns memory writing, maintenance and retention. The controls above are unavailable; the strategy and memory configuration below are sent through its contract.</p>}
      <TargetProfileEditor value={targetProfile} onChange={setTargetProfile} disabled={busy}/>
      <h3>Audit Dimensions</h3><p className="dimensions">Accuracy · Freshness · Conflict Resolution · Appropriate Use</p>
      <UIButton disabled={busy || Boolean(modelSelectionError) || !targetProfile.label.trim() || (suiteMode === "paired_contextual" && budget < 2) || selectedTargets.length === 0 || selectedStrategies.length === 0 || !selectedPipeline?.configured || !selectedEvaluator?.configured} onClick={start}>Start {conditionCount > 1 ? `${conditionCount}-Run Comparison` : 'Memory Audit'}</UIButton>
    </section>}
    {step === 3 && <section className="running">
      <h1>Prepare Memory Audit</h1>
      {busy && runningLabel && <p className="running-model">Currently working: <b>{runningLabel}</b>{runningRunId && <> <UIButton type="button" className="secondary" onClick={cancelCurrentRun}>Cancel current run &amp; stop queue</UIButton>{runs.length > 1 && <UIButton type="button" className="secondary" onClick={cancelExperiment}>Cancel entire comparison</UIButton>}</>}</p>}
      <ul className="progress"><li>Preparing confirmed ground truth <b>Complete</b></li><li>Generating shared behavioural tests <b>{reviewTests ? 'Complete' : busy ? 'In progress' : 'Waiting'}</b></li><li>Test-suite quality checks <b>{readyForExecution ? 'Complete' : reviewTests ? 'Action required' : 'Waiting'}</b></li><li>Initialising target AI <b>{readyForExecution ? 'Ready' : 'Waiting'}</b></li><li>Executing memory tests <b>{runningStage === 'execute' ? 'In progress' : runningStage === 'evaluate' ? 'Complete' : runningStage === 'recover' ? 'Recovering' : 'Waiting'}</b></li><li>Evaluating responses <b>{runningStage === 'evaluate' ? 'In progress' : runningStage === 'recover' ? 'Recovering' : 'Waiting'}</b></li></ul>
      {!reviewTests ? <UIButton disabled={busy} onClick={prepareTests}>{busy ? 'Generating Shared Test Suite…' : 'Generate Tests for Review'}</UIButton> : <><TestSuiteReview tests={reviewTests} busy={busy || completedRunIds.current.size > 0 || cancelledRunIds.current.size > 0} onReview={reviewTest} onRegenerate={regenerateTest} /><UIButton disabled={busy || !readyForExecution || queueStopped} onClick={() => runAudit()}>{queueStopped ? 'Execution Queue Cancelled' : busy ? `Running ${runningLabel || 'audit'}…` : runs.length > 1 ? 'Run Comparison & View Results' : 'Run Audit & View Results'}</UIButton>{queueStopped && <div className="provider-note"><p>{entireExperimentCancelled ? 'This comparison is terminal. Start a new audit for a fresh controlled comparison.' : remainingConditions.length ? 'The current condition was cancelled. Remaining conditions still use the same frozen suite.' : 'No conditions remain to run. Saved evidence is available in Audit History.'}</p>{!entireExperimentCancelled && remainingConditions.length > 0 && <><UIButton type="button" className="secondary" onClick={() => runAudit(true)}>Continue Remaining Conditions</UIButton><UIButton type="button" className="secondary" onClick={cancelExperiment}>Cancel Remaining Conditions</UIButton></>}{remainingConditions.length === 0 && <a href="/history">Open Audit History</a>}</div>}{!readyForExecution && <p className="provider-note">Accept pending questions, and accept or regenerate rejected questions before execution. Duplicate questions must be regenerated.</p>}</>}
    </section>}
    {step === 4 && results.length > 0 && <section>
      <h1>{results.length > 1 ? 'Memory Health Model Comparison' : 'Memory Health Report'}</h1>
      {results.length < runs.length && <UIAlert role="status" className="partial-run-warning"><b>Incomplete comparison</b><p>{results.length} of {runs.length} planned runs completed · {cancelledRunIds.current.size} cancelled · {runs.length - results.length - cancelledRunIds.current.size} unfinished.</p><p>Scores include completed runs only. Cancelled and unfinished runs have no score; this does not establish a complete strategy comparison.</p><a href="/history">Check every planned run in Audit History</a></UIAlert>}
      {failedRuns.length > 0 && <div className="partial-run-warning"><b>{failedRuns.length} condition{failedRuns.length === 1 ? '' : 's'} did not complete.</b><ul>{failedRuns.map((run) => <li key={run.runId}>{run.label}: {run.detail}</li>)}</ul><UIButton disabled={busy} onClick={retryFailedRuns}>{busy ? `Retrying ${runningLabel || 'run'}…` : 'Retry Failed Conditions'}</UIButton></div>}
      {results.length > 1 && <><Suspense fallback={<p className="chart-loading" role="status">Loading visual comparison charts…</p>}><ComparisonVisualizations runs={results} /></Suspense><ModelComparison runs={results} /><ExperimentStatistics runs={results} /></>}
      {results.map((item) => <UIPanel className="individual-report" key={item.result.run_id} open={results.length === 1}><UISummary>{item.label} detailed report</UISummary><ResultDashboard result={item.result} /><TargetMemoryTrace runId={item.result.run_id} /></UIPanel>)}
      <UIButton className="secondary" onClick={() => window.location.reload()}>Start New Audit</UIButton>
    </section>}
  </main>;
}
