import {describe,it,expect} from 'vitest';
import {defaultTargetProfile} from '../components/TargetProfileEditor';
import {parseAuditDraftSettings} from './auditDraftSettings';

const settings={selectedStrategies:['weak_first_hit'],targetProviders:['openrouter'],targetModels:{openrouter:'openai/gpt-6-luna'},pipelineProvider:'openrouter',evaluatorProvider:'openrouter',pipelineModel:'openai/gpt-6-luna',evaluatorModel:'openai/gpt-6-luna',budget:4,repetitions:1,suiteMode:'behavioural',maintenancePolicy:'append_only',targetMemoryCapacity:50,targetMemoryWriter:'rule_based',targetProfile:defaultTargetProfile,targetSystem:'controlled-memory',compareAuditors:false};

describe('strict optional answer validation draft fields',()=>{
  it('preserves legacy omission and explicit off without adding paid controls',()=>{
    const legacy=parseAuditDraftSettings(settings)!;
    expect(legacy).not.toBeNull();
    expect(legacy.targetProfile).not.toHaveProperty('answer_validation');
    expect(legacy.targetProfile).not.toHaveProperty('answer_validation_output_token_limit');
    expect(legacy.targetProfile).not.toHaveProperty('answer_validation_reasoning_effort');
    expect(parseAuditDraftSettings({...settings,targetProfile:{...defaultTargetProfile,answer_validation:'off'}})?.targetProfile.answer_validation).toBe('off');
  });

  it.each(['low','medium'])('retains requested %s and independent budget across save/restore',effort=>{
    const profile={...defaultTargetProfile,answer_validation:'source_grounding',answer_validation_output_token_limit:8192,answer_validation_reasoning_effort:effort};
    expect(parseAuditDraftSettings({...settings,targetProfile:profile})?.targetProfile).toMatchObject(profile);
  });

  it.each([
    {answer_validation:null},{answer_validation:'automatic'},
    {answer_validation_output_token_limit:null},{answer_validation_output_token_limit:511},
    {answer_validation_output_token_limit:8193},{answer_validation_output_token_limit:'8192'},
    {answer_validation_output_token_limit:1024.5},{answer_validation_output_token_limit:true},
    {answer_validation_reasoning_effort:null},{answer_validation_reasoning_effort:'high'},
  ])('rejects invalid optional values instead of silently dropping them: %j',patch=>{
    expect(parseAuditDraftSettings({...settings,targetProfile:{...defaultTargetProfile,...patch}})).toBeNull();
  });
});
