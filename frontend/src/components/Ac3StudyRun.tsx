import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import { UIButton, UICard } from './ui';

type FrozenStudy = { file: string; sha256: string; questions: number; histories: number; reservation_usd: string; executable?: boolean };
type StudyStatus = { study_id: string; status: string; completed?: number; total?: number; failed_test_id?: string };

/** Only reviewed frozen studies are selectable; this does not display answers or scores. */
export function Ac3StudyRun() {
  const [studies, setStudies] = useState<FrozenStudy[]>([]);
  const [selected, setSelected] = useState('');
  const [status, setStatus] = useState<StudyStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [review1, setReview1] = useState<File | null>(null);
  const [review2, setReview2] = useState<File | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const refresh = useCallback(async () => {
    try {
      const result = await api.ac3FrozenStudies();
      setStudies(result.studies);
      setSelected(current => result.studies.some(item => item.sha256 === current) ? current : (result.studies[0]?.sha256 ?? ''));
    } catch { setMessage('The study list is unavailable. Check the audit service and try again.'); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    setReview1(null); setReview2(null); setReviewed(false);
    if (!selected) { setStatus(null); return; }
    let active = true;
    const poll = async () => {
      try { const next = await api.ac3StudyStatus(selected); if (active) setStatus(next); }
      catch { if (active) setMessage('Could not check progress. Saved work is preserved.'); }
    };
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 4000);
    return () => { active = false; window.clearInterval(timer); };
  }, [selected]);
  const chosen = studies.find(item => item.sha256 === selected);
  const start = async () => {
    if (!chosen || chosen.executable === false) return;
    setLoading(true); setMessage('');
    try { setStatus(await api.ac3StartStudy({ frozen_file: chosen.file, frozen_sha256: chosen.sha256 })); }
    catch { setMessage('This study is not ready to run. Check its frozen review and settings.'); }
    finally { setLoading(false); }
  };
  const submitReviews = async () => {
    if (!status || !review1 || !review2) return;
    setLoading(true); setMessage('');
    try {
      await api.ac3SubmitReviews(status.study_id, { reviewer_1_json: await review1.text(), reviewer_2_json: await review2.text() });
      setReviewed(true);
    } catch { setMessage('The reviews could not be verified. Check that both files are complete, independent, and match this study.'); }
    finally { setLoading(false); }
  };
  return <UICard>
    <h3>AC3 · Independent Auditor validation</h3>
    <p>Run a reviewed, frozen study and prepare independent answer reviews.</p>
    {!studies.length ? <p role="status">No fully reviewed frozen study is ready.</p> : <>
      <label>Frozen study <select aria-label="Frozen AC3 study" value={selected} onChange={event => setSelected(event.target.value)}>
        {studies.map(item => <option key={item.sha256} value={item.sha256}>{item.histories} histories · {item.questions} questions · {item.sha256.slice(0,8)}{item.executable === false ? ' · historical, review only' : ''}</option>)}
      </select></label>
      {chosen?.executable === false ? <p>This completed historical study is available for review only; its original runtime cannot be rerun.</p> : <p>Uses the configured online model. The per-request reservation is an estimate, not a provider spending guarantee.</p>}
      <UIButton onClick={() => void start()} disabled={chosen?.executable === false || loading || status?.status === 'running'}>{status?.status === 'running' ? 'Running…' : 'Run or resume study'}</UIButton>
      {status && status.status !== 'not_active' && <p role="status">{status.status === 'running' ? 'Running' : status.status === 'awaiting_human_review' ? 'Ready for human review' : 'Stopped — check saved progress'} · {status.completed ?? (status.status === 'awaiting_human_review' ? chosen?.questions : 0)}/{status.total ?? chosen?.questions ?? 0}</p>}
      {status?.status === 'awaiting_human_review' && <div>
        <a href={api.ac3ReviewDownloadUrl(status.study_id,'blind-packet.json')} download>Download anonymous answers</a>{' · '}
        <a href={api.ac3ReviewDownloadUrl(status.study_id,'reviewer-1.json')} download>Reviewer 1 JSON</a>{' · '}
        <a href={api.ac3ReviewDownloadUrl(status.study_id,'reviewer-2.json')} download>Reviewer 2 JSON</a>
        <p>Each reviewer needs the anonymous answers and their own JSON. Automated scores and the identity key are not included.</p>
        <label>Completed reviewer 1 JSON <input key={`review1-${selected}`} type="file" accept="application/json,.json" aria-label="Completed reviewer 1 JSON" onChange={event => setReview1(event.target.files?.[0] ?? null)} /></label>{' '}
        <label>Completed reviewer 2 JSON <input key={`review2-${selected}`} type="file" accept="application/json,.json" aria-label="Completed reviewer 2 JSON" onChange={event => setReview2(event.target.files?.[0] ?? null)} /></label>{' '}
        <UIButton onClick={() => void submitReviews()} disabled={loading || !review1 || !review2}>Compare human reviews</UIButton>
        {reviewed && <p role="status">Reviewed results are ready for the Dashboard.</p>}
      </div>}
    </>}
    {message && <p role="alert">{message}</p>}
    <UIButton onClick={() => void refresh()}>Refresh studies</UIButton>
  </UICard>;
}
