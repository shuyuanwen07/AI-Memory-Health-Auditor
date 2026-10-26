import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { AuditComparison } from '../types/domain';
import { saveBlob } from '../services/download';
vi.mock('../services/download',()=>({saveBlob:vi.fn()}));
import { ComparisonVisualizations } from './ComparisonVisualizations';

// Unpaired questions improve the overall scores; only one canonical pair
// belongs in the default comparison chart.
const data = {
  before: { run: { model: 'Qwen', run_id: 'BEFORE' }, result: { dimensions: [
    { dimension: 'accuracy', passed: 4, total: 10, percentage: 40 },
  ] } },
  after: { run: { model: 'Qwen', run_id: 'AFTER' }, result: { dimensions: [
    { dimension: 'accuracy', passed: 9, total: 10, percentage: 90 },
  ] } },
  paired_tests: [{ dimension: 'accuracy', before: { passed: true }, after: { passed: false } }],
  counts: { fixed: 0, regressed: 1, still_failed: 0, still_passed: 0 },
} as unknown as AuditComparison;

test('charts actual paired outcomes, including regressions, rather than full-suite improvement', async () => {
  render(<ComparisonVisualizations data={data} />);
  const chart = screen.getByRole('img');
  expect(chart.textContent).toContain('before 100% (1/1), after 0% (0/1), change -100 pp');
  expect(chart.textContent).toContain('Freshness: before Not scored');
  await userEvent.click(screen.getByRole('button', { name: 'Full test suites' }));
  expect(chart.textContent).toContain('before 40% (4/10), after 90% (9/10), change No comparison');
});

