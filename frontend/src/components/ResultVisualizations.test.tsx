import { UIProvider } from './ui';
import { render, screen, waitFor } from '@testing-library/react';
import { ComparisonVisualizations, ScoreRadarChart } from './ResultVisualizations';
import type { AuditResult } from '../types/domain';
import { calculateExperimentStatistics } from './ExperimentStatistics';

function result(runId: string, overall: number, freshness: number): AuditResult {
  return {
    run_id: runId,
    overall_score: overall,
    tests_passed: 3,
    tests_total: 4,
    dimensions: [
      { dimension: 'accuracy', percentage: 100, passed: 1, total: 1 },
      { dimension: 'freshness', percentage: freshness, passed: freshness / 100, total: 1 },
      { dimension: 'conflict_resolution', percentage: 50, passed: 1, total: 2 },
      { dimension: 'appropriate_use', percentage: 75, passed: 3, total: 4 },
    ],
    failures: Array.from({ length: freshness < 100 ? 1 : 0 }, (_, index) => ({
      failure_id: `${runId}-failure-${index}`,
      test: { test_id: `T-${runId}-${index}`, run_id: runId, dimension: 'freshness', prompt: 'What database is current?', expected_behavior: 'Use PostgreSQL.', supporting_memory_ids: ['M002'], generator_version: 'test-v1' },
      response: { response_id: `R-${runId}-${index}`, test_id: `T-${runId}-${index}`, run_id: runId, response_text: 'MySQL', model: 'target', temperature: 0, created_at: '2026-01-01T00:00:00Z' },
      evaluation: { evaluation_id: `E-${runId}-${index}`, test_id: `T-${runId}-${index}`, response_id: `R-${runId}-${index}`, passed: false, failure_type: 'freshness', reason: 'An outdated value was used.', evidence_memory_ids: ['M002'], evaluator: 'rule-v1' },
      evidence: [],
    })),
  };
}

test('keeps different frozen conditions separate even when their display names match', () => {
  const runs = [
    {label:'Original configuration', groupLabel:'Same name', groupKey:'internal-condition-one', result:result('ONE',25,0)},
    {label:'Original configuration', groupLabel:'Same name', groupKey:'internal-condition-two', result:result('TWO',75,100)},
  ];
  const groups = calculateExperimentStatistics(runs);
  expect(groups.map(group => group.overallAverage)).toEqual([25,75]);
  expect(groups.map(group => group.runs)).toEqual([1,1]);
  render(<ComparisonVisualizations runs={runs} />);
  expect(screen.getByRole('img', {name:/Horizontal bar chart.*Same name · Setting 1: 25%.*Same name · Setting 2: 75%/})).toBeInTheDocument();
  expect(screen.queryByText(/internal-condition/)).not.toBeInTheDocument();
});

test('a completed assessor keeps its plan colour when preceding assessors have no result',()=>{
  const {container}=render(<ComparisonVisualizations compact hideFailureChart runs={[
    {label:'Third assessor',groupKey:'third-assessor',colour:'#b7791f',result:result('SAVED',75,100)},
  ]}/>);
  const bars=container.querySelectorAll('.dimension-column');
  expect(bars.length).toBeGreaterThan(0);
  bars.forEach(bar=>expect(bar).toHaveStyle({backgroundColor:'#b7791f'}));
});

test('does not invent zero variation when a repeated condition has only one decided score', () => {
  const pending: AuditResult = {...result('PENDING',0,0), overall_score:null, tests_passed:0, tests_total:0, failures:[], uncertain_count:4,
    dimensions:result('PENDING',0,0).dimensions.map(score => ({...score, percentage:null, passed:0, total:0, uncertain_count:1}))};
  render(<ComparisonVisualizations runs={[
    {label:'First attempt', groupKey:'same-condition', groupLabel:'Repeated setting', result:result('SCORED',75,100)},
    {label:'Second attempt', groupKey:'same-condition', groupLabel:'Repeated setting', result:pending},
  ]} />);
  const chart = screen.getByRole('img', {name:/Horizontal bar chart.*Repeated setting: 75% tested-ability average · n=1 scored run; 4 decided answers; 4 awaiting review.*variation not measured/});
  expect(chart).toBeInTheDocument();
  expect(chart.getAttribute('aria-label')).not.toContain('± 0');
  expect(screen.getByRole('heading', {name:'Repeated setting'})).toBeInTheDocument();
  expect(screen.getAllByText('Scored runs').length).toBeGreaterThan(0);
});

