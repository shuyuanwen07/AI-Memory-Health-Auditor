import { spreadsheetCsvCell } from './csvExport';

export type JsonRecord = Record<string, unknown>;
export type StudySplitName = 'development' | 'development_regression' | 'development_repair' | 'evaluation' | 'safety_guards';
export type GradeOutcome = 'correct' | 'incorrect' | 'uncertain' | 'error' | 'missing';
export type RunStatus = 'completed' | 'error' | 'missing';

export interface StabilityRun extends JsonRecord {
  round: string | number;
  arm: string;
  status: RunStatus;
  grade_outcome: GradeOutcome;
  response_text: string | null;
  semantic_grade: JsonRecord | null;
  grading_attempt?: JsonRecord | null;
  failure_diagnostics?: JsonRecord | null;
  auxiliary_analysis?: JsonRecord | null;
  execution_metadata?: unknown;
  input_receipt?: unknown;
  source_review?: unknown;
  extra_agent_executions?: unknown[];
}

export interface StabilityCase extends JsonRecord {
  case_id: string;
  type: string;
  question: string | null;
  reference_answer: string | number | null;
  runs: StabilityRun[];
}

export interface StabilitySplit extends JsonRecord {
  name: StudySplitName;
  planned_case_ids: string[];
  rounds: Array<string | number>;
  arms: string[];
  cases: StabilityCase[];
}

export interface StabilityStudyPayload extends JsonRecord {
  study_id: string;
  created_at: string;
  protocol: JsonRecord;
  provenance: JsonRecord;
  acceptance_results: unknown;
  splits: StabilitySplit[];
  replay: JsonRecord;
  limitations: string[];
}

export interface StabilityStudyEnvelope {
  schema_version: 'memory-stability-study-package-v1';
  payload_json: string;
  payload_sha256: string;
}

export interface DecodedStabilityPackage {
  envelope: StabilityStudyEnvelope;
  payload: StabilityStudyPayload;
  sha256_verified: string;
  raw_envelope: string;
}

export interface SplitCounts {
  split: StudySplitName;
  round: string | number;
  arm: string;
  planned_cases: number;
  correct: number;
  incorrect: number;
  uncertain: number;
  error: number;
  missing: number;
}

export interface RepeatAgreement {
  arm: string;
  agreed: number;
  resolved: number;
  planned: number;
}

const DB_NAME = 'mha-local-stability-study-v1';
const STORE_NAME = 'packages';
const LATEST_KEY = 'latest';
const OUTCOMES = new Set<GradeOutcome>(['correct', 'incorrect', 'uncertain', 'error', 'missing']);
const STATUSES = new Set<RunStatus>(['completed', 'error', 'missing']);
const SENSITIVE_KEY = /^(?:api[-_]?key|access[-_]?token|refresh[-_]?token|client[-_]?secret|private[-_]?key|password|credentials?|full[-_]?transcript|conversation[-_]?transcript|raw[-_]?transcript|transcript|full[-_]?source|raw[-_]?source|source[-_]?transcript|source[-_]?text|conversation[-_]?messages|conversation[-_]?history)$/i;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, label: string): JsonRecord {
  if (!isRecord(value)) throw new Error(`${label} must be a JSON object.`);
  return value;
}

function requireString(value: unknown, label: string, allowEmpty = false): string {
  if (typeof value !== 'string' || (!allowEmpty && value.trim() === '')) throw new Error(`${label} must be a${allowEmpty ? '' : ' non-empty'} string.`);
  return value;
}

function requireStringOrNumber(value: unknown, label: string): string | number {
  if (typeof value !== 'string' && (typeof value !== 'number' || !Number.isFinite(value))) {
    throw new Error(`${label} must be a string or finite number.`);
  }
  return value;
}

function validateNoSensitiveKeys(value: unknown, path = 'payload'): void {
  if (Array.isArray(value)) {
    value.forEach((child, index) => validateNoSensitiveKeys(child, `${path}[${index}]`));
    return;
  }
  if (!isRecord(value)) return;
  for (const [key, child] of Object.entries(value)) {
    const normalisedKey = key.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();
    if (SENSITIVE_KEY.test(normalisedKey)) throw new Error(`${path} contains a field that cannot be imported here: ${key}. Remove credentials and full-source transcript fields from the package.`);
    validateNoSensitiveKeys(child, `${path}.${key}`);
  }
}

function uniqueStrings(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.some(item => typeof item !== 'string' || item.trim() === '')) throw new Error(`${label} must be a non-empty list of strings.`);
  if (value.length === 0 || new Set(value).size !== value.length) throw new Error(`${label} must contain unique entries.`);
  return value as string[];
}

