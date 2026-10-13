import { render, screen, waitFor, within } from '@testing-library/react';
import { buildAuditResultCsv, ResultDashboard } from './ResultDashboard';
import type { AuditResult, AuditRun } from '../types/domain';
import {saveBlob} from '../services/download';
vi.mock('../services/download',()=>({saveBlob:vi.fn()}));

function csvColumnCount(line:string) {
  let fields=1;
  let quoted=false;
  for (let index=0;index<line.length;index++) {
    if (line[index]==='"' && quoted && line[index+1]==='"') { index++; continue; }
    if (line[index]==='"') quoted=!quoted;
    else if (line[index]===',' && !quoted) fields++;
  }
  return fields;
}

const result: AuditResult = {
  run_id: 'RUN001', overall_score: null, tests_passed: 0, tests_total: 0,
  dimensions: [
    { dimension: 'accuracy', percentage: null, passed: 0, total: 0 },
    { dimension: 'freshness', percentage: 50, passed: 1, total: 2 },
    { dimension: 'conflict_resolution', percentage: null, passed: 0, total: 0 },
    { dimension: 'appropriate_use', percentage: null, passed: 0, total: 0 },
  ],
  failures: [{
    failure_id: 'E001',
    test: { test_id: 'T001', run_id: 'RUN001', dimension: 'freshness', prompt: 'Which database is current?', expected_behavior: 'Use the current value: PostgreSQL', supporting_memory_ids: ['M001'], generator_version: 'rule-based-v1' },
    response: { response_id: 'R001', test_id: 'T001', run_id: 'RUN001', response_text: 'MySQL', model: 'baseline', temperature: 0, created_at: '2026-01-01T00:00:00Z' },
    evaluation: { evaluation_id: 'E001', test_id: 'T001', response_id: 'R001', passed: false, failure_type: 'freshness', reason: 'The response retained an older value.', evidence_memory_ids: [], evaluator: 'rule-based-v1' },
    evidence: [],
  }],
};

test('explains untested dimensions and makes failure evidence inspectable', () => {
  render(<ResultDashboard result={result} />);

  expect(screen.getAllByText('Not tested')).toHaveLength(4);
  expect(screen.getByText(/Untested dimensions are excluded from the macro-average/)).toBeTruthy();
  expect(screen.getByText('Download CSV')).toBeTruthy();
  expect(screen.getByText('1 flagged')).toBeTruthy();
  expect(screen.getByText('Expected behaviour')).toBeTruthy();
  expect(screen.getByText(/No traceable ground-truth evidence/)).toBeTruthy();
});

test('dimension overview links work from the keyboard and land on failure and pending evidence', async () => {
  const user = (await import('@testing-library/user-event')).default.setup();
  const uncertain = {...result.failures[0], evaluation:{...result.failures[0].evaluation,
    evaluation_id:'E-UNCERTAIN', passed:null, failure_type:null, reason:'Needs a human decision.'}};
  render(<ResultDashboard result={{...result, uncertain_count:1,
    dimensions:result.dimensions.map(d => d.dimension === 'freshness' ? {...d, uncertain_count:1} : d),
    uncertain_answers:[uncertain]}} />);

  await user.tab(); // Download CSV
  await user.tab(); // Download JSON
  await user.tab(); // Accuracy details
  expect(screen.getByRole('link', { name: 'View Accuracy details: 0 failures, 0 answers awaiting review' })).toHaveFocus();
  await user.keyboard('{Enter}');

  expect(window.location.hash).toBe('#dimension-details-accuracy');
  const accuracy = document.getElementById('dimension-details-accuracy');
  expect(accuracy).toHaveAttribute('tabindex', '-1');
  expect(accuracy).toHaveTextContent('No failed answers in this dimension.');
  expect(document.getElementById('dimension-details-freshness')).toHaveTextContent('The response retained an older value.');
  expect(screen.getByRole('link', { name: 'View Freshness details: 1 failures, 1 answers awaiting review' })).toHaveAttribute('href', '#dimension-details-freshness');
  await user.click(screen.getByRole('link', { name: 'View Freshness details: 1 failures, 1 answers awaiting review' }));
  const freshness = document.getElementById('dimension-details-freshness')!;
  expect(freshness).toHaveTextContent('Answers awaiting review');
  expect(within(freshness).getByText('Needs a human decision.')).toBeInTheDocument();
});