test('keeps an entirely unmeasured condition visible as pending instead of plotting zero', () => {
  const pending: AuditResult = {...result('PENDING-ONLY', 0, 0), overall_score:null, tests_passed:0, tests_total:0,
    failures:[], uncertain_count:4, dimensions:result('PENDING-ONLY', 0, 0).dimensions.map(score =>
      ({...score, percentage:null, passed:0, total:0, uncertain_count:1}))};
  render(<ComparisonVisualizations runs={[{label:'Pending only', result:pending}]}/>);

  expect(screen.getByRole('img', {name:/Horizontal bar chart\. Pending only: Not measured.*n=0 scored runs; 0 decided answers; 4 awaiting review/})).toBeInTheDocument();
  expect(screen.getByRole('heading', {name:'Pending only'})).toBeInTheDocument();
  expect(screen.getAllByText('Awaiting review').length).toBeGreaterThan(0);
});

test('renders the accessible four-dimension Memory Health profile', () => {
  render(<ScoreRadarChart result={result('RUN-RADAR', 68.75, 50)} />);

  expect(screen.getByRole('heading', { name: 'Memory Health Profile' })).toBeTruthy();
  expect(screen.getByRole('img', { name: /Radar chart: Accuracy: 100%; Freshness: 50%/ })).toBeTruthy();
  expect(screen.getByText(/Conflict Resolution: 50%/)).toBeTruthy();
  expect(screen.getByText(/Appropriate Use: 75%/)).toBeTruthy();
});

test('keeps an untested dimension out of the chart as Not tested rather than zero', () => {
  const partial = result('RUN-PARTIAL', 100, 100);
  partial.dimensions = partial.dimensions.filter((item) => item.dimension !== 'conflict_resolution');
  render(<ScoreRadarChart result={partial} />);

  expect(screen.getByRole('img', { name: /Conflict Resolution: Not tested/ })).toBeTruthy();
  expect(screen.getByText(/Conflict Resolution: Not tested/)).toBeTruthy();
});

test('failure counts distinguish untested, pending-only and measured zero dimensions', () => {
  const partial = result('PARTIAL', 100, 100);
  partial.dimensions = partial.dimensions.filter(item => item.dimension !== 'conflict_resolution')
    .map(item => item.dimension === 'appropriate_use' ? {...item, percentage:null, passed:0, total:0, uncertain_count:1}
      : item.dimension === 'accuracy' ? {...item, uncertain_count:1} : item);
  partial.uncertain_count = 2;
  render(<ComparisonVisualizations runs={[{label:'Partial setting',result:partial}]} />);
  const chart = screen.getByRole('img', {name:/Grouped failure bar chart/});
  expect(chart).toHaveAccessibleName(/Accuracy: Partial setting 0 failures · 1 awaiting review · n=1 decided answer/);
  expect(chart).toHaveAccessibleName(/Freshness: Partial setting 0 failures · n=1 decided answer/);
  expect(chart).toHaveAccessibleName(/Conflict Resolution: Partial setting Not tested · n=0 decided answers/);
  expect(chart).toHaveAccessibleName(/Appropriate Use: Partial setting Awaiting review · n=0 decided answers · 1 awaiting review/);
});

