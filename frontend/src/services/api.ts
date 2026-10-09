import { SESSION_ENDED, workspaceCsrf } from './access';
import type { AccessStatus } from './access';
import { friendlyText } from './display';
import type { TargetProvider, AnnotationImportReport, AuditResult, AuditRetryPlan, AuditRun, BenchmarkFamily, BenchmarkRunResponse, BenchmarkValidationResponse, CancelledAuditEvidence, Conversation, ConversationDeletionReceipt, ConversationInputMessage, EvaluationCalibrationSummary, EvaluationHumanReview, EvaluationReviewItem, Experiment, ExperimentAnalytics, ExperimentResult, FormalMatrixCreateResponse, LongMemEvalRunResponse, LongMemEvalValidationResponse, Memory, MemoryStrategy, PilotReadinessReport, ProviderOption, ResearchValidityReport, TargetMemoryTrace, TestCase, TestReviewSuite } from '../types/domain';
const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1';
import type { AuditComparison } from '../types/domain';
export function apiErrorMessage(detail: unknown): string {
  if (typeof detail === 'string') return friendlyText(detail);
  if (Array.isArray(detail)) {
    const fields: Record<string, string> = { canonical_value: 'Memory text', timestamp: 'Date and time', test_budget: 'Test budget', model: 'Model', content: 'Message text' };
    const messages = detail.flatMap((issue) => {
      if (!issue || typeof issue !== 'object' || typeof issue.msg !== 'string') return [];
      const field = Array.isArray(issue.loc) ? issue.loc.at(-1) : undefined;
      return [friendlyText(`${fields[String(field)] ?? 'Input'}: ${issue.msg}`)];
    });
    if (messages.length) return messages.join(' ');
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
async function request<T>(path:string, options?:RequestInit):Promise<T> { const r=await fetchResponse(`${BASE}${path}`,{headers:{'Content-Type':'application/json'},...options}); if(!r.ok) throw new Error(apiErrorMessage((await r.json().catch(()=>null))?.detail)); return r.status===204 ? undefined as T : r.json(); }
export const api = {
  runLiveBenchmark:(body:object,signal?:AbortSignal)=>request<import('../components/LiveBenchmark').LiveBenchmarkResult>('/research/benchmarks/longmemeval/live',{method:'POST',body:JSON.stringify(body),signal}),
  importSemanticReview:(body:object)=>request<import('../components/BenchmarkSemanticReview').SemanticReviewResult>('/research/benchmarks/longmemeval/semantic-review',{method:'POST',body:JSON.stringify(body)}),
  accessStatus:(signal?:AbortSignal)=>request<AccessStatus>('/access/status',{signal}),
  signIn:(password:string)=>request<AccessStatus>('/access/sign-in',{method:'POST',body:JSON.stringify({password})}),
  signOut:()=>request<{signed_out:boolean}>('/access/sign-out',{method:'POST'}),
  getAudit:(id:string)=>request<AuditRun>(`/audits/${id}`),
  auditorQuality:()=>request<import("../pages/AuditorQuality").QualityReport>("/auditor-quality"),
  diagnosis:(id:string)=>request<import("../components/ValidationWorkbench").Diagnosis>(`/audits/${id}/diagnosis`),
  validationHistories:()=>request<Array<{conversation_id:string;label:string}>>("/validation-histories"),
  repairExperiment:(id:string,body:object)=>request<import("../components/ValidationWorkbench").Package>(`/audits/${id}/repair-experiment`,{method:"POST",body:JSON.stringify(body)}),
  methodComparisonResults:(id:string)=>request<{conditions:Array<{run_id:string;label:string;actual_calls:number|null;completed_answers?:number;unknown_attempt_records?:number;resolved_labels:number;human_confirmed_distinct_findings:number}>;notice:string}>(`/audits/${id}/method-comparison-results`),
  methodComparison:(id:string)=>request<import("../components/ValidationWorkbench").Package>(`/audits/${id}/method-comparison`,{method:"POST"}),
  interventions:(id:string)=>request<import("../components/ValidationWorkbench").Package>(`/audits/${id}/interventions`,{method:"POST"}),
  followUp:(id:string,test_budget:number)=>request<import("../components/ValidationWorkbench").Package>(`/audits/${id}/follow-up`,{method:"POST",body:JSON.stringify({test_budget})}),
  targetSystems:()=>request<Array<{value:string;label:string;configured:boolean}>>("/target-systems"),
  blindEvaluationReview:(id:string)=>request<import("../types/domain").BlindEvaluationReviewItem[]>(`/audits/${id}/blind-review`),
  compareAudits:(before:string,after:string)=>request<AuditComparison>(`/audit-comparisons?before=${encodeURIComponent(before)}&after=${encodeURIComponent(after)}`),
  ollamaModels:()=>request<Array<{value:string;label:string}>>('/ollama-models'),
  openRouterModels:()=>request<Array<{value:string;label:string}>>('/openrouter-models'),
  targetProviders:()=>request<ProviderOption[]>('/target-providers'),
  createConversation:(authorised:boolean,pasted_text:string,messages?:ConversationInputMessage[]|null)=>request<Conversation>('/conversations',{method:'POST',body:JSON.stringify({authorised,pasted_text,messages})}),
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
  validateAnnotationDataset:(dataset:object)=>request<AnnotationImportReport>('/research/annotations/validate',{method:'POST',body:JSON.stringify({dataset})}),
  researchValidity:(dataset:object,predictions:object)=>request<ResearchValidityReport>('/research/validity/report',{method:'POST',body:JSON.stringify({dataset,predictions})}),
  analysePilot:(packageData:object)=>request<PilotReadinessReport>('/research/pilot/analyse',{method:'POST',body:JSON.stringify({package:packageData})}),
  createFormalSyntheticMatrix:(body:object)=>request<FormalMatrixCreateResponse>('/research/formal/synthetic-matrix',{method:'POST',body:JSON.stringify(body)}),
  validateLongMemEval:(payload:object|object[])=>request<LongMemEvalValidationResponse>('/research/benchmarks/longmemeval/validate',{method:'POST',body:JSON.stringify({payload})}),
  runLongMemEval:(payload:object|object[], source_label:string, memory_strategy:MemoryStrategy)=>request<LongMemEvalRunResponse>('/research/benchmarks/longmemeval/run',{method:'POST',body:JSON.stringify({payload,source_authorised:true,source_label,memory_strategy,random_seed:42})}),
  validateBenchmark:(family:BenchmarkFamily,payload:object|object[])=>request<BenchmarkValidationResponse>(`/research/benchmarks/${family}/validate`,{method:'POST',body:JSON.stringify({payload})}),
  runBenchmark:(family:BenchmarkFamily,payload:object|object[],source_label:string,memory_strategy:MemoryStrategy)=>request<BenchmarkRunResponse>(`/research/benchmarks/${family}/run`,{method:'POST',body:JSON.stringify({payload,source_authorised:true,source_label,memory_strategy,random_seed:42})}),
  createAudit:(body:object)=>request<AuditRun>('/audits',{method:'POST',body:JSON.stringify(body)}),
  generate:(id:string)=>request(`/audits/${id}/generate-tests`,{method:'POST'}), execute:(id:string)=>request(`/audits/${id}/execute`,{method:'POST'}), evaluate:(id:string)=>request(`/audits/${id}/evaluate`,{method:'POST'}), cancel:(id:string)=>request<AuditRun>(`/audits/${id}/cancel`,{method:'POST'}),
  testReview:(id:string)=>request<TestReviewSuite>(`/audits/${id}/test-review`),
  reviewTest:(runId:string,testId:string,quality_status:'accepted'|'rejected',note?:string)=>request<TestCase>(`/audits/${runId}/tests/${testId}/review`,{method:'PATCH',body:JSON.stringify({quality_status,note})}),
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
