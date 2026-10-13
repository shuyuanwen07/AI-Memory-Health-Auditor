import { useParams } from 'react-router-dom';
import { Alert, Button, Input } from 'antd';
import { useState } from 'react';
import { api } from '../services/api';
import { saveBlob } from '../services/download';
import { EvaluationReview } from '../components/EvaluationReview';
export function BlindReviewPage() {
  const {runId} = useParams();
  return <BlindReviewSession key={runId} runId={runId}/>;
}
function BlindReviewSession({runId}: {runId: string | undefined}) {
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [materials,setMaterials]=useState('');
  const download=async()=>{
    if(!runId)return;
    setBusy(true);setError('');
    try{
      const packet=await api.blindReviewPack(runId);
      const content=JSON.stringify(packet,null,2);
      setMaterials(content);
      saveBlob(new Blob([content],{type:'application/json'}),'independent-review-blank.json');
    }catch(cause){setError(cause instanceof Error?cause.message:'Review materials could not be downloaded.');}
    finally{setBusy(false);}
  };
  return <main className="page"><h1>Independent blind review</h1>
    <Alert type="info" showIcon title="Judge the answer against the complete source. References are system proposals and must be checked. Model identity, automated scores and other reviewers’ labels are withheld."/>
    <p>Review every answer in the assigned batch, including correct answers and uncertain cases. Use a distinct reviewer pseudonym and work independently before adjudication.</p>
    <Button onClick={()=>void download()} loading={busy}>Download blank review materials</Button>
    <p>The download contains the complete source and all answers with empty labels. Save decisions here after reviewing; downloading alone does not count as validation.</p>
    {error&&<Alert type="error" showIcon title={error}/>}
    {materials&&<section aria-label="Blank review materials">
      <Alert type="success" showIcon title="Review materials ready. If your browser does not save the download, copy the JSON below into a file."/>
      <Input.TextArea aria-label="Blank review JSON" value={materials} readOnly autoSize={{minRows:4,maxRows:8}}/>
    </section>}
    {runId && <EvaluationReview runId={runId} independentOnly/>}
  </main>;
}
