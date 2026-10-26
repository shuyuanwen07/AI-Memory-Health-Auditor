import { webcrypto } from 'node:crypto';
import { afterAll, beforeAll, describe, expect, test, vi } from 'vitest';
import {
  decodeStabilityStudyPackage, repeatAgreement, sha256Hex, stabilitySummaryCsv, summarizeSplit,
  type StabilitySplit, type StabilityStudyPayload,
} from './stabilityStudyPackage';
import { makeEnvelope, makeMetadataOnlyStabilityPayload, makeSingleRoundStabilityPayload, makeStabilityPayload, makeThreeRoundPilotPayload } from '../test/stabilityStudyFixture';

beforeAll(() => vi.stubGlobal('crypto', webcrypto as unknown as Crypto));
afterAll(() => vi.unstubAllGlobals());

describe('stability-study package decoding', () => {
  test('retains failed grading evidence separately while counting the cell only as an error', async () => {
    const payload = makeMetadataOnlyStabilityPayload();
    const attempt = { status: 'failed', error_code: 'SyntheticTimeout', verdict: { correct: true } };
    Object.assign(payload.splits[1].cases[0].runs[0], { status: 'error', grade_outcome: 'error', grading_attempt: attempt });
    const raw = await makeEnvelope(payload);
    const decoded = await decodeStabilityStudyPackage(raw);
    const evaluation = decoded.payload.splits[1];
    expect(evaluation.cases[0].runs[0].semantic_grade).toBeNull();
    expect(evaluation.cases[0].runs[0].grading_attempt).toEqual(attempt);
    expect(summarizeSplit(evaluation)[0]).toMatchObject({ correct: 0, error: 1, missing: 11 });
    expect(decoded.raw_envelope).toBe(raw);
  });

  test('verifies the exact UTF-8 payload text and preserves the original envelope', async () => {
    const raw = await makeEnvelope(makeStabilityPayload(), 'pretty');
    const decoded = await decodeStabilityStudyPackage(raw);
    expect(decoded.raw_envelope).toBe(raw);
    expect(decoded.envelope.payload_sha256).toBe(decoded.sha256_verified);
    expect(decoded.payload.splits.map(split => split.name)).toEqual(['development', 'evaluation', 'safety_guards']);
  });

  test('checks hash before parsing payload_json', async () => {
    const raw = JSON.stringify({ schema_version: 'memory-stability-study-package-v1', payload_json: '{not json', payload_sha256: '0'.repeat(64) });
    await expect(decodeStabilityStudyPackage(raw)).rejects.toThrow('does not match');
  });

  test.each([0, 7.5])('preserves numeric reference answer %s and the original envelope', async referenceAnswer => {
    const payload = makeMetadataOnlyStabilityPayload();
    payload.splits[1].cases[0].reference_answer = referenceAnswer;
    const raw = await makeEnvelope(payload);
    const decoded = await decodeStabilityStudyPackage(raw);
    expect(decoded.payload.splits[1].cases[0].reference_answer).toBe(referenceAnswer);
    expect(decoded.raw_envelope).toBe(raw);
    expect(decoded.sha256_verified).toBe(decoded.envelope.payload_sha256);
  });

  test.each([true, {}, [], { numeric: 0 }])('rejects unsupported reference answer %j', async referenceAnswer => {
    const payload = makeMetadataOnlyStabilityPayload();
    Object.assign(payload.splits[1].cases[0], { reference_answer: referenceAnswer });
    await expect(decodeStabilityStudyPackage(await makeEnvelope(payload))).rejects.toThrow('reference_answer must be a string, finite number, or null');
  });

  test('rejects a nonfinite JSON reference number', async () => {
    const payload = makeMetadataOnlyStabilityPayload();
    const payloadJson = JSON.stringify(payload).replace('"reference_answer":null', '"reference_answer":1e400');
    const raw = JSON.stringify({ schema_version: 'memory-stability-study-package-v1', payload_json: payloadJson, payload_sha256: await sha256Hex(payloadJson) });
    await expect(decodeStabilityStudyPackage(raw)).rejects.toThrow('reference_answer must be a string, finite number, or null');
  });

  test('does not parse payload_json after consent is withdrawn during asynchronous hash verification', async () => {
    const payloadJson = '{not json';
    const raw = JSON.stringify({ schema_version: 'memory-stability-study-package-v1', payload_json: payloadJson, payload_sha256: await sha256Hex(payloadJson) });
    await expect(decodeStabilityStudyPackage(raw, () => false)).rejects.toThrow('authorisation was withdrawn');
  });

  test('rejects a completed grade that disagrees with the original structured label', async () => {
    const payload = makeStabilityPayload();
    const semanticGrade = payload.splits[1].cases[0].runs[0].semantic_grade as { correct: boolean };
    semanticGrade.correct = false;
    const raw = await makeEnvelope(payload);
    await expect(decodeStabilityStudyPackage(raw)).rejects.toThrow('matching original binary semantic grade');
  });

  test('keeps error and missing distinct from uncertain and rejects credential or source fields', async () => {
    const payload = makeStabilityPayload();
    expect(() => payload.splits[1].cases[1].runs[0].grade_outcome).not.toThrow();
    const sensitive = { ...payload, provenance: { ...payload.provenance, api_key: 'do-not-import' } };
    await expect(decodeStabilityStudyPackage(await makeEnvelope(sensitive))).rejects.toThrow('credentials and full-source transcript fields');
  });
});

