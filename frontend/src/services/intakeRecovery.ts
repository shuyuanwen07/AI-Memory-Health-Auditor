import type { ConversationInputMessage, ConversationSourceOrigin, TargetProvider } from '../types/domain';
export const INTAKE_KEY = 'mha-new-audit-intake-v1';
export interface IntakeRecovery {
  requestKey: string; text: string; messages: ConversationInputMessage[] | null;
  provider: TargetProvider; model: string | null; sourceOrigin: ConversationSourceOrigin; conversationId?: string;
}
export function loadIntakeRecovery(): IntakeRecovery | null {
  try {
    const value=JSON.parse(sessionStorage.getItem(INTAKE_KEY) ?? 'null');
    if (!value || typeof value!=='object' || typeof value.requestKey!=='string'
      || !/^[A-Za-z0-9_-]{16,100}$/.test(value.requestKey)
      || typeof value.text!=='string' || value.text.length>1000000
      || !['rule_based','openrouter','openai','deepseek','gemini'].includes(value.provider)
      || (value.provider!=='rule_based' && value.model===null)
      || (value.model!==null && (typeof value.model!=='string' || !value.model.trim()))
      || (value.conversationId!==undefined && (typeof value.conversationId!=='string'||!value.conversationId.trim()))
      || (value.messages!==null && (!Array.isArray(value.messages) || !value.messages.length || value.messages.length>10000
        || !value.messages.every((message:ConversationInputMessage)=>message && typeof message.role==='string' && typeof message.content==='string' && Boolean(message.content.trim())
          && (message.message_id===undefined||typeof message.message_id==='string')
          && (message.timestamp===undefined||typeof message.timestamp==='string'))))) return null;
    const allowedOrigins=['synthetic','authorised','deidentified','unknown'];
    if (value.sourceOrigin!==undefined && !allowedOrigins.includes(value.sourceOrigin)) return null;
    return {...value,sourceOrigin:value.sourceOrigin ?? 'unknown'};
  } catch { return null; }
}
