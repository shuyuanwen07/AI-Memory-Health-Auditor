import { UIAlert, UICard } from './ui';
import { UIProgress, UIButton, UITextArea } from './ui';
import {useState} from 'react';
import { friendlyText } from '../services/display';
import type { Dimension, DimensionCoverage, TestCase } from '../types/domain';

export const hasDuplicateQuestions = (tests: TestCase[]) => {
  const prompts = tests.map(test => test.prompt.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu, ''));
  return new Set(prompts).size !== prompts.length;
};

const abilities: [Dimension, string][] = [['accuracy','Accuracy'],['freshness','Freshness'],['conflict_resolution','Conflict Resolution'],['appropriate_use','Appropriate Use']];

const typeLabels: Record<string, string> = { direct: 'Direct', contextual: 'Contextual', paraphrased: 'Paraphrased', indirect: 'Indirect' };

export function TestSuiteReview({ tests, dimensionCoverage, busy, onReview, onRegenerate, onAcceptAll, onHumanValidityReview }: {
  tests: TestCase[];
  dimensionCoverage?: DimensionCoverage[];
  busy: boolean;
  onReview: (test: TestCase, decision: 'accepted' | 'rejected', note?:string) => void;
  onRegenerate: (test: TestCase) => void;
  onAcceptAll?: (tests: TestCase[]) => void | Promise<void>;
  onHumanValidityReview?: (test:TestCase, decision:'accepted'|'rejected', reviewerPseudonym:string, note?:string) => void;
}) {
  const [notes,setNotes]=useState<Record<string,string>>({});
  const [humanValidityNotes,setHumanValidityNotes]=useState<Record<string,string>>({});
  const [humanValidityReviewer,setHumanValidityReviewer]=useState('');
  const decide=(test:TestCase,decision:'accepted'|'rejected')=>{const note=notes[test.test_id]?.trim();if(note)onReview(test,decision,note);else onReview(test,decision);};
  const frozen = tests.some(test => test.generator_version?.startsWith('synthetic-formal-matrix-'));
  const duplicateQuestions = hasDuplicateQuestions(tests);
  const accepted = tests.filter((test) => test.quality_status === 'accepted').length;
  const notAccepted = tests.filter((test) => test.quality_status !== 'accepted');
  const pending = tests.filter((test) => test.quality_status !== 'accepted' && test.quality_status !== 'rejected').length;
  const coverage = abilities.map(([dimension,label]) => {
    const report = dimensionCoverage?.find(item => item.dimension === dimension);
    return {dimension,label,count:tests.filter(test=>test.dimension===dimension && test.quality_status==='accepted').length,
      supported:report?.evidence_supported ?? null, reason:report?.reason,
      required:report?.required_question_count ?? 0, available:report?.available_question_count ?? 0};
  });
  const supported = coverage.filter(item=>item.supported===true);
  const coveredSupported = supported.filter(item=>item.count>=(item.required || 1));
  const unsupported = coverage.filter(item=>item.supported===false);
  const missingSupported = supported.filter(item=>item.count<(item.required || 1));
  const supportVerified = coverage.some(item=>item.supported!==null);
  const showSupportStatus = Boolean(dimensionCoverage?.length);
  const uncovered = coverage.filter(item=>item.count===0);
  const maximumCount = Math.max(1,...coverage.map(item=>item.count));
  const rejected = tests.filter((test) => test.quality_status === 'rejected').length;
  const humanValidityAccepted=tests.filter(test=>test.human_validity_status==='accepted').length;
  const humanValidityRejected=tests.filter(test=>test.human_validity_status==='rejected').length;
  const humanValidityPending=tests.length-humanValidityAccepted-humanValidityRejected;
  return <section className="test-suite-review" aria-label="Generated test suite review">
    <h2>{frozen ? 'Frozen reference questions' : 'Review Generated Test Suite'}</h2>
    {frozen && <UIAlert role="status">These reference questions belong to a reviewed dataset version and are read-only. To change them, review and import a new dataset version.</UIAlert>}
    {!frozen && <p>{onHumanValidityReview
      ? 'Review the automatic question-quality result and your human validity decision separately. Every question needs an accepted quality decision and an explicit researcher validity confirmation before Experiment A can run.'
      : 'Automatic checks can accept questions; this does not constitute independent human review. Inspect the frozen questions before any target model is executed. A decision or replacement is synchronised to every model and strategy condition in this experiment.'}</p>}
    {duplicateQuestions && <UIAlert role="alert" className="alert">Two questions have the same wording. Regenerate the duplicate questions before running; different expected answers do not make an identical question valid.</UIAlert>}
    <div className="summary"><span>Accepted {accepted}</span><span>Needs review {pending}</span><span>Rejected {rejected}</span></div>
    {!frozen && onAcceptAll && notAccepted.length > 0 && <UIButton type="button" className="secondary" disabled={busy} onClick={() => onAcceptAll(notAccepted)}>Accept all questions</UIButton>}
    {tests.length > 0 && <div className="review-progress"><div><b>{duplicateQuestions ? 'Duplicate questions need repair' : rejected > 0 ? `${rejected} rejected ${rejected === 1 ? 'question blocks' : 'questions block'} execution` : pending === 0 ? 'Quality decisions complete' : `${pending} ${pending === 1 ? 'question still needs' : 'questions still need'} review`}</b><span>{accepted + rejected} / {tests.length} decided</span></div><UIProgress aria-label="Question review progress" max={tests.length} value={accepted + rejected} /></div>}
    {tests.length > 0 && <section className="question-coverage" aria-label="Accepted question coverage">
      <h3>Accepted questions by ability</h3>
      <p>{supportVerified
        ? `${coveredSupported.length} of ${supported.length} evidence-supported abilities meet their minimum question count.`
        : `${4-uncovered.length} of 4 abilities have accepted questions. Evidence support was not recorded for this suite.`}</p>
      <div className="question-coverage-grid">{coverage.map(item=><div key={item.label}>
        <span>{item.label}</span><b>{item.count}</b>
        {showSupportStatus && <small>{item.supported===true
          ? `Evidence-supported${item.required>0?` · need ${item.required}, available slots ${item.available}`:''}`
          : item.supported===false?'Not testable from current evidence':'Support not recorded'}</small>}
        <div className="question-coverage-track" role="img" aria-label={`${item.label}: ${item.count} accepted questions`}><span style={{width:`${item.count/maximumCount*100}%`}}/></div>
      </div>)}</div>
      {supportVerified && unsupported.length>0 && <p className="trace-note">Not testable from the confirmed evidence: {unsupported.map(item=>`${item.label} — ${item.reason}`).join(' · ')}</p>}
      {supportVerified && missingSupported.length>0 && <UIAlert role="alert">The evidence supports these abilities, but their minimum is not met: {missingSupported.map(item=>`${item.label} needs ${item.required || 1}, has ${item.count}`).join('; ')}. Add or regenerate questions before execution.</UIAlert>}
      {!supportVerified && uncovered.length>0 && <p className="trace-note">No accepted questions for: {uncovered.map(item=>item.label).join(', ')}. Scores will cover only tested abilities.</p>}
    </section>}
    {onHumanValidityReview&&<section className="question-coverage" aria-label="Human validity review">
      <h3>Researcher validity review · separate from quality checks</h3>
      <p>{humanValidityAccepted} accepted · {humanValidityPending} awaiting decision · {humanValidityRejected} rejected. Rejected or unreviewed questions block Experiment A execution.</p>
      <label>Researcher pseudonym<input aria-label="Human validity reviewer pseudonym" autoComplete="off" disabled={busy} value={humanValidityReviewer} onChange={event=>setHumanValidityReviewer(event.target.value)} /></label>
    </section>}
    <div className="test-review-list">{tests.map((test, index) => <UICard className={`test-review-card ${test.quality_status ?? 'pending'}`} key={test.test_id}>
      <div className="row"><b>Test {index + 1}</b><span className="pill">{typeLabels[test.test_type ?? 'contextual'] ?? test.test_type}</span></div>
      <p className={`review-decision-note ${test.quality_status === 'accepted' ? 'accepted' : test.quality_status === 'rejected' ? 'rejected' : 'pending'}`} role="status">{onHumanValidityReview
        ? test.quality_status === 'accepted' ? duplicateQuestions ? 'Quality decision accepted · The suite is blocked by duplicate questions.' : '✓ Quality decision accepted.' : test.quality_status === 'rejected' ? 'Quality decision rejected · This question cannot run.' : 'Quality decision pending · Review the automatic quality result.'
        : test.quality_status === 'accepted' ? duplicateQuestions ? 'Accepted decision · The suite is blocked by duplicate questions.' : '✓ Accepted · This question is ready for testing.' : test.quality_status === 'rejected' ? 'Blocked · Accept or regenerate this question before execution.' : 'Needs review · Choose whether to include this question.'}</p>
      {onHumanValidityReview&&<p className="test-review-meta"><b>Automated grounding check:</b> {test.grounding_status==='grounded'?'Grounded':test.grounding_status==='ungrounded'?'Ungrounded':'Not recorded'} · <b>Quality decision:</b> {test.quality_status??'pending'}</p>}
      <p className="test-dimension">{test.dimension.replaceAll('_', ' ')}</p>
      <p><b>Question</b><br />{friendlyText(test.prompt)}</p>
      <p><b>Expected behaviour</b><br />{friendlyText(test.expected_behavior)}</p>
      {!onHumanValidityReview&&<p className="test-review-meta">{test.grounding_status==='grounded'?'Source evidence checked':test.grounding_status==='ungrounded'?'Source evidence needs correction':'Source evidence needs review'} · {friendlyText((test.validation_notes ?? 'No review note available.').replace(/^rule-based-quality-v[\d.]+:\s*/i,''))}</p>}
      {onHumanValidityReview&&<p className={`review-decision-note ${test.human_validity_status==='accepted'?'accepted':test.human_validity_status==='rejected'?'rejected':'pending'}`} role="status" aria-label={`Human validity status for question ${index+1}`}>
        {test.human_validity_status==='accepted'?`Human validity confirmed by ${test.human_validity_reviewer||'researcher'}${test.human_validity_note?` · ${friendlyText(test.human_validity_note)}`:''}`:test.human_validity_status==='rejected'?`Human validity rejected by ${test.human_validity_reviewer||'researcher'}${test.human_validity_note?` · ${friendlyText(test.human_validity_note)}`:''}`:'Human validity not yet reviewed.'}
      </p>}
      {!frozen&&<label>{onHumanValidityReview?'Quality review reason (optional)':'Review reason (optional)'}<UITextArea aria-label={`Review reason for question ${index+1}`} rows={2} maxLength={1000} disabled={busy} value={notes[test.test_id]??''} onChange={event=>setNotes(current=>({...current,[test.test_id]:event.target.value}))}/></label>}
      {onHumanValidityReview&&!frozen&&<>
        <label>Human validity note (optional)<UITextArea aria-label={`Human validity note for question ${index+1}`} rows={2} maxLength={1000} disabled={busy} value={humanValidityNotes[test.test_id]??''} onChange={event=>setHumanValidityNotes(current=>({...current,[test.test_id]:event.target.value}))}/></label>
        <div className="actions">
          <UIButton type="button" disabled={busy||!humanValidityReviewer.trim()} onClick={()=>onHumanValidityReview(test,'accepted',humanValidityReviewer.trim(),humanValidityNotes[test.test_id]?.trim()||undefined)}>Confirm valid</UIButton>
          <UIButton type="button" className="ghost" disabled={busy||!humanValidityReviewer.trim()} onClick={()=>onHumanValidityReview(test,'rejected',humanValidityReviewer.trim(),humanValidityNotes[test.test_id]?.trim()||undefined)}>Mark invalid</UIButton>
        </div>
      </>}
      {!frozen&&test.quality_status==='rejected'&&<UIButton disabled={busy||!notes[test.test_id]?.trim()} onClick={()=>decide(test,'rejected')}>Save rejection reason</UIButton>}
      {!frozen && <div className="actions">
        <UIButton type="button" className={test.quality_status === 'accepted' ? 'review-accepted-button' : ''} disabled={busy || test.quality_status === 'accepted'} onClick={() => decide(test, 'accepted')}>{test.quality_status === 'accepted' ? '✓ Accepted' : 'Accept'}</UIButton>
        <UIButton type="button" className="ghost" disabled={busy || test.quality_status === 'rejected'} onClick={() => decide(test, 'rejected')}>Reject</UIButton>
        <UIButton type="button" className="secondary" disabled={busy} onClick={() => onRegenerate(test)}>Regenerate</UIButton>
      </div>}
    </UICard>)}</div>
  </section>;
}
