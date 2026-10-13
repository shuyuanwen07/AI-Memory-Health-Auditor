import { Input, InputNumber, Switch, Form, Card, Space, Tag, Select } from 'antd';
import type { ReactNode } from 'react';
import type { MemoryMaintenancePolicy, TargetMemoryWriterKind } from '../types/domain';
export interface TargetMemoryProfile {
  label: string; version: number; max_retrieved_records: number; context_character_budget: number;
  isolate_project_scope: boolean; prefer_current_state: boolean; additional_instructions: string;
  output_token_limit?: number | null;
}
export const defaultTargetProfile: TargetMemoryProfile = {label:'Original configuration',version:1,max_retrieved_records:50,context_character_budget:16000,isolate_project_scope:false,prefer_current_state:false,additional_instructions:'',output_token_limit:512};
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
export function TargetProfileEditor({value,onChange,disabled=false,storeSettings,retrievalControls}: {value:TargetMemoryProfile;onChange:(value:TargetMemoryProfile)=>void;disabled?:boolean;storeSettings?:StoreSettings;retrievalControls?:ReactNode}) {
  const patch = (change:Partial<TargetMemoryProfile>)=>onChange({...value,...change});
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
      <Form.Item label="Answer length limit" extra="Maximum generated tokens, not words. Some models include reasoning in this limit. Saved for every new model audit; use the same limit when comparing memory repairs. Local rule-based answers do not use this setting."><InputNumber aria-label="Answer length limit" min={1} max={8192} value={value.output_token_limit ?? null} placeholder="Not recorded" onChange={number=>{if(number!=null)patch({output_token_limit:number});}}/></Form.Item>
      <Form.Item label="Additional target instructions" extra="Use general rules. Inserting a question's expected answer would invalidate the experiment."><Input.TextArea aria-label="Additional target instructions" rows={4} maxLength={4000} showCount value={value.additional_instructions} onChange={event=>patch({additional_instructions:event.target.value})}/></Form.Item>
    </Form>
  </Card>;
}