function validateRun(value: unknown, splitName: string, caseId: string, rounds: Set<string>, arms: Set<string>): StabilityRun {
  const run = requireRecord(value, `Run for ${caseId}`);
  const round = requireStringOrNumber(run.round, `Run round for ${caseId}`);
  const arm = requireString(run.arm, `Run arm for ${caseId}`);
  const status = requireString(run.status, `Run status for ${caseId}`) as RunStatus;
  const gradeOutcome = requireString(run.grade_outcome, `Grade outcome for ${caseId}`) as GradeOutcome;
  if (!STATUSES.has(status)) throw new Error(`Run for ${caseId} has an unsupported status.`);
  if (!OUTCOMES.has(gradeOutcome)) throw new Error(`Run for ${caseId} has an unsupported grade outcome.`);
  if (!rounds.has(String(round)) || !arms.has(arm)) throw new Error(`Run for ${caseId} uses an undeclared round or arm in ${splitName}.`);
  if (run.response_text !== null && typeof run.response_text !== 'string') throw new Error(`Response text for ${caseId} must be a string or null.`);
  if (run.semantic_grade !== null && !isRecord(run.semantic_grade)) throw new Error(`Semantic grade for ${caseId} must be an object or null.`);
  if (run.grading_attempt !== undefined && run.grading_attempt !== null && !isRecord(run.grading_attempt)) throw new Error(`Grading attempt for ${caseId} must be an object or null.`);
  if (run.failure_diagnostics !== undefined && run.failure_diagnostics !== null && !isRecord(run.failure_diagnostics)) throw new Error(`Failure diagnostics for ${caseId} must be an object or null.`);
  if (run.auxiliary_analysis !== undefined && run.auxiliary_analysis !== null && !isRecord(run.auxiliary_analysis)) throw new Error(`Auxiliary analysis for ${caseId} must be an object or null.`);
  if (run.extra_agent_executions !== undefined && !Array.isArray(run.extra_agent_executions)) throw new Error(`Extra agent executions for ${caseId} must be a list.`);

  if (status === 'completed') {
    if (typeof run.response_text !== 'string') throw new Error(`Completed run for ${caseId} must retain its target answer text.`);
    if (gradeOutcome === 'correct' || gradeOutcome === 'incorrect') {
      const correct = run.semantic_grade?.correct;
      if (typeof correct !== 'boolean' || correct !== (gradeOutcome === 'correct')) throw new Error(`Completed run for ${caseId} must retain the matching original binary semantic grade.`);
    } else if (gradeOutcome === 'uncertain') {
      if (!run.semantic_grade || run.semantic_grade.correct !== null || run.semantic_grade.status !== 'uncertain') throw new Error(`Uncertain run for ${caseId} requires an explicit structured uncertain semantic grade.`);
    } else {
      throw new Error(`Completed run for ${caseId} cannot have an error or missing grade outcome.`);
    }
  } else if (gradeOutcome !== status || run.semantic_grade !== null) {
    throw new Error(`${status === 'error' ? 'Errored' : 'Missing'} run for ${caseId} must have a null semantic grade and ${status} outcome.`);
  }
  return run as StabilityRun;
}

function validateSplit(value: unknown): StabilitySplit {
  const split = requireRecord(value, 'Study split');
  const name = requireString(split.name, 'Split name') as StudySplitName;
  if (name !== 'development' && name !== 'development_regression' && name !== 'development_repair' && name !== 'evaluation' && name !== 'safety_guards') throw new Error('Split name must be development, development_regression, development_repair, evaluation, or safety_guards.');
  const plannedCaseIds = uniqueStrings(split.planned_case_ids, `${name} planned_case_ids`);
  if (!Array.isArray(split.rounds) || split.rounds.length === 0) throw new Error(`${name} rounds must be a non-empty list.`);
  const rounds = split.rounds.map((round, index) => requireStringOrNumber(round, `${name} round ${index + 1}`));
  if (new Set(rounds.map(String)).size !== rounds.length) throw new Error(`${name} rounds must be unique.`);
  const arms = uniqueStrings(split.arms, `${name} arms`);
  if (!Array.isArray(split.cases)) throw new Error(`${name} cases must be a list.`);
  const planned = new Set(plannedCaseIds);
  const cases = split.cases.map(value => {
    const studyCase = requireRecord(value, `${name} case`);
    const caseId = requireString(studyCase.case_id, `${name} case_id`);
    if (!planned.has(caseId)) throw new Error(`${name} includes unplanned case ${caseId}.`);
    if (!Array.isArray(studyCase.runs)) throw new Error(`${name} case ${caseId} runs must be a list.`);
    if (studyCase.type !== null && typeof studyCase.type !== 'string') throw new Error(`${name} case ${caseId} type must be a string or null.`);
    if (studyCase.question !== null && typeof studyCase.question !== 'string') throw new Error(`${name} case ${caseId} question must be a string or null.`);
    const referenceAnswer = studyCase.reference_answer;
    if (referenceAnswer !== null && typeof referenceAnswer !== 'string' && !(typeof referenceAnswer === 'number' && Number.isFinite(referenceAnswer))) {
      throw new Error(`${name} case ${caseId} reference_answer must be a string, finite number, or null.`);
    }
    const runRows = studyCase.runs.map(run => validateRun(run, name, caseId, new Set(rounds.map(String)), new Set(arms)));
    const cellKeys = runRows.map(run => `${String(run.round)}\u0000${run.arm}`);
    const expectedCells = rounds.length * arms.length;
    if (cellKeys.length !== expectedCells || new Set(cellKeys).size !== expectedCells) throw new Error(`${name} case ${caseId} must contain exactly one result for every planned round and arm.`);
    return studyCase as StabilityCase;
  });
  const caseIds = cases.map(studyCase => studyCase.case_id);
  if (new Set(caseIds).size !== cases.length || cases.length !== plannedCaseIds.length || plannedCaseIds.some(id => !caseIds.includes(id))) {
    throw new Error(`${name} must retain exactly one case record for every planned case ID.`);
  }
  return { ...split, name, planned_case_ids: plannedCaseIds, rounds, arms, cases } as StabilitySplit;
}

