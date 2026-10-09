import { assessmentLabel, friendlyText } from './display';

test('keeps the finding readable without displaying linked internal evidence IDs', () => {
  const text = friendlyText('Failed freshness: expected PostgreSQL. Evidence records: M046299B31D45700D0AA4190E0BADC1, M001.');
  expect(text).toContain('expected PostgreSQL');
  expect(text).not.toContain('M046299');
  expect(text).not.toContain('M001');
  expect(text).toContain('Supporting memories were checked');
});

test('keeps fallback assessments distinguishable and handles missing legacy metadata', () => {
  expect(assessmentLabel('fallback-rule-based-v8')).toContain('AI assessment unavailable');
  expect(assessmentLabel()).toBe('Automated assessment');
});
