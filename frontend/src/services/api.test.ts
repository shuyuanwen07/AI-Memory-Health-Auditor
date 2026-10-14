import { api, apiErrorMessage } from './api';

test('keeps formal Experiment B and exploratory matrix submissions on separate endpoints',async()=>{
  const response={dataset_id:'synthetic-v1',dataset_version:'1',dataset_fingerprint_sha256:'a'.repeat(64),pilot_id:'pilot-v1',condition_count:2,repetition_count:3,scenario_count:1,total_audit_runs:6,total_target_calls:24,scenarios:[{source_conversation_id:'S1',experiment_id:'EXP1',run_ids:['R1','R2','R3','R4','R5','R6'],test_count:4}],notice:'fixture'};
  const transport=vi.fn().mockImplementation(()=>new Response(JSON.stringify(response),{status:201}));vi.stubGlobal('fetch',transport);
  const payload={study_design:{sampling_rule:'Select the complete fixed source inventory before viewing results.',primary_outcome:'freshness'},repetitions:3};
  try{
    await api.createFormalSyntheticMatrix(payload);
    await api.createExploratorySyntheticMatrix({repetitions:1});
    expect(transport.mock.calls[0][0]).toBe('/api/v1/research/formal/synthetic-matrix');
    expect(transport.mock.calls[1][0]).toBe('/api/v1/research/exploratory/synthetic-matrix');
    expect(JSON.parse(transport.mock.calls[0][1].body)).toEqual(payload);
  }finally{vi.unstubAllGlobals();}
});

test('selected assessor requests carry only assessor settings and preserve the original default request',async()=>{
  const transport=vi.fn().mockImplementation(async()=>new Response(JSON.stringify({run_id:'PREPARED',status:'TESTS_EXECUTED'}),{status:201}));
  vi.stubGlobal('fetch',transport);
  try {
    await api.prepareReassessment('ORIGINAL');
    expect(transport.mock.calls[0][1].body).toBeUndefined();
    const selection={evaluator_provider:'openrouter' as const,evaluator_model:'anthropic/fixed-claude-test'};
    await api.prepareReassessment('ORIGINAL',selection);
    expect(transport.mock.calls[1][0]).toBe('/api/v1/audits/ORIGINAL/reassessment');
    expect(JSON.parse(transport.mock.calls[1][1].body)).toEqual(selection);
    expect(transport.mock.calls[1][1].method).toBe('POST');
  } finally {vi.unstubAllGlobals();}
});

it('explains missing pilot provenance without an internal field name', () => {
  const message = apiErrorMessage([{ loc: ['body', 'package', 'annotation_mode'], msg: 'Field required' }]);
  expect(message).toContain('independent human review or an AI-assisted dry run');
  expect(message).toContain('upload the corrected package');
  expect(message).not.toContain('annotation_mode');
});

test('explains structured input errors using a friendly field name', () => {
  expect(apiErrorMessage([{ loc: ['body', 'canonical_value'], msg: 'String should have at most 4000 characters' }])).toBe('Memory text: String should have at most 4000 characters');
  expect(apiErrorMessage({ unexpected: true })).not.toContain('[object Object]');
});

test('groups repeated review-label errors while retaining different input problems', () => {
  const repeated = Array.from({length:90}, (_, index) => ({
    loc:['body','package','annotators',0,'labels',index],
    msg:'Value error, Invalid relationship_type label. Allowed values: UPDATE, none.',
  }));
  const message=apiErrorMessage([...repeated,{loc:['body','timestamp'],msg:'Invalid date'}]);
  expect(message.match(/Invalid relationship type label/g)).toHaveLength(1);
  expect(message).toContain('90 occurrences');
  expect(message).toContain('Date and time: Invalid date');
  expect(message).not.toContain('relationship_type');
  expect(message.length).toBeLessThan(250);
});

test('explains a lost connection without automatically repeating a write', async () => {
  const transport = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
  vi.stubGlobal('fetch', transport);
  try {
    await expect(api.createConversation(true, '[User] I prefer Rust.')).rejects.toThrow('Connection to the audit service was interrupted');
    expect(transport).toHaveBeenCalledTimes(1);
  } finally { vi.unstubAllGlobals(); }
});

