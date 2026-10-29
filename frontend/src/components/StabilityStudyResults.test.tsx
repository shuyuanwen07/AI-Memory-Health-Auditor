import { webcrypto } from 'node:crypto';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StabilityStudyResults } from './StabilityStudyResults';
import type { StabilityStudyPayload } from '../services/stabilityStudyPackage';
import { makeEnvelope, makeMetadataOnlyStabilityPayload, makeSingleRoundStabilityPayload, makeStabilityPayload, makeThreeRoundPilotPayload } from '../test/stabilityStudyFixture';

const storageMocks = vi.hoisted(() => ({
  hasSaved: vi.fn(), readSaved: vi.fn(), save: vi.fn(), remove: vi.fn(),
}));
const downloadMocks = vi.hoisted(() => ({ saveBlob: vi.fn() }));
vi.mock('../services/stabilityStudyPackage', async importOriginal => {
  const actual = await importOriginal<typeof import('../services/stabilityStudyPackage')>();
  return { ...actual, hasSavedStabilityStudyPackage: storageMocks.hasSaved, readSavedStabilityStudyPackage: storageMocks.readSaved,
    saveStabilityStudyPackage: storageMocks.save, removeSavedStabilityStudyPackage: storageMocks.remove };
});
vi.mock('../services/download', () => downloadMocks);

beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto as unknown as Crypto);
  storageMocks.hasSaved.mockReset().mockResolvedValue(false);
  storageMocks.readSaved.mockReset().mockResolvedValue(null);
  storageMocks.save.mockReset().mockResolvedValue(undefined);
  storageMocks.remove.mockReset().mockResolvedValue(undefined);
  downloadMocks.saveBlob.mockReset();
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function authorize(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('checkbox', { name: 'Stability-study package authorisation' }));
  await waitFor(() => expect(storageMocks.hasSaved).toHaveBeenCalledTimes(1));
}

