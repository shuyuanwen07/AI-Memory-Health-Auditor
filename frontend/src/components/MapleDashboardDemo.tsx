import { useEffect, useState } from 'react';
import { api } from '../services/api';
import { auditDisplayNames, modelDisplayName } from '../services/display';
import type { AuditComparison, AuditRun } from '../types/domain';
import { MAPLE_AFTER_RUN, MAPLE_BEFORE_RUN } from '../data/mapleDemoLinks';
import './MapleDashboardDemo.css';

const readableAnswer = (answer: string) => answer.replaceAll('**', '');

/** The default is a saved pair; users can compare any two completed audits. */
export function MapleDashboardDemo() {
  const [before, setBefore] = useState(MAPLE_BEFORE_RUN);
  const [after, setAfter] = useState(MAPLE_AFTER_RUN);
  const [runs, setRuns] = useState<AuditRun[]>([]);
  const [data, setData] = useState<AuditComparison | null>(null);
  const [failed, setFailed] = useState(false);
  const [historyFailed, setHistoryFailed] = useState(false);
  useEffect(() => {
    let active = true;
    api.audits().then(items => { if (active) setRuns(items.filter(item => item.status === 'COMPLETED')); })
      .catch(() => { if (active) setHistoryFailed(true); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    setData(null);
    setFailed(false);
    if (!before || !after || before === after) return () => { active = false; };
    api.compareAudits(before, after)
      .then(result => { if (active) setData(result); })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [before, after]);
  const names = auditDisplayNames(runs);
  const question = data?.paired_tests.find(item => item.outcome === 'fixed') ?? data?.paired_tests[0];
  const selected = [before, after];
  return <section className="maple-demo" aria-labelledby="audit-summary-title">
    <div className="maple-demo-heading"><div><p className="maple-demo-kicker">SAVED AUDIT RESULTS</p><h2 id="audit-summary-title">Before and after comparison</h2></div><span>Compare completed audits on shared questions</span></div>
    <div className="audit-summary-selectors">{(['Before', 'After'] as const).map((label, index) => <label key={label}>{label} audit
      <select aria-label={`${label} audit`} value={selected[index]} onChange={event => index === 0 ? setBefore(event.target.value) : setAfter(event.target.value)}>
        {!runs.some(run => run.run_id === selected[index]) && <option value={selected[index]}>Saved {label.toLowerCase()} audit</option>}
        {runs.map(run => <option key={run.run_id} value={run.run_id}>{names[run.run_id]} · {modelDisplayName(run.model)} · {new Date(run.created_at).toLocaleString()}</option>)}
      </select>
    </label>)}</div>
    {historyFailed && <p role="status">Audit history could not be loaded; other audits cannot be selected.</p>}
    {before === after && <p role="status">Choose two different audits to compare.</p>}
    {failed && <p role="status">This saved comparison is unavailable. Check that the audit service and saved runs are available.</p>}
    {!failed && !data && before !== after && <p role="status">Loading comparison…</p>}
    {data && <>
      <div className="maple-scoreline" aria-label="Automated assessment comparison"><span>Tests passed · automatic</span><strong>{data.before.result.tests_passed}/{data.before.result.tests_total}</strong><span>before</span><span aria-hidden="true">→</span><strong>{data.after.result.tests_passed}/{data.after.result.tests_total}</strong><span>after</span><span className="maple-score-context">{data.paired_tests.length} comparable questions · {data.counts.fixed} improved · {data.counts.regressed} regressed · <a href={`/compare?before=${encodeURIComponent(before)}&after=${encodeURIComponent(after)}`}>Details</a></span></div>
      {question ? <div className="maple-answers"><div><span className="maple-step">SHARED QUESTION</span><p>{question.prompt}</p></div><div><span className="maple-step">BEFORE · {question.before.passed ? 'PASSED' : 'FAILED'}</span><p>{readableAnswer(question.before.response_text)}</p></div><div><span className="maple-step">AFTER · {question.after.passed ? 'PASSED' : 'FAILED'}</span><p>{readableAnswer(question.after.response_text)}</p></div></div> : <p role="status">There are no comparable decided questions for this pair.</p>}
    </>}
  </section>;
}
