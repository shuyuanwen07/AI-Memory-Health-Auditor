import type { AnnotationImportReport, AuditResult, AuditRetryPlan, AuditRun, BenchmarkFamily, BenchmarkRunResponse, BenchmarkValidationResponse, Conversation, ConversationDeletionReceipt, ConversationInputMessage, EvaluationCalibrationSummary, EvaluationHumanReview, EvaluationReviewItem, Experiment, ExperimentAnalytics, ExperimentResult, LongMemEvalRunResponse, LongMemEvalValidationResponse, Memory, MemoryStrategy, PilotReadinessReport, ProviderOption, ResearchValidityReport, TargetMemoryTrace, TestCase, TestReviewSuite } from '../types/domain';
const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1';
async function request<T>(path:string, options?:RequestInit):Promise<T> { const r=await fetch(`${BASE}${path}`,{headers:{'Content-Type':'application/json'},...options}); if(!r.ok) throw new Error((await r.json().catch(()=>null))?.detail ?? 'The request could not be completed.'); return r.status===204 ? undefined as T : r.json(); }
export const api = {
  targetProviders:()=>request<ProviderOption[]>('/target-providers'),
  createConversation:(authorised:boolean,pasted_text:string,messages?:ConversationInputMessage[]|null)=>request<Conversation>('/conversations',{method:'POST',body:JSON.stringify({authorised,pasted_text,messages})}),
  deleteConversation:(id:string, confirmation:string)=>request<ConversationDeletionReceipt>(`/conversations/${id}`,{method:'DELETE',body:JSON.stringify({confirmation})}),
  downloadConversationExport: async (id:string) => {
    const response = await fetch(`${BASE}/conversations/${id}/export`);
    if (!response.ok) throw new Error('The local data export could not be created.');
    return response.blob();
  },
  extract:(id:string)=>request<Memory[]>(`/conversations/${id}/extract`,{method:'POST'}),
  updateMemory:(id:string,body:object)=>request<Memory>(`/memories/${id}`,{method:'PATCH',body:JSON.stringify(body)}),
  addMemory:(body:object)=>request<Memory>('/memories',{method:'POST',body:JSON.stringify(body)}),
  confirm:(id:string,confirmed_memory_ids:string[])=>request<Memory[]>(`/conversations/${id}/confirm-ground-truth`,{method:'POST',body:JSON.stringify({confirmed_memory_ids})}),
  createExperiment:(body:object)=>request<Experiment>('/experiments',{method:'POST',body:JSON.stringify(body)}),
  experimentGroups:()=>request<Experiment[]>('/experiments'),
  experimentResults:(id:string)=>request<ExperimentAnalytics>(`/experiments/${id}/results`),
  downloadExperimentCsv: async (id:string) => {
    const response = await fetch(`${BASE}/experiments/${id}/export.csv`);
    if (!response.ok) throw new Error('The experiment export could not be created.');
    return response.blob();
  },
  validateAnnotationDataset:(dataset:object)=>request<AnnotationImportReport>('/research/annotations/validate',{method:'POST',body:JSON.stringify({dataset})}),
  researchValidity:(dataset:object,predictions:object)=>request<ResearchValidityReport>('/research/validity/report',{method:'POST',body:JSON.stringify({dataset,predictions})}),
  analysePilot:(packageData:object)=>request<PilotReadinessReport>('/research/pilot/analyse',{method:'POST',body:JSON.stringify({package:packageData})}),
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
  retryPlan:(id:string)=>request<AuditRetryPlan>(`/audits/${id}/retry-plan`),
  retry:(id:string)=>request<AuditRun>(`/audits/${id}/retry`,{method:'POST'}),
  evaluationReview:(id:string)=>request<EvaluationReviewItem[]>(`/audits/${id}/evaluation-review`),
  reviewEvaluation:(runId:string,evaluationId:string,body:object)=>request<EvaluationHumanReview>(`/audits/${runId}/evaluations/${evaluationId}/review`,{method:'PATCH',body:JSON.stringify(body)}),
  evaluationCalibration:(id:string)=>request<EvaluationCalibrationSummary>(`/audits/${id}/evaluation-calibration`),
  downloadExperimentBundle: async (id:string) => {
    const response = await fetch(`${BASE}/experiments/${id}/reproducibility-bundle.json`);
    if (!response.ok) throw new Error('The reproducibility bundle could not be created.');
    return response.blob();
  },
  downloadExperimentArtifact: async (id:string) => {
    const response = await fetch(`${BASE}/experiments/${id}/artifact.zip`);
    if (!response.ok) throw new Error('The frozen experiment artifact could not be created.');
    return response.blob();
  },
  results:(id:string)=>request<AuditResult>(`/audits/${id}/results`), audits:()=>request<AuditRun[]>('/audits'), experiments:()=>request<ExperimentResult[]>('/experiments/summary')
};