describe('StabilityStudyResults local import panel', () => {
  test.each(['pass', 'fail', 'pending'])('presents recorded %s stage checks before results and keeps technical evidence collapsed without changing the envelope', async status => {
    const payload=makeStabilityPayload();
    payload.acceptance_results={overall_status:status,gates:{
      usable_targets:{status:'pass',observed:1,threshold:1},
      grade_coverage:{status:'pending',observed:.5,threshold:1},
      critical_source_safety_guards:{status:'fail',observed:{critical_error_count:1,reviewed_trials:3,planned_trials:3},threshold:'Zero critical source errors.'},
    }};
    const raw=await makeEnvelope(payload);
    storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(raw);
    const user=userEvent.setup();render(<StabilityStudyResults />);await authorize(user);
    await user.click(screen.getByRole('button',{name:'Restore saved package'}));
    const title=await screen.findByRole('heading',{name:`Package stage status: ${status}`});
    const overview=within(title.closest('section')!);
    expect(overview.getByText(/not formal research acceptance/)).toBeInTheDocument();
    const complete=overview.getByText('Complete target answers').closest('tr')!;
    expect(within(complete).getByText('pass')).toBeInTheDocument();
    expect(within(complete).getAllByText('1')).toHaveLength(2);
    expect(overview.getByText('Original grading coverage')).toBeInTheDocument();
    expect(overview.getByText('critical error count: 1 · reviewed trials: 3 · planned trials: 3')).toBeInTheDocument();
    expect(overview.getByText('Zero critical source errors.')).toBeInTheDocument();
    const technical=screen.getByText('Technical evidence and limitations').closest('details')!;
    expect(technical).not.toHaveAttribute('open');
    expect(within(technical).getByText('Protocol')).not.toBeVisible();
    const split=screen.getByRole('heading',{name:'Evaluation split'}).closest('section')!;
    expect(split.compareDocumentPosition(technical)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(title.compareDocumentPosition(split)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText(/2 planned cases · 8 planned result cells · 4 with an original semantic grade · 1 error · 3 missing/)).toBeInTheDocument();
    await user.click(screen.getByText('Technical evidence and limitations'));
    expect(within(technical).getByText('Protocol')).toBeVisible();
    for(const [label,value] of [['Protocol',payload.protocol],['Provenance',payload.provenance],['Acceptance results',payload.acceptance_results],['Replay proof',payload.replay]] as const){
      expect(within(technical).getByText(label).nextElementSibling?.textContent).toBe(JSON.stringify(value,null,2));
    }
    expect(within(technical).getByText(payload.limitations[0])).toBeInTheDocument();
    await user.click(screen.getByRole('button',{name:'Export original envelope'}));
    const original=downloadMocks.saveBlob.mock.calls[0][0] as Blob;
    expect(await original.text()).toBe(raw);
    expect(JSON.parse(JSON.parse(await original.text()).payload_json).splits[1].cases[0].runs[1].semantic_grade.correct).toBe(false);
  });

  test('surfaces saved case critical findings beside pending safety gates and counts each guard-wrapped review once',async()=>{
    const payload:StabilityStudyPayload=makeStabilityPayload();
    const runs=payload.splits.flatMap(split=>split.cases.flatMap(entry=>entry.runs));
    runs.forEach(run=>Object.assign(run,{source_review:null}));
    const completed=runs.filter(run=>run.status==='completed');
    Object.assign(completed[0],{source_review:{review_status:'reviewed',critical_errors:[{category:'synthetic_unsupported_year'}]}});
    Object.assign(completed[1],{source_review:{status:'completed',critical_errors:[]}});
    Object.assign(completed[2],{source_review:{status:'completed',critical_errors:['Outer duplicate must not count'],automatic_guard_findings:{source_contradiction:true},agent_review:{review_status:'reviewed',critical_errors:[]}}});
    payload.acceptance_results={overall_status:'pending',gates:{critical_source_safety_guards:{status:'pending',observed:null,threshold:'36 separate guard reviews'}}};
    const raw=await makeEnvelope(payload);
    storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(raw);
    const user=userEvent.setup();render(<StabilityStudyResults/>);await authorize(user);await user.click(screen.getByRole('button',{name:'Restore saved package'}));
    const summary=await screen.findByRole('region',{name:'Recorded case source reviews'});
    expect(within(summary).getByText('3 reviewed replies; 1 critical finding.')).toBeInTheDocument();
    expect(within(summary).getByText(/Unreviewed replies have no recorded source-safety assessment/)).toBeInTheDocument();
    const gate=screen.getByText('Source safety review').closest('tr')!;
    expect(within(gate).getByText('pending')).toBeInTheDocument();
    expect(screen.getByRole('heading',{name:'Package stage status: pending'})).toBeInTheDocument();
    expect(summary.compareDocumentPosition(gate)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await user.click(screen.getByRole('button',{name:'Export original envelope'}));
    expect(await (downloadMocks.saveBlob.mock.calls[0][0] as Blob).text()).toBe(raw);
  });

  test.each([null,{critical_errors:'unknown'}, {status:'future',critical_errors:[]}, {reviewable:false,critical_errors:[]}])('keeps absent or unknown source review formats unknown instead of declaring zero findings: %j',async review=>{
    const payload=makeStabilityPayload();
    payload.splits.forEach(split=>split.cases.forEach(entry=>entry.runs.forEach(run=>Object.assign(run,{source_review:null}))));
    Object.assign(payload.splits[1].cases[0].runs[0],{source_review:review});
    storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(await makeEnvelope(payload));
    const user=userEvent.setup();render(<StabilityStudyResults/>);await authorize(user);await user.click(screen.getByRole('button',{name:'Restore saved package'}));
    const summary=within(await screen.findByRole('region',{name:'Recorded case source reviews'}));
    expect(summary.getByText('No interpretable case source-review counts recorded.')).toBeInTheDocument();
    expect(summary.queryByText(/0 critical findings/)).not.toBeInTheDocument();
    if(review!==null)expect(summary.getByText(/critical findings are not assumed to be zero/)).toBeInTheDocument();
  });

  test('shows complete recorded pilot quality counts ahead of scope fields without changing gates or unknown evidence', async () => {
    const payload=makeThreeRoundPilotPayload(true);
    payload.acceptance_results={overall_status:'fail',gates:{
      development_quality_1:{status:'fail',observed:{split:'development',arm:'strong_rule_based',planned:12,graded:12,correct:8,extra_note:'Retained synthetic field'},threshold:9},
      development_quality_2:{status:'fail',observed:{split:'development_regression',arm:'strong_rule_based',planned:6,graded:6,correct:3},threshold:5},
      future_gate:{status:'pending',observed:{future_count:2},threshold:'Future recorded rule'},
    }};
    const raw=await makeEnvelope(payload);
    storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(raw);
    const user=userEvent.setup();render(<StabilityStudyResults />);await authorize(user);
    await user.click(screen.getByRole('button',{name:'Restore saved package'}));
    const title=await screen.findByRole('heading',{name:'Package stage status: fail'});
    const overview=within(title.closest('section')!);
    for(const [label,counts,minimum] of [['development quality 1','Correct: 8/12 · Graded: 12/12','9'],['development quality 2','Correct: 3/6 · Graded: 6/6','5']]){
      const row=within(overview.getByText(label).closest('tr')!);
      expect(row.getByText(counts)).toBeInTheDocument();
      expect(row.getByText(minimum)).toBeInTheDocument();
      expect(row.getByText('fail')).toBeInTheDocument();
    }
    expect(overview.getByText('future count: 2')).toBeInTheDocument();
    expect(screen.getByText('Acceptance results').nextElementSibling?.textContent).toBe(JSON.stringify(payload.acceptance_results,null,2));
    await user.click(screen.getByRole('button',{name:'Export original envelope'}));
    expect(await (downloadMocks.saveBlob.mock.calls[0][0] as Blob).text()).toBe(raw);
  });

  test('shows target and grader replay counts separately without changing the recorded failed gate', async () => {
    const payload=makeStabilityPayload();
    payload.acceptance_results={overall_status:'fail',gates:{input_replay:{status:'fail',observed:1,threshold:1}}};
    Object.assign(payload.replay,{status:'failed',target_input_comparisons:120,planned_trials:120,grader_input_comparisons:119,planned_grader_input_comparisons:120,
      independent_safety_guards:{status:'passed',compared_trials:36,planned_trials:36,grader_input_comparisons:36,planned_grader_input_comparisons:36}});
    const raw=await makeEnvelope(payload);
    storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(raw);
    const user=userEvent.setup();render(<StabilityStudyResults />);await authorize(user);
    await user.click(screen.getByRole('button',{name:'Restore saved package'}));
    const title=await screen.findByRole('heading',{name:'Package stage status: fail'});
    const overview=within(title.closest('section')!);
    expect(overview.getByText(/status failed · Target inputs: 120\/120 · Grader inputs: 119\/120/)).toBeInTheDocument();
    expect(overview.getByText(/status passed · Target inputs: 36\/36 · Grader inputs: 36\/36/)).toBeInTheDocument();
    const gate=overview.getByText('Offline input replay').closest('tr')!;
    expect(within(gate).getByText('fail')).toBeInTheDocument();
    expect(within(gate).getAllByText('1')).toHaveLength(2);
    expect(screen.getByText('Replay proof').nextElementSibling?.textContent).toBe(JSON.stringify(payload.replay,null,2));
    await user.click(screen.getByRole('button',{name:'Export original envelope'}));
    expect(await (downloadMocks.saveBlob.mock.calls[0][0] as Blob).text()).toBe(raw);
  });

  test.each([
    {stages:['development-pilot','safety-guards','final'],minimum:.9,expected:'Development pilot: auxiliary validation is required by this protocol. Validation coverage requirement: 90.0%. See the recorded gate status above.'},
    {stages:['development-pilot'],minimum:.85,expected:'Development pilot: auxiliary validation is required by this protocol. Validation coverage requirement: 85.0%. See the recorded gate status above.'},
    {stages:['safety-guards','final'],minimum:.9,expected:'Development pilot: descriptive auxiliary results only. This protocol does not apply an auxiliary validation gate to this pilot.'},
    {stages:[],minimum:.9,expected:'Development pilot: descriptive auxiliary results only. This protocol does not apply an auxiliary validation gate to this pilot.'},
    ...[undefined,'development-pilot',['development-pilot',3],['future-stage']].map(stages=>({stages,minimum:.9,expected:'Development pilot: whether the auxiliary validation gate applies is not recorded clearly in this protocol. No applicability decision is inferred.'})),
  ])('derives pilot auxiliary applicability from recorded protocol stages: %j',async ({stages,minimum,expected})=>{
    const payload:StabilityStudyPayload=makeStabilityPayload();
    payload.protocol={...payload.protocol,additional_acceptance_requirements:{applies_to_stages:stages,auxiliary_validation_coverage_minimum:minimum}};
    payload.auxiliary_analysis={stages:{'development-pilot':{total:{attempted:1,validated:0,degraded:1,unknown:0,validation_coverage:0,degraded_rate:1},by_split_arm_round:[]}}};
    payload.acceptance_results={overall_status:'fail',gates:{auxiliary_validation_coverage:{status:'fail',observed:0,threshold:minimum}}};
    const raw=await makeEnvelope(payload);
    storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(raw);
    const user=userEvent.setup();render(<StabilityStudyResults/>);await authorize(user);await user.click(screen.getByRole('button',{name:'Restore saved package'}));
    expect(await screen.findByText(expected)).toBeInTheDocument();
    const gate=screen.getByText('Auxiliary output validation coverage').closest('tr')!;
    expect(within(gate).getByText('fail')).toBeInTheDocument();
    expect(screen.getByText(/Validation coverage: 0.0% · Degraded rate: 100.0%/)).toBeInTheDocument();
    expect(screen.queryByText(/The 90% auxiliary validation gate is not applied/)).not.toBeInTheDocument();
    expect(screen.getByText('Protocol').nextElementSibling?.textContent).toBe(JSON.stringify(payload.protocol,null,2));
    await user.click(screen.getByRole('button',{name:'Export original envelope'}));
    expect(await (downloadMocks.saveBlob.mock.calls[0][0] as Blob).text()).toBe(raw);
  });

  test.each(['final', 'development-pilot'])('keeps a refused auxiliary suggestion separate from a completed final answer and original grade in %s', async (stage) => {
    const payload=makeSingleRoundStabilityPayload();
    Object.assign(payload.protocol,{additional_acceptance_requirements:{applies_to_stages:['safety-guards','final'],auxiliary_validation_coverage_minimum:.9}});
    const evaluation=payload.splits[1];
    evaluation.planned_case_ids=[evaluation.cases[0].case_id];evaluation.cases=[evaluation.cases[0]];
    payload.splits=[evaluation];
    const run=evaluation.cases[0].runs.find(item=>item.arm==='strong_rule_based')!;
    run.source_review={status:'completed',critical_errors:['Synthetic critical source mismatch preserved from the review.']};
    run.auxiliary_analysis={planned_eligible:true,attempted_calls:1,status:'degraded',validated:false,degraded:true,blocked:false,skipped:false,unknown:false,unexpected_calls:false,
      http_execution_status:'parsed',analyzer_status:'failed',advisory_applied:false,
      failure_diagnostics:{identity_observations:[{last_observation:{error_code:'invalid_identity_contract',error_diagnostics:{reason_code:'exact_substring_mismatch'}}}]}};
    payload.auxiliary_analysis={stages:{[stage]:{total:{planned_eligible:1,attempted:1,validated:0,degraded:1,blocked:0,skipped:0,unknown:0,validation_coverage:0,degraded_rate:1,degraded_unreviewed:1},
      by_split_arm_round:[{split:'evaluation',round:1,arm:'strong_rule_based',planned_eligible:1,attempted:1,validated:0,degraded:1,blocked:0,skipped:0,unknown:0,unexpected_calls:0}]}}};
    storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(await makeEnvelope(payload));
    const user=userEvent.setup();render(<StabilityStudyResults />);await authorize(user);
    await user.click(screen.getByRole('button',{name:'Restore saved package'}));
    expect(await screen.findByText('Imported study package')).toBeInTheDocument();
    expect(screen.getByText('1 attempted · 0 validated · 1 continued without suggestions · 0 unknown')).toBeInTheDocument();
    expect(screen.getByText(/Validation coverage: 0.0% · Degraded rate: 100.0%/)).toBeInTheDocument();
    if(stage === 'development-pilot') expect(screen.getByText(/This protocol does not apply an auxiliary validation gate to this pilot/)).toBeInTheDocument();
    else expect(screen.queryByText(/This protocol does not apply an auxiliary validation gate to this pilot/)).not.toBeInTheDocument();
    expect(screen.getByText(/1 planned cases · 2 planned result cells · 2 with an original semantic grade · 0 errors · 0 missing/)).toBeInTheDocument();
    await user.click(screen.getByText('EVAL-1 · knowledge-update'));
    const summary=screen.getByText('Round 1 · Relationship-priority retrieval · completed · incorrect');await user.click(summary);
    const details=within(summary.closest('details')!);
    expect(details.getByText('Auxiliary suggestions not used')).toBeInTheDocument();
    expect(details.getByText(/Synthetic critical source mismatch preserved from the review/)).toBeInTheDocument();
    expect(screen.getByText(/Source safety clearance requires a completed review with zero critical errors/)).toBeInTheDocument();
    expect(screen.getByText(/Continued answers without source safety clearance: 1/)).toBeInTheDocument();
    expect(details.getByText('HTTP response status: parsed · Identity validation: failed')).toBeInTheDocument();
    expect(details.getByText(/exact_substring_mismatch/)).toBeInTheDocument();
    expect(details.queryByText('Recorded execution failure diagnostics')).not.toBeInTheDocument();
    expect(details.getByText(/Official incorrect fixture/)).toBeInTheDocument();
    expect(screen.getByText(/It does not isolate retrieval or have equal total call cost/)).toBeInTheDocument();
    expect(screen.getByText(/Validated means the saved output contract and source-quote checks passed/)).toBeInTheDocument();
    expect(screen.getByText(/It does not prove that an identity relationship is semantically true/)).toBeInTheDocument();
  });

  test('shows the recorded identity failure cause when no target or grader receipt exists', async () => {
    const payload = makeMetadataOnlyStabilityPayload();
    Object.assign(payload.splits[1].cases[0].runs[0], {
      status: 'error', grade_outcome: 'error',
      failure_diagnostics: { report_status: 'failed', report_error_code: 'PipelineRequestError',
        target_error_code: null, target_receipt_count: 0, grading_attempt_count: 0,
        identity_observations: [{ attempt: 1, exception_type: 'PipelineRequestError',
          last_observation: { error_code: 'invalid_identity_contract',
            error_summary: 'Target identity evidence was not accepted.',
            error_diagnostics: { phase: 'output_validation', reason_code: 'duplicate_mention_quote_reference' } } }] },
      extra_agent_executions: [{ agent_role: 'target_identity_evidence', execution: { status: 'parsed' } }],
    });
    storageMocks.hasSaved.mockResolvedValue(true);
    storageMocks.readSaved.mockResolvedValue(await makeEnvelope(payload));
    const user = userEvent.setup();
    render(<StabilityStudyResults />);
    await authorize(user);
    await user.click(screen.getByRole('button', { name: 'Restore saved package' }));
    expect(await screen.findByText('Imported study package')).toBeInTheDocument();
    await user.click(screen.getByText('EVAL-SYNTHETIC-1 · synthetic-preparation'));
    const runSummary = screen.getByText('Round 1 · First-match retrieval · error · error');
    await user.click(runSummary);
    const runDetails = within(runSummary.closest('details')!);
    expect(runDetails.getByText('Recorded execution failure diagnostics')).toBeInTheDocument();
    expect(runDetails.getByText(/duplicate_mention_quote_reference/)).toHaveTextContent('"target_receipt_count": 0');
    expect(runDetails.getByText(/duplicate_mention_quote_reference/)).toHaveTextContent('invalid_identity_contract');
    expect(runDetails.queryByText('Original grading attempt (separate from valid semantic grades)')).not.toBeInTheDocument();
  });

  test('displays an original failed grading attempt separately without counting its retained verdict as a grade', async () => {
    const payload = makeMetadataOnlyStabilityPayload();
    Object.assign(payload.splits[1].cases[0].runs[0], {
      status: 'error', grade_outcome: 'error', response_text: 'Synthetic saved target answer.',
      grading_attempt: { status: 'failed', error_code: 'SyntheticTimeout',
        verdict: { correct: true, reason: 'Synthetic retained attempt only.' },
        execution: { requested_model: 'fixture-reviewer', reported_model: 'fixture-reviewer-v1' } },
    });
    storageMocks.hasSaved.mockResolvedValue(true);
    storageMocks.readSaved.mockResolvedValue(await makeEnvelope(payload));
    const user = userEvent.setup();
    render(<StabilityStudyResults />);
    await authorize(user);
    await user.click(screen.getByRole('button', { name: 'Restore saved package' }));
    expect(await screen.findByText('Imported study package')).toBeInTheDocument();
    expect(screen.getByText(/12 planned cases · 72 planned result cells · 0 with an original semantic grade · 1 error · 71 missing/)).toBeInTheDocument();
    await user.click(screen.getByText('EVAL-SYNTHETIC-1 · synthetic-preparation'));
    const runSummary = screen.getByText('Round 1 · First-match retrieval · error · error');
    await user.click(runSummary);
    const runDetails = within(runSummary.closest('details')!);
    expect(runDetails.getByText('Original grading attempt (separate from valid semantic grades)')).toBeInTheDocument();
    expect(runDetails.getByText(/SyntheticTimeout/)).toHaveTextContent('"status": "failed"');
    expect(runDetails.getByText('fixture-reviewer → fixture-reviewer-v1')).toBeInTheDocument();
  });

  test('marks single-round repeat consistency as not measured without displaying agreement counts', async () => {
    storageMocks.hasSaved.mockResolvedValue(true);
    storageMocks.readSaved.mockResolvedValue(await makeEnvelope(makeSingleRoundStabilityPayload()));
    const user = userEvent.setup();
    render(<StabilityStudyResults />);
    await authorize(user);
    await user.click(screen.getByRole('button', { name: 'Restore saved package' }));
    expect(await screen.findByText('Imported study package')).toBeInTheDocument();
    expect(screen.getAllByText('Not measured: only one round is included. Repeat consistency requires at least two rounds.')).toHaveLength(3);
    expect(screen.queryByText(/resolved pairs agree/)).not.toBeInTheDocument();
    expect(screen.getByText(/2 planned cases · 4 planned result cells · 2 with an original semantic grade · 1 error · 1 missing/)).toBeInTheDocument();
  });

  test('does not inspect local storage or read a selected file before explicit authorisation', async () => {
    const raw = await makeEnvelope(makeStabilityPayload());
    const file = new File([raw], 'study.json', { type: 'application/json' });
    const text = vi.fn().mockResolvedValue(raw);
    Object.defineProperty(file, 'text', { value: text });
    render(<StabilityStudyResults />);
    const fileInput = screen.getByLabelText('Study results JSON') as HTMLInputElement;
    expect(fileInput).toBeDisabled();
    expect(storageMocks.hasSaved).not.toHaveBeenCalled();
    fireEvent.change(fileInput, { target: { files: [file] } });
    expect(text).not.toHaveBeenCalled();
    expect(screen.getByText('No file selected.')).toBeInTheDocument();
  });

  test('reads only after consent and explicit import, then shows split counts, actual model, separate review, and saves/exports locally', async () => {
    const raw = await makeEnvelope(makeStabilityPayload());
    const file = new File([raw], 'study.json', { type: 'application/json' });
    const text = vi.fn().mockResolvedValue(raw);
    Object.defineProperty(file, 'text', { value: text });
    const user = userEvent.setup();
    render(<StabilityStudyResults />);
    await authorize(user);
    await user.upload(screen.getByLabelText('Study results JSON'), file);
    expect(text).not.toHaveBeenCalled();
    expect(screen.getByText('study.json selected.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Read and verify package' }));
    await waitFor(() => expect(text).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Imported study package')).toBeInTheDocument();
    expect(screen.getByText('study.json selected.')).toBeInTheDocument();
    expect(screen.queryByText(/has not been read yet/)).not.toBeInTheDocument();
    expect(screen.getByText(/2 planned cases · 8 planned result cells · 4 with an original semantic grade · 1 error · 3 missing/)).toBeInTheDocument();
    expect(screen.getByText(/0 \/ 1 resolved pairs agree/)).toBeInTheDocument();
    expect(screen.getByText('Safety guards · engineering checks')).toBeInTheDocument();
    expect(screen.getByText(/not pooled with the development or evaluation split/i)).toBeInTheDocument();

    await user.click(screen.getByText(/EVAL-1 · knowledge-update/));
    const runSummary = screen.getByText(/Round 1 · First-match retrieval · completed · correct/);
    await user.click(runSummary);
    const expandedRun = runSummary.closest('details')!;
    expect(within(expandedRun).getByText('fixture-target → fixture-target-v1')).toBeInTheDocument();
    expect(within(expandedRun).getByText('fixture-reviewer → fixture-reviewer-v1')).toBeInTheDocument();
    expect(within(expandedRun).getByText('Original semantic grade')).toBeInTheDocument();
    expect(within(expandedRun).getByText('Source review (separate from the original grade)')).toBeInTheDocument();
    expect(within(expandedRun).getByText(/Official correct fixture/)).toBeInTheDocument();
    expect(within(expandedRun).getByText(/Shown separately from the official grade/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Save latest package on this browser' }));
    await waitFor(() => expect(storageMocks.save).toHaveBeenCalledWith(raw));
    await user.click(screen.getByRole('button', { name: 'Export original envelope' }));
    await user.click(screen.getByRole('button', { name: 'Download summary CSV' }));
    expect(downloadMocks.saveBlob).toHaveBeenCalledTimes(2);
    const originalBlob = downloadMocks.saveBlob.mock.calls[0][0] as Blob;
    expect(await originalBlob.text()).toBe(raw);
    const csvBlob = downloadMocks.saveBlob.mock.calls[1][0] as Blob;
    expect(await csvBlob.text()).toContain('"evaluation","1","weak_first_hit"');
    await user.click(screen.getByRole('button', { name: 'Remove saved package' }));
    expect(storageMocks.remove).toHaveBeenCalledTimes(1);
  });

  test('consent withdrawal invalidates an in-flight file read and clears the loaded preview', async () => {
    const raw = await makeEnvelope(makeStabilityPayload());
    let finishRead!: (value: string) => void;
    const file = new File([], 'study.json', { type: 'application/json' });
    const text = vi.fn(() => new Promise<string>(resolve => { finishRead = resolve; }));
    Object.defineProperty(file, 'text', { value: text });
    const user = userEvent.setup();
    render(<StabilityStudyResults />);
    await authorize(user);
    await user.upload(screen.getByLabelText('Study results JSON'), file);
    await user.click(screen.getByRole('button', { name: 'Read and verify package' }));
    await waitFor(() => expect(text).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole('checkbox', { name: 'Stability-study package authorisation' }));
    await act(async () => { finishRead(raw); });
    expect(screen.queryByText('Imported study package')).not.toBeInTheDocument();
    expect(screen.getByText('The currently loaded package and preview were cleared. A saved local copy remains until you remove it.')).toBeInTheDocument();
    expect(storageMocks.save).not.toHaveBeenCalled();
  });

  test('restores a saved package only after authorization and keeps the preparation sample visibly unscored', async () => {
    const raw = await makeEnvelope(makeMetadataOnlyStabilityPayload());
    storageMocks.hasSaved.mockResolvedValue(true);
    storageMocks.readSaved.mockResolvedValue(raw);
    const user = userEvent.setup();
    render(<StabilityStudyResults />);
    expect(storageMocks.hasSaved).not.toHaveBeenCalled();
    await authorize(user);
    expect(screen.getByRole('button', { name: 'Restore saved package' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Restore saved package' }));
    expect(storageMocks.readSaved).toHaveBeenCalledTimes(1);
    expect(await screen.findByText('Imported study package')).toBeInTheDocument();
    expect(screen.getByText(/12 planned cases · 72 planned result cells · 0 with an original semantic grade · 0 errors · 72 missing/)).toBeInTheDocument();
    expect(screen.getByText(/"overall_status"\s*:\s*"pending"/)).toBeInTheDocument();
    expect(screen.getByText(/Evaluation split present but incomplete: 0 graded cells, 0 errors, 72 missing/)).toBeInTheDocument();
    expect(screen.queryByText(/evaluation complete/i)).not.toBeInTheDocument();
  });

  test('displays a synthetic numeric zero reference answer without replacing it with missing metadata', async () => {
    const payload = makeMetadataOnlyStabilityPayload();
    payload.splits[1].cases[0].reference_answer = 0;
    storageMocks.hasSaved.mockResolvedValue(true);
    storageMocks.readSaved.mockResolvedValue(await makeEnvelope(payload));
    const user = userEvent.setup();
    render(<StabilityStudyResults />);
    await authorize(user);
    await user.click(screen.getByRole('button', { name: 'Restore saved package' }));
    expect(await screen.findByText('Imported study package')).toBeInTheDocument();
    const caseSummary = screen.getByText('EVAL-SYNTHETIC-1 · synthetic-preparation');
    await user.click(caseSummary);
    const caseDetails = caseSummary.closest('details')!;
    expect(within(caseDetails).getByText('Reference answer:').parentElement).toHaveTextContent(/^Reference answer: 0$/);
  });
});


test('shows the 24-cell repeat pilot separately from six previously used target-policy regression cells',async()=>{
  const payload=makeThreeRoundPilotPayload(true);
  storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(await makeEnvelope(payload));
  const user=userEvent.setup();render(<StabilityStudyResults/>);await authorize(user);
  await user.click(screen.getByRole('button',{name:'Restore saved package'}));
  expect(await screen.findByRole('heading',{name:'Development split'})).toBeInTheDocument();
  expect(screen.getByRole('heading',{name:'Known failure regression · used questions'})).toBeInTheDocument();
  expect(screen.getByText(/4 planned cases · 24 planned result cells · 0 with an original semantic grade · 0 errors · 24 missing/)).toBeInTheDocument();
  expect(screen.getByText(/6 planned cases · 6 planned result cells · 0 with an original semantic grade · 0 errors · 6 missing/)).toBeInTheDocument();
  expect(screen.getByText(/This split is not evidence on unseen questions/)).toBeInTheDocument();
  expect(screen.getAllByText('Not measured: only one round is included. Repeat consistency requires at least two rounds.')).toHaveLength(1);
  expect(screen.queryByRole('heading',{name:'Evaluation split'})).not.toBeInTheDocument();
});

test('discloses mutual public distractor reuse without claiming full-source separation',async()=>{
  const payload=makeStabilityPayload();
  Object.assign(payload.provenance,{source_disjoint_metadata_only_selection:false,source_reuse_scope:{
    policy_id:'question-and-answer-evidence-disjoint-mutual-filler-reuse-v1',question_disjoint:true,answer_evidence_disjoint:true,
    public_distractor_conversations_may_repeat:true,full_source_disjoint:false,metadata_checks_status:'passed'}});
  storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(await makeEnvelope(payload));
  const user=userEvent.setup();render(<StabilityStudyResults/>);await authorize(user);await user.click(screen.getByRole('button',{name:'Restore saved package'}));
  expect(await screen.findByText('Questions: Declared separate')).toBeInTheDocument();
  expect(screen.getByText('Answer-bearing evidence: Declared separate')).toBeInTheDocument();
  expect(screen.getByText('Public distractor conversations may repeat: Yes')).toBeInTheDocument();
  expect(screen.getByText(/only when they are public distractors on both sides/)).toBeInTheDocument();
  expect(screen.getByText('Full-source separation: Not claimed')).toBeInTheDocument();
  expect(screen.getByText(/frozen, unseen questions and answer-bearing evidence/)).toBeInTheDocument();
  expect(screen.getByText(/does not independently verify source overlap/)).toBeInTheDocument();
});

test('missing source scope remains unknown and a legacy failed package stays failed',async()=>{
  const payload=makeStabilityPayload();Object.assign(payload.provenance,{source_disjoint_metadata_only_selection:true});payload.acceptance_results={overall_status:'fail',gates:{}};
  storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(await makeEnvelope(payload));
  const user=userEvent.setup();render(<StabilityStudyResults/>);await authorize(user);await user.click(screen.getByRole('button',{name:'Restore saved package'}));
  expect(await screen.findByRole('heading',{name:'Package stage status: fail'})).toBeInTheDocument();
  expect(screen.getByText('Not recorded. Selection metadata alone does not establish full-source separation.')).toBeInTheDocument();
  expect(screen.queryByText('Full-source separation: Declared; not independently verified here')).not.toBeInTheDocument();
});

test.each(['low','medium'] as const)('shows requested %s and a recorded grader omission without claiming actual reasoning effort',async effort=>{
  const payload=makeStabilityPayload();const run=payload.splits[1].cases[0].runs[0];
  Object.assign(run.execution_metadata!,{requested_reasoning_effort:effort,request_contract:{version:'openrouter-request-contract-v1',reasoning:{present:true,value:{effort}}}});
  Object.assign((run.semantic_grade as {execution_metadata:Record<string,unknown>}).execution_metadata,{request_contract:{version:'openrouter-request-contract-v1',reasoning:{present:false}}});
  storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(await makeEnvelope(payload));
  const user=userEvent.setup();render(<StabilityStudyResults/>);await authorize(user);await user.click(screen.getByRole('button',{name:'Restore saved package'}));
  await screen.findByText('Imported study package');await user.click(screen.getByText('EVAL-1 · knowledge-update'));
  const summary=screen.getByText('Round 1 · First-match retrieval · completed · correct');await user.click(summary);
  const details=within(summary.closest('details')!);
  expect(details.getByText(`${effort==='medium'?'Medium':'Low'} requested; the saved request contract includes ${effort}. Actual reasoning effort is not reported.`)).toBeInTheDocument();
  expect(details.getByText(/No reasoning setting sent in the saved request contract \(provider default\)/)).toBeInTheDocument();
  expect(details.getByText(/Official correct fixture/)).toBeInTheDocument();
});


describe('ordinary final source-review gate scope', () => {
  test('shows the declared safety condition while retaining comparison findings',async()=>{
    const payload=makeStabilityPayload();
    payload.acceptance_results={overall_status:'pass',gates:{final_case_source_safety:{status:'pass',observed:{review_state:'completed',planned_trials:120,reviewed_trials:120,critical_error_count:2,critical_error_required_arms:['strong_rule_based'],required_arm_critical_error_count:0},threshold:'All replies reviewed; Strong zero critical; Weak findings descriptive.'}}};
    storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(await makeEnvelope(payload));
    const user=userEvent.setup();render(<StabilityStudyResults/>);await authorize(user);
    await user.click(screen.getByRole('button',{name:'Restore saved package'}));
    const row=(await screen.findByText('All benchmark replies source review')).closest('tr')!;
    expect(within(row).getByText(/Zero critical errors is required for: Relationship-priority retrieval/)).toHaveTextContent('Recorded findings in required conditions: 0; findings across all conditions: 2');
    expect(within(row).getByText(/Findings in comparison conditions remain reported/)).toBeInTheDocument();
  });
  test.each([120,18])('uses the recorded %i reply denominator separately from guard review', async planned => {
    const payload=makeStabilityPayload();
    payload.acceptance_results={overall_status:'pending',gates:{
      final_case_source_safety:{status:'pending',observed:{review_state:'missing',planned_trials:planned,reviewed_trials:0,critical_error_count:0},threshold:'All final replies reviewed with zero critical errors.'},
      critical_source_safety_guards:{status:'pass',observed:{planned_trials:36,reviewed_trials:36,critical_error_count:0},threshold:'Separate synthetic guard reviews.'},
    }};
    const raw=await makeEnvelope(payload);
    storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(raw);
    const user=userEvent.setup();render(<StabilityStudyResults />);await authorize(user);
    await user.click(screen.getByRole('button',{name:'Restore saved package'}));
    const row=(await screen.findByText('All benchmark replies source review')).closest('tr')!;
    expect(within(row).getByText('pending')).toBeInTheDocument();
    expect(within(row).getByText(`Recorded scope: ${planned} ordinary final replies; synthetic safety guards are reviewed separately. Pending or missing reviews do not establish source safety.`)).toBeInTheDocument();
    const guard=screen.getByText('Source safety review').closest('tr')!;
    expect(within(guard).getByText('pass')).toBeInTheDocument();
    expect(within(guard).queryByText(/ordinary final replies/)).not.toBeInTheDocument();
    expect(screen.getByText('Acceptance results').nextElementSibling?.textContent).toBe(JSON.stringify(payload.acceptance_results,null,2));
  });

  test('does not invent a denominator when the final gate omits recorded scope',async()=>{
    const payload=makeStabilityPayload();
    payload.acceptance_results={overall_status:'pending',gates:{final_case_source_safety:{status:'pending',observed:{review_state:'missing'},threshold:'Await all source reviews.'}}};
    storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(await makeEnvelope(payload));
    const user=userEvent.setup();render(<StabilityStudyResults />);await authorize(user);
    await user.click(screen.getByRole('button',{name:'Restore saved package'}));
    const row=(await screen.findByText('All benchmark replies source review')).closest('tr')!;
    expect(within(row).getByText(/Recorded scope: All planned ordinary final replies/)).toBeInTheDocument();
    expect(within(row).getByText(/Pending or missing reviews do not establish source safety/)).toBeInTheDocument();
    expect(within(row).queryByText(/120/)).not.toBeInTheDocument();
  });

  test('legacy13 packages do not gain an inferred ordinary-final source gate',async()=>{
    const payload=makeStabilityPayload();
    payload.acceptance_results={overall_status:'fail',gates:{critical_source_safety_guards:{status:'pass',observed:{reviewed_trials:36},threshold:'Synthetic guards only.'}}};
    storageMocks.hasSaved.mockResolvedValue(true);storageMocks.readSaved.mockResolvedValue(await makeEnvelope(payload));
    const user=userEvent.setup();render(<StabilityStudyResults />);await authorize(user);
    await user.click(screen.getByRole('button',{name:'Restore saved package'}));
    await screen.findByText('Source safety review');
    expect(screen.queryByText('All benchmark replies source review')).not.toBeInTheDocument();
    expect(screen.queryByText(/Recorded scope:.*ordinary final replies/)).not.toBeInTheDocument();
  });
});
