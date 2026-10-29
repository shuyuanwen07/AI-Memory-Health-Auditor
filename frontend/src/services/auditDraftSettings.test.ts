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
test('preserves explicit history/context controls and rejects invalid saved values',()=>{
  const profile={...defaultTargetProfile,retain_assistant_history:true,retrieve_message_context:true};
  expect(parseAuditDraftSettings({...valid,targetProfile:profile})?.targetProfile).toMatchObject({retain_assistant_history:true,retrieve_message_context:true});
  expect(parseAuditDraftSettings({...valid,targetProfile:{...profile,retain_assistant_history:'true'}})).toBeNull();
  expect(parseAuditDraftSettings({...valid,targetProfile:{...profile,retrieve_message_context:1}})).toBeNull();
});
test('preserves the optional identity pass and its separate output budget',()=>{
  const profile={...defaultTargetProfile,identity_analysis:'evidence_links',identity_analysis_output_token_limit:4096};
  expect(parseAuditDraftSettings({...valid,targetProfile:profile})?.targetProfile).toMatchObject({identity_analysis:'evidence_links',identity_analysis_output_token_limit:4096});
  for(const patch of [{identity_analysis:'automatic'},{identity_analysis_output_token_limit:511},{identity_analysis_output_token_limit:'4096'}]){
    expect(parseAuditDraftSettings({...valid,targetProfile:{...profile,...patch}})).toBeNull();
  }
});

test('legacy drafts default to stopping while explicit auxiliary refusal continuation is preserved',()=>{
  const legacy={...defaultTargetProfile};
  delete legacy.identity_analysis_failure_policy;
  expect(parseAuditDraftSettings({...valid,targetProfile:legacy})?.targetProfile.identity_analysis_failure_policy).toBe('fail_closed');
  const optedIn={...defaultTargetProfile,identity_analysis:'evidence_links',identity_analysis_failure_policy:'continue_without_advisory'};
  expect(parseAuditDraftSettings({...valid,targetProfile:optedIn})?.targetProfile.identity_analysis_failure_policy).toBe('continue_without_advisory');
  expect(parseAuditDraftSettings({...valid,targetProfile:{...optedIn,identity_analysis_failure_policy:'automatic'}})).toBeNull();
});

test.each(['low','medium'] as const)('preserves optional %s target request through strict restore and cloning without filling omitted settings',effort=>{
  const restored=parseAuditDraftSettings({...valid,targetProfile:{...defaultTargetProfile,reasoning_effort:effort,identity_analysis_reasoning_effort:'low'}})!;
  expect(restored.targetProfile).toMatchObject({reasoning_effort:effort,identity_analysis_reasoning_effort:'low'});
  expect(structuredClone(restored.targetProfile)).toEqual(restored.targetProfile);
  const legacy=parseAuditDraftSettings(valid)!;
  expect(legacy.targetProfile).not.toHaveProperty('reasoning_effort');
  expect(legacy.targetProfile).not.toHaveProperty('identity_analysis_reasoning_effort');
  expect(legacy.targetProfile.output_token_limit).toBe(2048);
  expect(JSON.stringify(legacy.targetProfile)).not.toContain('reasoning_effort');
  for(const key of ['reasoning_effort','identity_analysis_reasoning_effort']){
    for(const value of [null,'high','LOW','',0,false,{},[]]){
      expect(parseAuditDraftSettings({...valid,targetProfile:{...defaultTargetProfile,[key]:value}})).toBeNull();
    }
  }
});

test('rejects medium auxiliary effort rather than silently changing it',()=>{
  expect(parseAuditDraftSettings({...valid,targetProfile:{...defaultTargetProfile,reasoning_effort:'medium',identity_analysis_reasoning_effort:'medium'}})).toBeNull();
});

test('preserves an explicit retention policy and never fills an absent legacy choice',()=>{
  expect(parseAuditDraftSettings(valid)?.targetProfile).not.toHaveProperty('retention_policy');
  for(const policy of ['scope_recency','source_coverage']){
    expect(parseAuditDraftSettings({...valid,targetProfile:{...defaultTargetProfile,retention_policy:policy}})?.targetProfile.retention_policy).toBe(policy);
  }
  for(const policy of [null,'automatic',false,{},[]]){
    expect(parseAuditDraftSettings({...valid,targetProfile:{...defaultTargetProfile,retention_policy:policy}})).toBeNull();
  }
});
test('coverage policy restores explicit opt-in and defaults old drafts to strict',()=>{
  expect(parseAuditDraftSettings(valid)?.coveragePolicy).toBe('strict_full_v1');
  expect(parseAuditDraftSettings({...valid,coveragePolicy:'evidence_supported_only_v1'})?.coveragePolicy).toBe('evidence_supported_only_v1');
  expect(parseAuditDraftSettings({...valid,coveragePolicy:'invented'})).toBeNull();
});
