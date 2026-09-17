import { ChangeEvent, useMemo, useState } from 'react';
import type { ConversationInputMessage } from '../types/domain';
import './review.css';

type Props = {
  text: string;
  consent: boolean;
  busy: boolean;
  onTextChange: (text: string) => void;
  onConsentChange: (consent: boolean) => void;
  onImport: (messages: ConversationInputMessage[], previewText: string) => void;
  onImportError: (message: string) => void;
  onClearDraft: () => void;
  onContinue: () => void;
};

type UploadMessage = ConversationInputMessage;

const supportedRoles = new Set(['user', 'assistant', 'system', 'tool']);
const MAX_CONVERSATION_FILE_BYTES = 1_000_000;
const MAX_CONVERSATION_CHARACTERS = 1_000_000;

function getMessageCount(value: string) {
  return value.split(/\r?\n/).filter((line) => line.trim()).length;
}

function isUploadMessage(value: unknown): value is UploadMessage {
  if (!value || typeof value !== 'object') return false;
  const message = value as { message_id?: unknown; role?: unknown; content?: unknown; timestamp?: unknown };
  if (message.message_id !== undefined && typeof message.message_id !== 'string') return false;
  if (message.timestamp !== undefined && (typeof message.timestamp !== 'string' || Number.isNaN(Date.parse(message.timestamp)))) return false;
  return typeof message.role === 'string' && typeof message.content === 'string' && Boolean(message.content.trim());
}

export function ConversationStep({ text, consent, busy, onTextChange, onConsentChange, onImport, onImportError, onClearDraft, onContinue }: Props) {
  const [importFeedback, setImportFeedback] = useState('');
  const messageCount = useMemo(() => getMessageCount(text), [text]);
  const hasConversation = messageCount > 0;
  const importJson = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      if (file.size > MAX_CONVERSATION_FILE_BYTES) {
        throw new Error('file-too-large');
      }
      const source = JSON.parse(await file.text());
      const rawMessages: unknown = Array.isArray(source) ? source : source?.messages;
      if (!Array.isArray(rawMessages) || rawMessages.length === 0 || !rawMessages.every(isUploadMessage)) {
        throw new Error('invalid conversation JSON');
      }
      const messages = rawMessages as UploadMessage[];
      const unknownRoles = messages.filter((message) => !supportedRoles.has(message.role.toLowerCase())).length;
      const previewText = messages.map((message) => `[${message.role}] ${message.content.trim()}`).join('\n');
      onImport(messages.map((message) => ({
        message_id: message.message_id?.trim() || undefined,
        role: message.role.trim(), content: message.content.trim(), timestamp: message.timestamp,
      })), previewText);
      onImportError('');
      setImportFeedback(`${messages.length} message${messages.length === 1 ? '' : 's'} imported successfully.${unknownRoles ? ` ${unknownRoles} custom role${unknownRoles === 1 ? ' was' : 's were'} preserved.` : ''}`);
    } catch (error) {
      const message = error instanceof Error && error.message === 'file-too-large'
        ? 'That JSON file is larger than 1 MB. Split it into smaller authorised conversation files.'
        : 'That JSON file must contain a non-empty messages array with string role and content fields.';
      onImportError(message);
      setImportFeedback('Import was not completed. Your pasted conversation has not been changed.');
    } finally {
      event.target.value = '';
    }
  };

  return <section className="intro" aria-labelledby="new-audit-title">
    <h1 id="new-audit-title">AI Memory Health Auditor</h1>
    <label htmlFor="conversation-text">Authorised conversation text
      <textarea id="conversation-text" value={text} maxLength={MAX_CONVERSATION_CHARACTERS} onChange={(event) => { onTextChange(event.target.value); setImportFeedback(''); }} placeholder="Example: [User] I now use PostgreSQL for the backend." rows={10} aria-describedby="conversation-help conversation-count" aria-invalid={!hasConversation} />
    </label>
    <p id="conversation-help" className="input-help">Paste one message per line. To retain speaker context, use <code>[User]</code> or <code>[Assistant]</code> at the start of each line. You can also import a JSON file.</p>
    <p className="input-help">This browser tab temporarily keeps this draft so it can recover after a refresh. <button type="button" className="text-button" onClick={onClearDraft}>Clear local draft</button></p>
    <p id="conversation-count" className={hasConversation ? 'input-feedback' : 'input-feedback input-error'} role="status">{hasConversation ? `${messageCount} message line${messageCount === 1 ? '' : 's'} ready for review.` : 'Add at least one non-empty message to continue.'}</p>
    <label className="file" htmlFor="conversation-upload">Or upload conversation JSON
      <input id="conversation-upload" type="file" accept="application/json,.json" onChange={importJson} />
    </label>
    <p className="input-help">Supported format: <code>{'{ "messages": [{ "message_id": "MSG001", "role": "user", "content": "…", "timestamp": "…" }] }'}</code>. A top-level message array is also accepted. Source IDs and timestamps are preserved when supplied. JSON uploads are limited to 1 MB.</p>
    {importFeedback && <p className="input-feedback" role="status">{importFeedback}</p>}
    <label className="check"><input type="checkbox" checked={consent} onChange={(event) => onConsentChange(event.target.checked)} /> I confirm that I am authorised to use this conversation data for this audit.</label>
    <button disabled={!consent || !hasConversation || busy} onClick={onContinue}>{busy ? 'Preparing conversation…' : 'Continue to Ground Truth'}</button>
  </section>;
}
