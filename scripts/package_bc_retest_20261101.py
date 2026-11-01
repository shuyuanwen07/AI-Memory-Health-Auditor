"""Build the report and full human-verification handoff after both AI reviews."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'output/proposal-delivery/bc-reader-retest-20261101-v2'


def read(path):
    return json.loads(path.read_text())


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')


def main():
    analysis = read(BASE/'analysis.json')
    if not all(s['collection_and_review_complete'] for s in analysis['studies']):
        raise ValueError('Complete both studies and two independent reviews first')
    consensus = read(BASE/'review/consensus.json')
    effort=consensus.get('review_reasoning_effort','high')
    c_flags=sum(s.get('study')=='C' and not s['accepted_by_both_ai'] for s in consensus['sources'])
    if len(consensus['items']) != 384:
        raise ValueError('Expected every one of the384planned answers to have two reviews')
    bpack = read(BASE/'B/blind-review/compact-batch-001.json')
    cpack = read(BASE/'C/compact-review/batch-001.json')
    answers = []
    for sid, folder, pattern in [('B','B/blind-review','compact-batch-*.json'),('C','C/compact-review','batch-*.json')]:
        for path in sorted((BASE/folder).glob(pattern)):
            if '.private-key.' in path.name:
                continue
            pack = read(path)
            for item in pack['items']:
                answers.append({'study':sid, **{k:item[k] for k in ('review_id','question_id','source_handle','answer') if k in item}})
    if len(answers) != 384 or len({a['review_id'] for a in answers}) != 384:
        raise ValueError('Human material must cover384unique answers exactly once')
    labels = {x['review_id']:x for x in consensus['items']}
    for item in answers:
        label = labels[item['review_id']]
        item.update(ai_consensus=label['verdict'], ai_judgments=label['answer_judgments'],
            ai_reasons=label['reasons'], human_verdict=None, human_note=None)
    handoff = {'format':'bc-human-verification-v2','created_at':datetime.now(timezone.utc).isoformat(),
        'review_mode':'AI-assisted human verification; independent human work must be declared after completion.',
        'ai_review_configuration':{'model':'gpt-6-astra','reasoning_effort':effort},
        'instructions':['逐项核对原文、题目、参考答案及回答。AI意见只作参考。',
            'human_verdict填写pass、fail或uncertain；human_note填写理由。',
            '题目或参考答案有歧义时，先处理source_reviews中的human_question_validity和human_reference_validity，保留未决。',
            '仅安全地询问澄清但未满足所需事实细节，可记录safe_but_incomplete，不自动视为严格通过。',
            '完成后填写声明。两位审核者分别填写自己的文件，不查看对方判断。'],
        'reviewer_declaration':{'reviewer_slot':None,'completed_by_human':False,'completed_independently':None,'used_ai_assistance':True},
        'sources':{'B':bpack['sources'],'C':cpack['sources']},'B_questions':bpack['questions'],
        'source_reviews':[{**x,'human_question_validity':None,'human_reference_validity':None,'human_note':None} for x in consensus['sources']],
        'answers':answers}
    human = BASE/'human-review'; human.mkdir(exist_ok=True)
    for slot in (1,2):
        handoff['reviewer_declaration']['reviewer_slot']=slot
        write(human/f'reviewer-{slot}.json',handoff)
    write(human/'需要重点裁定.json',{'sources':[x for x in handoff['source_reviews'] if not x['accepted_by_both_ai']],
        'answers':[x for x in answers if x['ai_consensus']=='uncertain'],
        'notice':'这份文件聚焦分歧；完整逐项复核仍在各reviewer JSON中。所有材料均保持人工待确认。'})
    (human/'填写说明.md').write_text('本批共32道题目及参考答案、384条回答。两份JSON由两人各自填写。\n\n'
        '先核对source_reviews，再核对answers。human_verdict填pass/fail/uncertain；有效性填valid/invalid/uncertain。\n'
        '两份JSON包含AI意见，记录为AI辅助人工复核。完成前不要把completed_by_human改为true。\n'
        '两人独立完成后再填写completed_independently。需要重点裁定.json列出待决来源和回答，不覆盖原意见。\n')
    human_zip = BASE/'BC复测-待人工确认.zip'
    with ZipFile(human_zip,'w',ZIP_DEFLATED) as z:
        for path in sorted(human.iterdir()):
            if path.is_file():z.write(path,path.name)
    names={'weak_first_hit':'First-match','strong_rule_based':'Relationship-priority','scope_aware':'Task/project','temporal_importance':'Time/importance'}
    lines=['# B/C Astra repeated retest','', '**Status: two independent AI reviews complete; human confirmation pending.**','',
        'Both studies use OpenAI GPT-6 Astra with max reasoning,16questions perpolicy and3repetitions:48planned answers perpolicy. All384answers were collected. The original studies remain archived.','',
        '| Policy | B pass / planned | B unresolved | C pass / planned | C unresolved |','| --- | --- | --- | --- | --- |']
    b,c=analysis['studies']
    for left,right in zip(b['policies'],c['policies']):
        lines.append(f"| {names[left['id']]} | {left['pass']}/48 | {left['unresolved']} | {right['pass']}/48 | {right['unresolved']} |")
    lines += ['', 'Pass/planned is conservative verified-success coverage. Unresolved references and disagreements are not model failures. Decided-only accuracy and per-repeat counts are in analysis.json.','',
        '## What changed','',
        'B fixes the shared reader configuration. Old advanced policies retrieved2–5records but delivered only1. Allnewconditions use one common full reader, which changes both delivery and reader instructions. The original rule writer remains fixed and omits the venue facts, limiting conflict-question completion.','',
        'C uses Astra rather than the earlier Luna run and a fixed stratified16-case Oracle sample. Sixteen cases and3repeats replace the old2-case display. The two oldanchors are retained separately in the analysis; model,budget andcohort differences prevent an isolated model-causation claim.','',
        '## Repetitions','', '| Study / policy | Repeat1 | Repeat2 | Repeat3 |','| --- | --- | --- | --- |']
    for study in (b,c):
        for p in study['policies']:
            values=[f"{r.get('pass',0)}/16 ({r.get('uncertain',0)} unresolved)" for r in p['per_repeat']]
            lines.append(f"| {study['id']} / {names[p['id']]} | {' | '.join(values)} |")
    lines += ['', '## Objectivity and limits','',
        '- Source versions, question text, model settings and sampling rules were frozen before calls; no outcome-dependent substitutions or paid request retries.',
        '- C uses a pinned external LongMemEval Oracle release, a deterministic stratified selection and16distinct questions across7categories. Actual normalized source content was checked for duplication.',
        '- Receipts bind the actual model,maxeffort,outputbudget and sentmemory. Repeated-condition input hashes match; provider sampling is not claimed deterministic.',
        f'- Two separate Astra {effort} reviewers saw opaque source/answer handles without policy,model,repetition,automated scores or the other review. Source-validity judgments remain canonical; changes would remain disputed.',
        f'- {c_flags} C question/reference pairs need human adjudication. They remain in the planned sample and their answers are unresolved,not automatically failed.',
        '- B has four structurally related synthetic sourceclusters. C has16selected benchmarkcases. Repetitions are correlated measurements,not48independent histories. Source-cluster intervals and paired differences are descriptive.',
        '- These are development and compatibility studies,not official full-benchmark scores or population-wide validation. Equaldenominators do not equalize datasetdifficulty.',
        '- Human-verification declarations remain unset. AI judgments are not represented as human labels.','',
        '## Evidence','',
        '`output/proposal-delivery/bc-reader-retest-20261101-v2/` contains frozen protocols,raw journals,source snapshots,receiptcontrols,original reviewfiles,consensus andanalysis. The humanhandoff is `BC复测-待人工确认.zip`.','']
    report=ROOT/'docs/BC_ASTRA_RETEST_20261101.md'; report.write_text('\n'.join(lines))
    release=ROOT/'research/bc-astra-retest-20261101';release.mkdir(exist_ok=True)
    evidence=release/'bc-astra-retest-evidence.zip'
    with ZipFile(evidence,'w',ZIP_DEFLATED) as z:
        for path in sorted(BASE.rglob('*')):
            if path.is_file() and path.suffix not in ('.zip','.tmp'):
                z.write(path,path.relative_to(ROOT).as_posix())
        for path in sorted((ROOT/'backend/app').rglob('*.py')):
            z.write(path,'implementation/'+path.relative_to(ROOT).as_posix())
        for path in sorted((ROOT/'scripts').glob('*bc*20261101.py')):
            z.write(path,'implementation/'+path.relative_to(ROOT).as_posix())
    (release/'README.md').write_text('See ../../docs/BC_ASTRA_RETEST_20261101.md.\n\nThe evidence archive preserves all384answers,frozenprotocols,sourcebounds,independentAIreviews andunresolveditems. Humanconfirmation ispending. No PPT is included; the deck remainslocalonly.\n')
    write(release/'manifest.json',{'report':str(report.relative_to(ROOT)),'evidence_sha256':hashlib.sha256(evidence.read_bytes()).hexdigest(),
        'human_confirmation_pending':True,'planned_answers':384,'saved_answers':384,'two_ai_reviewed_answers':384,
        'protocol_sha256':{s:hashlib.sha256((BASE/s/'protocol.json').read_bytes()).hexdigest() for s in ('B','C')}})
    print(json.dumps({'report':str(report),'human_zip':str(human_zip),'evidence':str(evidence)}))


if __name__=='__main__':main()