test('does not invent zero bars or a delta when no frozen questions can be paired', () => {
  render(<ComparisonVisualizations data={{ ...data, paired_tests: [] }} />);
  expect(screen.queryByRole('img')).toBeNull();
  expect(screen.getByText(/No shared questions with comparable decided assessments/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Save chart (SVG)' })).toBeNull();
  expect(screen.queryByLabelText('Shared question outcomes')).toBeNull();
});


test('retains the reused-answer limitation inside the exportable SVG',()=>{
  render(<ComparisonVisualizations data={{...data,answer_provenance:'same_saved_answers',after:{...data.after,run:{...data.after.run,reproducibility:{assessment_source_run_id:'BEFORE'}}}} as AuditComparison}/>);
  const chart=screen.getByRole('img');
  expect(chart.textContent).toContain('Saved-answer assessment pass rates');
  expect(chart.textContent).toContain('Reused answers · assessment changes, not model improvement');
  expect(chart.textContent).not.toContain('before and after improvement');
});


test('offers the exact export source if the browser cannot save a chart',async()=>{
  vi.mocked(saveBlob).mockImplementationOnce(()=>{throw new Error('Download unavailable');});
  render(<ComparisonVisualizations data={{...data,answer_provenance:'same_saved_answers',after:{...data.after,run:{...data.after.run,reproducibility:{assessment_source_run_id:'BEFORE'}}}} as AuditComparison}/>);
  await userEvent.click(screen.getByRole('button',{name:'Save chart (SVG)'}));
  expect(screen.getByRole('status')).toHaveTextContent('could not start the download');
  await userEvent.click(screen.getByText('Last prepared chart source (SVG)'));
  const source=screen.getByRole('textbox',{name:'Prepared chart SVG'});
  const markup=(source as HTMLTextAreaElement).value;
  expect(markup).toContain('Reused answers · assessment changes, not model improvement');
  expect(new DOMParser().parseFromString(markup,'image/svg+xml').querySelector('parsererror')).toBeNull();
  expect(source).toHaveAttribute('readonly');
});


test('identical answers with recorded shared provenance retain the assessment-only explanation',()=>{
  render(<ComparisonVisualizations data={{...data,answer_provenance:'same_saved_answers',after:{...data.after,run:{...data.after.run,reproducibility:{assessment_source_run_id:'BEFORE'}}}} as AuditComparison}/>);
  expect(screen.getByText(/Both sides reuse the exact same original answers/)).toBeTruthy();
  expect(screen.getByRole('img').textContent).toContain('assessment changes, not model improvement');
});


test('unknown answer lineage does not invent judgement-only differences in chart or export',()=>{
  render(<ComparisonVisualizations data={{...data,answer_provenance:'unknown_saved_answers',after:{...data.after,run:{...data.after.run,reproducibility:{assessment_source_run_id:'BEFORE'}}}} as AuditComparison}/>);
  expect(screen.getByText(/Answer provenance is incomplete or mixed/)).toBeTruthy();
  expect(screen.getByRole('img').textContent).toContain('source relation unverified');
  expect(screen.getByRole('img').textContent).not.toContain('assessment changes, not model improvement');
});


test('export preserves denominators, settings and comparison limits without copying source text',async()=>{
  vi.mocked(saveBlob).mockImplementation(()=>{});
  const compared={...data,answer_provenance:'different_saved_executions',shared_question_count:1,
    before:{...data.before,run:{...data.before.run,temperature:0,evaluator_provider:'rule_based',evaluator_model:'rule-based-v4',reproducibility:{assessment_source_run_id:'ORIGINAL_A',private_note:'PRIVATE SOURCE CONTENT'}}},
    after:{...data.after,run:{...data.after.run,temperature:0,reproducibility:{assessment_source_run_id:'ORIGINAL_B'}}},
    setting_differences:[{field:'target_configuration',label:'Reader behaviour',before:'weak',after:'strong'},
      {field:'target_memory_profile',label:'Memory profile',before:'PRIVATE SOURCE CONTENT',after:'PRIVATE INSTRUCTIONS'}],
    warnings:['Reader behaviour also changes.'],excluded_assessments:[{reason:'different standards'}],
  } as unknown as AuditComparison;
  render(<ComparisonVisualizations data={compared}/>);
  await userEvent.click(screen.getByRole('button',{name:'Full test suites'}));
  await userEvent.click(screen.getByRole('button',{name:'Save chart (SVG)'}));
  await userEvent.click(screen.getByText('Last prepared chart source (SVG)'));
  const markup=(screen.getByRole('textbox',{name:'Prepared chart SVG'}) as HTMLTextAreaElement).value;
  const parsed=new DOMParser().parseFromString(markup,'image/svg+xml');
  expect(parsed.querySelector('parsererror')).toBeNull();
  const metadata=JSON.parse(parsed.querySelector('metadata')!.textContent!);
  expect(metadata.scope).toBe('full_test_suites');
  expect(metadata.answer_provenance).toBe('different_saved_executions');
  expect(metadata.before.assessment_source_run_id).toBe('ORIGINAL_A');
  expect(metadata.before.temperature).toBe(0);
  expect(metadata.dimensions[0]).toMatchObject({beforePassed:4,beforeTotal:10,afterPassed:9,afterTotal:10,delta:null});
  expect(markup).toContain('Full suites may differ; these scores are descriptive only.');
  expect(markup).toContain('Configurations differ; this does not isolate one memory mechanism.');
  expect(markup).toContain('Assessment standards differ; excluded questions cannot establish improvement.');
  expect(markup).not.toContain('PRIVATE SOURCE CONTENT');
  expect(markup).not.toContain('PRIVATE INSTRUCTIONS');
  expect(Number(parsed.documentElement.getAttribute('viewBox')!.split(' ')[3])).toBeGreaterThan(420);
});

test.each(['low','medium'] as const)('chart configuration evidence preserves explicit %s versus omitted settings and server fingerprints',async effort=>{
  const {defaultTargetProfile}=await import('./TargetProfileEditor');
  const compared={...data,
    before:{...data.before,run:{...data.before.run,target_memory_profile:{...defaultTargetProfile},reproducibility:{configuration_fingerprint:'legacy-configuration-signature'}}},
    after:{...data.after,run:{...data.after.run,target_memory_profile:{...defaultTargetProfile,reasoning_effort:effort,identity_analysis_reasoning_effort:'low'},reproducibility:{configuration_fingerprint:`explicit-${effort}-configuration-signature`}}},
  } as unknown as AuditComparison;
  render(<ComparisonVisualizations data={compared}/>);
  await userEvent.click(screen.getByRole('button',{name:'Save chart (SVG)'}));
  await userEvent.click(screen.getByText('Last prepared chart source (SVG)'));
  const markup=(screen.getByRole('textbox',{name:'Prepared chart SVG'}) as HTMLTextAreaElement).value;
  const metadata=JSON.parse(new DOMParser().parseFromString(markup,'image/svg+xml').querySelector('metadata')!.textContent!);
  expect(metadata.before.memory_profile).not.toHaveProperty('reasoning_effort');
  expect(metadata.before.memory_profile).not.toHaveProperty('identity_analysis_reasoning_effort');
  expect(metadata.after.memory_profile).toMatchObject({reasoning_effort:effort,identity_analysis_reasoning_effort:'low'});
  expect(metadata.before.configuration_fingerprint).toBe('legacy-configuration-signature');
  expect(metadata.after.configuration_fingerprint).toBe(`explicit-${effort}-configuration-signature`);
});
