"""Validate returned blind forms and preserve per-reviewer judgments.

This script cannot authenticate reviewers or decide disagreements. It does not
change the original experiment, AI opinions, or frozen reference materials.
"""
from collections import Counter
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'output/proposal-delivery/ac2-four-dimension-new-source-20261029-v1'
LABELS={'valid','invalid','uncertain'}

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def keyed(items, field):
    if not isinstance(items,list): raise ValueError(f'{field}: list required')
    result={item[field]:item for item in items}
    if len(result)!=len(items): raise ValueError(f'{field}: duplicate identifier')
    return result

def require_label(value, where):
    if value not in LABELS: raise ValueError(f'{where}: expected valid, invalid or uncertain')
    return value

def source_decisions(original, returned):
    if returned.get('source_sha256')!=original['source_sha256']:
        raise ValueError('Source fingerprint changed')
    before=keyed(original['histories'],'history_id');after=keyed(returned['histories'],'history_id')
    if before.keys()!=after.keys():raise ValueError('Source history IDs changed')
    result={}
    for identity,expected in before.items():
        actual=after[identity]
        if actual['source_messages']!=expected['source_messages']:raise ValueError(f'{identity}: source text changed')
        old=keyed(expected['facts'],'id');new=keyed(actual['facts'],'id')
        if old.keys()!=new.keys():raise ValueError(f'{identity}: fact IDs changed')
        for fid,fact in old.items():
            if new[fid]['text']!=fact['text']:raise ValueError(f'{fid}: fact text changed')
            result['fact:'+fid]={'label':require_label(new[fid].get('source_support'),fid),'reason':new[fid].get('reason','')}
        def edge_key(edge):return (edge['source_id'],edge['target_id'],edge['claimed_relation'])
        expected_edges={edge_key(e) for e in expected['relationships']}; actual_edges={edge_key(e) for e in actual['relationships']}
        if len(expected_edges)!=len(expected['relationships']) or len(actual_edges)!=len(actual['relationships']) or expected_edges!=actual_edges:
            raise ValueError(f'{identity}: relationship definitions changed')
        for edge in actual['relationships']:
            key='edge:'+identity+':'+':'.join(edge_key(edge))
            result[key]={'label':require_label(edge.get('relation_validity'),key),'reason':edge.get('reason','')}
    return result

def question_decisions(original, returned):
    if returned.get('source_ledger_sha256')!=original['source_ledger_sha256']:
        raise ValueError('Question ledger fingerprint changed')
    before=keyed(original['items'],'review_item_id');after=keyed(returned['items'],'review_item_id')
    if before.keys()!=after.keys():raise ValueError('Question IDs changed')
    fields=('history_id','source_history_id','dimension','source_messages','cited_facts','question','reference_answer')
    result={}
    for identity,item in before.items():
        actual=after[identity]
        if any(actual.get(field)!=item.get(field) for field in fields):raise ValueError(f'{identity}: question or evidence changed')
        review=actual.get('review')
        if not isinstance(review,dict):raise ValueError(f'{identity}: review required')
        decisions={k:require_label(review.get(k),identity+':'+k) for k in ('source_support','question_clarity','reference_answer_correctness','overall')}
        if decisions['overall']=='valid' and any(decisions[k]!='valid' for k in ('source_support','question_clarity','reference_answer_correctness')):
            raise ValueError(f'{identity}: overall valid conflicts with an invalid or uncertain component')
        result[identity]={'dimension':item.get('dimension','not_recorded'),
                          'history_id':item.get('history_id',item.get('source_history_id')),
                          'decisions':decisions,'notes':review.get('notes','')}
    return result

def reconcile(source_forms, question_forms, source_templates, question_templates):
    if len(source_forms)!=2 or len(question_forms)!=2 or len(source_templates)!=2 or len(question_templates)!=2:
        raise ValueError('Exactly two source forms and two question forms are required')
    for i in range(2):
        expected=f'reviewer-{i+1}'
        if source_forms[i].get('reviewer')!=expected or question_forms[i].get('reviewer_id')!=expected:
            raise ValueError(f'{expected}: reviewer slot does not match the returned form')
    source=[source_decisions(template,form) for template,form in zip(source_templates,source_forms)]
    questions=[question_decisions(template,form) for template,form in zip(question_templates,question_forms)]
    if source[0].keys()!=source[1].keys() or questions[0].keys()!=questions[1].keys():raise ValueError('Reviewer coverage differs')
    source_rows=[]
    for identity in source[0]:
        labels=[r[identity]['label'] for r in source]
        source_rows.append({'id':identity,'reviewer_1':deepcopy(source[0][identity]),'reviewer_2':deepcopy(source[1][identity]),
                            'consensus':labels[0] if labels[0]==labels[1] and labels[0]!='uncertain' else 'unresolved'})
    question_rows=[]
    for identity in questions[0]:
        left,right=questions[0][identity],questions[1][identity]
        consensus={}
        for field in ('source_support','question_clarity','reference_answer_correctness','overall'):
            a,b=left['decisions'][field],right['decisions'][field]
            consensus[field]=a if a==b and a!='uncertain' else 'unresolved'
        question_rows.append({'id':identity,'dimension':left['dimension'],'history_id':left['history_id'],
                              'reviewer_1':left,'reviewer_2':right,'consensus':consensus})
    return {'source_items':len(source_rows),'source_consensus':dict(Counter(r['consensus'] for r in source_rows)),
            'questions':len(question_rows),'question_overall_consensus':dict(Counter(r['consensus']['overall'] for r in question_rows)),
            'source_rows':source_rows,'question_rows':question_rows,
            'provenance':'This result records submitted labels only; human checking, reviewer identity, independence and exposure require separate confirmation. Disagreements and uncertainty remain unresolved.',
            'limitations':['Synthetic related histories, not an estimate for a population.','Source references are authored study materials, not exhaustive real-world gold.']}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source1',type=Path,required=True);parser.add_argument('--source2',type=Path,required=True)
    parser.add_argument('--questions1',type=Path,required=True);parser.add_argument('--questions2',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();paths=[args.source1,args.source2,args.questions1,args.questions2]
    if args.output.exists():raise ValueError('Output already exists; preserve earlier intake and choose a new file')
    templates=[STUDY/'source-review'/f'reviewer-{i}.json' for i in (1,2)]+[STUDY/'blind-review'/f'reviewer-{i}.json' for i in (1,2)]
    returned=[json.loads(p.read_text()) for p in paths];original=[json.loads(p.read_text()) for p in templates]
    result=reconcile(returned[:2],returned[2:],original[:2],original[2:])
    result['input_sha256']=[sha(p) for p in paths]
    result['declarations']=[{k:v for k,v in obj.items() if k in ('reviewer','reviewer_id','completed_by_human','independent_review','reviewed_without_other_review','reviewed_without_system_quality_feedback')} for obj in returned]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:result[k] for k in ('source_items','source_consensus','questions','question_overall_consensus')},ensure_ascii=False))

if __name__=='__main__':main()
