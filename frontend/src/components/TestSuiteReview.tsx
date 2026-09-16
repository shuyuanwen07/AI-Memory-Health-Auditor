import type { TestCase } from '../types/domain';

const typeLabels: Record<string, string> = { direct: 'Direct', contextual: 'Contextual', paraphrased: 'Paraphrased', indirect: 'Indirect' };

export function TestSuiteReview({ tests, busy, onReview, onRegenerate }: {
  tests: TestCase[];
  busy: boolean;
  onReview: (test: TestCase, decision: 'accepted' | 'rejected') => void;
  onRegenerate: (test: TestCase) => void;
}) {
  const accepted = tests.filter((test) => test.quality_status === 'accepted').length;
  const pending = tests.filter((test) => test.quality_status === 'pending').length;
  const rejected = tests.filter((test) => test.quality_status === 'rejected').length;
  return <section className="test-suite-review" aria-label="Generated test suite review">
    <h2>Review Generated Test Suite</h2>
    <p>Inspect the frozen questions before any target model is executed. A decision or replacement is synchronised to every model and strategy condition in this experiment.</p>
    <div className="summary"><span>Accepted {accepted}</span><span>Needs review {pending}</span><span>Rejected {rejected}</span></div>
    <div className="test-review-list">{tests.map((test) => <article className={`test-review-card ${test.quality_status ?? 'pending'}`} key={test.test_id}>
      <div className="row"><b>{test.test_id}</b><span className="pill">{typeLabels[test.test_type ?? 'contextual'] ?? test.test_type}</span></div>
      <p className="test-dimension">{test.dimension.replaceAll('_', ' ')}</p>
      <p><b>Question</b><br />{test.prompt}</p>
      <p><b>Expected behaviour</b><br />{test.expected_behavior}</p>
      <p className="test-review-meta">Grounding: {test.grounding_status ?? 'pending'} · {test.validation_notes ?? 'No validation note.'}</p>
      <div className="actions">
        <button type="button" disabled={busy || test.quality_status === 'accepted'} onClick={() => onReview(test, 'accepted')}>Accept</button>
        <button type="button" className="ghost" disabled={busy || test.quality_status === 'rejected'} onClick={() => onReview(test, 'rejected')}>Reject</button>
        <button type="button" className="secondary" disabled={busy} onClick={() => onRegenerate(test)}>Regenerate</button>
      </div>
    </article>)}</div>
  </section>;
}
