import { sha256Hex, type StabilityStudyPayload } from '../services/stabilityStudyPackage';

/** Synthetic preparation data only: no benchmark questions, answers, or model results. */
export function makeMetadataOnlyStabilityPayload(): StabilityStudyPayload {
  const rounds = [1, 2, 3];
  const arms = ['weak_first_hit', 'strong_rule_based'];
  const makeSplit = (name: 'development' | 'evaluation', prefix: string, count: number) => {
    const caseIds = Array.from({ length: count }, (_, index) => `${prefix}-SYNTHETIC-${index + 1}`);
    return {
      name, planned_case_ids: caseIds, rounds: [...rounds], arms: [...arms],
      cases: caseIds.map(caseId => ({
        case_id: caseId, type: 'synthetic-preparation', question: null, reference_answer: null,
        runs: rounds.flatMap(round => arms.map(arm => ({
          round, arm, status: 'missing' as const, grade_outcome: 'missing' as const,
          response_text: null, semantic_grade: null, execution_metadata: null,
          input_receipt: null, source_review: null, extra_agent_executions: [],
        }))),
      })),
    };
  };
  return {
    study_id: 'synthetic-metadata-only-study', created_at: '2026-10-21T00:00:00Z',
    protocol: { preregistration: { status: 'frozen' }, rounds },
    provenance: { package_kind: 'synthetic-test-fixture' },
    acceptance_results: { overall_status: 'pending', gates: {} },
    splits: [makeSplit('development', 'DEV', 1), makeSplit('evaluation', 'EVAL', 12)],
    replay: { status: 'pending' },
    limitations: ['Synthetic metadata only; all planned result cells are missing.'],
  };
}

export function makeStabilityPayload() {
  const completed = (round: number, arm: string, outcome: 'correct' | 'incorrect') => ({
    round, arm, status: 'completed' as const, grade_outcome: outcome,
    response_text: outcome === 'correct' ? 'The current answer is Cedar.' : 'The answer is old.' as string | null,
    semantic_grade: { correct: outcome === 'correct', reason: `Official ${outcome} fixture.`, execution_metadata: { requested_model: 'fixture-reviewer', reported_model: 'fixture-reviewer-v1' } },
    execution_metadata: { requested_model: 'fixture-target', reported_model: 'fixture-target-v1', finish_reason: 'stop' },
    input_receipt: { replay_sha256: 'a'.repeat(64), records_read: 1 },
    source_review: { verdict: 'advisory_only', finding: 'Shown separately from the official grade.' },
    extra_agent_executions: [{ execution: { reported_model: 'fixture-reviewer-v1' } }],
  });
  const missing = (round: number, arm: string) => ({ round, arm, status: 'missing' as const, grade_outcome: 'missing' as const,
    response_text: null, semantic_grade: null, execution_metadata: null, input_receipt: null, source_review: null, extra_agent_executions: [] });
  const errored = (round: number, arm: string) => ({ round, arm, status: 'error' as const, grade_outcome: 'error' as const,
    response_text: null, semantic_grade: null, execution_metadata: { error_code: 'fixture-error' }, input_receipt: null, source_review: null, extra_agent_executions: [] });
  const weak = 'weak_first_hit';
  const strong = 'strong_rule_based';
  return {
    study_id: 'fixture-study', created_at: '2026-10-21T00:00:00Z',
    protocol: { preregistration: { status: 'frozen' }, rounds: [1, 2] },
    provenance: { package_kind: 'test-fixture', source_sha256: 'b'.repeat(64) },
    acceptance_results: { overall_status: 'pending', gates: {} },
    splits: [
      { name: 'development' as const, planned_case_ids: ['DEV-1'], rounds: [1, 2], arms: [weak, strong], cases: [{
        case_id: 'DEV-1', type: 'preparation', question: null, reference_answer: null,
        runs: [missing(1, weak), missing(1, strong), missing(2, weak), missing(2, strong)],
      }] },
      { name: 'evaluation' as const, planned_case_ids: ['EVAL-1', 'EVAL-2'], rounds: [1, 2], arms: [weak, strong], cases: [
        { case_id: 'EVAL-1', type: 'knowledge-update', question: 'Which location is current?', reference_answer: 'Cedar.',
          runs: [completed(1, weak, 'correct'), completed(1, strong, 'incorrect'), completed(2, weak, 'correct'), completed(2, strong, 'correct')] },
        { case_id: 'EVAL-2', type: 'temporal-reasoning', question: null, reference_answer: null,
          runs: [missing(1, weak), errored(1, strong), missing(2, weak), missing(2, strong)] },
      ] },
      { name: 'safety_guards' as const, planned_case_ids: ['GUARD-1'], rounds: [1, 2, 3], arms: [strong], cases: [{
        case_id: 'GUARD-1', type: 'unsupported-identity-merge', question: 'Does the system invent a shared identity?', reference_answer: 'No unsupported merge.',
        runs: [1, 2, 3].map(round => ({ round, arm: strong, status: 'completed' as const, grade_outcome: 'correct' as const,
          response_text: 'There is not enough evidence to merge these identities.',
          semantic_grade: { assessment_role: 'stability_guard_assessment', correct: true, reason: 'Guard rule held.' },
          execution_metadata: { reported_model: 'fixture-target-v1' }, input_receipt: { replay_sha256: 'c'.repeat(64) },
          source_review: { verdict: 'separate_advisory_review' }, extra_agent_executions: [] })),
      }] },
    ],
    replay: { status: 'verified', target_replay_coverage: 0.5 },
    limitations: ['Fixture only; contains no actual model outputs.'],
  };
}

export async function makeEnvelope(payload: unknown, formatting: 'compact' | 'pretty' = 'compact'): Promise<string> {
  const payloadJson = JSON.stringify(payload, null, formatting === 'pretty' ? 2 : undefined);
  const envelope = { schema_version: 'memory-stability-study-package-v1', payload_json: payloadJson, payload_sha256: await sha256Hex(payloadJson) };
  return JSON.stringify(envelope, null, 2);
}

export function makeSingleRoundStabilityPayload(): StabilityStudyPayload {
  const payload = makeStabilityPayload();
  return {
    ...payload,
    protocol: { ...payload.protocol, rounds: [1] },
    splits: payload.splits.map(split => ({
      ...split, rounds: [1],
      cases: split.cases.map(studyCase => ({ ...studyCase, runs: studyCase.runs.filter(run => run.round === 1) })),
    })),
  };
}


/** Artificial planning metadata: 24 repeat-study cells, optionally 6 used-question checks. */
export function makeThreeRoundPilotPayload(includeRegression=false): StabilityStudyPayload {
  const payload=makeMetadataOnlyStabilityPayload();
  const make=(prefix:string,count:number,rounds:number[],arms:string[])=>{
    const ids=Array.from({length:count},(_,i)=>`${prefix}-${i+1}`);
    return {planned_case_ids:ids,rounds,arms,cases:ids.map(case_id=>({case_id,type:'synthetic-preparation',question:null,reference_answer:null,
      runs:rounds.flatMap(round=>arms.map(arm=>({round,arm,status:'missing' as const,grade_outcome:'missing' as const,response_text:null,semantic_grade:null})))}))};
  };
  payload.study_id='synthetic-development-pilot';
  payload.splits=[{name:'development',...make('DEV-PLAN',4,[1,2,3],['weak_first_hit','strong_rule_based'])}];
  if(includeRegression)payload.splits.push({name:'development_regression',...make('USED-REGRESSION',6,[1],['strong_rule_based'])});
  return payload;
}
