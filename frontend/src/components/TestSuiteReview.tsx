import { UIAlert, UICard } from './ui';
import { UIProgress, UIButton } from './ui';
import { friendlyText } from '../services/display';
import type { TestCase } from '../types/domain';

export const hasDuplicateQuestions = (tests: TestCase[]) => {
  const prompts = tests.map(test => test.prompt.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim());
  return new Set(prompts).size !== prompts.length;
};

const typeLabels: Record<string, string> = { direct: 'Direct', contextual: 'Contextual', paraphrased: 'Paraphrased', indirect: 'Indirect' };

export function TestSuiteReview({ tests, busy, onReview, onRegenerate }: {
  tests: TestCase[];
  busy: boolean;
  onReview: (test: TestCase, decision: 'accepted' | 'rejected') => void;
  onRegenerate: (test: TestCase) => void;
}) {
  const frozen = tests.some(test => test.generator_version?.startsWith('synthetic-formal-matrix-'));
  const duplicateQuestions = hasDuplicateQuestions(tests);
  const accepted = tests.filter((test) => test.quality_status === 'accepted').length;
  const pending = tests.filter((test) => test.quality_status !== 'accepted' && test.quality_status !== 'rejected').length;
  const rejected = tests.filter((test) => test.quality_status === 'rejected').length;
  return <section className="test-suite-review" aria-label="Generated test suite review">
    <h2>{frozen ? 'Frozen reference questions' : 'Review Generated Test Suite'}</h2>
    {frozen && <UIAlert role="status">These reference questions belong to a reviewed dataset version and are read-only. To change them, review and import a new dataset version.</UIAlert>}
    {!frozen && <p>Automatic checks can accept questions; this does not constitute independent human review. Inspect the frozen questions before any target model is executed. A decision or replacement is synchronised to every model and strategy condition in this experiment.</p>}
    {duplicateQuestions && <UIAlert role="alert" className="alert">Two questions have the same wording. Regenerate the duplicate questions before running; different expected answers do not make an identical question valid.</UIAlert>}
    <div className="summary"><span>Accepted {accepted}</span><span>Needs review {pending}</span><span>Rejected {rejected}</span></div>
    {tests.length > 0 && <div className="review-progress"><div><b>{duplicateQuestions ? 'Duplicate questions need repair' : rejected > 0 ? `${rejected} rejected ${rejected === 1 ? 'question blocks' : 'questions block'} execution` : pending === 0 ? 'Quality decisions complete' : `${pending} ${pending === 1 ? 'question still needs' : 'questions still need'} review`}</b><span>{accepted + rejected} / {tests.length} decided</span></div><UIProgress aria-label="Question review progress" max={tests.length} value={accepted + rejected} /></div>}
    <div className="test-review-list">{tests.map((test, index) => <UICard className={`test-review-card ${test.quality_status ?? 'pending'}`} key={test.test_id}>
      <div className="row"><b>Test {index + 1}</b><span className="pill">{typeLabels[test.test_type ?? 'contextual'] ?? test.test_type}</span></div>
      <p className={`review-decision-note ${test.quality_status === 'accepted' ? 'accepted' : test.quality_status === 'rejected' ? 'rejected' : 'pending'}`} role="status">{test.quality_status === 'accepted' ? duplicateQuestions ? 'Accepted decision · The suite is blocked by duplicate questions.' : '✓ Accepted · This question is ready for testing.' : test.quality_status === 'rejected' ? 'Blocked · Accept or regenerate this question before execution.' : 'Needs review · Choose whether to include this question.'}</p>
      <p className="test-dimension">{test.dimension.replaceAll('_', ' ')}</p>
      <p><b>Question</b><br />{test.prompt}</p>
      <p><b>Expected behaviour</b><br />{test.expected_behavior}</p>
      <p className="test-review-meta">Grounding: {test.grounding_status ?? 'pending'} · {friendlyText(test.validation_notes ?? 'No validation note.')}</p>
      {!frozen && <div className="actions">
        <UIButton type="button" className={test.quality_status === 'accepted' ? 'review-accepted-button' : ''} disabled={busy || test.quality_status === 'accepted'} onClick={() => onReview(test, 'accepted')}>{test.quality_status === 'accepted' ? '✓ Accepted' : 'Accept'}</UIButton>
        <UIButton type="button" className="ghost" disabled={busy || test.quality_status === 'rejected'} onClick={() => onReview(test, 'rejected')}>Reject</UIButton>
        <UIButton type="button" className="secondary" disabled={busy} onClick={() => onRegenerate(test)}>Regenerate</UIButton>
      </div>}
    </UICard>)}</div>
  </section>;
}