test('renders overall, dimension, and failure comparison charts for experimental conditions', () => {
  render(<ComparisonVisualizations runs={[
    { label: 'Weak run one', groupLabel: 'Weak Memory', result: result('RUN-WEAK-1', 50, 0) },
    { label: 'Weak run two', groupLabel: 'Weak Memory', result: result('RUN-WEAK-2', 60, 25) },
    { label: 'Strong run', groupLabel: 'Strong Memory', result: result('RUN-STRONG-1', 90, 100) },
  ]} />);

  expect(screen.getByRole('heading', { name: 'Visual Comparison' })).toBeTruthy();
  expect(screen.getByRole('heading', { name: 'Tested Ability Average by Condition' })).toBeTruthy();
  expect(screen.getByRole('heading', { name: 'Dimension Comparison' })).toBeTruthy();
  expect(screen.getByRole('heading', { name: 'Failed Tests by Tested Ability' })).toBeTruthy();
  expect(screen.getByRole('img', { name: /Horizontal bar chart\. Weak Memory: 55%.*Strong Memory: 90%/ })).toBeTruthy();
  expect(screen.getByRole('img', { name: /Grouped bar chart\. Accuracy: Weak Memory 100% average · n=2 decided answers · 2 measured runs, Strong Memory 100% average · n=1 decided answer · 1 measured run/ })).toBeTruthy();
  expect(screen.getByRole('img', { name: /Grouped failure bar chart\. .*Freshness: Weak Memory 2 failures · n=2 decided answers, Strong Memory 0 failures · n=1 decided answer/ })).toBeTruthy();
});

test('keeps provider/model labels with dots as display names rather than Recharts data paths', () => {
  render(<ComparisonVisualizations runs={[
    { label: 'Ollama · qwen3:1.7b · Weak', result: result('RUN-DOTTED', 25, 0) },
    { label: 'Ollama · qwen3:1.7b · Strong', result: result('RUN-DOTTED-STRONG', 75, 100) },
  ]} />);

  // This accessible summary comes from the same keyed data series as the
  // rendered bars. A dotted display label must retain its actual values.
  expect(screen.getByRole('img', { name: /Accuracy: Ollama · qwen3:1.7b · Weak 100% average · n=1 decided answer · 1 measured run, Ollama · qwen3:1.7b · Strong 100% average · n=1 decided answer · 1 measured run/ })).toBeTruthy();
  expect(screen.getByRole('img', { name: /Freshness: Ollama · qwen3:1.7b · Weak 0% average · n=1 decided answer · 1 measured run, Ollama · qwen3:1.7b · Strong 100% average · n=1 decided answer · 1 measured run/ })).toBeTruthy();
  expect(screen.getByText(/Ollama · qwen3:1\.7b · Weak/)).toBeInTheDocument();
});


test('comparison distinguishes pending judgments from untested dimensions', () => {
  const pending = result('PENDING', 100, 100);
  pending.dimensions[3] = { dimension: 'appropriate_use', percentage: null, passed: 0, total: 0, uncertain_count: 1 };
  render(<ComparisonVisualizations runs={[{ label: 'Qwen pending', result: pending }]} />);
  expect(screen.getByRole('img', { name: /Grouped bar chart.*Appropriate Use: Qwen pending Awaiting review · n=0 decided answers · 1 awaiting review/ })).toBeTruthy();
  expect(screen.getAllByText(/Awaiting review/).length).toBeGreaterThanOrEqual(2);
});


test('shows pending coverage above aggregate charts instead of implying every answer passed', () => {
  const partial = {...result('PENDING',100,100), tests_total:2, tests_passed:2, uncertain_count:3, evaluated_count:5};
  render(<ComparisonVisualizations runs={[{label:'Qwen · Scope-Aware',result:partial}]} />);
  expect(screen.getByText('3 answers await review')).toBeTruthy();
  expect(screen.getByText('Scored runs')).toBeTruthy();
  expect(screen.getByText('Awaiting review')).toBeTruthy();
});


