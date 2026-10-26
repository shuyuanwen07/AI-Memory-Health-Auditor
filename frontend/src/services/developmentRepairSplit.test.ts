import {webcrypto} from 'node:crypto';
import {afterAll,beforeAll,expect,it,vi} from 'vitest';
import {decodeStabilityStudyPackage,stabilitySummaryCsv,summarizeSplit,type StabilitySplit} from './stabilityStudyPackage';
import {makeEnvelope,makeThreeRoundPilotPayload} from '../test/stabilityStudyFixture';

beforeAll(()=>vi.stubGlobal('crypto',webcrypto as unknown as Crypto));
afterAll(()=>vi.unstubAllGlobals());

it('keeps four used repair diagnostics outside the original six-question regression denominator',async()=>{
  const payload=makeThreeRoundPilotPayload(true);
  const repair:StabilitySplit={...structuredClone(payload.splits[1]),name:'development_repair'};
  repair.cases=repair.cases.slice(0,4).map((item,index)=>({...item,case_id:`REPAIR-SYNTHETIC-${index+1}`}));
  repair.planned_case_ids=repair.cases.map(item=>item.case_id);
  payload.splits.push(repair);
  const raw=await makeEnvelope(payload),decoded=await decodeStabilityStudyPackage(raw);
  expect(decoded.raw_envelope).toBe(raw);
  const regression=decoded.payload.splits.find(split=>split.name==='development_regression')!;
  const diagnostics=decoded.payload.splits.find(split=>split.name==='development_repair')!;
  expect(summarizeSplit(regression)).toEqual([expect.objectContaining({planned_cases:6,missing:6})]);
  expect(summarizeSplit(diagnostics)).toEqual([expect.objectContaining({planned_cases:4,missing:4,arm:'strong_rule_based'})]);
  expect(stabilitySummaryCsv(decoded.payload)).toContain('"development_repair","1","strong_rule_based"');
  expect(stabilitySummaryCsv(decoded.payload)).not.toContain('"development_repair","1","weak_first_hit"');
  expect(decoded.payload.splits.some(split=>split.name==='evaluation')).toBe(false);
});
