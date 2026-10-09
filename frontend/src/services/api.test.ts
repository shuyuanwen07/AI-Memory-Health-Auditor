import { api, apiErrorMessage } from './api';

test('explains structured input errors using a friendly field name', () => {
  expect(apiErrorMessage([{ loc: ['body', 'canonical_value'], msg: 'String should have at most 4000 characters' }])).toBe('Memory text: String should have at most 4000 characters');
  expect(apiErrorMessage({ unexpected: true })).not.toContain('[object Object]');
});

test('explains a lost connection without automatically repeating a write', async () => {
  const transport = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
  vi.stubGlobal('fetch', transport);
  try {
    await expect(api.createConversation(true, '[User] I prefer Rust.')).rejects.toThrow('Connection to the audit service was interrupted');
    expect(transport).toHaveBeenCalledTimes(1);
  } finally { vi.unstubAllGlobals(); }
});

test('sends session cookies and the CSRF header for a protected write',async()=>{
  const {setWorkspaceCsrf}=await import('./access');setWorkspaceCsrf('synthetic-csrf-value');
  const transport=vi.fn().mockResolvedValue(new Response(JSON.stringify({signed_out:true}),{status:200}));vi.stubGlobal('fetch',transport);
  try{await api.signOut();const options=transport.mock.calls[0][1];expect(options.credentials).toBe('include');expect(options.headers.get('X-CSRF-Token')).toBe('synthetic-csrf-value');}
  finally{setWorkspaceCsrf(null);vi.unstubAllGlobals();}
});
