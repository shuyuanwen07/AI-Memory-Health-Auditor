"""Prepare a single-question restoration as a new draft, preserving all inputs.

The restored wording is copied exactly from an already user-confirmed v5
question. This script does not create new reviewer judgments or freeze a study.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.import_ac3_expanded_reviews import verify_parent_user_confirmation

V5=ROOT/'output/proposal-delivery/ac3-expanded-v5-confirmed-intake-2026-10-28'
V6=ROOT/'output/proposal-delivery/ac3-expanded-30-candidate-draft-2026-10-28-v6'
TARGET='AC3-H19-Q4'
EXPECTED='For an unrelated session, should the arrangement to offer large-print digital instructions for this accessible session replace the general preference?'


def _sha(data):return hashlib.sha256(data).hexdigest()


def build():
    paths={'v5_source':V5/'original-candidate-inputs.json','v5_plan':V5/'original-proposed-fact-plan.json',
           'v5_confirmation':V5/'confirmation.json','v6_source':V6/'candidate-inputs.json',
           'v6_plan':V6/'proposed-fact-plan.json','v6_manifest':V6/'manifest.json'}
    for i in (1,2):
        paths[f'v5_original_review_{i}']=V5/f'original-reviewer-{i}.json'
        paths[f'v5_confirmed_review_{i}']=V5/f'reviewer-{i}-user-confirmed.json'
    if any(not p.is_file() or p.is_symlink() for p in paths.values()):raise ValueError('Sources must be regular files.')
    raw={k:p.read_bytes() for k,p in paths.items()}
    verify_parent_user_confirmation(raw['v5_source'],raw['v5_plan'],
        [raw[f'v5_confirmed_review_{i}'] for i in (1,2)],
        [raw[f'v5_original_review_{i}'] for i in (1,2)],raw['v5_confirmation'])
    old,new=json.loads(raw['v5_source']),json.loads(raw['v6_source'])
    oldplan,newplan=json.loads(raw['v5_plan']),json.loads(raw['v6_plan'])
    manifest=json.loads(raw['v6_manifest'])
    if manifest.get('revised_source_sha256')!=_sha(raw['v6_source']) or manifest.get('revised_fact_plan_sha256')!=_sha(raw['v6_plan']):
        raise ValueError('V6 source or plan differs from its recorded manifest.')
    def case(suite):
        matches=[x for x in suite['cases'] if x.get('history_id')=='AC3-H19']
        if len(matches)!=1:raise ValueError('H19 source history is missing or duplicated.')
        return matches[0]
    previous,current=case(old),case(new)
    def question(history):
        matches=[q for q in history['tests'] if q.get('test_id')==TARGET]
        if len(matches)!=1:raise ValueError('H19-Q4 is missing or duplicated.')
        return matches[0]
    prior_q,current_q=question(previous),question(current)
    if (prior_q.get('question')!=EXPECTED or 'requirement' not in current_q.get('question','').lower() or
        {k:v for k,v in prior_q.items() if k!='question'}!={k:v for k,v in current_q.items() if k!='question'}):
        raise ValueError('Reviewed v5 question and v6 question differ beyond the expected wording.')
    support=set(prior_q['supporting_source_message_ids'])
    source=lambda history:[m for m in history['source_messages'] if m['message_id'] in support]
    if source(previous)!=source(current) or len(source(current))!=len(support):
        raise ValueError('Restored question supporting source differs from the reviewed v5 source.')
    def related(plan):
        section=plan['histories']['AC3-H19']
        facts=[f for f in section['facts'] if f['source_message_id'] in support]
        ids={f['memory_id'] for f in facts}
        relations=[edge for edge in section['relationships'] if edge['memory_id'] in ids or edge['target_memory_id'] in ids]
        return facts,relations
    if related(oldplan)!=related(newplan):raise ValueError('Restored question related facts or relationships differ from reviewed v5.')
    for slot in (1,2):
        review=json.loads(raw[f'v5_confirmed_review_{slot}']); matches=[x for x in review['cases'] if x['history_id']=='AC3-H19']
        if len(matches)!=1:raise ValueError('Previous H19 human review missing.')
        r=matches[0]; q=[x for x in r['questions'] if x['test_id']==TARGET]
        if len(q)!=1 or {k:v for k,v in q[0].items() if k!='review'}!=prior_q or q[0]['review'].get('question_validity')!='valid':
            raise ValueError('Previous human review does not accept the exact restored question.')
        if r['fact_review'].get('decision')!='accept' or r.get('additional_source_facts_missing')!=[]:
            raise ValueError('Previous human review did not accept relevant facts.')
        edges=[e for e in r['relationship_checks'] if e.get('relationship_type')=='CONTEXTUAL_OVERRIDE']
        if len(edges)!=1 or edges[0]['review'].get('decision')!='valid':
            raise ValueError('Previous human review did not accept the relevant relationship.')
    result=copy.deepcopy(new); q=question(case(result));q['question']=prior_q['question']
    return result,raw,paths,copy.deepcopy(current_q),copy.deepcopy(prior_q),source(current),related(newplan)


def encode(data):return (json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',required=True,type=Path);a=p.parse_args()
    revised,raw,paths,before,after,sources,(facts,relations)=build();source_bytes=encode(revised)
    audit={'format':'ac3-h19-restoration-draft-v1','parent_v6_source_sha256':_sha(raw['v6_source']),
        'parent_v6_plan_sha256':_sha(raw['v6_plan']),'reviewed_v5_source_sha256':_sha(raw['v5_source']),
        'revised_source_sha256':_sha(source_bytes),'test_id':TARGET,'changed_fields':['question'],
        'evidence':{k:{'path':str(path.resolve()),'sha256':_sha(raw[k])} for k,path in paths.items()},
        'review_status':'Restored wording was previously reviewed in v5; reuse is subject to user direction. No new review is represented.',
        'protocol_frozen':False,'model_called':False,'identity_authenticated':False}
    a.output_dir.mkdir(parents=True,exist_ok=False)
    (a.output_dir/'candidate-inputs.json').write_bytes(source_bytes)
    (a.output_dir/'proposed-fact-plan.json').write_bytes(raw['v6_plan'])
    (a.output_dir/'manifest.json').write_bytes(encode(audit))
    for slot in (1,2):
        packet={'format':'ac3-h19-restoration-review-v1','reviewer_slot':slot,'revised_source_sha256':_sha(source_bytes),
            'manifest_sha256':_sha(encode(audit)),
            '说明':'可选：如需重新审核，请核对 H19 原文、恢复前后题目、事实和关系。完成后如实填写声明和 review；原有 v5 审核记录独立保留。',
            'reviewer_declaration':{'reviewer_label':None,'completed_by_human':None,'completed_independently':None,'used_ai_assistance':None,'note':''},
            'history_id':'AC3-H19','supporting_source_messages':sources,'previous_question':before,'restored_question':after,
            'supporting_facts':facts,'supporting_relationships':relations,
            'review':{'question_validity':None,'comment':''}}
        (a.output_dir/f'reviewer-{slot}.json').write_bytes(encode(packet))
    (a.output_dir/'说明.md').write_text('该目录是草稿。H19-Q4 恢复为 v5 中两位审核者已确认的原题；支持来源、事实和关系与 v5 相同。是否直接复用既有逐题审核，依据用户决定；可选复审表未填写。未冻结，未运行。\n',encoding='utf8')
    if any(paths[k].read_bytes()!=v for k,v in raw.items()):raise ValueError('An input changed during preparation.')
    print(json.dumps({'output':str(a.output_dir),'source_sha256':_sha(source_bytes),'changed_questions':1,
                      'new_review_claimed':False,'protocol_frozen':False,'model_called':False}))


if __name__=='__main__':main()
