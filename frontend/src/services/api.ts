import { SESSION_ENDED, workspaceCsrf } from './access';
import type { AccessStatus } from './access';
import { friendlyText } from './display';
import type { AgentExecution, SceneEvidenceVerification, FormalStudySummary, SavedFormalRunPage, ReviewedSavedAcceptanceReport, AcceptanceCheckReport, TargetProvider, AnnotationImportReport, AuditResult, AuditRetryPlan, AuditRun, BenchmarkFamily, BenchmarkRunResponse, BenchmarkValidationResponse, CancelledAuditEvidence, Conversation, ConversationDeletionReceipt, ConversationInputMessage, DimensionCoveragePreview, EvaluationCalibrationSummary, EvaluationHumanReview, EvaluationReviewItem, Experiment, ExperimentAnalytics, ExperimentResult, FormalMatrixCreateResponse, LongMemEvalRunResponse, LongMemEvalValidationResponse, Memory, MemoryStrategy, PilotReadinessReport, ProviderOption, ResearchValidityReport, TargetMemoryTrace, TestCase, TestReviewSuite } from '../types/domain';
const BASE = import.meta.env.VITE_API_URL?.trim() || '/api/v1';
import type { AuditComparison } from '../types/domain';
export function apiErrorMessage(detail: unknown): string {
  if (typeof detail === 'string') return friendlyText(detail);
  if (Array.isArray(detail)) {
    const fields: Record<string, string> = { canonical_value: 'Memory text', timestamp: 'Date and time', test_budget: 'Test budget', model: 'Model', content: 'Message text', label: 'Review label', source_authorised: 'Source processing permission' };
    const reviewTasks: Record<string, string> = {memory_inclusion:'memory inclusion',relationship_type:'relationship type',test_validity:'test validity',evaluator_verdict:'answer decision',failure_dimension:'failure category'};
    const messages = detail.flatMap((issue) => {
      if (!issue || typeof issue !== 'object' || typeof issue.msg !== 'string') return [];
      const field = Array.isArray(issue.loc) ? issue.loc.at(-1) : undefined;
      if (field === 'annotation_mode') return ['The pilot package must declare whether its labels come from independent human review or an AI-assisted dry run. Check the review origin and upload the corrected package.'];
      const reason = issue.msg.replace(/^Value error,\s*/, '').replace(/\b(memory_inclusion|relationship_type|test_validity|evaluator_verdict|failure_dimension)\b/g, (task: string) => reviewTasks[task]);
      return [friendlyText(`${fields[String(field)] ?? 'Input'}: ${reason}`)];
    });
    if (messages.length) {
      const counts = new Map<string, number>();
      for (const message of messages) counts.set(message, (counts.get(message) ?? 0) + 1);
      return [...counts].map(([message,count]) => count > 1 ? `${message} (${count} occurrences)` : message).join(' ');
    }
  }
  return 'The request could not be completed. Please check your input and try again.';
}
async function fetchResponse(url: string, options?: RequestInit): Promise<Response> {
  try {
    const headers=new Headers(options?.headers);
    const csrf=workspaceCsrf();if(csrf)headers.set('X-CSRF-Token',csrf);
    const response=await fetch(url,{...options,credentials:'include',headers});
    if(response.status===401&&!url.endsWith('/access/sign-in')&&!url.endsWith('/access/status'))window.dispatchEvent(new Event(SESSION_ENDED));
    return response;
  }
  catch { throw new Error('Connection to the audit service was interrupted. Check that the local service is running, then retry this step.'); }
}
async function request<T>(path:string, options?:RequestInit):Promise<T> {
  const r=await fetchResponse(`${BASE}${path}`,{headers:{'Content-Type':'application/json'},...options});
  if(!r.ok){
    const detail=(await r.json().catch(()=>null))?.detail;
    if(detail==null&&[502,503,504].includes(r.status))throw new Error('The audit service is temporarily unavailable. Check saved progress before retrying this step.');
    throw new Error(apiErrorMessage(detail));
  }
  return r.status===204 ? undefined as T : r.json();
}
export const api = {
  ac3FrozenStudies:()=>request<{studies:Array<{file:string;sha256:string;questions:number;histories:number;reservation_usd:string;executable?:boolean}>}>('/ac3/studies/frozen'),
  ac3StartStudy:(body:{frozen_file:string;frozen_sha256:string})=>request<{study_id:string;status:string;completed?:number;total?:number}>('/ac3/studies/start',{method:'POST',body:JSON.stringify(body)}),
  ac3StudyStatus:(id:string)=>request<{study_id:string;status:string;completed?:number;total?:number;failed_test_id?:string}>(`/ac3/studies/${encodeURIComponent(id)}/status`),
  ac3ReviewDownloadUrl:(id:string,file:'blind-packet.json'|'reviewer-1.json'|'reviewer-2.json')=>`${BASE}/ac3/studies/${encodeURIComponent(id)}/review/${file}`,
  ac3SubmitReviews:(id:string,body:{reviewer_1_json:string;reviewer_2_json:string})=>request<{status:string;summary:unknown}>(`/ac3/studies/${encodeURIComponent(id)}/reviews`,{method:'POST',body:JSON.stringify(body)}),
  ac3StudySummary:(id:string)=>request<unknown>(`/ac3/studies/${encodeURIComponent(id)}/summary`),
  ac3StudySummaries:()=>request<{studies:Array<{study_id:string;study_role:string;summary:unknown}>}>('/ac3/studies/summaries'),
  createGeneratorComparison:(body:{creation_request_key:string;source_run_id:string;generators:import('../types/domain').GeneratorSelection[]})=>request<import('../types/domain').GeneratorComparisonBatch>('/generator-comparisons',{method:'POST',body:JSON.stringify(body)}),
  generatorComparisons:()=>request<import('../types/domain').GeneratorComparisonBatch[]>('/generator-comparisons'),
  createExtractionComparison:(body:{creation_request_key:string;source_run_id:string;extractors:import('../types/domain').GeneratorSelection[]})=>request<import('../types/domain').ExtractionComparison>('/extraction-comparisons',{method:'POST',body:JSON.stringify(body)}),
  extractionComparisons:()=>request<import('../types/domain').ExtractionComparison[]>('/extraction-comparisons'),
  extractionComparison:(id:string)=>request<import('../types/domain').ExtractionComparison>(`/extraction-comparisons/${id}`),
  extractComparisonEntry:(id:string,index:number)=>request<import('../types/domain').ExtractionComparison>(`/extraction-comparisons/${id}/entries/${index}/extract`,{method:'POST'}),
  generatorComparison:(id:string)=>request<import('../types/domain').GeneratorComparisonBatch>(`/generator-comparisons/${id}`),
  prepareGeneratorComparison:(id:string)=>request<import('../types/domain').GeneratorComparisonBatch>(`/generator-comparisons/${id}/prepare`,{method:'POST'}),
  createAssessorComparison:(body:{creation_request_key:string;source_run_id:string;assessors:import('../types/domain').AssessorSelection[]})=>request<import('../types/domain').AssessorComparisonBatch>('/assessor-comparisons',{method:'POST',body:JSON.stringify(body)}),
  assessorComparisons:()=>request<import('../types/domain').AssessorComparisonBatch[]>('/assessor-comparisons'),
  assessorComparison:(id:string)=>request<import('../types/domain').AssessorComparisonBatch>(`/assessor-comparisons/${id}`),
  prepareAssessorComparison:(id:string)=>request<import('../types/domain').AssessorComparisonBatch>(`/assessor-comparisons/${id}/prepare`,{method:'POST'}),
  compareBenchmarkRankings:(body:object)=>request<import('../components/BenchmarkRankingAgreement').RankingAgreementResult>('/research/benchmarks/longmemeval/ranking-agreement',{method:'POST',body:JSON.stringify(body)}),
  createBenchmarkPlan:(body:object)=>request<import('../components/BenchmarkExecutionPlan').BenchmarkPlan>('/research/benchmarks/longmemeval/plans',{method:'POST',body:JSON.stringify(body)}),
  listBenchmarkPlans:()=>request<import('../components/BenchmarkExecutionPlan').BenchmarkPlan[]>('/research/benchmarks/longmemeval/plans'),
  listBenchmarkAnalyses:()=>request<Array<{id:string;plan_id:string;created_at:string;report:{status:string;planned_trials:number;measured_trials:number;reference_strategy:string|null;candidate_strategy:string|null;ranking_agreement_percentage:number|null;notice:string}}>>('/research/benchmarks/longmemeval/analyses'),
  restoreBenchmarkPlan:(id:string)=>request<import('../components/BenchmarkExecutionPlan').BenchmarkPlan>(`/research/benchmarks/longmemeval/plans/${encodeURIComponent(id)}`),
  executeBenchmarkPlan:(id:string,body:object)=>request<unknown>(`/research/benchmarks/longmemeval/plans/${encodeURIComponent(id)}/execute`,{method:'POST',body:JSON.stringify(body)}),
  analyseBenchmarkPlan:(id:string,analysis:object)=>request<import('../components/RepeatedBenchmarkRanking').RepeatedRankingResult>(`/research/benchmarks/longmemeval/plans/${encodeURIComponent(id)}/analyse`,{method:'POST',body:JSON.stringify({analysis})}),
  compareRepeatedBenchmarkRankings:(body:object)=>request<import('../components/RepeatedBenchmarkRanking').RepeatedRankingResult>('/research/benchmarks/longmemeval/ranking-agreement/repeated',{method:'POST',body:JSON.stringify(body)}),
  runLiveBenchmark:(body:object,signal?:AbortSignal)=>request<import('../components/LiveBenchmark').LiveBenchmarkResult>('/research/benchmarks/longmemeval/live',{method:'POST',body:JSON.stringify(body),signal}),
  importSemanticReview:(body:object)=>request<import('../components/BenchmarkSemanticReview').SemanticReviewResult>('/research/benchmarks/longmemeval/semantic-review',{method:'POST',body:JSON.stringify(body)}),
  accessStatus:(signal?:AbortSignal)=>request<AccessStatus>('/access/status',{signal}),
  signIn:(password:string)=>request<AccessStatus>('/access/sign-in',{method:'POST',body:JSON.stringify({password})}),
  signOut:()=>request<{signed_out:boolean}>('/access/sign-out',{method:'POST'}),
  auditSourceHistory:(id:string)=>request<Array<{role:string;content:string;timestamp:string}>>(`/audits/${id}/source-history`),
  prepareReassessment:(id:string,selection?:{evaluator_provider:TargetProvider|'openrouter_taxonomy';evaluator_model?:string})=>request<AuditRun>(`/audits/${id}/reassessment`,{method:'POST',...(selection?{body:JSON.stringify(selection)}:{})}),
  getAudit:(id:string)=>request<AuditRun>(`/audits/${id}`),
  auditAgentExecutions:(id:string)=>request<AgentExecution[]>(`/audits/${id}/agent-executions`),
  auditorQuality:()=>request<import("../pages/AuditorQuality").QualityReport>("/auditor-quality"),
  diagnosis:(id:string)=>request<import("../components/ValidationWorkbench").Diagnosis>(`/audits/${id}/diagnosis`),
  runDiagnosticAgent:(id:string)=>request<import("../components/ValidationWorkbench").DiagnosticAgentResponse>(`/audits/${id}/diagnostic-agent`,{method:'POST'}),
  validationHistories:()=>request<Array<{conversation_id:string;label:string}>>("/validation-histories"),
  repairExperiment:(id:string,body:object)=>request<import("../components/ValidationWorkbench").Package>(`/audits/${id}/repair-experiment`,{method:"POST",body:JSON.stringify(body)}),
  methodComparisonResults:(id:string,comparisonId?:string)=>request<{
    comparison_id:string;source_run_id:string;source_fingerprint_sha256:string;
    inventory:{status:string;release_id:string|null;fingerprint_sha256:string|null;distinct_failure_count:number|null;reviewers:string[]|null;authorship_verified:boolean;fixed_template_release_id:string|null;fixed_template_reviewers:string[]|null;fixed_template_question_count:number|null;fixed_template_draft_generator_version:string|null;fixed_template_draft_fingerprint_sha256:string|null;fixed_template_final_fingerprint_sha256:string|null;fixed_template_review_confirmed:boolean;fixed_template_review_identity_verified:boolean;defects:Array<{defect_id:string;dimension:string;explanation:string}>};
    planned_test_budgets_equal:boolean;target_and_evaluation_settings_match:boolean;realised_call_attempts_equal:boolean|null;
    conditions:Array<{run_id:string;label:string;suite_mode:string;status:string;test_budget:number;planned_call_cap:number;
      actual_target_call_attempts:number|null;completed_answers:number;unknown_attempt_records:number;test_count:number;valid_test_count:number;
      human_validity_accepted_count:number;human_validity_reviewed_count:number;human_validity_pending_count:number;human_validity_acceptance_rate:number|null;
      valid_test_dimensions:string[];human_confirmed_failure_categories:string[];human_confirmed_distinct_findings:number;automated_failures:number;
      category_coverage:{covered_dimensions:number;total_dimensions:number;value:number|null;status:string};
      response_level:{independently_labelled_responses:number;unresolved_or_single_reviewer_labels:number;true_positives:number;false_negatives:number;false_positives:number;true_negatives:number;failure_detection_recall:number|null;false_positive_rate:number|null;status:string};
      failure_discovery_rate:{discovered_distinct_failures:number|null;known_distinct_failures:number|null;value:number|null;undiscovered_failure_ids:string[]|null;status:string};
      discovery_mapping:{status:string;release_id:string|null;reviewer_pseudonym:string|null;fingerprint_sha256:string|null;mapped_response_count:number;total_response_count:number;entries:Array<{response_id:string;test_id:string;question:string;response:string;human_passed:boolean|null;defect_ids:string[]}>}}>
    notice:string;
  }>(`/audits/${id}/method-comparison-results${comparisonId?`?comparison_id=${encodeURIComponent(comparisonId)}`:''}`),
  methodComparison:(id:string)=>request<import("../components/ValidationWorkbench").Package>(`/audits/${id}/method-comparison`,{method:"POST"}),
  freezeMethodComparisonInventory:(id:string,body:object)=>request<{comparison_id:string;inventory_fingerprint_sha256:string;defect_count:number;fixed_template_question_count:number;fixed_template_release_id:string;status:string;notice?:string}>(`/audits/${id}/method-comparison-inventory`,{method:"POST",body:JSON.stringify(body)}),
  freezeMethodComparisonDiscoveryMapping:(id:string,body:object)=>request<{comparison_id:string;run_id:string;mapping_fingerprint_sha256:string;status:string;mapped_response_count:number;reviewer_pseudonym?:string;notice?:string}>(`/audits/${id}/method-comparison-discovery-mapping`,{method:"POST",body:JSON.stringify(body)}),
  interventions:(id:string)=>request<import("../components/ValidationWorkbench").Package>(`/audits/${id}/interventions`,{method:"POST"}),
  followUp:(id:string,test_budget:number)=>request<import("../components/ValidationWorkbench").Package>(`/audits/${id}/follow-up`,{method:"POST",body:JSON.stringify({test_budget})}),
  targetSystems:()=>request<Array<{value:string;label:string;configured:boolean}>>("/target-systems"),
  blindReviewPack:(id:string)=>request<Record<string,unknown>>(`/audits/${id}/blind-review-pack`),
  blindEvaluationReview:(id:string)=>request<import("../types/domain").BlindEvaluationReviewItem[]>(`/audits/${id}/blind-review`),
  compareAudits:(before:string,after:string)=>request<AuditComparison>(`/audit-comparisons?before=${encodeURIComponent(before)}&after=${encodeURIComponent(after)}`),
  ollamaModels:()=>request<Array<{value:string;label:string}>>('/ollama-models'),
  openRouterModels:()=>request<Array<{value:string;label:string}>>('/openrouter-models'),
  openRouterModelChecks:()=>request<import('../types/domain').ModelAvailabilityOption[]>('/openrouter-model-checks'),
  checkOpenRouterModel:(model:string)=>request<{model:string;status:'available'|'unavailable';reason?:string;checked_at:string}>('/openrouter-model-checks',{method:'POST',body:JSON.stringify({model})}),
  targetProviders:()=>request<ProviderOption[]>('/target-providers'),
  createConversation:(authorised:boolean,pasted_text:string,messages?:ConversationInputMessage[]|null,creation_request_key?:string,source_origin:import('../types/domain').ConversationSourceOrigin='unknown')=>request<Conversation>('/conversations',{method:'POST',body:JSON.stringify({authorised,pasted_text,messages,creation_request_key,source_origin})}),
  getConversation:(id:string)=>request<Conversation>(`/conversations/${id}`),
  conversationMemories:(id:string)=>request<Memory[]>(`/conversations/${id}/memories`),
  conversationAgentExecutions:(id:string)=>request<AgentExecution[]>(`/conversations/${id}/agent-executions`),
  coveragePreview:(id:string,testBudget:number,policy:'strict_full_v1'|'evidence_supported_only_v1'='strict_full_v1')=>request<DimensionCoveragePreview>(`/conversations/${id}/test-coverage-preview?test_budget=${testBudget}&coverage_policy=${policy}`),
  deleteConversation:(id:string, confirmation:string)=>request<ConversationDeletionReceipt>(`/conversations/${id}`,{method:'DELETE',body:JSON.stringify({confirmation})}),
  downloadConversationExport: async (id:string) => {
    const response = await fetchResponse(`${BASE}/conversations/${id}/export`);
    if (!response.ok) throw new Error('The local data export could not be created.');
    return response.blob();
  },
  extract:(id:string, provider?:TargetProvider, model?:string)=>request<Memory[]>(`/conversations/${id}/extract`,{method:'POST',body:JSON.stringify({provider,model})}),
  updateMemory:(id:string,body:object)=>request<Memory>(`/memories/${id}`,{method:'PATCH',body:JSON.stringify(body)}),
  addMemory:(body:object)=>request<Memory>('/memories',{method:'POST',body:JSON.stringify(body)}),
  confirm:(id:string,confirmed_memory_ids:string[])=>request<Memory[]>(`/conversations/${id}/confirm-ground-truth`,{method:'POST',body:JSON.stringify({confirmed_memory_ids})}),
  createExperiment:(body:object)=>request<Experiment>('/experiments',{method:'POST',body:JSON.stringify(body)}),
  cancelExperiment:(id:string)=>request<Experiment>(`/experiments/${id}/cancel`,{method:'POST'}),
  experimentGroups:()=>request<Experiment[]>('/experiments'),
  experimentResults:(id:string)=>request<ExperimentAnalytics>(`/experiments/${id}/results`),
  downloadExperimentCsv: async (id:string) => {
    const response = await fetchResponse(`${BASE}/experiments/${id}/export.csv`);
    if (!response.ok) throw new Error('The experiment export could not be created.');
    return response.blob();
  },
  validateAnnotationDataset:(dataset:object,sourceAuthorised=false)=>request<AnnotationImportReport>('/research/annotations/validate',{method:'POST',body:JSON.stringify({dataset,source_authorised:sourceAuthorised})}),
  researchValidity:(dataset:object,predictions:object,sourceAuthorised=false)=>request<ResearchValidityReport>('/research/validity/report',{method:'POST',body:JSON.stringify({dataset,predictions,source_authorised:sourceAuthorised})}),
  analysePilot:(packageData:object,sourceAuthorised=false)=>request<PilotReadinessReport>('/research/pilot/analyse',{method:'POST',body:JSON.stringify({package:packageData,source_authorised:sourceAuthorised})}),
  verifySceneEvidence:(id:string,summary:object)=>request<SceneEvidenceVerification>(`/research/formal/${id}/verify-summary`,{method:'POST',body:JSON.stringify({summary})}),
  formalStudySummary:(id:string)=>request<FormalStudySummary>(`/research/formal/${id}/study-summary`),
  restoreFormalPlan:(id:string)=>request<FormalMatrixCreateResponse>(`/research/formal/${id}/plan`),
  savedFormalRuns:(offset=0)=>request<SavedFormalRunPage>(`/research/formal/saved-runs?offset=${offset}&limit=25`),
  checkReviewedSavedThresholds:(id:string)=>request<ReviewedSavedAcceptanceReport>(`/research/formal/${id}/reviewed-acceptance`),
  checkFrozenThresholds:(body:object)=>request<AcceptanceCheckReport>('/research/formal/acceptance-check',{method:'POST',body:JSON.stringify(body)}),
  createFormalResearchMatrix:(body:object)=>request<FormalMatrixCreateResponse>('/research/formal/research-matrix',{method:'POST',body:JSON.stringify(body)}),
  createFormalSyntheticMatrix:(body:object)=>request<FormalMatrixCreateResponse>('/research/formal/synthetic-matrix',{method:'POST',body:JSON.stringify(body)}),
  createExploratorySyntheticMatrix:(body:object)=>request<FormalMatrixCreateResponse>('/research/exploratory/synthetic-matrix',{method:'POST',body:JSON.stringify(body)}),
  validateLongMemEval:(payload:object|object[],source_authorised:boolean)=>request<LongMemEvalValidationResponse>('/research/benchmarks/longmemeval/validate',{method:'POST',body:JSON.stringify({payload,source_authorised})}),
  runLongMemEval:(payload:object|object[],source_authorised:boolean,source_label:string,memory_strategy:MemoryStrategy)=>request<LongMemEvalRunResponse>('/research/benchmarks/longmemeval/run',{method:'POST',body:JSON.stringify({payload,source_authorised,source_label,memory_strategy,random_seed:42})}),
  validateBenchmark:(family:BenchmarkFamily,payload:object|object[],source_authorised:boolean)=>request<BenchmarkValidationResponse>(`/research/benchmarks/${family}/validate`,{method:'POST',body:JSON.stringify({payload,source_authorised})}),
  runBenchmark:(family:BenchmarkFamily,payload:object|object[],source_authorised:boolean,source_label:string,memory_strategy:MemoryStrategy)=>request<BenchmarkRunResponse>(`/research/benchmarks/${family}/run`,{method:'POST',body:JSON.stringify({payload,source_authorised,source_label,memory_strategy,random_seed:42})}),
  createAudit:(body:object)=>request<AuditRun>('/audits',{method:'POST',body:JSON.stringify(body)}),
  reuseAnswers:(id:string,sourceRunId:string)=>request(`/audits/${id}/reuse-answers`,{method:'POST',body:JSON.stringify({source_run_id:sourceRunId})}),
  generate:(id:string)=>request(`/audits/${id}/generate-tests`,{method:'POST'}), execute:(id:string)=>request(`/audits/${id}/execute`,{method:'POST'}), evaluate:(id:string)=>request(`/audits/${id}/evaluate`,{method:'POST'}), cancel:(id:string)=>request<AuditRun>(`/audits/${id}/cancel`,{method:'POST'}),
  testReview:(id:string)=>request<TestReviewSuite>(`/audits/${id}/test-review`),
  reviewQuestionScopes:(id:string)=>request<TestReviewSuite>(`/audits/${id}/tests/scope-review`,{method:'POST'}),
  continueGeneration:(id:string)=>request<TestReviewSuite>(`/audits/${id}/continue-generation`,{method:'POST'}),
  reviewTest:(runId:string,testId:string,quality_status:'accepted'|'rejected',note?:string)=>request<TestCase>(`/audits/${runId}/tests/${testId}/review`,{method:'PATCH',body:JSON.stringify({quality_status,note})}),
  reviewTestHumanValidity:(runId:string,testId:string,decision:'accepted'|'rejected',reviewer_pseudonym:string,note?:string)=>request<TestCase>(`/audits/${runId}/tests/${testId}/human-validity-review`,{method:'PATCH',body:JSON.stringify({decision,reviewer_pseudonym,note})}),
  regenerateTest:(runId:string,testId:string)=>request<TestCase>(`/audits/${runId}/tests/${testId}/regenerate`,{method:'POST'}),
  targetMemoryTrace:(id:string)=>request<TargetMemoryTrace>(`/audits/${id}/target-memory-trace`),
  cancelledEvidence:(id:string)=>request<CancelledAuditEvidence>(`/audits/${id}/cancelled-evidence`),
  retryPlan:(id:string)=>request<AuditRetryPlan>(`/audits/${id}/retry-plan`),
  retry:(id:string)=>request<AuditRun>(`/audits/${id}/retry`,{method:'POST'}),
  evaluationReview:(id:string)=>request<EvaluationReviewItem[]>(`/audits/${id}/evaluation-review`),
  reviewEvaluation:(runId:string,evaluationId:string,body:object)=>request<EvaluationHumanReview>(`/audits/${runId}/evaluations/${evaluationId}/review`,{method:'PATCH',body:JSON.stringify(body)}),
  evaluationCalibration:(id:string)=>request<EvaluationCalibrationSummary>(`/audits/${id}/evaluation-calibration`),
  downloadExperimentBundle: async (id:string) => {
    const response = await fetchResponse(`${BASE}/experiments/${id}/reproducibility-bundle.json`);
    if (!response.ok) throw new Error('The reproducibility bundle could not be created.');
    return response.blob();
  },
  downloadExperimentArtifact: async (id:string) => {
    const response = await fetchResponse(`${BASE}/experiments/${id}/artifact.zip`);
    if (!response.ok) throw new Error('The frozen experiment artifact could not be created.');
    return response.blob();
  },
  results:(id:string)=>request<AuditResult>(`/audits/${id}/results`), audits:()=>request<AuditRun[]>('/audits'), experiments:()=>request<ExperimentResult[]>('/experiments/summary')
};
