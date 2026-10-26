import { Input, InputNumber, Switch, Form, Card, Space, Tag, Select } from 'antd';
import type { ReactNode } from 'react';
import type { MemoryMaintenancePolicy, TargetMemoryWriterKind } from '../types/domain';
export interface TargetMemoryProfile {
  label: string; version: number; max_retrieved_records: number; context_character_budget: number;
  isolate_project_scope: boolean; prefer_current_state: boolean; additional_instructions: string;
  output_token_limit?: number | null;
  reasoning_effort?: 'low' | 'medium'; identity_analysis_reasoning_effort?: 'low';
  retain_assistant_history?: boolean; retrieve_message_context?: boolean;
  retention_policy?: 'scope_recency' | 'source_coverage';
  identity_analysis?: 'off' | 'evidence_links'; identity_analysis_output_token_limit?: number;
  identity_analysis_failure_policy?: 'fail_closed' | 'continue_without_advisory';
  answer_validation?: 'off' | 'source_grounding';
  answer_validation_output_token_limit?: number;
  answer_validation_reasoning_effort?: 'low' | 'medium';
}
export const defaultTargetProfile: TargetMemoryProfile = {label:'Original configuration',version:1,max_retrieved_records:50,context_character_budget:16000,isolate_project_scope:false,prefer_current_state:false,additional_instructions:'',output_token_limit:2048,identity_analysis_failure_policy:'fail_closed'};
type StoreSettings = {
  maintenancePolicy: MemoryMaintenancePolicy;
  onMaintenancePolicyChange: (value: MemoryMaintenancePolicy) => void;
  capacity: number;
  onCapacityChange: (value: number) => void;
  writer: TargetMemoryWriterKind;
  onWriterChange: (value: TargetMemoryWriterKind) => void;
  disableLlmWriter: boolean;
  disabled: boolean;
};
export function supportsAnswerValidation(provider: string, model: string, targetSystem = 'controlled-memory'): boolean {
  return targetSystem === 'controlled-memory' && provider === 'openrouter' && model === 'openai/gpt-6-luna';
}
export function TargetProfileEditor({value,onChange,disabled=false,storeSettings,retrievalControls,answerValidationAvailable=false}: {value:TargetMemoryProfile;onChange:(value:TargetMemoryProfile)=>void;disabled?:boolean;storeSettings?:StoreSettings;retrievalControls?:ReactNode;answerValidationAvailable?:boolean}) {
  const patch = (change:Partial<TargetMemoryProfile>)=>onChange({...value,...change});
  const validationOn = value.answer_validation === 'source_grounding';
  const toggleAnswerValidation = (checked: boolean) => {
    if (checked) {
      if (answerValidationAvailable) patch({answer_validation:'source_grounding',answer_validation_output_token_limit:value.answer_validation_output_token_limit ?? 8192});
      return;
    }
    const next = {...value,answer_validation:'off' as const};
    delete next.answer_validation_output_token_limit;
    delete next.answer_validation_reasoning_effort;
    onChange(next);
  };
  return <Card title="Memory system configuration" extra={<Tag>Version {value.version}</Tag>}>
    <p>Store settings control what the target remembers. Retrieval settings control what it can use for each answer. Reference answers stay in the auditor.</p>
    <Form layout="vertical" disabled={disabled}>
      <Form.Item label="Configuration name"><Input aria-label="Configuration name" value={value.label} maxLength={100} onChange={event=>patch({label:event.target.value})}/></Form.Item>
      {storeSettings && <>
        <h3>Store and update</h3>
        <Space wrap align="start">
          <Form.Item label="Target memory capacity" extra="Retention limit; unresolved conflicts may exceed it."><InputNumber aria-label="Target memory capacity" min={1} max={500} value={storeSettings.capacity} disabled={storeSettings.disabled} onChange={number=>{if(number!=null)storeSettings.onCapacityChange(number);}}/></Form.Item>
          <Form.Item label="Memory maintenance" extra="How new information updates existing memories."><Select<MemoryMaintenancePolicy> aria-label="Memory maintenance" value={storeSettings.maintenancePolicy} disabled={storeSettings.disabled} onChange={storeSettings.onMaintenancePolicyChange} options={[{value:'update_aware_consolidation',label:'Update-aware consolidation'},{value:'append_only',label:'Append only'}]}/></Form.Item>
          <Form.Item label="Target memory writer" extra={storeSettings.disableLlmWriter ? 'Model writing is unavailable in this audit setup.' : 'The writer reads the authorized conversation; reference answers stay private.'}><Select<TargetMemoryWriterKind> virtual={false} aria-label="Target memory writer" value={storeSettings.writer} disabled={storeSettings.disabled} onChange={storeSettings.onWriterChange} options={[{value:'rule_based',label:'Rule-based writer'},{value:'llm_structured',label:'Structured LLM writer',disabled:storeSettings.disableLlmWriter}]}/></Form.Item>
        </Space>
      </>}
      {retrievalControls && <><h3>Choose memories</h3>{retrievalControls}</>}
      <h3>Retrieve and answer</h3>
      <Space wrap align="start"><Form.Item label="Memories retrieved per answer" extra="Maximum records passed to the target model for one question."><InputNumber aria-label="Maximum retrieved memories" min={1} max={500} value={value.max_retrieved_records} onChange={number=>{if(number!=null)patch({max_retrieved_records:number});}}/></Form.Item>
      <Form.Item label="Memory context character budget" extra="Maximum memory text passed to the target for one answer."><InputNumber aria-label="Memory context character budget" min={100} max={100000} value={value.context_character_budget} onChange={number=>{if(number!=null)patch({context_character_budget:number});}}/></Form.Item></Space>
      <Form.Item label="Keep projects separate"><Switch aria-label="Keep projects separate" checked={value.isolate_project_scope} onChange={checked=>patch({isolate_project_scope:checked})}/></Form.Item>
      <Form.Item label="Prefer current facts for current-state questions"><Switch aria-label="Prefer current facts" checked={value.prefer_current_state} onChange={checked=>patch({prefer_current_state:checked})}/></Form.Item>
      <Form.Item label="Remember previous assistant replies" extra="Stores attributed conversation history, not verified user facts. Counts toward memory capacity."><Switch aria-label="Remember previous assistant replies" checked={value.retain_assistant_history ?? false} onChange={checked=>patch({retain_assistant_history:checked})}/></Form.Item>
      <Form.Item label="When memory fills up" extra="Both choices use the same capacity and protect unresolved conflicts. Balancing messages can preserve earlier evidence while losing other details; it does not guarantee complete recall."><Select aria-label="When memory fills up" virtual={false} value={value.retention_policy ?? 'scope_recency'} onChange={retention_policy=>patch({retention_policy})} options={[{value:'scope_recency',label:'Prefer recent facts within each importance level'},{value:'source_coverage',label:'Balance coverage across messages'}]}/></Form.Item>
      <Form.Item label="Retrieve related fragments from the same message" extra="Keeps available source context together within the existing answer budget. The first-hit baseline remains unchanged."><Switch aria-label="Retrieve same-message context" checked={value.retrieve_message_context ?? false} onChange={checked=>patch({retrieve_message_context:checked})}/></Form.Item>
      <Form.Item label="Check event identity before answering" extra="Uses an additional request to the target model for counting or event-identity questions. Links remain tentative; source quotations and extra usage are recorded."><Switch aria-label="Check event identity" checked={value.identity_analysis === 'evidence_links'} onChange={checked=>patch({identity_analysis:checked?'evidence_links':'off',identity_analysis_failure_policy:'fail_closed'})}/></Form.Item>
      {value.identity_analysis === 'evidence_links' && <Form.Item label="Identity analysis output limit" extra="Separate from the final answer budget; may include model reasoning."><InputNumber aria-label="Identity analysis output limit" min={512} max={8192} value={value.identity_analysis_output_token_limit ?? 4096} onChange={number=>{if(number!=null)patch({identity_analysis_output_token_limit:number});}}/></Form.Item>}
      {value.identity_analysis === 'evidence_links' && <Form.Item label="If identity suggestions are unavailable" extra="For a verifiable OpenRouter identity reply that is rejected, continuing discards those suggestions and uses the same planned final model with its existing memories. The failed check remains recorded. Other providers, network errors, and model or budget mismatches still stop the answer."><Select aria-label="If identity suggestions are unavailable" virtual={false} value={value.identity_analysis_failure_policy ?? 'fail_closed'} onChange={policy=>patch({identity_analysis_failure_policy:policy})} options={[{value:'fail_closed',label:'Stop and show the error'},{value:'continue_without_advisory',label:'Continue without identity suggestions'}]}/></Form.Item>}
      <Form.Item label="Check answer facts before returning" extra="Optional, for controlled GPT-6 Luna through OpenRouter only. Adds one model request using only the target’s supplied memories and answer draft. A failed check stops the answer. The check can still be wrong."><Switch aria-label="Check answer facts before returning" checked={validationOn} disabled={disabled || (!answerValidationAvailable && !validationOn)} onChange={toggleAnswerValidation}/></Form.Item>
      {!answerValidationAvailable && <p role={validationOn?'alert':'status'}>{validationOn ? 'This saved check is not supported by the selected target. Turn it off or select controlled GPT-6 Luna before running; it will not be silently removed.' : 'Select controlled GPT-6 Luna through OpenRouter to enable this optional check. Target support is not assumed when it is unknown.'}</p>}
      {validationOn && <Space wrap align="start">
        <Form.Item label="Answer check output limit" extra="Separate from the answer limit; 8192 tokens by default, including any reasoning."><InputNumber aria-label="Answer check output limit" min={512} max={8192} precision={0} disabled={!answerValidationAvailable || disabled} value={value.answer_validation_output_token_limit ?? 8192} onChange={number=>{if(number!=null)patch({answer_validation_output_token_limit:number});}}/></Form.Item>
        <Form.Item label="Answer check reasoning effort" extra="A requested setting, not proof of the provider’s actual reasoning."><Select<'default'|'low'|'medium'> aria-label="Answer check reasoning effort" virtual={false} disabled={!answerValidationAvailable || disabled} value={value.answer_validation_reasoning_effort ?? 'default'} onChange={effort=>{
          if(effort==='default'){const next={...value};delete next.answer_validation_reasoning_effort;onChange(next);}
          else patch({answer_validation_reasoning_effort:effort});
        }} options={[{value:'default',label:'Provider default (not sent)'},{value:'low',label:'Low'},{value:'medium',label:'Medium'}]}/></Form.Item>
      </Space>}
      <Form.Item label="Answer length limit" extra="Maximum generated tokens, not words. Some models include reasoning in this limit. New configurations start at 2048 to leave room for reasoning and the answer; larger limits can increase cost and latency. Saved for every new model audit; use the same limit when comparing memory repairs. Local rule-based answers do not use this setting."><InputNumber aria-label="Answer length limit" min={1} max={8192} value={value.output_token_limit ?? null} placeholder="Not recorded" onChange={number=>{if(number!=null)patch({output_token_limit:number});}}/></Form.Item>
      <Form.Item label="Additional target instructions" extra="Use general rules. Inserting a question's expected answer would invalidate the experiment."><Input.TextArea aria-label="Additional target instructions" rows={4} maxLength={4000} showCount value={value.additional_instructions} onChange={event=>patch({additional_instructions:event.target.value})}/></Form.Item>
    </Form>
  </Card>;
}