test('missing reference identifiers are not presented as checked source evidence',()=>{
  const sample={...result,failures:[{...result.failures[0],evaluation:{...result.failures[0].evaluation,
    reason:'The answer omitted the expected value. Evidence records: none linked to this test.'}}]};
  render(<ResultDashboard result={sample}/>);
  expect(screen.getByRole('button',{name:/No reference memories are listed in this explanation/})).toBeInTheDocument();
  expect(screen.getByText(/No traceable ground-truth evidence/)).toBeInTheDocument();
  expect(screen.queryByText(/Supporting memories were checked/)).toBeNull();
  expect(sample.failures[0].evaluation.reason).toContain('none linked to this test');
});

test('classification explanations hide internal identifiers without changing saved evidence',()=>{
  const reason = 'The confirmed memory M222DEC204BDF4848B811737BA6E2482B contains the Nacre access code.';
  const sample:AuditResult = {...result,failures:[{...result.failures[0],evaluation:{...result.failures[0].evaluation,
    failure_classification:{status:'classified',method:'fixture',reason}}}]};
  render(<ResultDashboard result={sample}/>);
  expect(screen.getByText('The confirmed memory saved record contains the Nacre access code.')).toBeInTheDocument();
  expect(screen.queryByText(/M222DEC204BDF4848B811737BA6E2482B/)).toBeNull();
  expect(sample.failures[0].evaluation.failure_classification?.reason).toBe(reason);
});

test('creates a local CSV report containing summaries and traceable failure details', () => {
  const csv = buildAuditResultCsv(result);

  expect(csv).toContain('"Audit summary"');
  expect(csv).toContain('"Dimension summary"');
  expect(csv).toContain('"Failure detail"');
  expect(csv).toContain('"The response retained an older value."');
  expect(csv).toContain('"MySQL"');
});