test('retains compact model identity when matching strategy has an unscored peer', () => {
  const pending = {...result('PENDING', 100, 100), overall_score:null, tests_total:0, tests_passed:0, uncertain_count:5, evaluated_count:5,
    dimensions: result('PENDING',100,100).dimensions.map(d => ({...d,percentage:null,passed:0,total:0,uncertain_count:1}))};
  render(<ComparisonVisualizations runs={[
    {label:'Ollama · qwen3:1.7b · Full Context', result:result('SCORED',100,100)},
    {label:'Ollama · qwen3:4b · Full Context', result:pending},
  ]} />);
  expect(screen.getByText(/Ollama · qwen3:1\.7b · Full Context/)).toBeInTheDocument();
  expect(screen.getByText(/Ollama · qwen3:4b · Full Context/)).toBeInTheDocument();
  expect(screen.getByRole('img', {name:/Horizontal bar chart/})).not.toHaveAccessibleName(/qwen3:4b.*100%/);
});


it('warns when an apparent average increase excludes abilities that remain uncertain',()=>{
  const original=result('original',25,0);
  const candidate=result('candidate',50,0);
  candidate.dimensions=candidate.dimensions.map(dimension=>dimension.dimension==='freshness'?{...dimension,percentage:null,total:0,uncertain_count:1}:dimension);
  candidate.uncertain_count=1;
  render(<ComparisonVisualizations runs={[{label:'Original',result:original},{label:'Candidate',result:candidate}]}/>);
  expect(screen.getByText('Different score coverage')).toBeInTheDocument();
  expect(screen.getByText(/their averages are not directly comparable/)).toBeInTheDocument();
});


test('compact presentation leads with one grouped dimension chart and keeps supplemental charts expandable', async()=>{
  const user=(await import('@testing-library/user-event')).default.setup();
  render(<UIProvider><ComparisonVisualizations compact runs={[{label:'Original',result:result('before',25,0)},{label:'Candidate',result:result('after',100,100)}]}/></UIProvider>);
  expect(screen.getByRole('img',{name:/Grouped bar chart/})).toBeVisible();
  expect(screen.queryByRole('img',{name:/Horizontal bar chart/})).toBeNull();
  await user.click(screen.getByRole('button',{name:'Average scores & failed-question counts'}));
  await waitFor(()=>expect(screen.getByRole('heading',{name:'Tested Ability Average by Condition'})).toBeVisible());
  expect(screen.getByRole('img',{name:/Horizontal bar chart/})).toBeInTheDocument();
  expect(screen.getByRole('img',{name:/Grouped failure bar chart/})).toBeVisible();
});


test('radar and grouped comparisons distinguish unavailable evidence from untested dimensions',()=>{
 const unavailable=result('unavailable',100,100);
 unavailable.dimensions=unavailable.dimensions.map(d=>d.dimension==='accuracy'?{...d,percentage:null,total:0,passed:0,expected_tests:1,excluded_evidence_count:1}:d);
 const {unmount}=render(<ScoreRadarChart result={unavailable}/>);
 expect(screen.getByRole('img',{name:/Radar chart: Accuracy: Evidence unavailable/})).toBeInTheDocument();
 unmount();
 render(<UIProvider><ComparisonVisualizations compact runs={[{label:'Test setting',result:unavailable}]}/></UIProvider>);
 expect(screen.getByRole('img',{name:/Grouped bar chart.*Accuracy:.*Evidence unavailable/})).toBeInTheDocument();
});


test('repeat error bars state population standard deviation in percentage points',()=>{
  render(<ComparisonVisualizations runs={[
    {label:'First',groupKey:'same',groupLabel:'Repeated setting',result:result('ONE',25,0)},
    {label:'Second',groupKey:'same',groupLabel:'Repeated setting',result:result('TWO',75,100)},
  ]}/>);
  expect(screen.getByRole('img',{name:/Horizontal bar chart.*± 25 pp population SD/})).toBeInTheDocument();
  expect(screen.getByText(/Error bars and ± values show population standard deviation.*not a confidence interval/)).toBeInTheDocument();
});
