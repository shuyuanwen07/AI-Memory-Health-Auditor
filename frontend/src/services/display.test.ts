import { assessmentLabel, auditMethodLabel, friendlyText, modelDisplayName } from './display';

test('labels declared methods and preserves uncertainty in incomplete historical settings',()=>{
  expect(auditMethodLabel({pipeline_provider:'openrouter',evaluator_provider:'openrouter',reproducibility:{auditor_method:'hybrid'} as any})).toBe('Model tests + hybrid review');
  expect(auditMethodLabel({pipeline_provider:'rule_based',evaluator_provider:'openrouter'})).toBe('Rule tests + AI review');
  expect(auditMethodLabel({pipeline_provider:'openrouter',evaluator_provider:'rule_based'})).toBe('Model tests + rule review');
  expect(auditMethodLabel({pipeline_provider:undefined,evaluator_provider:undefined} as any)).toBe('Audit method not recorded');
});

test('keeps the finding readable without displaying linked internal evidence IDs', () => {
  const text = friendlyText('Failed freshness: expected PostgreSQL. Evidence records: M046299B31D45700D0AA4190E0BADC1, M001.');
  expect(text).toContain('expected PostgreSQL');
  expect(text).not.toContain('M046299');
  expect(text).not.toContain('M001');
  expect(text).toContain('Reference memories are listed in this explanation.');
  expect(text).not.toContain('were checked');
});

test.each(['none linked to this test','None',''])('missing reference links %s do not become a verified-evidence claim',(references)=>{
  const original=`Failed accuracy. Evidence records: ${references}.`;
  const displayed=friendlyText(original);
  expect(displayed).toContain('No reference memories are listed in this explanation.');
  expect(displayed).not.toContain('were checked');
  expect(original).toContain(`Evidence records: ${references}.`);
});

test('unknown reference text stays an inspection request rather than an invented link or verification',()=>{
  const displayed=friendlyText('Evidence records: unavailable.');
  expect(displayed).toBe('Review the reference evidence for this assessment.');
  expect(displayed).not.toContain('links are recorded');
});

test('a narrative starting with none is not mistaken for an empty reference list',()=>{
  const displayed=friendlyText('Evidence records: none are omitted; M001.');
  expect(displayed).toBe('Review the reference evidence for this assessment.');
  expect(displayed).not.toContain('No reference memories');
});

test('keeps fallback assessments distinguishable and handles missing legacy metadata', () => {
  expect(assessmentLabel('fallback-rule-based-v8')).toContain('AI assessment unavailable');
  expect(assessmentLabel()).toBe('Automated assessment');
});


test('names model families clearly while retaining distinguishing version numbers', () => {
  expect(modelDisplayName('rule-based-target-ai')).toBe('Local rule-based baseline');
  expect(modelDisplayName('qwen3:1.7b')).toBe('qwen3:1.7b');
  expect(modelDisplayName('google/gemini-2.5-flash-lite')).toBe('Gemini 2.5 Flash Lite');
  expect(modelDisplayName('openai/gpt-5.4')).toBe('GPT 5.4');
  expect(modelDisplayName('anthropic/claude-sonnet-4.6')).toBe('Claude Sonnet 4.6');
});


test('automated explanations use readable dimension and assessment names', () => {
  const text = friendlyText('Passed conflict_resolution: matched ground-truth terms. 2 gold evidence record(s) are linked; this lexical verdict does not establish target memory use.');
  expect(text).toContain('Conflict Resolution');
  expect(text).toContain('reference terms');
  expect(text).toContain('2 reference memories');
  expect(text).toContain('word-match assessment');
  expect(text).toContain('does not establish target memory use');
  expect(text).not.toContain('conflict_resolution');
});


test('a single supporting memory uses a singular description', () => {
  expect(friendlyText('1 gold evidence record(s) are linked.')).toBe('1 reference memory is linked.');
});