function validatePayload(value: unknown): StabilityStudyPayload {
  const payload = requireRecord(value, 'Study payload');
  requireString(payload.study_id, 'study_id');
  requireString(payload.created_at, 'created_at');
  requireRecord(payload.protocol, 'protocol');
  requireRecord(payload.provenance, 'provenance');
  if (!isRecord(payload.acceptance_results) && !Array.isArray(payload.acceptance_results)) throw new Error('acceptance_results must be an object or list.');
  if (!Array.isArray(payload.splits) || payload.splits.length === 0) throw new Error('splits must contain at least one development or evaluation split.');
  const splits = payload.splits.map(validateSplit);
  const splitNames = splits.map(split => split.name);
  if (new Set(splitNames).size !== splitNames.length) throw new Error('Each study split can appear only once.');
  requireRecord(payload.replay, 'replay');
  if (!Array.isArray(payload.limitations) || payload.limitations.some(item => typeof item !== 'string')) throw new Error('limitations must be a list of strings.');
  validateNoSensitiveKeys(payload);
  return { ...payload, study_id: payload.study_id as string, created_at: payload.created_at as string, protocol: payload.protocol as JsonRecord,
    provenance: payload.provenance as JsonRecord, splits, replay: payload.replay as JsonRecord, limitations: payload.limitations as string[] } as StabilityStudyPayload;
}

export async function sha256Hex(text: string): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new Error('This browser cannot verify SHA-256 packages. Use a current browser in a secure local context.');
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

/** Parses the payload only after the exact payload_json bytes match the envelope hash. */
export async function decodeStabilityStudyPackage(rawText: string, stillAuthorised?: () => boolean): Promise<DecodedStabilityPackage> {
  let rawEnvelope: unknown;
  try { rawEnvelope = JSON.parse(rawText); } catch { throw new Error('The selected file is not valid JSON.'); }
  const envelope = requireRecord(rawEnvelope, 'Package envelope');
  const extraEnvelopeFields = Object.keys(envelope).filter(key => !['schema_version', 'payload_json', 'payload_sha256'].includes(key));
  if (extraEnvelopeFields.length) throw new Error(`Package envelope has unsupported fields: ${extraEnvelopeFields.join(', ')}.`);
  if (envelope.schema_version !== 'memory-stability-study-package-v1') throw new Error('This is not a memory-stability-study-package-v1 envelope.');
  const payloadJson = requireString(envelope.payload_json, 'payload_json', true);
  const expectedHash = requireString(envelope.payload_sha256, 'payload_sha256');
  if (!/^[a-f0-9]{64}$/i.test(expectedHash)) throw new Error('payload_sha256 must contain 64 hexadecimal characters.');
  const actualHash = await sha256Hex(payloadJson);
  if (actualHash !== expectedHash.toLowerCase()) throw new Error('The payload SHA-256 does not match. The package may have changed or been truncated.');
  if (stillAuthorised && !stillAuthorised()) throw new Error('Package authorisation was withdrawn before payload validation completed.');
  let parsedPayload: unknown;
  try { parsedPayload = JSON.parse(payloadJson); } catch { throw new Error('The SHA-256 matches, but payload_json is not valid JSON.'); }
  const payload = validatePayload(parsedPayload);
  return { envelope: envelope as unknown as StabilityStudyEnvelope, payload, sha256_verified: actualHash, raw_envelope: rawText };
}

