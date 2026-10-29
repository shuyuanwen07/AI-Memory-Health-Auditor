import { INTAKE_KEY, loadIntakeRecovery, type IntakeRecovery } from '../services/intakeRecovery';
import { memoryStrategyLabel, modelDisplayName, friendlyText } from '../services/display';
import { parseAuditDraftSettings, type AuditDraftSettings } from '../services/auditDraftSettings';
import { ReviewedMethodComparison } from '../components/ReviewedMethodComparison';
import { ModelPicker } from '../components/ModelPicker';
import { TargetProfileEditor, defaultTargetProfile, supportsAnswerValidation, type TargetMemoryProfile } from "../components/TargetProfileEditor";
import { UIAlert } from '../components/ui';
import { UISelect, UIOption, UIInput, UIButton, UIPanel, UISummary, UICheckbox } from '../components/ui';
import type { ConversationMessage } from '../types/domain';
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import type { AgentExecution, AuditResult, AuditRun, ConversationInputMessage, ConversationSourceOrigin, Dimension, DimensionCoverage, DimensionCoveragePreview, Memory, MemoryMaintenancePolicy, MemoryReviewPatch, MemoryReviewReport, MemoryStrategy, ProviderOption, RetrievalMode, TargetMemoryWriterKind, TargetProvider, TestCase, TestReviewSuite, TestSuiteMode } from '../types/domain';
import { StepIndicator } from '../components/StepIndicator';
import { ResultDashboard } from '../components/ResultDashboard';
import { ConversationStep } from '../components/ConversationStep';
import { GroundTruthReview } from '../components/GroundTruthReview';
import { ModelComparison } from '../components/ModelComparison';
import { ExperimentStatistics } from '../components/ExperimentStatistics';
import { TestSuiteReview, hasDuplicateQuestions } from '../components/TestSuiteReview';
import { TargetMemoryTrace } from '../components/TargetMemoryTrace';
import presentationDemo from '../data/presentationDemo.json';
import presentationDemoUrl from '../data/presentationDemo.json?url';
import presentationDemoRaw from '../data/presentationDemo.json?raw';
import presentationSettings from '../data/presentationSettings.json';
import { saveBlob } from '../services/download';
import { ResearchResultsPage } from './ResearchResults';

const ComparisonVisualizations = lazy(() => import('../components/ResultVisualizations').then((module) => ({ default: module.ComparisonVisualizations })));

const sample = presentationDemo.messages.map(message => `[${message.role}] ${message.content}`).join('\n');
const DRAFT_KEY = 'mha-new-audit-draft-v1';
const REVIEW_KEY = 'mha-new-audit-review-v1';
type SavedReview = { conversationId: string; settings?: AuditDraftSettings | null };
function loadSavedReview(): SavedReview | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(REVIEW_KEY) ?? 'null');
    return typeof value?.conversationId === 'string' && value.conversationId.trim() ? { conversationId: value.conversationId, settings: parseAuditDraftSettings(value.settings) } : null;
  } catch { return null; }
}

type ConversationDraft = { text?: string; importedMessages?: ConversationInputMessage[] | null; consent?: boolean; sourceOrigin?: ConversationSourceOrigin };

function loadConversationDraft(): ConversationDraft {
  try {
    const saved = sessionStorage.getItem(DRAFT_KEY);
    return saved ? JSON.parse(saved) as ConversationDraft : {};
  } catch { return {}; }
}

type PreparedRun = { runId: string; label: string; groupLabel: string; experimentId: string; generationGroup: string; sharedAnswerSourceRunId?: string; audit?: AuditRun };
type CreationBatch = {
  experiments: Array<{ key: string; body: Record<string, unknown>; id?: string }>;
  conditions: Array<{ body: Record<string, unknown>; label: string; groupLabel: string; experimentKey: string; runId?: string; audit?: AuditRun }>;
};
type CompletedRun = { label: string; groupLabel: string; result: AuditResult; run?: AuditRun };
type FailedRun = { runId: string; label: string; detail: string };

const auditDimensions: Dimension[] = ['accuracy','freshness','conflict_resolution','appropriate_use'];
const strategies: Array<{ value: MemoryStrategy; label: string; description: string }> = [
  { value: 'no_memory', label: memoryStrategyLabel('no_memory'), description: 'Reference baseline that gives the target AI no retrieved long-term memory.' },
  { value: 'full_context', label: memoryStrategyLabel('full_context'), description: 'Reference baseline that replays all active memories without ranking.' },
  { value: 'weak_first_hit', label: memoryStrategyLabel('weak_first_hit'), description: 'Uses only the first related memory, without resolving updates or conflicts.' },
  { value: 'strong_rule_based', label: memoryStrategyLabel('strong_rule_based'), description: 'Prioritises contextual requirements, updates, stable facts and superseded records.' },
  { value: 'strong_score_based', label: memoryStrategyLabel('strong_score_based'), description: 'Ranks memories with transparent relevance, freshness and context weights.' },
  { value: 'scope_aware', label: memoryStrategyLabel('scope_aware'), description: 'Prioritises project requirements for task prompts and uses profile or preferences only when relevant.' },
  { value: 'temporal_importance', label: memoryStrategyLabel('temporal_importance'), description: 'Ranks source-message recency and durable task importance using a frozen, explainable relative chronology.' },
];