test('CSV and JSON exports preserve every saved answer outcome and its source statement', async () => {
  const base = result.failures[0];
  const source = {role:'user', content:'Meadow now uses PostgreSQL.', timestamp:'2026-01-01T00:00:00Z'};
  const answers: NonNullable<AuditResult['answers']> = [
    {test:{...base.test,test_id:'T-PASS',prompt:'Which database is current?'},
      response:{...base.response,response_id:'R-PASS',test_id:'T-PASS',response_text:'PostgreSQL',execution_metadata:{request_attempts:1,response_source:'target',reported_model:'ollama/qwen3:1.7b'}},
      outcome:'pass',evaluation:{...base.evaluation,evaluation_id:'E-PASS',test_id:'T-PASS',response_id:'R-PASS',passed:true,failure_type:null,reason:'Current value used.'},reason:'Current value used.',evidence:[],source_statements:[source]},
    {test:{...base.test,test_id:'T-FAIL',prompt:'What is the old database?'},
      response:{...base.response,response_id:'R-FAIL',test_id:'T-FAIL',response_text:'SQLite'},
      outcome:'fail',evaluation:{...base.evaluation,evaluation_id:'E-FAIL',test_id:'T-FAIL',response_id:'R-FAIL',passed:false,reason:'Stale value.'},reason:'Stale value.',evidence:[],source_statements:[source]},
    {test:{...base.test,test_id:'T-UNCERTAIN',prompt:'Was a database selected?'},
      response:{...base.response,response_id:'R-UNCERTAIN',test_id:'T-UNCERTAIN',response_text:'Possibly PostgreSQL'},
      outcome:'uncertain',evaluation:{...base.evaluation,evaluation_id:'E-UNCERTAIN',test_id:'T-UNCERTAIN',response_id:'R-UNCERTAIN',passed:null,failure_type:null,reason:'Needs review.'},reason:'Needs review.',evidence:[],source_statements:[source]},
    {test:{...base.test,test_id:'T-UNASSESSED',prompt:'Which database did Meadow choose?'},
      response:{...base.response,response_id:'R-UNASSESSED',test_id:'T-UNASSESSED',response_text:'No answer was assessed.'},
      outcome:'unassessed',evaluation:null,reason:'No valid assessment is linked.',evidence:[],source_statements:[source]},
  ];
  const sample:AuditResult = {...result,answers,uncertain_count:1};
  const run:AuditRun = {run_id:'RUN001',conversation_id:'CONV001',status:'COMPLETED',target_configuration:'strong',provider:'ollama',model:'qwen3:1.7b',temperature:0,random_seed:42,test_budget:4,prompt_template_version:'prompt-v3',pipeline_provider:'rule_based',pipeline_model:'rules-v2',evaluator_provider:'rule_based',evaluator_model:'rules-v2',memory_strategy:'scope_aware',target_memory_profile:{label:'Synthetic profile',version:1,max_retrieved_records:5,context_character_budget:4000,isolate_project_scope:true,prefer_current_state:true,additional_instructions:'private instruction text',output_token_limit:256},created_at:'2026-01-01T00:00:00Z'};
  const csv = buildAuditResultCsv(sample,run);
  for (const answer of answers) {
    expect(csv).toContain(answer.test.test_id);
    expect(csv).toContain(answer.response.response_text);
    expect(csv).toContain(answer.source_statements?.[0].content);
  }
  expect(csv).toContain('"Passed"');
  expect(csv).toContain('"Failed"');
  expect(csv).toContain('"Awaiting review"');
  expect(csv).toContain('"Unassessed"');
  expect(csv).toContain('"Configured target provider","Configured target model","Reported target model(s)"');
  expect(csv).toContain('"ollama","qwen3:1.7b","ollama/qwen3:1.7b"');
  expect(csv).not.toContain('private instruction text');

  const user = (await import('@testing-library/user-event')).default.setup();
  render(<ResultDashboard result={sample} run={run}/>);
  const freshnessLink = screen.getByRole('link',{name:'View Freshness details: 1 failures, 1 answers awaiting review, 1 unassessed'});
  expect(freshnessLink).toHaveAttribute('href','#dimension-details-freshness');
  const freshness = document.getElementById('dimension-details-freshness')!;
  expect(freshness).toHaveTextContent('Answers awaiting review');
  expect(freshness).toHaveTextContent('Saved answers without an assessment');
  expect(freshness).toHaveTextContent('Unassessed · excluded from score');
  const unassessedCard = freshness.querySelector<HTMLElement>('.unassessed-answer-card')!;
  const unassessedEvidence = within(unassessedCard).getByRole('button',{name:'Reference and original conversation'});
  await user.click(unassessedEvidence);
  await waitFor(()=>expect(unassessedEvidence).toHaveAttribute('aria-expanded','true'));
  await waitFor(()=>expect(within(unassessedCard).getByText('Meadow now uses PostgreSQL.')).toBeVisible());
  await user.click(screen.getByRole('button',{name:'Download JSON'}));
  const [blob, filename] = vi.mocked(saveBlob).mock.calls.at(-1)!;
  expect(filename).toBe('memory-health-report-RUN001.json');
  expect(blob.type).toBe('application/json;charset=utf-8');
  const text = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
  const exported = JSON.parse(text);
  expect(exported.result).toEqual(sample);
  expect(exported.run_configuration).toMatchObject({
    target_provider:'ollama', configured_target_model:'qwen3:1.7b',
    reported_target_models:['ollama/qwen3:1.7b'], memory_strategy:'scope_aware', test_budget:4,
    target_memory_profile:{label:'Synthetic profile',output_token_limit:256},
  });
  expect(text).not.toContain('private instruction text');
});

test('protects formula-like model output in CSV while retaining the original saved response',()=>{
 const sample={...result,failures:[{...result.failures[0],response:{...result.failures[0].response,response_text:'=1+1'}}]};
 expect(buildAuditResultCsv(sample)).toContain('"\t=1+1"');
 expect(buildAuditResultCsv(sample)).toContain('Formula-like text has a leading tab');
 expect(sample.failures[0].response.response_text).toBe('=1+1');
});

test('exports numeric pending and excluded counts alongside unavailable scores with consistent columns',()=>{
 const sample:AuditResult={...result,failures:[],overall_score:null,uncertain_count:1,excluded_evidence_count:1,expected_tests:2,
  dimensions:[{dimension:'accuracy',percentage:null,passed:0,total:0,uncertain_count:1,excluded_evidence_count:1,expected_tests:2}]};
 const lines=buildAuditResultCsv(sample).split('\r\n');
 expect(lines[0]).toContain('"Awaiting review count","Excluded evidence count","Expected questions"');
 const summary=lines.find(line=>line.startsWith('"Audit summary"'))!;
 const dimension=lines.find(line=>line.startsWith('"Dimension summary"'))!;
 expect(summary).toContain('"Evidence unavailable"');
 expect(summary).toContain('"1","1","2","Not recorded"');
 expect(dimension).toContain('"1","1","2","Not recorded"');
 expect(csvColumnCount(lines[0])).toBe(46);
 expect(lines.map(csvColumnCount)).toEqual(Array.from({length:lines.length},()=>46));
});