export function summarizeSplit(split: StabilitySplit): SplitCounts[] {
  return split.rounds.flatMap(round => split.arms.map(arm => {
    const counts: SplitCounts = { split: split.name, round, arm, planned_cases: split.planned_case_ids.length,
      correct: 0, incorrect: 0, uncertain: 0, error: 0, missing: 0 };
    for (const studyCase of split.cases) {
      const run = studyCase.runs.find(item => String(item.round) === String(round) && item.arm === arm);
      if (run) {
        switch (run.grade_outcome) {
          case 'correct': counts.correct += 1; break;
          case 'incorrect': counts.incorrect += 1; break;
          case 'uncertain': counts.uncertain += 1; break;
          case 'error': counts.error += 1; break;
          case 'missing': counts.missing += 1; break;
        }
      }
    }
    return counts;
  }));
}

export function repeatAgreement(split: StabilitySplit): RepeatAgreement[] {
  if (split.rounds.length < 2) return [];
  return split.arms.map(arm => {
    let agreed = 0;
    let resolved = 0;
    for (const studyCase of split.cases) {
      const outcomes = split.rounds.map(round => studyCase.runs.find(run => String(run.round) === String(round) && run.arm === arm)?.grade_outcome);
      if (outcomes.length > 0 && outcomes.every(outcome => outcome === 'correct' || outcome === 'incorrect')) {
        resolved += 1;
        if (outcomes.every(outcome => outcome === outcomes[0])) agreed += 1;
      }
    }
    return { arm, agreed, resolved, planned: split.planned_case_ids.length };
  });
}

export function stabilitySummaryCsv(payload: StabilityStudyPayload): string {
  const header = ['study_id', 'split', 'round', 'arm', 'planned_cases', 'correct', 'incorrect', 'uncertain', 'error', 'missing', 'repeat_agreed', 'repeat_resolved', 'repeat_planned'];
  const rows = payload.splits.flatMap(split => {
    const agreement = new Map(repeatAgreement(split).map(item => [item.arm, item]));
    return summarizeSplit(split).map(row => {
      const repeat = agreement.get(row.arm);
      return [payload.study_id, row.split, row.round, row.arm, row.planned_cases, row.correct, row.incorrect, row.uncertain, row.error, row.missing, repeat?.agreed ?? '', repeat?.resolved ?? '', repeat?.planned ?? ''];
    });
  });
  return [header, ...rows].map(row => row.map(spreadsheetCsvCell).join(',')).join('\r\n') + '\r\n';
}

interface StoredPackage { key: string; rawEnvelope: string; savedAt: string; }

function openPackageDb(): Promise<IDBDatabase> {
  if (!globalThis.indexedDB) return Promise.reject(new Error('This browser does not provide local IndexedDB storage.'));
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) request.result.createObjectStore(STORE_NAME, { keyPath: 'key' });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error('Could not open local package storage.'));
    request.onblocked = () => reject(new Error('Local package storage is blocked by another open page.'));
  });
}

function idbRequest<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error('Local package storage request failed.'));
  });
}

export async function hasSavedStabilityStudyPackage(): Promise<boolean> {
  const db = await openPackageDb();
  try { return (await idbRequest(db.transaction(STORE_NAME, 'readonly').objectStore(STORE_NAME).getKey(LATEST_KEY))) !== undefined; }
  finally { db.close(); }
}

export async function readSavedStabilityStudyPackage(): Promise<string | null> {
  const db = await openPackageDb();
  try {
    const record = await idbRequest(db.transaction(STORE_NAME, 'readonly').objectStore(STORE_NAME).get(LATEST_KEY)) as StoredPackage | undefined;
    return record?.rawEnvelope ?? null;
  } finally { db.close(); }
}

export async function saveStabilityStudyPackage(rawEnvelope: string): Promise<void> {
  const db = await openPackageDb();
  try {
    const transaction = db.transaction(STORE_NAME, 'readwrite');
    transaction.objectStore(STORE_NAME).put({ key: LATEST_KEY, rawEnvelope, savedAt: new Date().toISOString() } satisfies StoredPackage);
    await new Promise<void>((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error('Could not save the local package.'));
      transaction.onabort = () => reject(transaction.error ?? new Error('Saving the local package was cancelled.'));
    });
  } finally { db.close(); }
}

export async function removeSavedStabilityStudyPackage(): Promise<void> {
  const db = await openPackageDb();
  try {
    const transaction = db.transaction(STORE_NAME, 'readwrite');
    transaction.objectStore(STORE_NAME).delete(LATEST_KEY);
    await new Promise<void>((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error('Could not remove the local package.'));
      transaction.onabort = () => reject(transaction.error ?? new Error('Removing the local package was cancelled.'));
    });
  } finally { db.close(); }
}
