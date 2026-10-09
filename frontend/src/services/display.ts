import type { AuditRun } from '../types/domain';

/** Presentation only: original identifiers remain in API requests and research exports. */
export function friendlyText(value: string) {
  return value
    .replace(/Evidence records:\s*[^.]*\./gi, 'Supporting memories were checked.')
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
