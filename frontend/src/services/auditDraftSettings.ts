import type { TargetMemoryProfile } from '../components/TargetProfileEditor';
import type { MemoryMaintenancePolicy, MemoryStrategy, RetrievalMode, TargetMemoryWriterKind, TargetProvider, TestSuiteMode } from '../types/domain';

export interface AuditDraftSettings {
  selectedStrategies: MemoryStrategy[]; targetProviders: TargetProvider[];
  targetModels: Partial<Record<TargetProvider,string>>;
  pipelineProvider: TargetProvider; evaluatorProvider: TargetProvider;
  semanticReviewProvider: TargetProvider | 'same_as_generator';
  retrievalMode: RetrievalMode; retrievalProvider: TargetProvider | 'automatic';
  retrievalModel: string | null;
  pipelineModel: string | null; semanticReviewModel: string | null; evaluatorModel: string | null;
  budget: number; repetitions: number; suiteMode: TestSuiteMode;
  coveragePolicy?: 'strict_full_v1' | 'evidence_supported_only_v1';
  maintenancePolicy: MemoryMaintenancePolicy; targetMemoryCapacity: number;
  targetMemoryWriter: TargetMemoryWriterKind; targetProfile: TargetMemoryProfile;
  targetSystem: string; compareAuditors: boolean;
}
const providerNames=['rule_based','openrouter','ollama','openai','deepseek','gemini'];
const strategyNames=['no_memory','full_context','weak_first_hit','strong_rule_based','strong_score_based','scope_aware','temporal_importance'];
const integer=(value:unknown,min:number,max:number)=>Number.isInteger(value)&&Number(value)>=min&&Number(value)<=max;
const selection=(value:unknown,options:string[])=>Array.isArray(value)&&value.length<=options.length&&value.every(item=>typeof item==='string'&&options.includes(item))&&new Set(value).size===value.length;
const model=(value:unknown)=>value===null||(typeof value==='string'&&value.length<=4000);