test('reports the save request accurately, handles export failure and does not carry feedback into another audit',async()=>{
 const user=(await import('@testing-library/user-event')).default.setup();
 vi.mocked(saveBlob).mockImplementation(()=>{});
 const view=render(<ResultDashboard result={result}/>);
 await user.click(screen.getByRole('button',{name:'Download CSV'}));
 expect(saveBlob).toHaveBeenCalledWith(expect.any(Blob),'memory-health-report.csv');
 expect(screen.getByText('CSV prepared. Your browser was asked to save memory-health-report.csv.')).toBeInTheDocument();
 view.rerender(<ResultDashboard result={{...result,run_id:'ANOTHER'}}/>);
 expect(screen.queryByText(/CSV prepared/)).not.toBeInTheDocument();
 vi.mocked(saveBlob).mockImplementation(()=>{throw new Error('Browser save unavailable');});
 await user.click(screen.getByRole('button',{name:'Download CSV'}));
 expect(screen.getByText('The CSV could not be prepared. Try downloading again.')).toBeInTheDocument();
 expect(screen.queryByText(/CSV prepared/)).not.toBeInTheDocument();
 vi.mocked(saveBlob).mockImplementation(()=>{});
});

test('labels incomplete coverage and shows original conversation evidence', () => {
  render(<ResultDashboard result={{...result,failures:[{...result.failures[0],source_statements:[{role:'user',content:'Atlas project now uses PostgreSQL.',timestamp:'2026-01-01T00:00:00Z'}]}]}}/>);
  expect(screen.getByText('TESTED ABILITY AVERAGE')).toBeTruthy();
  expect(screen.getByText(/A formal overall Memory Health score requires all four dimensions/)).toBeTruthy();
  expect(screen.getByText('Atlas project now uses PostgreSQL.')).toBeTruthy();
});


test('distinguishes completed uncertain answers from untested dimensions and exports that distinction', () => {
  const pending: AuditResult = {...result, uncertain_count: 1,
    dimensions: result.dimensions.map(d => d.dimension === 'appropriate_use' ? {...d, uncertain_count: 1} : d)};
  render(<ResultDashboard result={pending} />);
  expect(screen.getByText('Awaiting review', {selector:'strong'})).toBeTruthy();
  expect(screen.getByText('Completed answers need independent review')).toBeTruthy();
  expect(buildAuditResultCsv(pending)).toContain('Awaiting review');
});


test('explains excluded retrieval attempts instead of crediting an unfinished answer', () => {
  render(<ResultDashboard result={{...result, retrieval_quality:{
    tests_measured:0, unlinked_attempts_excluded:2,
    evidence_recall_at_k:null, evidence_precision_at_k:null,
    update_evidence_recall:null, conflict_evidence_coverage:null,
    unnecessary_memory_retrieval_rate:null,
  }}} />);
  expect(screen.getByText(/2 retrieval attempts without a linked saved answer are excluded/)).toBeTruthy();
  expect(screen.getByText(/No retrieval trace with source evidence is available/)).toBeTruthy();
});


test('shows uncertain answers beside the score rather than implying all completed answers passed', () => {
  render(<ResultDashboard result={{...result, overall_score:100, tests_total:4, tests_passed:4, uncertain_count:1}}/>);
  expect(screen.getByRole('region',{name:'Answer outcomes'})).toHaveTextContent('5 completed answers');
  expect(screen.getByRole('img',{name:'4 passed, 0 failed, 1 awaiting review out of 5 completed answers'})).toBeTruthy();
  expect(screen.getByText(/Awaiting review does not mean passed/)).toBeTruthy();
});

test('outcome chart includes failures and handles a wholly uncertain audit', () => {
  const view = render(<ResultDashboard result={{...result, tests_total:3, tests_passed:2, uncertain_count:2}}/>);
  expect(screen.getByRole('img',{name:'2 passed, 1 failed, 2 awaiting review out of 5 completed answers'})).toBeTruthy();
  view.rerender(<ResultDashboard result={{...result, uncertain_count:2}}/>);
  expect(screen.getByRole('img',{name:'0 passed, 0 failed, 2 awaiting review out of 2 completed answers'})).toBeTruthy();
  view.rerender(<ResultDashboard result={{...result, uncertain_count:0}}/>);
  expect(screen.getByText('No assessed answers are available.')).toBeTruthy();
});


