import { Alert, Button, Card, Form, Input, Spin } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../services/api';
import { ACCESS_CHANGED, SESSION_ENDED, clearPrivateWorkspaceDrafts, setWorkspaceCsrf } from '../services/access';
import type { AccessStatus } from '../services/access';

/** Private routes are mounted only after the server confirms workspace access. */
export function AccessBoundary({children}:{children:(signOut:(()=>Promise<void>)|null,signingOut:boolean)=>ReactNode}){
  const [status,setStatus]=useState<AccessStatus|null>(null);
  const [busy,setBusy]=useState(false);
  const inFlight=useRef(false);
  const checkGeneration=useRef(0);
  const activeCheck=useRef<AbortController|null>(null);
  const [error,setError]=useState('');
  const [form]=Form.useForm<{password:string}>();
  const apply=useCallback((next:AccessStatus)=>{
    setWorkspaceCsrf(next.csrf_token);setStatus(next);
    if(next.requires_sign_in&&!next.authenticated)clearPrivateWorkspaceDrafts();
  },[]);
  const invalidateCheck=useCallback(()=>{checkGeneration.current++;activeCheck.current?.abort();activeCheck.current=null;},[]);
  const load=useCallback(async()=>{
    invalidateCheck();const generation=checkGeneration.current;
    const controller=new AbortController();activeCheck.current=controller;
    const timer=window.setTimeout(()=>controller.abort(),10000);setError('');
    try{const next=await api.accessStatus(controller.signal);if(generation===checkGeneration.current)apply(next);}
    catch(cause){if(generation===checkGeneration.current){setWorkspaceCsrf(null);setStatus(null);setError(cause instanceof Error?cause.message:'Workspace access could not be checked.');}}
    finally{window.clearTimeout(timer);if(activeCheck.current===controller)activeCheck.current=null;}
  },[apply,invalidateCheck]);
  useEffect(()=>{void load();const expired=()=>{
    invalidateCheck();
    setWorkspaceCsrf(null);clearPrivateWorkspaceDrafts();setStatus(previous=>previous?{...previous,requires_sign_in:true,authenticated:false,csrf_token:null}:null);
    setError('Your session has ended. Sign in to continue.');
  };const changed=(event:StorageEvent)=>{if(event.key===ACCESS_CHANGED){if(event.newValue?.startsWith('signed_out:'))expired();void load();}};
    window.addEventListener(SESSION_ENDED,expired);window.addEventListener('storage',changed);
    return()=>{invalidateCheck();window.removeEventListener(SESSION_ENDED,expired);window.removeEventListener('storage',changed);};
  },[load,invalidateCheck]);
  useEffect(()=>{
    if(!status?.requires_sign_in||!status.authenticated||status.expires_in_seconds===null)return;
    const timer=window.setTimeout(()=>window.dispatchEvent(new Event(SESSION_ENDED)),Math.max(0,status.expires_in_seconds)*1000);
    return()=>window.clearTimeout(timer);
  },[status]);
  const signIn=async(values:{password:string})=>{
    if(inFlight.current)return;inFlight.current=true;invalidateCheck();setBusy(true);setError('');try{apply(await api.signIn(values.password));form.resetFields();localStorage.setItem(ACCESS_CHANGED,'signed_in:'+Date.now());}
    catch(cause){setError(cause instanceof Error?cause.message:'Sign-in could not be completed.');form.resetFields(['password']);}finally{inFlight.current=false;setBusy(false);}
  };
  const signOut=async()=>{
    if(inFlight.current)return;inFlight.current=true;invalidateCheck();setBusy(true);setError('');try{await api.signOut();apply({mode:'protected',requires_sign_in:true,authenticated:false,expires_at:null,expires_in_seconds:null,csrf_token:null});localStorage.setItem(ACCESS_CHANGED,'signed_out:'+Date.now());}
    catch(cause){setError(cause instanceof Error?cause.message:'Sign-out could not be completed.');}finally{inFlight.current=false;setBusy(false);}
  };
  if(status?.authenticated)return <>{error&&<Alert type="error" title={error} showIcon/>}{children(status.requires_sign_in?signOut:null,busy)}</>;
  return <main className="page access-page"><Card className="access-card" title="Memory Auditor">
    {!status&&!error?<Spin description="Checking workspace access…"><div style={{minHeight:100}}/></Spin>:<>
      <h1>{status?.requires_sign_in?'Sign in to your workspace':'Workspace unavailable'}</h1>
      {error&&<Alert type="warning" title={error} showIcon/>}
      {status?.requires_sign_in?<><p>Use the workspace password provided by its owner.</p><Form form={form} layout="vertical" onFinish={signIn}>
        <Form.Item name="password" label="Workspace password" rules={[{required:true,message:'Enter your workspace password.'}]}><Input.Password autoComplete="current-password" maxLength={1024}/></Form.Item>
        <Button htmlType="submit" type="primary" loading={busy} block>Sign in</Button>
      </Form></>:<Button onClick={()=>void load()}>Retry connection</Button>}
    </>}
  </Card></main>;
}
