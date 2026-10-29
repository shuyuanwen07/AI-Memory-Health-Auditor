import type { AuditRun, RelationshipType } from '../types/domain';

export const auditMethodLabels:Record<string,string> = {
  rules:'Rule tests + rule review',model_generation:'Model tests + rule review',hybrid:'Model tests + hybrid review',
};

export function auditMethodLabel(run:Pick<AuditRun,'reproducibility'|'pipeline_provider'|'evaluator_provider'>) {
  const declared=auditMethodLabels[run.reproducibility?.auditor_method ?? ''];
  if (declared) return declared;
  const providers=new Set(['rule_based','openrouter','ollama','openai','deepseek','gemini']);
  if (!providers.has(run.pipeline_provider) || !providers.has(run.evaluator_provider)) return 'Audit method not recorded';
  // Configuration labels identify the requested service, not whether a
  // particular model assessment succeeded or used a fallback.
  return `${run.pipeline_provider==='rule_based'?'Rule':'Model'} tests + ${run.evaluator_provider==='rule_based'?'rule':'AI'} review`;
}

export function failureCountLabel(count: number | null, pending = 0) {
  if (count === null) return pending > 0 ? 'Awaiting review' : 'Not tested';
  return `${count.toLocaleString()} failure${count === 1 ? '' : 's'}${pending > 0 ? ` · ${pending} awaiting review` : ''}`;
}

export function relationshipLabel(type: RelationshipType) {
  return { UPDATE: 'Update an older fact', CONFLICT: 'Conflicting requirements', CONTEXTUAL_OVERRIDE: 'Task-specific exception' }[type];
}

/** Reads from the related older/general record toward the current record. */
export function relationshipEvidenceLabel(type: RelationshipType) {
  return { UPDATE: 'Updated to', CONFLICT: 'Conflicts with', CONTEXTUAL_OVERRIDE: 'Overridden for this task by' }[type];
}

/** Presentation only: original identifiers remain in API requests and research exports. */
export function friendlyText(value: string) {
  return value
    .replace(/The configured pipeline model/g, 'The selected model')
    .replace(/The selected model returned an invalid memory relationship reference\./g,
      'The model linked a memory to a missing record or to itself. Extraction was not saved; retry or choose another model.')
    .replace(/Check PIPELINE_MODEL\./g, 'Choose another model or check the service settings.')
    .replace(/\bconflict_resolution\b/g, 'Conflict Resolution')
    .replace(/\bappropriate_use\b/g, 'Appropriate Use')
    .replace(/\bground-truth terms\b/g, 'reference terms')
    .replace(/\b(\d+) gold evidence record\(s\) are linked/g, (_, count: string) => `${count} reference ${count === '1' ? 'memory is' : 'memories are'} linked`)
    .replace(/\blexical verdict\b/g, 'word-match assessment')
    .replace(/Evidence records:\s*([^.]*)\./gi, (_match, references:string) => {
      const value=references.trim();
      if (!value || /^none(?:\s+linked\s+to\s+this\s+test)?$/i.test(value)) return 'No reference memories are listed in this explanation.';
      const identities=value.split(/\s*,\s*/);
      if (identities.every(identity=>/^M(?:[A-F0-9]{8,}|\d+|[-_][A-Z0-9_-]+)$/i.test(identity))) {
        return 'Reference memories are listed in this explanation.';
      }
      return 'Review the reference evidence for this assessment.';
    })
    .replace(/\b(?:RUN|EXP|CS|MSG|TM|TMR|TE|RET|REL|M|T|E|R)(?:[A-F0-9]{8,}|\d+|[-_][A-Z0-9_-]+)\b/g, 'saved record')
    .replace(/\b[a-f0-9]{32,64}\b/gi, 'verified record');
}

export function assessmentLabel(value = '') {
  if (value.startsWith('fallback')) return 'Rule-based assessment (AI assessment unavailable)';
  if (value.startsWith('rule-based')) return 'Rule-based assessment';
  if (value.startsWith('llm-judge')) return 'AI assessment';
  return 'Automated assessment';
}

export function retrievalExplanation(reason: string) {
  if (/conflict/i.test(reason)) return 'Checked for unresolved memory conflicts';
  if (/intent=current_project_requirement|intent=project_policy/.test(reason)) return 'Matched the current task or policy requirement';
  if (/intent=profile_fact/.test(reason)) return 'Matched a personal profile question';
  if (/intent=general_preference/.test(reason)) return 'Matched a general preference question';
  if (/superseded/i.test(reason)) return 'Checked whether a newer memory replaced this record';
  return 'Checked how closely this memory matches the question';
}

export function processingLabel(value?: string) {
  if (!value || value === 'rule_based' || value.startsWith('rule-based')) return 'Rule-based processing';
  if (value === 'llm_structured') return 'AI-assisted processing';
  if (value === 'controlled-memory') return 'Model with configurable memory';
  return friendlyText(value).replaceAll('_', ' ');
}

export function auditDisplayNames(runs: AuditRun[]) {
  const ordered = [...runs].sort((a, b) => a.created_at.localeCompare(b.created_at) || a.run_id.localeCompare(b.run_id));
  return Object.fromEntries(ordered.map((run, index) => [run.run_id, `Audit ${index + 1}`]));
}

export function memoryStrategyLabel(strategy: AuditRun['memory_strategy']) {
  const labels: Record<AuditRun['memory_strategy'],string> = {
    weak_first_hit: 'First-match retrieval', scope_aware: 'Match the task and project',
    strong_score_based: 'Rank memories by relevance', strong_rule_based: 'Relationship-priority retrieval',
    temporal_importance: 'Consider time and importance', full_context: 'Replay all retained memories',
    no_memory: 'Supply no memories',
  };
  return labels[strategy] ?? 'Other memory approach';
}

export function retrievalApproachKey(run: Pick<AuditRun, 'retrieval_mode'|'memory_strategy'>) {
  return run.retrieval_mode === 'agent' ? 'agent' : run.memory_strategy;
}

export function retrievalApproachLabel(run: Pick<AuditRun, 'retrieval_mode'|'memory_strategy'>) {
  return run.retrieval_mode === 'agent' ? 'AI retrieval Agent' : memoryStrategyLabel(run.memory_strategy);
}


/** Friendly baseline names only; real provider model identifiers stay exact. */
export function modelDisplayName(model: string) {
  if (model === 'rule-based-target-ai') return 'Local rule-based baseline';
  const known = /^(?:openai\/(gpt-[\w.:-]+)|anthropic\/(claude-[\w.:-]+)|google\/(gemini-[\w.:-]+))$/.exec(model);
  if (!known) return model;
  return known.slice(1).find(Boolean)!.split('-').map(word=>word==='gpt'?'GPT':word.charAt(0).toUpperCase()+word.slice(1)).join(' ');
}

/** Describe saved configuration only; absence is not an implicit default. */
export function memoryMaintenanceLabel(value?: string | null) {
  if (value === 'append_only') return 'Keep earlier and newer facts together';
  if (value === 'update_aware_consolidation') return 'Replace outdated facts when an update is identified';
  return value ? 'Other recorded update approach' : 'Not recorded';
}