export function NewAudit() {
  const restoredDraft = loadConversationDraft();
  const [step, setStep] = useState(0);
  const [text, setText] = useState(restoredDraft.text ?? sample);
  const [sourceMessages, setSourceMessages] = useState<ConversationMessage[]>([]);
  const [importedMessages, setImportedMessages] = useState<ConversationInputMessage[] | null>(restoredDraft.importedMessages || (restoredDraft.text !== undefined ? null : presentationDemo.messages));
  const [consent, setConsent] = useState(Boolean(restoredDraft.consent));
  const [sourceOrigin, setSourceOrigin] = useState<ConversationSourceOrigin>(restoredDraft.sourceOrigin ?? (restoredDraft.text !== undefined ? 'unknown' : 'synthetic'));
  const [conversationId, setConversationId] = useState('');
  const [memories, setMemories] = useState<Memory[]>([]);
  const [memoryReview, setMemoryReview] = useState<MemoryReviewReport | null>(null);
  const [agentExecutions, setAgentExecutions] = useState<AgentExecution[]>([]);
  const [selectedStrategies, setSelectedStrategies] = useState<MemoryStrategy[]>(['weak_first_hit']);
  const [targetProviders, setTargetProviders] = useState<TargetProvider[]>(['rule_based']);
  const [targetModels, setTargetModels] = useState<Partial<Record<TargetProvider, string>>>({});
  const [pipelineProvider, setPipelineProvider] = useState<TargetProvider>('rule_based');
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>('agent');
  const [pipelineModel, setPipelineModel] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProviderOption[]>([]);
  const [providerStatus, setProviderStatus] = useState<'loading'|'ready'|'error'>('loading');
  const providersInitialised = useRef(false);
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
  const [experimentIds, setExperimentIds] = useState<string[]>([]);
  const [compareAuditors, setCompareAuditors] = useState(false);
  const creationBatch = useRef<CreationBatch | null>(null);
  const [creationPending, setCreationPending] = useState(false);
  const [results, setResults] = useState<CompletedRun[]>([]);
  const [failedRuns, setFailedRuns] = useState<FailedRun[]>([]);
  const [reviewTests, setReviewTests] = useState<TestCase[] | null>(null);
  const [dimensionCoverage, setDimensionCoverage] = useState<Record<string, DimensionCoverage[]>>({});
  const [coveragePreview, setCoveragePreview] = useState<DimensionCoveragePreview | null>(null);
  const [coveragePreviewStatus, setCoveragePreviewStatus] = useState<'idle'|'loading'|'ready'|'error'>('idle');
  const [coveragePreviewError, setCoveragePreviewError] = useState('');
  const [questionCountNote, setQuestionCountNote] = useState('');
  const [continueGenerationRuns, setContinueGenerationRuns] = useState<string[]>([]);
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
  const [savedReview, setSavedReview] = useState(loadSavedReview);
  const [savedIntake, setSavedIntake] = useState(loadIntakeRecovery);
  const restoringSettings = useRef(Boolean(savedReview?.settings));
  const [recoveryNotice, setRecoveryNotice] = useState('');
  const conversationSubmissionInProgress = useRef(false);

  const loadProviders = useCallback(async () => {
    setProviderStatus('loading');
    try {
      const items = await api.targetProviders();
      if (!items.length) throw new Error('No services returned');
      const openRouter = items.find((item) => item.provider === 'openrouter');
      const initialAgent = openRouter?.configured
        ? openRouter
        : items.find((item) => item.provider !== 'rule_based' && item.configured);
      // Legacy providers stay readable in saved runs; new cloud calls use OpenRouter.
      setProviders(openRouter ? items.filter((item) => item.provider === 'openrouter' || item.provider === 'rule_based' || item.provider === 'ollama') : items);
      if (initialAgent && !restoringSettings.current && !providersInitialised.current) {
        setTargetProviders([initialAgent.provider]);
        setPipelineProvider(initialAgent.provider);
        setCompareAuditors(true);
        setRetrievalMode('agent');
      }
      if (!restoringSettings.current && !items.some((item) => item.provider !== 'rule_based' && item.configured)) {
        setRetrievalMode('fixed');
      }
      providersInitialised.current=true;
      setProviderStatus('ready');
    } catch { setProviderStatus('error'); }
  }, []);
  useEffect(() => {
    (api.targetSystems?.() ?? Promise.resolve([])).then(setSystems).catch(()=>setSystems([]));
    void loadProviders();
  }, [loadProviders]);
  useEffect(() => {
    try {
      if (step < 3 && consent) sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ text, importedMessages, consent, sourceOrigin }));
      else sessionStorage.removeItem(DRAFT_KEY);
    } catch { /* Submitted source and review decisions remain on the server. */ }
  }, [consent, importedMessages, sourceOrigin, step, text]);

  useEffect(() => {
    if (!conversationId || ![1,2].includes(step) || creationBatch.current || !providers.length) return;
    const frozenModels = {...targetModels};
    for (const provider of providers) if(targetProviders.includes(provider.provider) && frozenModels[provider.provider] === undefined) frozenModels[provider.provider]=provider.default_model;
    const pipeline = providers.find(item=>item.provider===pipelineProvider);
    const sharedModel=pipelineModel??pipeline?.default_pipeline_model??pipeline?.default_model??null;
    const settings: AuditDraftSettings = {selectedStrategies,targetProviders,targetModels:frozenModels,pipelineProvider,evaluatorProvider:pipelineProvider,
      semanticReviewProvider:'same_as_generator',retrievalMode,retrievalProvider:'automatic',retrievalModel:null,
      pipelineModel:sharedModel,semanticReviewModel:null,evaluatorModel:sharedModel,
      budget,repetitions,suiteMode,maintenancePolicy,targetMemoryCapacity,targetMemoryWriter,targetProfile,targetSystem,compareAuditors};
    try { sessionStorage.setItem(REVIEW_KEY,JSON.stringify({conversationId,settings})); }
    catch { setRecoveryNotice('Review decisions remain saved, but this browser cannot keep the audit settings. Keep this page open until the audit is created.'); }
  },[conversationId,step,providers,selectedStrategies,targetProviders,targetModels,pipelineProvider,retrievalMode,pipelineModel,budget,repetitions,suiteMode,maintenancePolicy,targetMemoryCapacity,targetMemoryWriter,targetProfile,targetSystem,compareAuditors]);

  const clearDraft = () => {
    sessionStorage.removeItem(DRAFT_KEY);
    setText(''); setImportedMessages(null); setConsent(false); setSourceOrigin('unknown'); setError('');
  };

  const act = async (operation: () => Promise<void>, propagateError = false) => {
    setBusy(true);
    setError('');
    try { await operation(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Something went wrong.'); if (propagateError) throw cause; }
    finally { setBusy(false); }
  };

  const saveIntake = (checkpoint:IntakeRecovery) => {
    setSavedIntake(checkpoint);
    try {sessionStorage.setItem(INTAKE_KEY,JSON.stringify(checkpoint));}
    catch {setRecoveryNotice('Your submission can be retried while this page stays open, but this browser could not save a refresh recovery link.');}
  };

  const submitConversation = () => {
    // Lock synchronously before React has a chance to rerender and disable the button.
    if (conversationSubmissionInProgress.current) return;
    conversationSubmissionInProgress.current = true;
    void act(async () => {
      if (providerStatus!=='ready') throw new Error('Load the available model services before continuing.');
      const selectedPipeline = providers.find(item=>item.provider===pipelineProvider);
      const model=(pipelineModel ?? selectedPipeline?.default_pipeline_model ?? selectedPipeline?.default_model)?.trim();
      if (!savedIntake && pipelineProvider!=='rule_based' && !model) throw new Error('Choose the shared Agent model before continuing.');
      const checkpoint:IntakeRecovery=savedIntake ?? {requestKey:crypto.randomUUID(),text,messages:importedMessages,sourceOrigin,
        provider:pipelineProvider,model:pipelineProvider==='rule_based'?null:model!};
      // Save the request identity before sending, including the original source and extractor.
      saveIntake(checkpoint);
      const conversation=checkpoint.conversationId ? await api.getConversation(checkpoint.conversationId)
        : await api.createConversation(true,checkpoint.text,checkpoint.messages,checkpoint.requestKey,checkpoint.sourceOrigin ?? 'unknown');
      const acknowledged={...checkpoint,conversationId:conversation.conversation_id};
      saveIntake(acknowledged);
      if (checkpoint.conversationId && (await api.audits()).some(run=>run.conversation_id===conversation.conversation_id)) {
        setRecoveryNotice('An audit already uses this conversation. Continue it in Audit History; its reference memories are frozen.');return;
      }
      setConversationId(conversation.conversation_id);
      setSourceOrigin(conversation.source_origin ?? checkpoint.sourceOrigin ?? 'unknown');
      setSourceMessages(conversation.messages ?? []);
      // Completed extraction, including zero candidates, is read rather than requested again.
      const reviewedMemories = conversation.extraction_provenance && conversation.extraction_provenance.status !== 'failed'
        ? await api.conversationMemories(conversation.conversation_id)
        : await api.extract(conversation.conversation_id,checkpoint.provider,checkpoint.model ?? undefined);
      const updatedConversation = await api.getConversation(conversation.conversation_id);
      setMemories(reviewedMemories);
      setMemoryReview(updatedConversation.extraction_provenance?.memory_review ?? null);
      setAgentExecutions(await api.conversationAgentExecutions(conversation.conversation_id));
      try {
        sessionStorage.setItem(REVIEW_KEY,JSON.stringify({conversationId:conversation.conversation_id}));
        sessionStorage.removeItem(INTAKE_KEY);setSavedIntake(null);
      } catch { setRecoveryNotice('Your memories are saved by the audit service. Keep this page open if the browser cannot save a resume link.'); }
      setStep(1);
    }).finally(() => { conversationSubmissionInProgress.current = false; });
  };

  const resumeReview = () => act(async () => {
    if (!savedReview) return;
    // Read current saved decisions; do not rerun extraction or restore stale labels.
    const [conversation, reviewedMemories, audits, executions] = await Promise.all([
      api.getConversation(savedReview.conversationId), api.conversationMemories(savedReview.conversationId), api.audits(),
      api.conversationAgentExecutions(savedReview.conversationId),
    ]);
    if (audits.some(run => run.conversation_id === conversation.conversation_id)) {
      setRecoveryNotice('An audit already uses this conversation. Open Audit History to continue it; its reference memories are frozen.');
      return;
    }
    setConversationId(conversation.conversation_id);
    setSourceOrigin(conversation.source_origin ?? 'unknown');
    setSourceMessages(conversation.messages);
    setMemories(reviewedMemories);
    setMemoryReview(conversation.extraction_provenance?.memory_review ?? null);
    setAgentExecutions(executions);
    const settings=savedReview.settings;
    if(settings){
      setSelectedStrategies(settings.selectedStrategies);setTargetProviders(settings.targetProviders);setTargetModels(settings.targetModels);
      setPipelineProvider(settings.pipelineProvider);
      setRetrievalMode(settings.pipelineProvider === 'rule_based' ? 'fixed' : settings.retrievalMode);
      setPipelineModel(settings.pipelineModel);
      setBudget(settings.budget);setRepetitions(settings.repetitions);setSuiteMode(settings.suiteMode);
      setMaintenancePolicy(settings.maintenancePolicy);setTargetMemoryCapacity(settings.targetMemoryCapacity);
      setTargetMemoryWriter(settings.targetMemoryWriter);setTargetProfile(settings.targetProfile);
      setTargetSystem(settings.targetSystem);setCompareAuditors(settings.compareAuditors);
    }
    setSavedReview(null);
    setRecoveryNotice(settings ? 'Saved review and audit settings restored. Your models, strategies and answer limits are preserved. Check them after confirming the review; no model request has been sent.' : 'Saved review restored. Accepted, rejected and edited memories are preserved. Audit settings were not available; choose them again after confirming the review.');
    setStep(1);
  });

  const startFresh = () => {
    sessionStorage.removeItem(REVIEW_KEY);sessionStorage.removeItem(INTAKE_KEY);setSavedIntake(null);
    restoringSettings.current=false;
    if(providers.some(item=>item.provider==='openrouter'&&item.configured)){
      setTargetProviders(['openrouter']);setPipelineProvider('openrouter');setCompareAuditors(true);
      setTargetMemoryWriter('rule_based');
    }
    setSavedReview(null); setRecoveryNotice(''); setError('');
  };

  const startSeparateAudit = () => {
    if(busy)return;
    startFresh();clearDraft();setStep(0);setConversationId('');setMemories([]);setMemoryReview(null);setAgentExecutions([]);setSourceMessages([]);
    setRuns([]);setExperimentIds([]);setResults([]);setFailedRuns([]);setReviewTests(null);setDimensionCoverage({});setQuestionCountNote('');setContinueGenerationRuns([]);
    creationBatch.current=null;setCreationPending(false);setRunningLabel('');setRunningRunId('');setRunningStage('idle');
    setQueueStopped(false);setEntireExperimentCancelled(false);cancellationRequested.current=false;
    entireExperimentCancelledRef.current=false;cancelledRunIds.current.clear();completedRunIds.current.clear();
  };

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
  const strategyCount = retrievalMode === 'agent' ? 1 : selectedStrategies.length;
  const answerValidationAvailable = selectedModels.length > 0 && selectedModels.every(({provider,models}) =>
    models.length > 0 && models.every(model=>supportsAnswerValidation(provider.provider,model,targetSystem)));
  const answerValidationError = targetProfile.answer_validation === 'source_grounding' && !answerValidationAvailable
    ? 'Answer fact checking requires controlled GPT-6 Luna through OpenRouter for every selected target. Turn it off or change the targets.' : '';
  const conditionCount = selectedModels.reduce((total, item) => total + item.models.length, 0) * strategyCount * repetitions * (compareAuditors ? 3 : 1);
  const modelSelectionError = selectedModels.some((item) => item.models.length === 0)
    ? `Select at least one model for ${selectedModels.filter((item) => item.models.length === 0).map((item) => item.provider.label).join(', ')}, or deselect that service above.`
    : selectedModels.some((item) => item.models.length > 8)
      ? 'Select up to eight models per service.'
      : conditionCount > 64 ? 'This comparison exceeds 64 runs. Reduce models, strategies or repetitions.' : '';
  const pipelineProviders = providers;
  const selectedPipeline = pipelineProviders.find((item) => item.provider === pipelineProvider);
  const effectiveRetrievalProvider = pipelineProvider === 'rule_based' ? undefined : pipelineProvider;
  const selectedEvaluator = providers.find((item) => item.provider === pipelineProvider);
  const effectiveSemanticReviewProvider = pipelineProvider;
  const effectiveJudgeProvider = pipelineProvider;
  const effectiveJudge = selectedPipeline;
  const dimensionQuotas = Object.fromEntries(auditDimensions.map((dimension,index) => [
    dimension, coveragePreview?.dimensions.find(item => item.dimension === dimension)?.required_question_count
      ?? (budget < auditDimensions.length
        ? 1
        : Math.floor(budget / auditDimensions.length) + Number(index < budget % auditDimensions.length)),
  ])) as Record<Dimension,number>;
  const coverageRequired = pipelineProvider !== 'rule_based' && (compareAuditors || suiteMode === 'behavioural');
  const dimensionSlots = Object.fromEntries(auditDimensions.map(dimension => [
    dimension,
    coveragePreview?.dimensions.find(item => item.dimension === dimension)?.available_question_count ?? 0,
  ])) as Record<Dimension,number>;
  const totalDimensionSlots = Object.values(dimensionSlots).reduce((total, count) => total + count, 0);
  const dimensionShortages = coveragePreviewStatus === 'ready'
    ? coveragePreview?.dimensions.filter(item => item.available_question_count < item.required_question_count) ?? []
    : [];
  const coverageBlocked = coverageRequired && (
    coveragePreviewStatus !== 'ready' || !coveragePreview?.minimum_met
  );

  useEffect(() => {
    if (step !== 2 || !coverageRequired || !conversationId) {
      setCoveragePreview(null);
      setCoveragePreviewStatus('idle');
      setCoveragePreviewError('');
      return;
    }
    let cancelled = false;
    setCoveragePreview(null);
    setCoveragePreviewStatus('loading');
    setCoveragePreviewError('');
    void api.coveragePreview(conversationId, budget).then((preview) => {
      if (cancelled) return;
      setCoveragePreview(preview);
      setCoveragePreviewStatus('ready');
    }).catch((cause: unknown) => {
      if (cancelled) return;
      setCoveragePreviewError(cause instanceof Error ? cause.message : 'Unable to check evidence coverage.');
      setCoveragePreviewStatus('error');
    });
    return () => { cancelled = true; };
  }, [step, coverageRequired, conversationId, budget]);
  // Null means use the displayed configured default; an explicit blank is not a default.
  const preparationModel = (pipelineModel ?? selectedPipeline?.default_pipeline_model ?? selectedPipeline?.default_model)?.trim();
  const semanticReviewerModel = preparationModel;
  const judgeModel = pipelineProvider === 'rule_based'
    ? (effectiveJudge?.default_evaluator_model ?? effectiveJudge?.default_model)?.trim()
    : preparationModel;
  const retrievalAgentModel = preparationModel;
  const retrievalAgentError = retrievalMode === 'agent'
    ? targetSystem === 'external-http'
      ? 'Agent retrieval needs the controlled-memory target system.'
      : !effectiveRetrievalProvider || !selectedPipeline?.configured || !retrievalAgentModel
        ? 'Choose the shared Agent model before starting.' : ''
    : '';
  const auditModelError = pipelineProvider !== 'rule_based' && !preparationModel
    ? 'Choose the shared Agent model before starting.'
    : effectiveJudgeProvider !== 'rule_based' && !judgeModel
      ? 'Choose the shared Agent model before starting.' : retrievalAgentError;
  const toggleTarget = (option: ProviderOption) => {
    if (!option.configured) return;
    // Re-enabling a service starts with its configured model, even if its
    // previous selection was cleared. Clearing an active picker stays explicit.
    if (!targetProviders.includes(option.provider) && !targetModels[option.provider]?.trim()) {
      setTargetModels((current) => ({ ...current, [option.provider]: option.default_model }));
    }
    setTargetProviders((current) => current.includes(option.provider)
      ? current.filter((provider) => provider !== option.provider)
      : [...current, option.provider]);
  };
  const selectSharedAgentProvider = (provider: TargetProvider) => {
    setPipelineProvider(provider);
    setPipelineModel(null);
    setRetrievalMode(provider === 'rule_based' ? 'fixed' : 'agent');
    if (provider === 'rule_based' && targetMemoryWriter === 'llm_structured') setTargetMemoryWriter('rule_based');
  };
  const toggleStrategy = (strategy: MemoryStrategy) => setSelectedStrategies((current) => current.includes(strategy)
    ? current.filter((value) => value !== strategy)
    : [...current, strategy]);

  const start = () => act(async () => {
    if (providerStatus!=='ready' && !creationBatch.current) throw new Error('Load the available model services before starting an audit.');
    if (!creationBatch.current && (modelSelectionError || auditModelError || answerValidationError)) throw new Error(modelSelectionError || auditModelError || answerValidationError);
    const generationService = selectedPipeline?.configured && selectedPipeline.provider !== 'rule_based' ? selectedPipeline : undefined;
    const strategiesForRun: MemoryStrategy[] = retrievalMode === 'agent'
      ? ['strong_rule_based']
      : selectedStrategies;
    if (compareAuditors && !generationService) throw new Error('Three-method comparison needs a configured model service.');
    if (!creationBatch.current) {
      const preparationProvider = compareAuditors ? generationService!.provider : pipelineProvider;
      const judgeProvider = pipelineProvider;
      const selectedSemanticProvider = effectiveSemanticReviewProvider;
      const selectedSemanticModel = semanticReviewerModel ?? preparationModel ?? 'rule-based-v2';
      const methods = compareAuditors ? [
        { key: 'rules', name: 'Rule tests + rule review', pipeline: 'rule_based' as TargetProvider, model: 'rule-based-v2', semantic: 'rule_based' as TargetProvider, semanticModel: 'rule-based-v1', evaluator: 'rule_based' as TargetProvider, judge: 'rule-based-v36' },
        { key: 'model', name: 'Model tests + rule review', pipeline: preparationProvider, model: preparationModel, semantic: selectedSemanticProvider, semanticModel: selectedSemanticModel, evaluator: 'rule_based' as TargetProvider, judge: 'rule-based-v36' },
        { key: 'model', name: 'Model tests + hybrid review', pipeline: preparationProvider, model: preparationModel, semantic: selectedSemanticProvider, semanticModel: selectedSemanticModel, evaluator: judgeProvider, judge: judgeModel },
      ] : [{ key: 'custom', name: '', pipeline: pipelineProvider, model: preparationModel, semantic: selectedSemanticProvider, semanticModel: selectedSemanticModel, evaluator: pipelineProvider, judge: judgeModel }];
      const auditorComparisonId = compareAuditors ? crypto.randomUUID() : undefined;
      const experiments = [...new Map(methods.map(method => [method.key, {
        key: method.key, body: {
          creation_request_key: crypto.randomUUID(), conversation_id: conversationId,
          label: `${compareAuditors ? 'Audit method comparison' : retrievalMode === 'agent' ? 'Memory retrieval comparison' : 'Memory strategy comparison'} · ${method.key} · ${new Date().toISOString()}`,
          test_suite_configuration: {
            test_budget: budget, random_seed: 42, prompt_template_version: 'rule-based-v4',
            pipeline_provider: method.pipeline, pipeline_model: method.model,
            semantic_review_provider: method.semantic, semantic_review_model: method.semanticModel,
            evaluator_provider: method.evaluator, evaluator_model: method.judge,
            compare_evaluators: compareAuditors && method.key === 'model', auditor_comparison_id: auditorComparisonId,
            suite_mode: compareAuditors ? 'behavioural' : suiteMode,
          },
        },
      }])).values()];
      const conditions = selectedModels.flatMap(({ provider, models }) => models.flatMap(model => strategiesForRun.flatMap(strategy =>
        methods.flatMap(method => Array.from({ length: repetitions }, (_, index) => {
          const strategyLabel = retrievalMode === 'agent'
            ? 'AI retrieval Agent'
            : strategies.find(item => item.value === strategy)?.label ?? strategy;
          const groupLabel = `${provider.label} · ${model} · ${strategyLabel}${method.name ? ` · ${method.name}` : ''}`;
          return { experimentKey: method.key, groupLabel, label: repetitions > 1 ? `${groupLabel} · Run ${index + 1}` : groupLabel, body: {
            creation_request_key: crypto.randomUUID(), conversation_id: conversationId,
            target_configuration: strategy === 'weak_first_hit' ? 'weak' : 'strong', memory_strategy: strategy,
            memory_maintenance_policy: maintenancePolicy, target_memory_capacity: targetMemoryCapacity,
            target_memory_writer: targetMemoryWriter, target_memory_profile: structuredClone(targetProfile),
            target_system_adapter: targetSystem, provider: provider.provider, model,
            pipeline_provider: method.pipeline, pipeline_model: method.model,
            semantic_review_provider: method.semantic, semantic_review_model: method.semanticModel,
            retrieval_mode: retrievalMode,
            ...(retrievalMode === 'agent' && effectiveRetrievalProvider && retrievalAgentModel
              ? { retrieval_provider: effectiveRetrievalProvider, retrieval_model: retrievalAgentModel }
              : {}),
            evaluator_provider: method.evaluator, evaluator_model: method.judge,
            temperature: 0, random_seed: 42, test_budget: budget, prompt_template_version: 'rule-based-v4',
          } };
        }))
      )));
      creationBatch.current = { experiments, conditions };
      // Once creation starts, saved audit records are recovered through History.
      try { sessionStorage.removeItem(REVIEW_KEY); } catch { /* History is still available. */ }
      setCreationPending(true);
    }
    const batch = creationBatch.current;
    for (const experiment of batch.experiments) {
      if (!experiment.id) experiment.id = (await api.createExperiment(experiment.body)).experiment_id;
    }
    setExperimentIds(batch.experiments.map(item => item.id!));
    setQueueStopped(false); setEntireExperimentCancelled(false);
    cancellationRequested.current = false; entireExperimentCancelledRef.current = false;
    cancelledRunIds.current.clear(); completedRunIds.current.clear();
    for (const condition of batch.conditions) {
      const experiment = batch.experiments.find(item => item.key === condition.experimentKey)!;
      const shared = condition.groupLabel.endsWith('Model tests + hybrid review')
        ? batch.conditions.filter(item => item.groupLabel === condition.groupLabel.replace('Model tests + hybrid review','Model tests + rule review'))[batch.conditions.filter(item => item.groupLabel === condition.groupLabel).indexOf(condition)] : undefined;
      if (!condition.runId) {
        condition.audit = await api.createAudit({ ...condition.body, experiment_id: experiment.id,
          ...(shared?.runId ? {shared_answer_source_run_id:shared.runId} : {}) });
        condition.runId = condition.audit.run_id;
      }
    }
    setRuns(batch.conditions.map(condition => {
      const shared = condition.groupLabel.endsWith('Model tests + hybrid review')
        ? batch.conditions.filter(item => item.groupLabel === condition.groupLabel.replace('Model tests + hybrid review','Model tests + rule review'))[batch.conditions.filter(item => item.groupLabel === condition.groupLabel).indexOf(condition)]
        : undefined;
      return {runId: condition.runId!, label: condition.label, groupLabel: condition.groupLabel,
        experimentId: batch.experiments.find(item => item.key === condition.experimentKey)!.id!, generationGroup: condition.experimentKey,
        sharedAnswerSourceRunId: shared?.runId, audit: condition.audit};
    }));
    setCreationPending(false); setStep(3);
  });

  const prepareTests = () => act(async () => {
    if (!runs[0]) throw new Error('No audit condition was created.');
    const canonicalRuns = [...new Map(runs.map(run => [run.generationGroup, run])).values()];
    const questions: TestCase[] = [];
    const coverageByRun: Record<string, DimensionCoverage[]> = {};
    const countNotes: string[] = [];
    const continuableRuns: string[] = [];
    for (const run of canonicalRuns) {
      setRunningLabel(`Preparing ${run.generationGroup === 'rules' || (run.generationGroup === 'custom' && pipelineProvider === 'rule_based') ? 'rule' : 'model'} test suite`);
      await api.generate(run.runId);
      const suite = await api.testReview(run.runId);
      questions.push(...suite.tests);
      coverageByRun[suite.canonical_run_id] = suite.dimension_coverage ?? [];
      if (suite.can_continue_generation) {
        continuableRuns.push(suite.canonical_run_id);
        countNotes.push(
          `The saved suite has ${suite.generated_test_count ?? suite.tests.length} of ${suite.requested_test_count ?? 'the requested'} questions. This earlier suite can be regenerated once with the target-count Agent before you review it.`
        );
      }
      if (suite.count_target_met === false && suite.requested_test_count != null) {
        countNotes.push(
          `The Agent generated ${suite.generated_test_count ?? suite.tests.length} of ${suite.requested_test_count} requested questions. `
          + (suite.quantity_shortfall_reason ?? 'The confirmed evidence did not support more distinct questions.')
        );
      }
    }
    setReviewTests(questions); setDimensionCoverage(coverageByRun); setQuestionCountNote(countNotes.join(' ')); setContinueGenerationRuns(continuableRuns); setRunningLabel('');
  });

  const continueGeneration = (runId: string) => act(async () => {
    setRunningLabel('Generating additional distinct questions');
    const suite: TestReviewSuite = await api.continueGeneration(runId);
    setReviewTests((items) => [...(items ?? []).filter(test => test.run_id !== suite.canonical_run_id), ...suite.tests]);
    setDimensionCoverage((items) => ({...items, [suite.canonical_run_id]: suite.dimension_coverage ?? []}));
    setQuestionCountNote(suite.count_target_met === false
      ? `The Agent generated ${suite.generated_test_count ?? suite.tests.length} of ${suite.requested_test_count ?? 'the requested'} questions. ${suite.quantity_shortfall_reason ?? 'The confirmed evidence did not support more distinct questions.'}`
      : 'The Agent generated the requested number of distinct, evidence-backed questions. Review them before running the audit.');
    setContinueGenerationRuns([]);
    setRunningLabel('');
  });

  const reviewQuestionScopes = (runId: string) => act(async () => {
    setRunningLabel('Checking questions against the source');
    const suite = await api.reviewQuestionScopes(runId);
    setReviewTests((items) => [...(items ?? []).filter(test => test.run_id !== suite.canonical_run_id), ...suite.tests]);
    setDimensionCoverage((items) => ({...items, [suite.canonical_run_id]: suite.dimension_coverage ?? []}));
    setRunningLabel('');
  });

  const reviewTest = (test: TestCase, decision: 'accepted' | 'rejected', note?:string) => act(async () => {
    if (!runs[0]) return;
    const changed = await (note?api.reviewTest(test.run_id,test.test_id,decision,note):api.reviewTest(test.run_id,test.test_id,decision));
    setReviewTests((items) => items?.map((item) => item.test_id === changed.test_id ? changed : item) ?? null);
  });
  const acceptAllTests = (tests: TestCase[]) => act(async () => {
    for (const test of tests) {
      const changed = await api.reviewTest(test.run_id, test.test_id, 'accepted');
      setReviewTests((items) => items?.map((item) =>
        item.run_id === changed.run_id && item.test_id === changed.test_id ? changed : item,
      ) ?? null);
    }
  });
  const regenerateTest = (test: TestCase) => act(async () => {
    if (!runs[0]) return;
    const changed = await api.regenerateTest(test.run_id, test.test_id);
    setReviewTests((items) => items?.map((item) => item.test_id === changed.test_id ? changed : item) ?? null);
  });
  const remainingConditions = runs.filter((run) => !cancelledRunIds.current.has(run.runId) && !completedRunIds.current.has(run.runId));
  const readyForExecution = Boolean(reviewTests?.length) && ![...new Set(reviewTests!.map(test => test.run_id))].some(runId => hasDuplicateQuestions(reviewTests!.filter(test => test.run_id === runId))) && reviewTests!.every((test) => test.quality_status === 'accepted');

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
        if (run.sharedAnswerSourceRunId) await api.reuseAnswers(run.runId, run.sharedAnswerSourceRunId);
        else await api.execute(run.runId);
        setRunningStage('evaluate');
        await api.evaluate(run.runId);
        completed.push({ label: run.label, groupLabel: run.groupLabel, result: await api.results(run.runId), run: run.audit });
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
    if (!completedRunIds.current.size) setError('No condition has completed yet. Check saved progress and resume below.');
    setStep(4);
  });

  const retryFailedRuns = () => act(async () => {
    const recovered: CompletedRun[] = [];
    const stillFailed: FailedRun[] = [];
    for (const failed of failedRuns) {
      setRunningLabel(failed.label); setRunningRunId(failed.runId);
      try {
        setRunningStage('recover');
        const plan = await api.retryPlan(failed.runId);
        if (plan.busy) throw new Error('Work is still running in the background. Check progress again after it finishes; no new model request was sent.');
        if (plan.resume_blocked_reason) throw new Error(plan.resume_blocked_reason);
        let audit = await api.retry(failed.runId);
        // Recovery saves one durable stage at a time. Continue only while
        // that stage advanced, up to generation, execution and evaluation.
        for (let stage = 1; stage < 3 && audit.status !== 'COMPLETED'; stage++) {
          if (!['TESTS_GENERATED', 'TESTS_EXECUTED'].includes(audit.status)) break;
          const previousStatus = audit.status;
          audit = await api.retry(failed.runId);
          if (audit.status === previousStatus) break;
        }
        if (audit.status !== 'COMPLETED') throw new Error('This condition still needs attention. Inspect its saved progress in Audit History before retrying.');
        const groupLabel = runs.find((run) => run.runId === failed.runId)?.groupLabel ?? failed.label;
        recovered.push({ label: failed.label, groupLabel, result: await api.results(failed.runId), run: runs.find(run => run.runId === failed.runId)?.audit });
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
    if (!experimentIds.length) return;
    try {
      cancellationRequested.current = true;
      for (const id of experimentIds) {
        await api.cancelExperiment(id);
        for (const run of runs) if (run.experimentId === id && !completedRunIds.current.has(run.runId)) cancelledRunIds.current.add(run.runId);
      }
      setEntireExperimentCancelled(true); entireExperimentCancelledRef.current = true;
      for (const run of runs) if (!completedRunIds.current.has(run.runId)) cancelledRunIds.current.add(run.runId);
      setError('The comparison was cancelled. Completed conditions remain available in Audit History.');
    } catch (cause) {
      setEntireExperimentCancelled(false);
      entireExperimentCancelledRef.current = false;
      // Keep the queue stopped after partial cancellation; terminal conditions
      // remain terminal and are skipped if the remaining groups are resumed.
      setQueueStopped(true);
      setError(`Cancellation was only partially confirmed. Confirmed cancelled conditions stay excluded. ${cause instanceof Error ? cause.message : 'Check Audit History before continuing.'}`);
    }
  };

  return <main className="workflow">
    <StepIndicator current={step} />
    {step < 3 && providerStatus==='loading' && <UIAlert role="status" aria-label="Model service availability">Loading available model services. You can prepare your conversation while we check the configuration.</UIAlert>}
    {step < 3 && providerStatus==='error' && <UIAlert role="alert"><p>We could not load the available model services. Your conversation and saved settings are preserved. Retry before submitting or starting an audit.</p><UIButton disabled={busy} onClick={()=>void loadProviders()}>Retry loading services</UIButton></UIAlert>}
    {error && <UIAlert role="alert" aria-live="assertive" className="alert">{step===0&&savedIntake?'This saved submission did not finish: ':''}{friendlyText(error)}</UIAlert>}
    {recoveryNotice && step < 3 && <UIAlert role="status">{recoveryNotice}</UIAlert>}
    {step === 0 && savedReview && <section aria-label="Unfinished memory review">
      <h1>Continue your saved memory review</h1>
      <p>Your previous conversation and review decisions are saved. Continue reviewing without extracting memories again.</p>
      <UIButton disabled={busy} onClick={resumeReview}>{busy ? 'Restoring review…' : 'Resume saved review'}</UIButton>
      <UIButton className="secondary" disabled={busy} onClick={startFresh}>Start a new conversation</UIButton>
      <p>Starting a new conversation leaves the previous saved data unchanged. This resume link is available in this browser tab until the audit is created.</p>
      <a href="/history">Open Audit History</a>
    </section>}
    {step === 0 && !savedReview && savedIntake && <section aria-label="Unfinished conversation submission">
      <h1>{busy ? 'Preparing your memory review' : 'Previous unfinished submission'}</h1>
      <p>This is a saved submission from this browser tab. Opening this page does not start a new extraction. Continue it below, or start a new conversation.</p>
      <UIPanel><UISummary>View the saved conversation</UISummary><p style={{whiteSpace:'pre-wrap'}}>{savedIntake.text}</p></UIPanel>
      <p><b>Extraction service:</b> {providers.find(item=>item.provider===savedIntake.provider)?.label ?? 'Previously selected service'} · <b>Extraction model:</b> {savedIntake.model ? modelDisplayName(savedIntake.model) : 'Rule-based extraction'}</p>
      {providers.filter(item => item.provider === 'openrouter' && item.configured
        && (savedIntake.provider !== 'openrouter' || savedIntake.model !== (item.default_pipeline_model ?? item.default_model))).map(item =>
        <UIButton key={item.provider} className="secondary" disabled={busy || providerStatus!=='ready'} onClick={() => {
          const nextModel=item.default_pipeline_model ?? item.default_model;
          saveIntake({...savedIntake,provider:'openrouter',model:nextModel});
          setPipelineProvider('openrouter');setPipelineModel(nextModel);setError('');
          setRecoveryNotice('The next extraction will use '+modelDisplayName(nextModel)+'. Continue below to resume the saved conversation.');
        }}>Use {modelDisplayName(item.default_pipeline_model ?? item.default_model)} for the next extraction</UIButton>)}
      <UIButton disabled={busy || providerStatus!=='ready'} onClick={submitConversation}>{busy ? 'Checking your submission…' : 'Continue saved submission'}</UIButton>
      <UIButton className="secondary" disabled={busy} onClick={startFresh}>Start a new conversation</UIButton>
      <p>Continuing may retry the selected extraction model. Starting new keeps previously saved server data. Neither action requests target answers at this step.</p>
      <a href="/history">Open Audit History</a>
    </section>}
    {step === 0 && !savedReview && !savedIntake && <>{providerStatus==='ready' && <><label>Shared Agent service<UISelect aria-label="Shared Agent service" value={pipelineProvider} disabled={busy} onChange={(event) => selectSharedAgentProvider(event.target.value as TargetProvider)}>{pipelineProviders.map((item) => <UIOption key={item.provider} value={item.provider} disabled={!item.configured}>{item.label}{item.configured ? '' : ' — unavailable'}</UIOption>)}</UISelect></label>{pipelineProvider !== 'rule_based' && <label>Shared Agent model<ModelPicker label="Shared Agent model" provider={pipelineProvider} defaultModel={selectedPipeline?.default_pipeline_model ?? selectedPipeline?.default_model} value={pipelineModel ?? selectedPipeline?.default_pipeline_model ?? selectedPipeline?.default_model ?? ''} onChange={setPipelineModel} disabled={busy} /></label>}<p className="input-help">{pipelineProvider === 'rule_based' ? 'An Agent is an AI task worker for one audit step, such as extracting memories or drafting questions. Rule-based mode uses deterministic processing; choose a local or cloud model service to let Agents call an LLM.' : 'An Agent is an AI task worker for one audit step, such as extracting memories or drafting questions. The shared model powers internal steps including memory extraction, question generation, duplicate review, memory retrieval and automatic assessment. The target model is selected separately.'}</p></>}<aside className="input-help" aria-label="Presentation example"><b>Presentation example · {presentationDemo.messages.length} messages</b><p>A synthetic project history with changing requirements, conflicting documents and unrelated details. Review the extracted memories before running. No model is called by loading this example.</p><UIButton type="button" className="secondary" disabled={busy} onClick={() => { setText(sample); setImportedMessages(presentationDemo.messages); setSourceOrigin('synthetic'); setError(''); }}>Load presentation example</UIButton>{' '}<a href={presentationDemoUrl} download="presentation-conversation.json" onClick={event => { event.preventDefault(); saveBlob(new Blob([presentationDemoRaw], {type:"application/json"}), "presentation-conversation.json"); }}>Download example JSON</a></aside><ConversationStep continueDisabled={providerStatus!=='ready'} text={text} consent={consent} sourceOrigin={sourceOrigin} busy={busy} onTextChange={(next) => { setText(next); setImportedMessages(null); }} onConsentChange={setConsent} onSourceOriginChange={setSourceOrigin} onImport={(messages, previewText) => { setImportedMessages(messages); setText(previewText); }} onImportError={setError} onClearDraft={clearDraft} onContinue={submitConversation} /></>}
    {step === 1 && <GroundTruthReview sourceMessages={sourceMessages} memories={memories} memoryReview={memoryReview} agentExecutions={agentExecutions} busy={busy} onChange={updateMemory} onAddMemory={addMemory} onConfirm={confirm} />}
    {step === 2 && creationPending && <section>
      <h1>Continue Preparing Your Audit</h1>
      <p>Your original settings are preserved. Some records may already be saved; continuing reuses them and finishes the remaining conditions.</p>
      <p>{creationBatch.current?.conditions.filter((item) => item.runId).length ?? 0} of {creationBatch.current?.conditions.length ?? 0} conditions acknowledged. No model answers have been requested at this step.</p>
      <UIButton disabled={busy} onClick={start}>{busy ? 'Preparing Audit…' : 'Resume Audit Preparation'}</UIButton>
      <p>Keep this page open to resume this preparation. After closing it, check Audit History for saved records.</p>
      <a href="/history">Open Audit History</a>
    </section>}
    {step === 2 && !creationPending && providerStatus!=='ready' && <section><h1>Configure Memory Audit</h1><p>Your saved choices are preserved. Load the available model services to review them before starting.</p></section>}
    {step === 2 && !creationPending && providerStatus==='ready' && <section>
      <h1>Configure Memory Audit</h1>
      <aside className="input-help" aria-label="Presentation settings">
        <UIButton type="button" className="secondary" disabled={busy || !providers.some(item=>item.provider==='openrouter' && item.configured)} onClick={() => {
          setCompareAuditors(false); setSelectedStrategies(['weak_first_hit','strong_rule_based']);
          setTargetProviders(['openrouter']); setTargetModels(current=>({...current,openrouter:presentationSettings.model}));
          setPipelineProvider('openrouter'); setPipelineModel(presentationSettings.pipeline_model);
          setRetrievalMode('fixed'); setBudget(presentationSettings.test_budget); setRepetitions(presentationSettings.repetitions);
          setMaintenancePolicy('update_aware_consolidation'); setTargetMemoryCapacity(presentationSettings.target_memory_capacity);
          setTargetMemoryWriter('rule_based'); setTargetSystem('controlled-memory'); setSuiteMode('behavioural');
          setTargetProfile({...defaultTargetProfile,...presentationSettings.target_memory_profile} as TargetMemoryProfile);
        }}>Use presentation settings · 3 repeats per retrieval strategy</UIButton>
        <p>GPT-6 Luna · 8 shared questions · 3 runs per strategy · 48 answers in total. Applies settings only; model calls start when you run the audit. Freshly generated questions may differ from the saved presentation experiment.</p>
      </aside>
      <UIButton type="button" className="secondary" disabled={busy} onClick={() => setStep(1)}>Back to Ground Truth Review</UIButton>
      <p className="input-help">Ground truth is the set of conversation-supported facts you confirmed in the previous step. The audit uses it as the reference when checking answers.</p>
      <UICheckbox checked={compareAuditors} disabled={busy || !pipelineProviders.some(item => item.configured && item.provider !== 'rule_based')} onChange={() => { if(!compareAuditors && pipelineProvider==='rule_based') {
          const service=pipelineProviders.find(item=>item.configured && item.provider!=='rule_based');
          if(service)selectSharedAgentProvider(service.provider);
        }
        setCompareAuditors(value => !value); setTargetMemoryWriter('rule_based'); }}>Compare all three audit methods (recommended)</UICheckbox>
      {compareAuditors ? <UIAlert role="status"><b>Three methods run automatically</b><p>Rule tests + rule review · Model tests + rule review · Model tests + AI review.</p><p>All methods use the same reviewed ground truth and target settings. The two model methods share exactly the same questions and saved target answers; the reviewer changes between rules and the shared Agent model. The rule method uses its own tests.</p></UIAlert> : <p>Custom audit configuration. The Agent model selected at the beginning is shared across internal AI tasks.</p>}
      <p className="provider-note"><b>Shared Agent model:</b> {selectedPipeline?.label ?? 'Rule-based'} · {pipelineProvider === 'rule_based' ? 'no LLM model' : preparationModel ?? 'choose a model'}. This is separate from the target model selected below.</p>
      <h3>Target Models to Compare</h3>
      <div className="provider-grid">{providers.map((item) => <UICheckbox checked={targetProviders.includes(item.provider)} disabled={!item.configured} onChange={() => toggleTarget(item)} className={`target ${targetProviders.includes(item.provider) ? 'selected' : ''}`} key={item.provider}><strong>{item.label}</strong><span>{item.description}</span><small className={item.configured ? 'ready' : 'missing'}>{item.configured ? 'Available for comparison' : 'API key required'}</small></UICheckbox>)}</div>
      {(selectedTargets.length===0 || (retrievalMode === 'fixed' && selectedStrategies.length===0))&&<UIAlert role="status">Choose at least one target service{retrievalMode === 'fixed' ? ' and one memory strategy' : ''} before starting.</UIAlert>}
      <div className="form-grid">
        {!compareAuditors && <label>Test suite design<UISelect aria-label={["Test suite design"].join(' ')} value={suiteMode} onChange={(event) => setSuiteMode(event.target.value as TestSuiteMode)}><UIOption value="paired_contextual">Paired recall &amp; task probes</UIOption><UIOption value="contextual_indirect">Contextual/indirect tests</UIOption><UIOption value="behavioural">Behavioural tests</UIOption><UIOption value="direct_ground_truth">Direct Ground-Truth baseline</UIOption><UIOption value="fixed_template">Fixed-Template baseline</UIOption></UISelect><small>Frozen once and shared by every condition. Paired probes need at least two calls; an odd budget leaves one call unused. Contextual/indirect suites contain no direct-recall items.</small></label>}
        <label>Requested test count<UIInput preserveValueOnClear type="number" min="1" max="100" value={budget} onChange={(event) => setBudget(Math.max(1, Math.min(100, Math.trunc(Number(event.target.value)) || 1)))} /><small>The Agent needs at least one distinct, evidence-backed question for each ability. It distributes the remaining questions as evenly as confirmed evidence allows; if one ability has only one slot, extra questions go to abilities with more supported slots. A dimension score based on one question is less stable, and results show the actual question count. Proposal Category Coverage also counts a dimension once it has at least one valid question. The full requested count still needs enough distinct evidence overall. Add a source-backed example if needed, and link UPDATE, CONFLICT and CONTEXTUAL_OVERRIDE records in Ground Truth Review before creating the audit.</small></label>
        <label>Repeated runs per condition<UIInput preserveValueOnClear type="number" min="1" max="10" value={repetitions} onChange={(event) => setRepetitions(Math.max(1, Math.min(10, Math.trunc(Number(event.target.value)) || 1)))} /></label>
      </div>
      {coverageRequired && <UIAlert role={coveragePreviewStatus === 'ready' && !coveragePreview?.minimum_met ? 'alert' : 'status'}>
        <b>{budget < 4
          ? 'All four abilities need at least one question, so request at least 4 questions.'
          : coveragePreviewStatus === 'ready'
            ? `Evidence-based question allocation: ${auditDimensions.map(dimension=>`${dimension.replaceAll('_',' ')} ${dimensionQuotas[dimension]}`).join(' · ')}.`
            : 'At least one question per ability; additional questions are allocated to remaining supported evidence.'}</b>
        {coveragePreviewStatus === 'loading' && <p>Checking confirmed evidence and relationship links for all four abilities…</p>}
        {coveragePreviewStatus === 'error' && <p>Could not check coverage: {coveragePreviewError} The audit is blocked until the evidence check succeeds.</p>}
        {coveragePreviewStatus === 'ready' && <>
          <p>Distinct evidence-supported question slots: {auditDimensions.map(dimension=>`${dimension.replaceAll('_',' ')} ${dimensionSlots[dimension]}`).join(' · ')}.</p>
          {dimensionShortages.length > 0
            ? <><p>Insufficient coverage: {dimensionShortages.map(item=>`${item.dimension.replaceAll('_',' ')} needs ${item.required_question_count}, currently ${item.available_question_count}`).join('; ')}.</p><p>{dimensionShortages.map(item=>item.reason).join(' ') } Go back to Ground Truth Review to confirm evidence and add the required links before creating the audit.</p></>
            : totalDimensionSlots < budget
              ? <p>Confirmed evidence supports {totalDimensionSlots} distinct question slots in total, fewer than the requested {budget}. Add source-backed evidence or lower the requested count.</p>
            : coveragePreview?.minimum_met
              ? <p>All four abilities have at least one supported question, and the requested count fits the available distinct evidence. The Agent will still validate each question and retry unsupported or duplicate slots before saving.</p>
              : <p>The requested count is too small to allocate at least one question to each ability. Increase it to 4 or more.</p>}
        </>}
      </UIAlert>}
      {selectedTargets.length > 0 && <div className="form-grid model-overrides">{selectedTargets.map((provider) => <label key={provider.provider}>Target model for {provider.label}<ModelPicker label={`Target model for ${provider.label}`} provider={provider.provider} defaultModel={provider.default_model} multiple disabled={provider.provider === 'rule_based'} value={provider.provider === 'rule_based' ? provider.default_model : targetModels[provider.provider] ?? provider.default_model} onChange={(value) => setTargetModels((current) => ({ ...current, [provider.provider]: value }))} /><small>{provider.provider === 'rule_based' ? 'This deterministic baseline has one fixed identity.' : 'Search and select up to eight models to compare.'}</small></label>)}</div>}
      {(modelSelectionError || auditModelError || answerValidationError) && <UIAlert role="alert">{modelSelectionError || auditModelError || answerValidationError}</UIAlert>}
      <label>System under test<UISelect aria-label="System under test" value={targetSystem} onChange={event=>setTargetSystem(event.target.value)}>{systems.length ? systems.map(system=><UIOption key={system.value} value={system.value} disabled={!system.configured || (retrievalMode === 'agent' && system.value === 'external-http')}>{system.label}{system.configured?'':' — backend setup required'}{retrievalMode === 'agent' && system.value === 'external-http' ? ' — uses its own retrieval' : ''}</UIOption>) : <UIOption value="controlled-memory">Configurable memory system</UIOption>}</UISelect></label>
      {targetSystem==='external-http'&&<p>The external service owns memory writing, updates and capacity. Store controls are disabled; its retrieval policy and target profile are sent through the service contract.</p>}
      <TargetProfileEditor value={targetProfile} onChange={setTargetProfile} disabled={busy} answerValidationAvailable={answerValidationAvailable} storeSettings={{
        maintenancePolicy, onMaintenancePolicyChange: setMaintenancePolicy,
        capacity: targetMemoryCapacity, onCapacityChange: setTargetMemoryCapacity,
        writer: targetMemoryWriter, onWriterChange: setTargetMemoryWriter,
        disableLlmWriter: compareAuditors || pipelineProvider === 'rule_based',
        disabled: busy || targetSystem === 'external-http',
      }} retrievalControls={<>
        <label>Retrieval method<UISelect aria-label="Memory retrieval method" value={retrievalMode} disabled={busy} onChange={event => {
          const next = event.target.value as RetrievalMode;
          setRetrievalMode(next);
          if (next === 'agent' && targetSystem === 'external-http') setTargetSystem('controlled-memory');
        }}><UIOption value="agent">AI retrieval Agent (default)</UIOption><UIOption value="fixed">Fixed retrieval policy</UIOption></UISelect><small>The Agent chooses relevant records by meaning and never receives reference answers.</small></label>
        {retrievalMode === 'agent' ? <>
          <p className="provider-note">This Agent uses the shared model selected above. It sees the test question and the target's private memory records, but never the reference answer.</p>
        </> : <>
          <h4>Fixed retrieval policies</h4>
          <div className="target-grid">{strategies.map((item) => <UICheckbox checked={selectedStrategies.includes(item.value)} onChange={() => toggleStrategy(item.value)} className={`target ${selectedStrategies.includes(item.value) ? 'selected' : ''}`} key={item.value}><strong>{item.label}</strong><span>{item.description}</span></UICheckbox>)}</div>
        </>}
      </>}/>
      <h3>Audit Dimensions</h3><p className="dimensions">Accuracy · Freshness · Conflict Resolution · Appropriate Use</p>
      <UIButton disabled={busy || providerStatus!=='ready' || (compareAuditors && pipelineProvider==='rule_based') || coverageBlocked || Boolean(modelSelectionError || auditModelError || answerValidationError) || !targetProfile.label.trim() || (!compareAuditors && suiteMode === "paired_contextual" && budget < 2) || selectedTargets.length === 0 || (retrievalMode === 'fixed' && selectedStrategies.length === 0) || !selectedPipeline?.configured || !selectedEvaluator?.configured} onClick={start}>Start {conditionCount > 1 ? `${conditionCount}-Run Comparison` : 'Memory Audit'}</UIButton>
    </section>}
    {step === 3 && <section className="running">
      <h1>Prepare Memory Audit</h1>
      <UIButton type="button" className="secondary" disabled={busy} onClick={startSeparateAudit}>Start a separate audit</UIButton><p>Starts with new source data. Existing conversations, questions and results stay available in Audit History.</p>
      {questionCountNote && <UIAlert role="status">{questionCountNote}</UIAlert>}
      {busy && runningLabel && <p className="running-model">Currently working: <b>{runningLabel}</b>{runningRunId && <> <UIButton type="button" className="secondary" onClick={cancelCurrentRun}>Cancel current run &amp; stop queue</UIButton>{runs.length > 1 && <UIButton type="button" className="secondary" onClick={cancelExperiment}>Cancel entire comparison</UIButton>}</>}</p>}
      <ul className="progress"><li>Preparing confirmed ground truth <b>Complete</b></li><li>Preparing reviewed test suites <b>{reviewTests ? 'Complete' : busy ? 'In progress' : 'Waiting'}</b></li><li>Test-suite quality checks <b>{readyForExecution ? 'Complete' : reviewTests ? 'Action required' : 'Waiting'}</b></li><li>Initialising target AI <b>{readyForExecution ? 'Ready' : 'Waiting'}</b></li><li>Executing memory tests <b>{runningStage === 'execute' ? 'In progress' : runningStage === 'evaluate' ? 'Complete' : runningStage === 'recover' ? 'Recovering' : 'Waiting'}</b></li><li>Evaluating responses <b>{runningStage === 'evaluate' ? 'In progress' : runningStage === 'recover' ? 'Recovering' : 'Waiting'}</b></li></ul>
      {!reviewTests ? <UIButton disabled={busy} onClick={prepareTests}>{busy ? 'Generating Shared Test Suite…' : 'Generate Tests for Review'}</UIButton> : <>{[...new Set(reviewTests.map(test => test.run_id))].map(id => <div key={id}><h2>{runs.find(run => run.runId === id)?.generationGroup === 'rules' ? 'Rule-generated questions' : compareAuditors ? 'Model-generated questions · shared by both reviewers' : 'Questions for review'}</h2>{continueGenerationRuns.includes(id) && <UIButton type="button" className="secondary" disabled={busy} onClick={() => continueGeneration(id)}>Regenerate the suite toward the requested count</UIButton>}<UIButton type="button" className="secondary" disabled={busy || completedRunIds.current.size > 0 || cancelledRunIds.current.size > 0} onClick={() => reviewQuestionScopes(id)}>Check question scope against source</UIButton><p className="provider-note">Flagged questions need your review. No warning does not guarantee a question is valid.</p><TestSuiteReview tests={reviewTests.filter(test => test.run_id === id)} dimensionCoverage={dimensionCoverage[id]} busy={busy || completedRunIds.current.size > 0 || cancelledRunIds.current.size > 0} onReview={reviewTest} onRegenerate={regenerateTest} onAcceptAll={acceptAllTests} /></div>)}<UIButton disabled={busy || !readyForExecution || queueStopped} onClick={() => runAudit()}>{queueStopped ? 'Execution Queue Cancelled' : busy ? runningLabel ? `Running ${runningLabel}…` : 'Updating question review…' : runs.length > 1 ? 'Run Comparison & View Results' : 'Run Audit & View Results'}</UIButton>{queueStopped && <div className="provider-note"><p>{entireExperimentCancelled ? 'This comparison is terminal. Start a new audit for a fresh controlled comparison.' : remainingConditions.length ? 'The current condition was cancelled. Remaining conditions still use the same frozen suite.' : 'No conditions remain to run. Saved evidence is available in Audit History.'}</p>{!entireExperimentCancelled && remainingConditions.length > 0 && <><UIButton type="button" className="secondary" onClick={() => runAudit(true)}>Continue Remaining Conditions</UIButton><UIButton type="button" className="secondary" onClick={cancelExperiment}>Cancel Remaining Conditions</UIButton></>}{remainingConditions.length === 0 && <a href="/history">Open Audit History</a>}</div>}{!readyForExecution && <p className="provider-note">Accept pending questions, and accept or regenerate rejected questions before execution. Duplicate questions must be regenerated.</p>}</>}
    </section>}
    {step === 4 && <section>
      {compareAuditors && <a href={`/audit-methods?groups=${encodeURIComponent(experimentIds.join(','))}`}>Open saved three-method comparison</a>}
      <h1>{results.length === 0 ? 'Audit needs attention' : results.length > 1 ? compareAuditors ? 'Audit Method Comparison' : 'Memory Health Model Comparison' : 'Memory Health Report'}</h1>
      {results.length < runs.length && <UIAlert role="status" className="partial-run-warning"><b>Incomplete comparison</b><p>{results.length} of {runs.length} planned runs completed · {cancelledRunIds.current.size} cancelled · {runs.length - results.length - cancelledRunIds.current.size} unfinished.</p><p>Scores include completed runs only. Cancelled and unfinished runs have no score; this does not establish a complete strategy comparison.</p><a href="/history">Check every planned run in Audit History</a></UIAlert>}
      {failedRuns.length > 0 && <div className="partial-run-warning"><b>{failedRuns.length} condition{failedRuns.length === 1 ? '' : 's'} need attention.</b><ul>{failedRuns.map((run) => <li key={run.runId}>{run.label}: {run.detail}</li>)}</ul><UIButton disabled={busy} onClick={retryFailedRuns}>{busy ? `Retrying ${runningLabel || 'run'}…` : 'Check progress & resume'}</UIButton></div>}
      {results.length > 1 && <><>{compareAuditors ? <ReviewedMethodComparison runs={results} /> : <Suspense fallback={<p className="chart-loading" role="status">Loading visual comparison charts…</p>}><ComparisonVisualizations runs={results} /></Suspense>}</>{!compareAuditors && <><ModelComparison runs={results} /><ExperimentStatistics runs={results} /></>}</>}
      {results.map((item) => <UIPanel className="individual-report" key={item.result.run_id} open={results.length === 1}><UISummary>{item.label} detailed report</UISummary><ResultDashboard result={item.result} run={item.run} /><TargetMemoryTrace runId={item.result.run_id} /></UIPanel>)}
      <UIButton className="secondary" onClick={() => window.location.reload()}>Start New Audit</UIButton>
      <ResearchResultsPage embedded />
    </section>}
  </main>;
}
