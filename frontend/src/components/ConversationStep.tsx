import { UITextArea, UIButton, UIInput, UICheckbox, UISelect, UIOption } from './ui';
import { ChangeEvent, useEffect, useMemo, useRef, useState } from 'react';
import type { ConversationInputMessage, ConversationSourceOrigin } from '../types/domain';
import './review.css';

type Props = {
  text: string;
  consent: boolean;
  sourceOrigin: ConversationSourceOrigin;
  busy: boolean;
  continueDisabled?: boolean;
  onTextChange: (text: string) => void;
  onConsentChange: (consent: boolean) => void;
  onSourceOriginChange: (origin: ConversationSourceOrigin) => void;
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
  const message = value as { message_id?: unknown; role?: unknown; content?: unknown; timestamp?: unknown; original_timestamp?:unknown };
  if (message.message_id !== undefined && typeof message.message_id !== 'string') return false;
  if (message.timestamp !== undefined && (typeof message.timestamp !== 'string' || Number.isNaN(Date.parse(message.timestamp)))) return false;
  if (message.original_timestamp != null && (typeof message.original_timestamp !== 'string'
    || typeof message.timestamp !== 'string' || Number.isNaN(Date.parse(message.original_timestamp))
    || Date.parse(message.original_timestamp) !== Date.parse(message.timestamp))) return false;
  return typeof message.role === 'string' && typeof message.content === 'string' && Boolean(message.content.trim());
}

export function ConversationStep({ text, consent, sourceOrigin, busy, continueDisabled=false, onTextChange, onConsentChange, onSourceOriginChange, onImport, onImportError, onClearDraft, onContinue }: Props) {
  const [importFeedback, setImportFeedback] = useState('');
  const [importing, setImporting] = useState(false);
  const importRevision = useRef(0);
  useEffect(() => () => { importRevision.current += 1; }, []);
  useEffect(() => {
    if (!consent) {
      importRevision.current += 1;
      setImporting(false);
      setImportFeedback('');
    }
  }, [consent]);
  const cancelImport = () => {
    importRevision.current += 1;
    setImporting(false); setImportFeedback('');
  };
  const messageCount = useMemo(() => getMessageCount(text), [text]);
  const hasConversation = messageCount > 0;
  const importJson = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!consent) {
      onImportError('Confirm that you are authorised to process this conversation before reading the file.');
      event.target.value = '';
      return;
    }
    const revision = ++importRevision.current;
    setImporting(true);
    setImportFeedback('Reading conversation file…');
    try {
      if (file.size > MAX_CONVERSATION_FILE_BYTES) {
        throw new Error('file-too-large');
      }
      const fileText = await file.text();
      if (revision !== importRevision.current) return;
      const source = JSON.parse(fileText);
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
        original_timestamp:message.original_timestamp,
      })), previewText);
      onImportError('');
      setImportFeedback(`${messages.length} message${messages.length === 1 ? '' : 's'} imported successfully.${unknownRoles ? ` ${unknownRoles} custom role${unknownRoles === 1 ? ' was' : 's were'} preserved.` : ''}`);
    } catch (error) {
      if (revision !== importRevision.current) return;
      const message = error instanceof Error && error.message === 'file-too-large'
        ? 'That JSON file is larger than 1 MB. Split it into smaller authorised conversation files.'
        : 'That JSON file must contain a non-empty messages array with string role and content fields.';
      onImportError(message);
      setImportFeedback('Import was not completed. Your pasted conversation has not been changed.');
    } finally {
      if (revision === importRevision.current) { event.target.value = ''; setImporting(false); }
    }
  };

  return <section className="intro" aria-labelledby="new-audit-title">
    <h1 id="new-audit-title">AI Memory Health Auditor</h1>
    <label htmlFor="conversation-text">Authorised conversation text
      <UITextArea id="conversation-text" value={text} maxLength={MAX_CONVERSATION_CHARACTERS} onChange={(event) => { cancelImport(); onTextChange(event.target.value); }} placeholder="Example: [User] I now use PostgreSQL for the backend." rows={10} aria-describedby="conversation-help conversation-count" aria-invalid={!hasConversation} />
    </label>
    <p id="conversation-help" className="input-help">Paste one message per line. To retain speaker context, use <code>[User]</code> or <code>[Assistant]</code> at the start of each line. You can also import a JSON file.</p>
    <p className="input-help">After you confirm authorisation, this browser tab temporarily keeps this draft so it can recover after a refresh. <UIButton type="button" className="text-button" onClick={() => { cancelImport(); onClearDraft(); }}>Clear local draft</UIButton></p>
    <p id="conversation-count" className={hasConversation ? 'input-feedback' : 'input-feedback input-error'} role="status">{hasConversation ? `${messageCount} message line${messageCount === 1 ? '' : 's'} ready for review.` : 'Add at least one non-empty message to continue.'}</p>
    <UICheckbox checked={consent} disabled={busy} onChange={(event) => { const authorised = event.target.checked; if (!authorised) cancelImport(); onConsentChange(authorised); }} className="check">I confirm that I am authorised to use this conversation data for this audit. This also authorises the browser to read an uploaded file.</UICheckbox>
    <label className="file" htmlFor="conversation-upload">Or upload conversation JSON
      <UIInput id="conversation-upload" type="file" accept="application/json,.json" disabled={!consent || busy} onChange={importJson} />
    </label>
    <p className="input-help">Supported format: <code>{'{ "messages": [{ "role": "user", "content": "…" }] }'}</code>. A top-level message array is also accepted. Optional source references and timestamps are retained. JSON uploads are limited to 1 MB.</p>
    {importFeedback && <p className="input-feedback" role="status">{importFeedback}</p>}
    <label>Source origin
      <UISelect aria-label="Conversation source origin" value={sourceOrigin} onChange={(event) => onSourceOriginChange(event.target.value as ConversationSourceOrigin)}>
        <UIOption value="unknown">Not recorded</UIOption>
        <UIOption value="synthetic">Synthetic test data</UIOption>
        <UIOption value="authorised">Authorised source</UIOption>
        <UIOption value="deidentified">Authorised, de-identified source</UIOption>
      </UISelect>
    </label>
    <p className="input-help">This records the source category. It does not create human labels or confirm research eligibility.</p>
    <UIButton disabled={!consent || !hasConversation || busy || importing || continueDisabled} onClick={onContinue}>{busy ? 'Preparing conversation…' : 'Continue to Ground Truth'}</UIButton>
  </section>;
}
