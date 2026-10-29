"""Prepare a source-faithful H19 fact and omit its unresolved override edge.

Preserves all previous source, human decisions and AI notes. This is a draft;
the requested two independent human rechecks are not filled or inferred.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.import_ac3_expanded_reviews import verify_expanded_manifest

V7=ROOT/'output/proposal-delivery/ac3-expanded-30-candidate-draft-2026-10-28-v7'
COMPOSITE=ROOT/'output/proposal-delivery/ac3-expanded-v7-composite-user-confirmed-2026-10-28'
DIRECTION=ROOT/'output/proposal-delivery/ac3-h19-relationship-user-direction-2026-10-28.json'


def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()


def build():
    paths={'source':V7/'candidate-inputs.json','parent_plan':V7/'proposed-fact-plan.json',
           'v7_manifest':V7/'manifest.json','prior_composite':COMPOSITE/'manifest.json','user_direction':DIRECTION}
    for i in (1,2):
        paths[f'ground_{i}']=COMPOSITE/f'grounding-reviewer-{i}.json'
        paths[f'fact_{i}']=COMPOSITE/f'fact-reviewer-{i}.json'
    if any(not p.is_file() or p.is_symlink() for p in paths.values()):raise ValueError('All source evidence must be regular files.')
    raw={key:path.read_bytes() for key,path in paths.items()}
    prior=verify_expanded_manifest(COMPOSITE/'manifest.json',raw['source'],
          [raw[f'ground_{i}'] for i in (1,2)],[raw[f'fact_{i}'] for i in (1,2)])
    source=json.loads(raw['source']);plan=json.loads(raw['parent_plan']);direction=json.loads(raw['user_direction'])
    if (direction.get('format')!='ac3-h19-relationship-user-direction-v1' or
            direction.get('user_response')!='同意，按此修正并复核'):
        raise ValueError('The user direction to preserve facts and recheck the unresolved edge is missing.')
    if prior['source_sha256']!=sha(raw['source']):raise ValueError('Prior source evidence does not match.')
    cases=[x for x in source['cases'] if x.get('history_id')=='AC3-H19']
    if len(cases)!=1:raise ValueError('H19 history is missing or duplicated.')
    case=cases[0];section=plan.get('histories',{}).get('AC3-H19',{})
    facts=[x for x in section.get('facts',[]) if x.get('memory_id')=='AC3-H19-F8']
    edges=[x for x in section.get('relationships',[]) if x.get('memory_id')=='AC3-H19-F8' and
           x.get('target_memory_id')=='AC3-H19-F7' and x.get('relationship_type')=='CONTEXTUAL_OVERRIDE']
    m1=[m for m in case['source_messages'] if m.get('message_id')=='AC3-H19-M1']
    q4=[q for q in case['tests'] if q.get('test_id')=='AC3-H19-Q4']
    if len(facts)!=1 or len(edges)!=1 or len(m1)!=1 or len(q4)!=1:raise ValueError('Expected unique H19 fact, edge, source and question.')
    old_fact=copy.deepcopy(facts[0]);removed=copy.deepcopy(edges[0])
    if (old_fact.get('source_message_id')!='AC3-H19-M1' or old_fact.get('source_span') not in m1[0]['text'] or
            not old_fact.get('canonical_value','').startswith('In the public library craft session scenario: ') or
            'arrangement to offer' not in q4[0]['question']):
        raise ValueError('H19 no longer matches the reviewed source-faithful correction.')
    corrected=copy.deepcopy(plan);target=corrected['histories']['AC3-H19']
    new_fact=next(x for x in target['facts'] if x['memory_id']=='AC3-H19-F8')
    new_fact['canonical_value']=new_fact['source_span']
    target['relationships']=[x for x in target['relationships'] if x!=removed]
    if any(paths[k].read_bytes()!=v for k,v in raw.items()):raise ValueError('Source evidence changed during preparation.')
    return source,corrected,raw,paths,case,old_fact,new_fact,removed,q4[0]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',required=True,type=Path);a=p.parse_args()
    source,plan,raw,paths,case,old_fact,new_fact,removed,q4=build();plan_bytes=encode(plan)
    manifest={'format':'ac3-h19-unresolved-revision-v1','source_sha256':sha(raw['source']),
        'parent_fact_plan_sha256':sha(raw['parent_plan']),'revised_fact_plan_sha256':sha(plan_bytes),
        'changed_history_ids':['AC3-H19'],'changed_fact_ids':['AC3-H19-F8'],
        'unresolved_edge':removed,'unresolved_edge_status':'unresolved_not_written_as_confirmed',
        'question_and_source_unchanged':True,'review_required':True,'protocol_frozen':False,'model_called':False,
        'evidence':{k:{'path':str(v.resolve()),'sha256':sha(raw[k])} for k,v in paths.items()},
        'disclosure':'Original human/AI review decisions remain unchanged. Omission is not a human invalid label; new fact projection and exclusion require two independent rechecks.'}
    a.output_dir.mkdir(parents=True,exist_ok=False)
    (a.output_dir/'candidate-inputs.json').write_bytes(raw['source'])
    (a.output_dir/'proposed-fact-plan.json').write_bytes(plan_bytes)
    manifest_bytes=encode(manifest);(a.output_dir/'manifest.json').write_bytes(manifest_bytes)
    for slot in (1,2):
        review={'format':'ac3-h19-unresolved-review-v1','reviewer_slot':slot,
            'source_sha256':sha(raw['source']),'revised_fact_plan_sha256':sha(plan_bytes),
            'manifest_sha256':sha(manifest_bytes),'说明':'只复核 H19 的 F8 原文与去除未证实前缀后的表述，以及 F8→F7 边暂列未决、不作为已确认关系。两个事实和题目均保留。两项分别填写 valid/invalid/uncertain 与 accept/revise/uncertain，并如实填写声明；此处不要求您把原边判为 invalid。',
            'reviewer_declaration':{'reviewer_label':None,'completed_by_human':None,'completed_independently':None,'used_ai_assistance':None,'note':''},
            'history_id':'AC3-H19','source_messages':case['source_messages'],'question':q4,
            'previous_fact':old_fact,'proposed_fact':new_fact,'previous_edge':removed,
            'edge_status':'unresolved_not_written_as_confirmed',
            'review':{'fact_validity':None,'edge_handling':None,'comment':''}}
        (a.output_dir/f'reviewer-{slot}.json').write_bytes(encode(review))
    (a.output_dir/'说明.md').write_text('H19 的两个事实和题目保留。F8 的规范表述改成其 source_span 原文；F8→F7 的 CONTEXTUAL_OVERRIDE 在此参考计划中暂列未决，不作为已确认关系写入，不等于人工判 invalid。两位审核者分别填写各自 JSON 的声明、fact_validity 和 edge_handling；AI 和身份声明如实填写。原人审与 AI 说明保留。\n',encoding='utf8')
    print(json.dumps({'output':str(a.output_dir),'source_sha256':sha(raw['source']),'new_fact_plan_sha256':sha(plan_bytes),
                      'unresolved_edges':1,'new_review_claimed':False,'protocol_frozen':False,'model_called':False}))


if __name__=='__main__':main()
