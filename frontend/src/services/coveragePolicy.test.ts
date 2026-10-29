import {effectiveCoveragePolicy} from './coveragePolicy';
test('partial is an explicit ordinary model behavioural choice; formal and other modes remain strict',()=>{
  const partial='evidence_supported_only_v1';
  expect(effectiveCoveragePolicy(partial,'openrouter',false,'behavioural')).toBe(partial);
  expect(effectiveCoveragePolicy(partial,'openrouter',true,'behavioural')).toBe('strict_full_v1');
  expect(effectiveCoveragePolicy(partial,'rule_based',false,'behavioural')).toBe('strict_full_v1');
  expect(effectiveCoveragePolicy(partial,'openrouter',false,'paired_contextual')).toBe('strict_full_v1');
  expect(effectiveCoveragePolicy('strict_full_v1','openrouter',false,'behavioural')).toBe('strict_full_v1');
});