test('persists the selected source origin when importing a conversation', async () => {
  const response = { conversation_id:'C-SYN', created_at:'2026-01-01T00:00:00Z', authorised:true, source_origin:'synthetic', messages:[] };
  const transport=vi.fn().mockResolvedValue(new Response(JSON.stringify(response),{status:201}));
  vi.stubGlobal('fetch',transport);
  try {
    await api.createConversation(true,'[User] Synthetic test fact.',null,'conversation-request-0001','synthetic');
    expect(JSON.parse(transport.mock.calls[0][1].body)).toEqual({authorised:true,pasted_text:'[User] Synthetic test fact.',messages:null,creation_request_key:'conversation-request-0001',source_origin:'synthetic'});
  } finally { vi.unstubAllGlobals(); }
});

test('sends session cookies and the CSRF header for a protected write',async()=>{
  const {setWorkspaceCsrf}=await import('./access');setWorkspaceCsrf('synthetic-csrf-value');
  const transport=vi.fn().mockResolvedValue(new Response(JSON.stringify({signed_out:true}),{status:200}));vi.stubGlobal('fetch',transport);
  try{await api.signOut();const options=transport.mock.calls[0][1];expect(options.credentials).toBe('include');expect(options.headers.get('X-CSRF-Token')).toBe('synthetic-csrf-value');}
  finally{setWorkspaceCsrf(null);vi.unstubAllGlobals();}
});

test('submits a separate Experiment A human validity decision',async()=>{
  const transport=vi.fn().mockResolvedValue(new Response(JSON.stringify({test_id:'TEST1',human_validity_status:'accepted'}),{status:200}));
  vi.stubGlobal('fetch',transport);
  try{
    await api.reviewTestHumanValidity('RUN1','TEST1','accepted','Researcher A','Question is supported by the cited fact.');
    expect(transport.mock.calls[0][0]).toBe('/api/v1/audits/RUN1/tests/TEST1/human-validity-review');
    expect(transport.mock.calls[0][1].method).toBe('PATCH');
    expect(JSON.parse(transport.mock.calls[0][1].body)).toEqual({decision:'accepted',reviewer_pseudonym:'Researcher A',note:'Question is supported by the cited fact.'});
  }finally{vi.unstubAllGlobals();}
});

test('uses the page origin for default API traffic instead of another localhost port',async()=>{
  const transport=vi.fn().mockResolvedValue(new Response(JSON.stringify({mode:'local'}),{status:200}));vi.stubGlobal('fetch',transport);
  try{await api.accessStatus();expect(transport.mock.calls[0][0]).toBe('/api/v1/access/status');}
  finally{vi.unstubAllGlobals();}
});

test.each([
  ['   ','/api/v1/access/status'],
  ['https://audit.example.test/api/v1','https://audit.example.test/api/v1/access/status'],
])('keeps blank and explicit API origin configuration usable (%s)',async(configured,expected)=>{
  vi.stubEnv('VITE_API_URL',configured);vi.resetModules();
  const transport=vi.fn().mockResolvedValue(new Response(JSON.stringify({mode:'local'}),{status:200}));vi.stubGlobal('fetch',transport);
  try{const {api:configuredApi}=await import('./api');await configuredApi.accessStatus();expect(transport.mock.calls[0][0]).toBe(expected);}
  finally{vi.unstubAllEnvs();vi.unstubAllGlobals();vi.resetModules();}
});

test('explains an unavailable proxy service without blaming input or repeating a write',async()=>{
  const transport=vi.fn().mockResolvedValue(new Response('Bad Gateway',{status:502}));vi.stubGlobal('fetch',transport);
  try{await expect(api.createConversation(true,'[User] I prefer Rust.')).rejects.toThrow('Check saved progress before retrying');expect(transport).toHaveBeenCalledTimes(1);}
  finally{vi.unstubAllGlobals();}
});


test('research file requests default to no permission and forward only explicit authorisation',async()=>{
  const transport=vi.fn().mockImplementation(()=>new Response('{}',{status:200}));
  vi.stubGlobal('fetch',transport);
  try {
    await api.validateAnnotationDataset({dataset_id:'synthetic-fixture'});
    await api.researchValidity({},{});
    await api.analysePilot({});
    await api.validateAnnotationDataset({},true);
    await api.researchValidity({},{},true);
    await api.analysePilot({},true);
    expect(transport.mock.calls.slice(0,3).map(call=>JSON.parse(call[1].body).source_authorised)).toEqual([false,false,false]);
    expect(transport.mock.calls.slice(3).map(call=>JSON.parse(call[1].body).source_authorised)).toEqual([true,true,true]);
    expect(apiErrorMessage([{loc:['body','source_authorised'],msg:'Input should be a valid boolean'}])).toContain('Source processing permission');
  } finally {vi.unstubAllGlobals();}
});