test('whole pending audit headline and summary export acknowledge completed answers', () => {
  const pending = {...result, overall_score:null, tests_total:0,tests_passed:0,uncertain_count:5};
  render(<ResultDashboard result={pending}/>);
  expect(screen.getByRole('heading',{name:'Unscored'})).toBeTruthy();
  expect(screen.getByText('5 completed answers await review')).toBeTruthy();
  expect(screen.queryByText('No completed tests are available for scoring')).toBeNull();
  expect(buildAuditResultCsv(pending)).toContain('Awaiting review');
});


test('shared answers retain the original-evidence entry rather than implying a new execution',()=>{
  render(<ResultDashboard result={{...result,reproducibility:{schema_version:'v1',target_retry_policy:{max_attempts:1,timeout_seconds:10,retryable_status_codes:[]},shared_answer_source_run_id:'SOURCE'}}}/>);
  expect(screen.getByText(/No second target call was made/)).toBeTruthy();
  expect(screen.getByRole('link',{name:'View original memory and model-input evidence'}).getAttribute('href')).toBe('/audits/SOURCE');
});

test('shows review reasons and original replies directly and exports uncertainty without changing it to failure', async () => {
  const user=(await import('@testing-library/user-event')).default.setup();
  const answer={...result.failures[0],evaluation:{...result.failures[0].evaluation,passed:null,failure_type:null,reason:'The saved answer was truncated.'},response:{...result.failures[0].response,response_text:'The current platform is\n'},source_statements:[{role:'user',content:'The review meeting uses Teams.',timestamp:'2026-01-01T00:00:00Z'}]};
  const pending={...result,failures:[],uncertain_count:1,uncertain_answers:[answer]};
  render(<ResultDashboard result={pending}/>);
  const section=screen.getByRole('region',{name:'Answers needing review'});
  expect(section).toHaveTextContent('The saved answer was truncated.');
  expect(section).toHaveTextContent('The current platform is');
  expect(section).toHaveTextContent('excluded from the score');
  expect(section).not.toHaveTextContent('E001');
  await user.click(within(section).getByRole('button',{name:'Inspect the reference and original conversation'}));
  expect(await within(section).findByText('The review meeting uses Teams.')).toBeTruthy();
  const csv=buildAuditResultCsv(pending);
  expect(csv).toContain('"Review required"');
  expect(csv).toContain('"Awaiting review"');
  expect(csv).toContain('The saved answer was truncated.');
  expect(csv).not.toContain('"Failure detail"');
});

test('legacy pending reports expose a next step instead of inventing an explanation', () => {
  render(<ResultDashboard result={{...result,uncertain_count:1}}/>);
  expect(screen.getByRole('region',{name:'Answers needing review'})).toHaveTextContent('Individual explanations are unavailable');
  expect(screen.getByRole('region',{name:'Answers needing review'})).toHaveTextContent('Open Review Evaluations');
});

test.each([
  ['review_source_uncertainty', 'Check whether the question and reference support a clear verdict.'],
  ['review_disagreement', 'Compare both assessments with the original conversation.'],
  ['uncertain_fallback', 'Check the assessment service and saved evidence.'],
  ['future_status', 'Inspect the question, reference and complete model answer'],
])('pending guidance follows saved assessment status %s without inventing a verdict', (status, guidance) => {
  const answer = {...result.failures[0], evaluation: {...result.failures[0].evaluation,
    passed: null, failure_type: null, reason: 'Original explanation retained.',
    judge_execution: {version:'judge-execution-v1',provider:'openrouter',model:'judge',
      request_attempts:1,failed_http_attempts:0,elapsed_ms:10,reported_input_tokens:null,
      reported_output_tokens:null,reported_total_tokens:null,usage_scope:'request',verdict_status:status}}};
  const pending: AuditResult = {...result, failures:[], uncertain_count:1, uncertain_answers:[answer]};
  render(<ResultDashboard result={pending}/>);
  const section = screen.getByRole('region',{name:'Answers needing review'});
  expect(section).toHaveTextContent(guidance);
  expect(section.querySelector('[role="status"]')).toHaveTextContent('Suggested next step');
  expect(section.querySelector('[role="alert"]')).toBeNull();
  expect(section).toHaveTextContent('Original explanation retained.');
  expect(answer.evaluation.passed).toBeNull();
  expect(buildAuditResultCsv(pending)).toContain('"Awaiting review"');
  expect(buildAuditResultCsv(pending)).not.toContain('"Failure detail"');
});