describe('stability-study evidence summaries', () => {
  test('leaves single-round repeat agreement unmeasured and CSV repeat fields blank', () => {
    const payload = makeSingleRoundStabilityPayload();
    for (const split of payload.splits) expect(repeatAgreement(split)).toEqual([]);
    const rows = stabilitySummaryCsv(payload).trim().split('\r\n').slice(1);
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) expect(row).toMatch(/,"","",""$/);
    expect(summarizeSplit(payload.splits[1])[0]).toMatchObject({ correct: 1, missing: 1 });
  });

  test('does not treat missing or errored target cells as uncertain or incorrect', () => {
    const payload = makeStabilityPayload();
    const evaluation = payload.splits[1];
    const rows = summarizeSplit(evaluation);
    expect(rows.find(row => row.round === 1 && row.arm === 'weak_first_hit')).toMatchObject({ correct: 1, incorrect: 0, uncertain: 0, error: 0, missing: 1 });
    expect(rows.find(row => row.round === 1 && row.arm === 'strong_rule_based')).toMatchObject({ correct: 0, incorrect: 1, uncertain: 0, error: 1, missing: 0 });
    expect(repeatAgreement(evaluation)).toEqual([
      { arm: 'weak_first_hit', agreed: 1, resolved: 1, planned: 2 },
      { arm: 'strong_rule_based', agreed: 0, resolved: 1, planned: 2 },
    ]);
  });

  test('excludes uncertain outcomes from binary repeat agreement while retaining their coverage count', () => {
    const evaluation = makeStabilityPayload().splits[1] as unknown as StabilitySplit;
    const uncertainRun = evaluation.cases[0].runs.find(run => run.round === 2 && run.arm === 'weak_first_hit')!;
    uncertainRun.grade_outcome = 'uncertain';
    uncertainRun.semantic_grade = { correct: null, status: 'uncertain' };

    expect(repeatAgreement(evaluation)).toEqual([
      { arm: 'weak_first_hit', agreed: 0, resolved: 0, planned: 2 },
      { arm: 'strong_rule_based', agreed: 0, resolved: 1, planned: 2 },
    ]);
    expect(summarizeSplit(evaluation).find(row => row.round === 2 && row.arm === 'weak_first_hit')).toMatchObject({ uncertain: 1 });
  });

  test('exports per-split semantic counts without pooling development and evaluation', () => {
    const csv = stabilitySummaryCsv(makeStabilityPayload());
    expect(csv).toContain('"development","1","weak_first_hit"');
    expect(csv).toContain('"evaluation","1","weak_first_hit"');
    expect(csv).toContain('"safety_guards"');
    expect(csv).toContain('"repeat_agreed","repeat_resolved","repeat_planned"');
    expect(csv).not.toContain('token_f1');
  });

  test('protects imported study IDs and arm names from spreadsheet formula execution in CSV', () => {
    const payload = makeStabilityPayload();
    payload.study_id = '=2+2';
    const evaluation = payload.splits[1];
    evaluation.arms[0] = '=SUM(1,1)';
    for (const studyCase of evaluation.cases) {
      for (const run of studyCase.runs) {
        if (run.arm === 'weak_first_hit') run.arm = '=SUM(1,1)';
      }
    }

    const csv = stabilitySummaryCsv(payload as unknown as StabilityStudyPayload);
    expect(csv).toContain('"\t=2+2"');
    expect(csv).toContain('"\t=SUM(1,1)"');
  });

  test('accepts a synthetic metadata-only package while preserving its all-missing evaluation denominator', async () => {
    const raw = await makeEnvelope(makeMetadataOnlyStabilityPayload());
    const decoded = await decodeStabilityStudyPackage(raw);
    const evaluation = decoded.payload.splits.find(split => split.name === 'evaluation')!;
    expect(evaluation.planned_case_ids).toHaveLength(12);
    expect(evaluation.rounds).toEqual([1, 2, 3]);
    expect(evaluation.arms).toEqual(['weak_first_hit', 'strong_rule_based']);
    expect(summarizeSplit(evaluation).reduce((sum, row) => sum + row.missing, 0)).toBe(72);
    expect(summarizeSplit(evaluation).reduce((sum, row) => sum + row.correct + row.incorrect + row.uncertain + row.error, 0)).toBe(0);
    expect(decoded.payload.acceptance_results).toMatchObject({ overall_status: 'pending' });
    expect(await sha256Hex(decoded.envelope.payload_json)).toBe(decoded.sha256_verified);
  });
});


