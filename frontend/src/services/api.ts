import type { AnnotationImportReport, AuditResult, AuditRun, Conversation, Experiment, ExperimentAnalytics, ExperimentResult, LongMemEvalValidationResponse, Memory, ProviderOption, ResearchValidityReport, TargetMemoryTrace, TestCase, TestReviewSuite } from '../types/domain';
const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1';
async function request<T>(path:string, options?:RequestInit):Promise<T> { const r=await fetch(`${BASE}${path}`,{headers:{'Content-Type':'application/json'},...options}); if(!r.ok) throw new Error((await r.json().catch(()=>null))?.detail ?? 'The request could not be completed.'); return r.status===204 ? undefined as T : r.json(); }
export const api = {
  targetProviders:()=>request<ProviderOption[]>('/target-providers'),
  createConversation:(authorised:boolean,pasted_text:string)=>request<Conversation>('/conversations',{method:'POST',body:JSON.stringify({authorised,pasted_text})}),
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
  validateLongMemEval:(payload:object|object[])=>request<LongMemEvalValidationResponse>('/research/benchmarks/longmemeval/validate',{method:'POST',body:JSON.stringify({payload})}),
  createAudit:(body:object)=>request<AuditRun>('/audits',{method:'POST',body:JSON.stringify(body)}),
  generate:(id:string)=>request(`/audits/${id}/generate-tests`,{method:'POST'}), execute:(id:string)=>request(`/audits/${id}/execute`,{method:'POST'}), evaluate:(id:string)=>request(`/audits/${id}/evaluate`,{method:'POST'}),
  testReview:(id:string)=>request<TestReviewSuite>(`/audits/${id}/test-review`),
  reviewTest:(runId:string,testId:string,quality_status:'accepted'|'rejected',note?:string)=>request<TestCase>(`/audits/${runId}/tests/${testId}/review`,{method:'PATCH',body:JSON.stringify({quality_status,note})}),
  regenerateTest:(runId:string,testId:string)=>request<TestCase>(`/audits/${runId}/tests/${testId}/regenerate`,{method:'POST'}),
  targetMemoryTrace:(id:string)=>request<TargetMemoryTrace>(`/audits/${id}/target-memory-trace`),
  retry:(id:string)=>request<AuditRun>(`/audits/${id}/retry`,{method:'POST'}),
  results:(id:string)=>request<AuditResult>(`/audits/${id}/results`), audits:()=>request<AuditRun[]>('/audits'), experiments:()=>request<ExperimentResult[]>('/experiments/summary')
};
