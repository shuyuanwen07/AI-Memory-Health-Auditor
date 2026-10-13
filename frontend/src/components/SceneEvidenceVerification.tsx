import {useEffect,useRef,useState,type ChangeEvent} from 'react';
import {Tag} from 'antd';
import {api} from '../services/api';
import {UIInput,UIButton,UIAlert} from './ui';
import type {SceneEvidenceVerification as Check} from '../types/domain';

export function SceneEvidenceVerification({runId,executionBusy=false}:{runId:string;executionBusy?:boolean}){
 const [file,setFile]=useState<object|null>(null);const [filename,setFilename]=useState('No file selected');
 const [check,setCheck]=useState<Check|null>(null);const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 const revision=useRef(0);const importRevision=useRef(0);const active=useRef(false);
 useEffect(()=>{revision.current++;setCheck(null);setError('');},[runId,executionBusy]);
 const upload=async(event:ChangeEvent<HTMLInputElement>)=>{
  const source=event.target.files?.[0];if(!source)return;
  const current=++importRevision.current;revision.current++;setFile(null);setCheck(null);setError('');setFilename(source.name);
  try{
   if(source.size>1024*1024)throw new Error('Choose a comparison JSON file smaller than 1 MB.');
   const parsed:unknown=JSON.parse(await source.text());
   if(!parsed||typeof parsed!=='object'||Array.isArray(parsed))throw new Error('Choose the downloaded scene-comparison JSON object.');
   if(importRevision.current===current)setFile(parsed);
  }catch(reason){if(importRevision.current===current)setError(reason instanceof SyntaxError?'This file is not valid JSON.':reason instanceof Error?reason.message:'The file could not be read.');}
 };
 const verify=async()=>{
  if(!file||!runId||active.current||executionBusy)return;
  active.current=true;setBusy(true);setCheck(null);setError('');const current=revision.current;
  try{const result=await api.verifySceneEvidence(runId,file);if(revision.current===current)setCheck(result);}
  catch(reason){if(revision.current===current)setError(reason instanceof Error?reason.message:'The saved evidence could not be checked.');}
  finally{active.current=false;setBusy(false);}
 };
 return <section aria-label="Verify a saved scene comparison"><h4>Does an exported comparison still match?</h4><p>Checks this file against the selected saved plan and current evidence. No model calls or label changes.</p>
  <label>Exported scene comparison JSON<UIInput aria-label="Exported scene comparison JSON" type="file" accept="application/json,.json" disabled={busy||executionBusy} onChange={upload}/><small>{filename}</small></label>
  <UIButton disabled={!file||!runId||busy||executionBusy} onClick={verify}>{busy?'Checking exported evidence…':'Verify exported comparison'}</UIButton>
  {!runId&&<p>Restore the matching experiment plan before verifying this file.</p>}
  {error&&<UIAlert role="alert">{error}</UIAlert>}
  {check&&<div role="status"><Tag color={check.matches_current_snapshot?'green':'orange'}>{check.matches_current_snapshot?'Matches current saved evidence':'Does not match current snapshot'}</Tag><p>{check.message}</p></div>}
 </section>;
}