/** Invalid browser settings never replace saved server evidence or reach controls. */
export function parseAuditDraftSettings(value: unknown): AuditDraftSettings | null {
  if(!value||typeof value!=='object')return null;
  const v=value as Record<string,unknown>;
  const p=v.targetProfile as Record<string,unknown>|undefined;
  if(!selection(v.selectedStrategies,strategyNames)||!selection(v.targetProviders,providerNames)
    ||typeof v.pipelineProvider!=='string'||!providerNames.includes(v.pipelineProvider)
    ||typeof v.evaluatorProvider!=='string'||!providerNames.includes(v.evaluatorProvider)
    ||(v.semanticReviewProvider!==undefined&&v.semanticReviewProvider!=='same_as_generator'
      &&(typeof v.semanticReviewProvider!=='string'||!providerNames.includes(v.semanticReviewProvider)))
    ||(v.retrievalMode!==undefined&&!['agent','fixed'].includes(String(v.retrievalMode)))
    ||(v.retrievalProvider!==undefined&&v.retrievalProvider!=='automatic'
      &&(typeof v.retrievalProvider!=='string'||!providerNames.includes(v.retrievalProvider)))
    ||!model(v.retrievalModel??null)
    ||!model(v.pipelineModel)||!model(v.semanticReviewModel??null)||!model(v.evaluatorModel)
    ||!v.targetModels||typeof v.targetModels!=='object'||Array.isArray(v.targetModels)
    ||!Object.entries(v.targetModels).every(([key,item])=>providerNames.includes(key)&&typeof item==='string'&&item.length<=4000)
    ||(v.coveragePolicy!==undefined&&!['strict_full_v1','evidence_supported_only_v1'].includes(String(v.coveragePolicy)))
    ||!integer(v.budget,1,100)||!integer(v.repetitions,1,10)||!integer(v.targetMemoryCapacity,1,500)
    ||!['behavioural','direct_ground_truth','fixed_template','paired_contextual','contextual_indirect'].includes(String(v.suiteMode))
    ||!['append_only','update_aware_consolidation'].includes(String(v.maintenancePolicy))
    ||!['rule_based','llm_structured'].includes(String(v.targetMemoryWriter))
    ||!['controlled-memory','external-http'].includes(String(v.targetSystem))||typeof v.compareAuditors!=='boolean'
    ||!p||typeof p!=='object'||typeof p.label!=='string'||!p.label.trim()||p.label.length>100
    ||!integer(p.version,1,1000000)||!integer(p.max_retrieved_records,1,500)||!integer(p.context_character_budget,100,100000)
    ||typeof p.isolate_project_scope!=='boolean'||typeof p.prefer_current_state!=='boolean'
    ||(p.retain_assistant_history!=null&&typeof p.retain_assistant_history!=='boolean')
    ||(p.retrieve_message_context!=null&&typeof p.retrieve_message_context!=='boolean')
    ||(p.retention_policy!==undefined&&!['scope_recency','source_coverage'].includes(String(p.retention_policy)))
    ||(p.identity_analysis!=null&&!['off','evidence_links'].includes(String(p.identity_analysis)))
    ||(p.identity_analysis_output_token_limit!=null&&!integer(p.identity_analysis_output_token_limit,512,8192))
    ||(p.reasoning_effort!==undefined&&p.reasoning_effort!=='low'&&p.reasoning_effort!=='medium')
    ||(p.identity_analysis_reasoning_effort!==undefined&&p.identity_analysis_reasoning_effort!=='low')
    ||(p.answer_validation!==undefined&&p.answer_validation!=='off'&&p.answer_validation!=='source_grounding')
    ||(p.answer_validation_output_token_limit!==undefined&&!integer(p.answer_validation_output_token_limit,512,8192))
    ||(p.answer_validation_reasoning_effort!==undefined&&p.answer_validation_reasoning_effort!=='low'&&p.answer_validation_reasoning_effort!=='medium')
    ||(p.identity_analysis_failure_policy!=null&&!['fail_closed','continue_without_advisory'].includes(String(p.identity_analysis_failure_policy)))
    ||typeof p.additional_instructions!=='string'||p.additional_instructions.length>4000
    ||(p.output_token_limit!=null&&!integer(p.output_token_limit,1,8192)))return null;
  // Copy only known fields; browser debris is not part of the target profile.
  return {...v,coveragePolicy:v.coveragePolicy??'strict_full_v1',semanticReviewProvider:v.semanticReviewProvider??'same_as_generator',semanticReviewModel:v.semanticReviewModel??null,
    retrievalMode:v.retrievalMode??'agent',retrievalProvider:v.retrievalProvider??'automatic',retrievalModel:v.retrievalModel??null,
    targetProfile:{label:p.label,version:p.version,max_retrieved_records:p.max_retrieved_records,
    context_character_budget:p.context_character_budget,isolate_project_scope:p.isolate_project_scope,
    prefer_current_state:p.prefer_current_state,additional_instructions:p.additional_instructions,
    ...(p.retain_assistant_history!=null?{retain_assistant_history:p.retain_assistant_history}:{}),
    ...(p.retrieve_message_context!=null?{retrieve_message_context:p.retrieve_message_context}:{}),
    ...(p.retention_policy!==undefined?{retention_policy:p.retention_policy}:{}),
    ...(p.reasoning_effort!==undefined?{reasoning_effort:p.reasoning_effort}:{}),
    ...(p.identity_analysis_reasoning_effort!==undefined?{identity_analysis_reasoning_effort:p.identity_analysis_reasoning_effort}:{}),
    ...(p.answer_validation!==undefined?{answer_validation:p.answer_validation}:{}),
    ...(p.answer_validation_output_token_limit!==undefined?{answer_validation_output_token_limit:p.answer_validation_output_token_limit}:{}),
    ...(p.answer_validation_reasoning_effort!==undefined?{answer_validation_reasoning_effort:p.answer_validation_reasoning_effort}:{}),
    ...(p.identity_analysis!=null?{identity_analysis:p.identity_analysis}:{}),
    ...(p.identity_analysis_output_token_limit!=null?{identity_analysis_output_token_limit:p.identity_analysis_output_token_limit}:{}),
    identity_analysis_failure_policy:p.identity_analysis_failure_policy??'fail_closed',
    output_token_limit:p.output_token_limit??null}} as unknown as AuditDraftSettings;
}
