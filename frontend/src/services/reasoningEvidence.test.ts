import { describe,test,expect } from 'vitest';
import { reasoningRequestDescription } from './reasoningEvidence';
const contract=(reasoning:unknown)=>({version:'openrouter-request-contract-v1',reasoning});
describe('recorded reasoning request descriptions',()=>{
  test('legacy absence and reported token counts do not prove omission or effective effort',()=>{
    for(const evidence of [undefined,{}, {reasoning_tokens:0},{reasoning_tokens:200}])expect(reasoningRequestDescription(evidence)).toBe('Not recorded. Actual reasoning effort is not reported.');
  });
  test('separates explicit low request from saved wire contract and unknown actual effort',()=>{
    expect(reasoningRequestDescription({requested_reasoning_effort:'low'})).toContain('sent setting is not recorded');
    expect(reasoningRequestDescription({requested_reasoning_effort:'low',request_contract:contract({present:true,value:{effort:'low'}})})).toBe('Low requested; the saved request contract includes low. Actual reasoning effort is not reported.');
    expect(reasoningRequestDescription({requested_reasoning_effort:'low',request_contract:contract({present:false})})).toContain('saved contract records no reasoning setting');
  });
  test('only an explicit known contract proves no setting was sent',()=>{
    expect(reasoningRequestDescription({request_contract:contract({present:false})})).toContain('No reasoning setting sent');
    expect(reasoningRequestDescription({request_contract:{version:'unknown',reasoning:{present:false}}})).toContain('Not recorded.');
    expect(reasoningRequestDescription({request_contract:contract({present:true,value:null})})).toContain('Not recorded.');
  });
  test('preserves medium request and saved control independently without inferring effective effort',()=>{
    expect(reasoningRequestDescription({requested_reasoning_effort:'medium'})).toContain('Medium requested; the sent setting is not recorded');
    expect(reasoningRequestDescription({requested_reasoning_effort:'medium',request_contract:contract({present:true,value:{effort:'medium'}})})).toBe('Medium requested; the saved request contract includes medium. Actual reasoning effort is not reported.');
    expect(reasoningRequestDescription({requested_reasoning_effort:'medium',request_contract:contract({present:true,value:{effort:'low'}})})).toContain('includes low, which differs from the requested setting');
    expect(reasoningRequestDescription({request_contract:contract({present:true,value:{effort:'medium'}})})).toContain('includes medium; the requested setting is not recorded separately');
    expect(reasoningRequestDescription({requested_reasoning_effort:'medium',request_contract:contract({present:false})})).toContain('saved contract records no reasoning setting');
  });
});
