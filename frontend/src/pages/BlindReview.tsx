import { useParams } from 'react-router-dom';
import { Alert } from 'antd';
import { EvaluationReview } from '../components/EvaluationReview';
export function BlindReviewPage() {
  const {runId} = useParams();
  return <main className="page"><h1>Independent blind review</h1>
    <Alert type="info" showIcon title="Judge the answer against the source-derived reference. Model identity, automated scores and other reviewers’ labels are withheld."/>
    <p>Use a distinct reviewer pseudonym. Submit labels only when you are a human reviewer; AI checks cannot substitute for independent human evidence.</p>
    {runId && <EvaluationReview runId={runId} independentOnly/>}
  </main>;
}
