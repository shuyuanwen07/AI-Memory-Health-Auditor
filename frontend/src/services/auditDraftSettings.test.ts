import { parseAuditDraftSettings } from './auditDraftSettings';
import { defaultTargetProfile } from '../components/TargetProfileEditor';
const valid={selectedStrategies:['scope_aware'],targetProviders:['ollama'],targetModels:{ollama:'qwen3:1.7b'},pipelineProvider:'rule_based',evaluatorProvider:'rule_based',pipelineModel:'rules',evaluatorModel:'rules',budget:4,repetitions:1,suiteMode:'behavioural',maintenancePolicy:'update_aware_consolidation',targetMemoryCapacity:50,targetMemoryWriter:'rule_based',targetProfile:defaultTargetProfile,targetSystem:'controlled-memory',compareAuditors:false};
test('rejects corrupt control values while permitting intentionally empty model selections',()=>{
  expect(parseAuditDraftSettings({...valid,targetModels:{ollama:''}})?.targetModels.ollama).toBe('');
  for(const change of [{targetProviders:'ollama'},{selectedStrategies:['unknown']},{targetModels:{ollama:[]}}, {budget:NaN},{budget:101},{repetitions:0},{targetProfile:{...defaultTargetProfile,output_token_limit:8193}},{targetProfile:{...defaultTargetProfile,additional_instructions:[]}}]){
    expect(parseAuditDraftSettings({...valid,...change})).toBeNull();
  }
});
test('normalises legacy limits to unknown and strips unknown profile fields',()=>{
  const profile={...defaultTargetProfile,output_token_limit:null,unexpected:'discard'};
  expect(parseAuditDraftSettings({...valid,targetProfile:profile})?.targetProfile).not.toHaveProperty('unexpected');
  expect(parseAuditDraftSettings({...valid,targetProfile:profile})?.targetProfile.output_token_limit).toBeNull();
});
test('accepts the Experiment A contextual/indirect suite mode',()=>{
  expect(parseAuditDraftSettings({...valid,suiteMode:'contextual_indirect'})?.suiteMode).toBe('contextual_indirect');
});
