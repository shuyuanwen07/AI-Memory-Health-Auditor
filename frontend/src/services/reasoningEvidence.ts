/** Display recorded request controls without claiming a measured provider effect. */
const record=(value:unknown):value is Record<string,unknown>=>typeof value==='object'&&value!==null&&!Array.isArray(value);
export function reasoningRequestDescription(evidence:unknown):string {
  if(!record(evidence))return 'Not recorded. Actual reasoning effort is not reported.';
  const requested=evidence.requested_reasoning_effort;
  const contract=record(evidence.request_contract)?evidence.request_contract:null;
  const control=contract?.version==='openrouter-request-contract-v1'&&record(contract.reasoning)?contract.reasoning:null;
  const value=record(control?.value)?control.value:null;
  if(requested==='low'||requested==='medium') {
    const sent=control?.present===true&&(value?.effort==='low'||value?.effort==='medium')
      ? `the saved request contract includes ${value.effort}${value.effort===requested?'':', which differs from the requested setting'}`
      :control?.present===false?'the saved contract records no reasoning setting':'the sent setting is not recorded';
    return `${requested==='medium'?'Medium':'Low'} requested; ${sent}. Actual reasoning effort is not reported.`;
  }
  if(control?.present===false)return 'No reasoning setting sent in the saved request contract (provider default). Actual reasoning effort is not reported.';
  if(control?.present===true&&(value?.effort==='low'||value?.effort==='medium'))return `The saved request contract includes ${value.effort}; the requested setting is not recorded separately. Actual reasoning effort is not reported.`;
  return 'Not recorded. Actual reasoning effort is not reported.';
}
