import { useState } from 'react';
import { api } from '../services/api';
import { UIAlert, UIButton } from './ui';

export function SavedAnswerReassessment({runId, sourceId}:{runId:string;sourceId?:string|null}) {
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [resultId,setResultId]=useState('');
  const reassess=async()=>{
    setBusy(true);setError('');
    try {
      let run=await api.prepareReassessment(runId);
      if(run.status==='TESTS_EXECUTED') await api.evaluate(run.run_id);
      else if(run.status==='FAILED') run=await api.retry(run.run_id);
      const saved=await api.getAudit(run.run_id);
      if(saved.status!=='COMPLETED') throw new Error('The saved reassessment needs attention. Check its progress in Audit History before continuing.');
      setResultId(saved.run_id);
    } catch(cause) {setError(cause instanceof Error?cause.message:'The saved answers could not be reassessed. Try again or inspect Audit History.');}
    finally {setBusy(false);}
  };
  return <section aria-label="Reassess saved answers">
    <h2>Check these answers with the current assessor</h2>
    <p><a href={`/assessor-models?source=${sourceId||runId}`}>Compare different AI assessors on these answers</a></p>
    {sourceId&&<p>This is a separate assessment of saved answers. <a href={`/audits/${sourceId}`}>View the original assessment</a>.</p>}
    <p>The original questions, answers and result stay saved. This creates a separate result using the same assessment service and model with the installed software. The target model is not called again. An AI assessor may make new review requests.</p>
    <UIButton disabled={busy} onClick={reassess}>{busy?'Reassessing saved answers…':'Reassess saved answers'}</UIButton>
    {error&&<UIAlert role="alert">{error} <a href="/history">Open Audit History</a></UIAlert>}
    {resultId&&<p role="status">Reassessment saved. <a href={`/audits/${resultId}`}>View reassessment result</a>.</p>}
  </section>;
}
