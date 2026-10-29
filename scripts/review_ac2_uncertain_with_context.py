"""Source-bound AI follow-up on AC2 cases previously left uncertain.

This is a separate analytical opinion, not an independent human review and not
an overwrite of the human-confirmed sequential adjudication. The target context
diagnostic is an offline reconstruction, not the original AC2 execution.
"""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'output/proposal-delivery'
ADJ = BASE / 'review-package-intake-2026-10-28/user-confirmed/ac2-adjudication.json'
BASELINE = BASE / 'ac2-generation-adjudicated-summary-2026-10-28-v1.json'
CONTEXT = ROOT / 'output/ac3-generated/ac2-context-reconstruction-2026-10-28.json'
OUTPUT = BASE / 'ac2-uncertain-ai-followup-2026-10-28.json'
GENERIC = "What is the user's recorded stored information? State the relevant fact only."


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def build(adjudication_raw, baseline_raw, diagnostic_raw):
    adj, baseline, diag = map(json.loads, (adjudication_raw, baseline_raw, diagnostic_raw))
    if (adj.get('format') != 'ac2-structural-disagreement-adjudication-v1' or
        adj.get('adjudicator_declaration',{}).get('completed_by_human') is not True or
        baseline.get('format') != 'ac2-human-confirmed-adjudication-summary-v1' or
        baseline.get('source_sha256',{}).get('confirmed_adjudication') != digest(adjudication_raw) or
        diag.get('format') != 'ac2-offline-target-context-diagnostic-v1' or
        diag.get('input_sha256') != digest(adjudication_raw) or diag.get('model_called') is not False or
        diag.get('live_database_written') is not False):
        raise ValueError('Human-confirmed adjudication and offline diagnostic must be bound to the same input.')
    diag_cases = {(x['history_id'],x['test_id']):x for x in diag['cases_detail']}
    if len(diag_cases) != 99 or diag.get('cases') != 99:
        raise ValueError('Diagnostic must cover the 99 distinct uncertain cases.')
    items=[]
    for history in adj['histories']:
        hid = history['history_id']
        refs = {x['memory_id']:x for x in history['reviewed_reference']['facts']}
        source = {m['message_id']:m['text'] for m in history['source_messages']}
        for case in history['cases']:
            if case['adjudication']['structurally_executable'] != 'uncertain':
                continue
            key = (hid,case['test_id'])
            obs=diag_cases.get(key)
            if obs is None or obs['dimension'] != case['dimension']:
                raise ValueError('Each uncertain test must have matching offline retrieval evidence.')
            observation = {'source_id_coverage':obs['source_id_coverage'], 'sent_context_count':obs['sent_context_count'],
                'required_source_ids':obs['required_source_ids'], 'selected_source_ids':obs['selected_source_ids']}
            result='uncertain'
            if case['test_id']=='T001' and case['question']==GENERIC:
                target_ids=case['supporting_memory_ids']
                if len(target_ids)!=1 or target_ids[0] not in refs:
                    raise ValueError('Generic case does not bind its expected reference fact.')
                target=refs[target_ids[0]]
                alternatives=[x for mid,x in refs.items() if mid not in target_ids and x['source_message_id']!=target['source_message_id'] and x['source_span']!=target['source_span']]
                if not alternatives or target['source_message_id'] not in source or alternatives[0]['source_message_id'] not in source:
                    raise ValueError('The multiple-source ambiguity was not established.')
                other=alternatives[0]
                result='invalid'
                reason=('The prompt asks only for the user’s recorded stored information and names no subject or property. '
                        f"Its expected answer selects {target['memory_id']} ({target['source_span']}), while another recorded fact is "
                        f"{other['memory_id']} ({other['source_span']}). Both fit the broad wording; a single hidden expected fact "
                        'is therefore not uniquely specified. This is a question/answer-target mismatch, not a claim that a retrieval failure itself makes a question invalid.')
                evidence_ids=[target['source_message_id'],other['source_message_id']]
            elif key==('AC3-H14','T002'):
                result='invalid'; evidence_ids=['AC3-H14-M3','AC3-H14-M6']
                reason=('The question asks for a delivery deadline, but the supplied evidence identifies a submission deadline '
                        'changing from the fifth to the eighth; the source does not establish these as the same deadline. '
                        'Answering with the submission date requires an unsupported property substitution.')
            elif key==('AC3-H23','T002'):
                result='invalid'; evidence_ids=['AC3-H23-M3','AC3-H23-M6']
                reason=('The question asks for a meeting schedule, while the cited evidence changes the meeting point '
                        'from the fountain to the bridge entrance. A location is not a schedule and no meeting time '
                        'or timing change is established by those sources.')
            else:
                evidence_ids=sorted({refs[mid]['source_message_id'] for mid in case['supporting_memory_ids'] if mid in refs})
                if len(evidence_ids)==0:
                    raise ValueError('No traceable expected-source evidence for uncertain case.')
                reason=('The wording does not explicitly identify the expected subject or property. The source and '
                        'reference make the intended answer clear to an auditor, but the original AC2 study did not '
                        'fix or run target retrieval, so they do not establish exactly what context a target would receive. '
                        'The isolated reconstruction is a useful diagnostic of one frozen target setup, not an observed '
                        'AC2 execution or proof that this question is always executable or always invalid. Retain uncertain.')
                if key==('AC3-H19','T004'):
                    reason += (' Separately, the item is labelled conflict_resolution although the expected evidence '
                               'is an update; this is a dimension-coverage concern, not by itself proof of structural non-executability.')
            if any(mid not in source for mid in evidence_ids):
                raise ValueError('AI opinion references a nonexistent source message.')
            items.append({'history_id':hid,'test_id':case['test_id'],'dimension':case['dimension'],
                'question':case['question'],'expected_behavior':case['expected_behavior'],
                'human_adjudication':case['adjudication']['structurally_executable'],
                'ai_followup':result,'ai_reason':reason,'evidence_source_messages':[{'message_id':mid,'text':source[mid]} for mid in evidence_ids],
                'reconstructed_target_context':observation})
    if len(items)!=99 or {(x['history_id'],x['test_id']) for x in items} != set(diag_cases):
        raise ValueError('AI follow-up must cover exactly the original 99 uncertain items.')
    counts=Counter(x['ai_followup'] for x in items)
    if counts != {'invalid':24,'uncertain':75}:
        raise ValueError('Unexpected follow-up scope; inspect the case differences.')
    return {'format':'ac2-ai-followup-uncertain-v1',
        'status':'AI SUPPLEMENT ONLY; human adjudications remain unchanged',
        'user_authorization':{'review_request':'uncertain的地方你直接先复审一遍 然后如果没有特别难决定的就直接用',
            'review_expectation':'复审完之后告诉我 我会人工审核一遍 如果有问题我会和你说 如果没和你说就是没有问题 默认人工审核已过 我会一直守着你的输出 你输出之后如果五分钟没有响应的话就是没有问题 你就可以认为是已经人工审核通过',
            'note':'Both statements are preserved; no human completion is inferred from elapsed time or silence.'},
        'method':'Case-by-case comparison of each question and expected evidence, plus one isolated deterministic product-retrieval reconstruction. Invalid is used only for a specific unsupported property or a generic prompt with multiple distinct facts and one hidden scoring target; unresolved contextual cases remain uncertain.',
        'counts':dict(counts),'context_source_id_coverage_counts':diag['source_id_coverage_counts'],
        'mixed_supplemental_summary':{'structurally_executable':{'valid':8,'invalid':37,'unresolved':75,'denominator':120},
            'qualification':'Combines original user-confirmed human/AI adjudications with 24 new AI-only opinions; not a wholly human or independent blind result.'},
        'limitations':['No original AC2 target answers were collected. The SQLite reconstruction is not the original run.',
            'Retrieved source ID match does not establish semantic completeness or a correct answer.',
            'AI decisions are not independent human review; previous uncertain judgments are preserved.',
            'Synthetic case selection does not establish population performance.'],
        'source_sha256':{'human_confirmed_adjudication':digest(adjudication_raw),'human_adjudicated_summary':digest(baseline_raw),
                         'offline_context_diagnostic':digest(diagnostic_raw)},'cases':items}


def main():
    paths=[ADJ,BASELINE,CONTEXT]
    if any(p.is_symlink() or not p.is_file() for p in paths):
        raise ValueError('All inputs must be existing regular files.')
    data=[p.read_bytes() for p in paths]
    result=build(*data)
    if any(path.read_bytes()!=raw for path,raw in zip(paths,data)):
        raise ValueError('An input changed while the AI follow-up was built.')
    fd=os.open(OUTPUT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'output':str(OUTPUT),'counts':result['counts'],'model_called':False},ensure_ascii=False))


if __name__ == '__main__':
    main()
