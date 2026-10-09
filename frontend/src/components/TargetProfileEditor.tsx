import { Input, InputNumber, Switch, Form, Card, Space, Tag } from 'antd';
export interface TargetMemoryProfile {
  label: string; version: number; max_retrieved_records: number; context_character_budget: number;
  isolate_project_scope: boolean; prefer_current_state: boolean; additional_instructions: string;
}
export const defaultTargetProfile: TargetMemoryProfile = {label:'Original configuration',version:1,max_retrieved_records:50,context_character_budget:16000,isolate_project_scope:false,prefer_current_state:false,additional_instructions:''};
export function TargetProfileEditor({value,onChange,disabled=false}: {value:TargetMemoryProfile;onChange:(value:TargetMemoryProfile)=>void;disabled?:boolean}) {
  const patch = (change:Partial<TargetMemoryProfile>)=>onChange({...value,...change});
  return <Card title="Memory configuration" extra={<Tag>Version {value.version}</Tag>}>
    <p>These settings control the target's memory and instructions. Reference answers stay in the auditor. Every run saves its own configuration.</p>
    <Form layout="vertical" disabled={disabled}>
      <Form.Item label="Configuration name"><Input aria-label="Configuration name" value={value.label} maxLength={100} onChange={event=>patch({label:event.target.value})}/></Form.Item>
      <Space wrap align="start"><Form.Item label="Maximum retrieved memories"><InputNumber aria-label="Maximum retrieved memories" min={1} max={500} value={value.max_retrieved_records} onChange={number=>patch({max_retrieved_records:number??1})}/></Form.Item>
      <Form.Item label="Memory context character budget"><InputNumber aria-label="Memory context character budget" min={100} max={100000} value={value.context_character_budget} onChange={number=>patch({context_character_budget:number??100})}/></Form.Item></Space>
      <Form.Item label="Keep projects separate"><Switch aria-label="Keep projects separate" checked={value.isolate_project_scope} onChange={checked=>patch({isolate_project_scope:checked})}/></Form.Item>
      <Form.Item label="Prefer current facts for current-state questions"><Switch aria-label="Prefer current facts" checked={value.prefer_current_state} onChange={checked=>patch({prefer_current_state:checked})}/></Form.Item>
      <Form.Item label="Additional target instructions" extra="Use general rules. Inserting a question's expected answer would invalidate the experiment."><Input.TextArea aria-label="Additional target instructions" rows={4} maxLength={4000} showCount value={value.additional_instructions} onChange={event=>patch({additional_instructions:event.target.value})}/></Form.Item>
    </Form>
  </Card>;
}