describe('complete-grid development pilot cohorts',()=>{
  test.each([false,true])('preserves 24 three-round cells with optional separate used-question cohort=%s',async includeRegression=>{
    const payload=makeThreeRoundPilotPayload(includeRegression);const raw=await makeEnvelope(payload);
    const decoded=await decodeStabilityStudyPackage(raw);
    const development=decoded.payload.splits[0];
    expect(development.rounds).toEqual([1,2,3]);
    expect(summarizeSplit(development).reduce((sum,row)=>sum+row.missing,0)).toBe(24);
    expect(repeatAgreement(development)).toHaveLength(2);
    expect(decoded.raw_envelope).toBe(raw);
    if(includeRegression){
      const regression=decoded.payload.splits[1];
      expect(regression.name).toBe('development_regression');
      expect(regression.rounds).toEqual([1]);expect(regression.arms).toEqual(['strong_rule_based']);
      expect(summarizeSplit(regression)).toEqual([expect.objectContaining({planned_cases:6,missing:6,error:0})]);
      expect(repeatAgreement(regression)).toEqual([]);
      expect(stabilitySummaryCsv(decoded.payload)).toContain('"development_regression","1","strong_rule_based"');
      expect(stabilitySummaryCsv(decoded.payload)).not.toContain('"development_regression","1","weak_first_hit"');
      expect(decoded.payload.splits.some(split=>split.name==='evaluation')).toBe(false);
    }
  });
  test('does not accept an incomplete cohort or synthesize an unplanned arm',async()=>{
    const missing=makeThreeRoundPilotPayload(true);missing.splits[1].cases[0].runs=[];
    await expect(decodeStabilityStudyPackage(await makeEnvelope(missing))).rejects.toThrow('exactly one result');
    const extra=makeThreeRoundPilotPayload(true);extra.splits[1].cases[0].runs.push({...extra.splits[1].cases[0].runs[0],arm:'weak_first_hit'});
    await expect(decodeStabilityStudyPackage(await makeEnvelope(extra))).rejects.toThrow();
  });
});