test('saved-answer reassessment does not imply two distinct evaluators',()=>{
  render(<ResultDashboard result={{...result,reproducibility:{schema_version:'v1',target_retry_policy:{max_attempts:1,timeout_seconds:10,retryable_status_codes:[]},shared_answer_source_run_id:'SOURCE',assessment_source_run_id:'SOURCE'}}}/>);
  expect(screen.getByText(/This reassessment uses the original saved target answers/)).toBeTruthy();
  expect(screen.queryByText(/Both evaluators/)).toBeNull();
  expect(screen.getByRole('link',{name:'View original memory and model-input evidence'})).toHaveAttribute('href','/audits/SOURCE');
});

test('one four-ability chart distinguishes zero, pending and untested without duplicate radar',()=>{
  render(<ResultDashboard result={{...result,dimensions:[
    {dimension:'accuracy',percentage:0,passed:0,total:2},
    {dimension:'freshness',percentage:50,passed:1,total:2,uncertain_count:1},
    {dimension:'conflict_resolution',percentage:null,passed:0,total:0,uncertain_count:2},
    {dimension:'appropriate_use',percentage:null,passed:0,total:0},
  ]}}/>);
  expect(screen.getByRole('img',{name:'Accuracy: 0%, 0 of 2 tests passed'}).firstChild).toHaveStyle({height:'0%'});
  expect(screen.getByRole('img',{name:'Freshness: 50%, 1 of 2 tests passed, 1 awaiting review'}).firstChild).toHaveStyle({height:'50%'});
  expect(screen.getByRole('img',{name:'Conflict Resolution: Awaiting review, 2 awaiting review'})).toHaveClass('unscored');
  expect(screen.getByRole('img',{name:'Appropriate Use: Not tested'})).toBeEmptyDOMElement();
  expect(screen.queryByRole('heading',{name:'Memory Health Profile'})).toBeNull();
  expect(screen.getByRole('button',{name:'Score coverage & request settings'})).toBeTruthy();
});


test('retrieval matching checks share one chart without presenting missing values as zero',()=>{
  render(<ResultDashboard result={{...result,retrieval_quality:{tests_measured:2,evidence_recall_at_k:0,evidence_precision_at_k:50,update_evidence_recall:null,conflict_evidence_coverage:100,unnecessary_memory_retrieval_rate:50}}}/>);
  expect(screen.getByText(/Not model accuracy or proof of memory use/)).toBeTruthy();
  expect(screen.getByRole('img',{name:'Required fact text matched: 0%'}).firstChild).toHaveStyle({width:'0%'});
  expect(screen.getByRole('img',{name:'Update fact text matched: Not tested'})).toBeEmptyDOMElement();
  expect(screen.getByRole('img',{name:'Retrieved fact text matched: 50%'}).firstChild).toHaveStyle({width:'50%'});
  expect(screen.getByRole('button',{name:'How to interpret these matching checks'})).toBeTruthy();
});


test('unusable evidence retains the saved question denominator without becoming a failure',()=>{
 const partial:AuditResult={...result,overall_score:100,tests_passed:3,tests_total:3,failures:[],evaluated_count:3,expected_tests:4,excluded_evidence_count:1,evaluation_warnings:['One question has inconsistent evidence and is excluded.']};
 render(<ResultDashboard result={partial}/>);
 expect(screen.getByText('3 of 4 question assessments usable')).toBeTruthy();
 expect(screen.getByText('PARTIAL RESULT')).toBeTruthy();
 expect(screen.getByText('One question has inconsistent evidence and is excluded.')).toBeTruthy();
 expect(buildAuditResultCsv(partial)).toContain('3 usable question assessments; 1 excluded');
});


test('a saved question with unavailable evidence is not labelled as never tested',()=>{
 const unavailable:AuditResult={...result,failures:[],dimensions:result.dimensions.map(d=>d.dimension==='accuracy'?{...d,expected_tests:1,excluded_evidence_count:1}:d)};
 render(<ResultDashboard result={unavailable}/>);
 expect(screen.getByText('Evidence unavailable',{selector:'strong'})).toBeTruthy();
 expect(screen.getByText('Saved questions lack usable assessment evidence')).toBeTruthy();
 expect(buildAuditResultCsv(unavailable)).toContain('Evidence unavailable');
});
