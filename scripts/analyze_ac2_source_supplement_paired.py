"""Analyze returned blind reviews for the fixed AC2 source supplement study."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'output/proposal-delivery/ac2-source-supplement-paired-20261029-v1'
DEV=ROOT/'output/proposal-delivery/ac2-scope-guard-development-20261029'
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()


def analyze(material,key,reviews):
    digest=sha(canonical(material));questions={q['blind_id']:q for q in material['questions']}
    if len(questions)!=len(material['questions']) or key.get('material_sha256')!=digest or set(questions)!=set(key['identity']) or len(reviews)!=2:
        raise ValueError('Question material or private key differs')
    declarations=[];labels=set();tables=[]
    for slot,r in enumerate(reviews,1):
        d=r.get('reviewer_declaration',{});name=d.get('reviewer_label')
        if (r.get('format')!='ac2-source-supplement-human-review-v1' or r.get('reviewer_slot')!=slot or r.get('material_sha256')!=digest
            or any(r.get(k)!=material[k] for k in ('histories','questions'))):raise ValueError('Source or question content changed')
        if (not isinstance(name,str) or not name.strip() or name.strip().casefold() in labels or d.get('completed_by_human') is not True
            or d.get('completed_independently') is not True or d.get('seen_other_review') is not False or d.get('seen_automatic_flags_or_arm') is not False
            or type(d.get('used_ai_assistance')) is not bool or (d.get('prior_source_exposure') is not None and type(d.get('prior_source_exposure')) is not bool)):
            raise ValueError('Blind, independent human review not properly declared')
        labels.add(name.strip().casefold());declarations.append(d)
        decisions=r.get('decisions',[]);table={x.get('blind_id'):x for x in decisions}
        if len(decisions)!=len(table) or set(table)!=set(questions):raise ValueError('Missing or duplicate review')
        for x in decisions:
            if (set(x)!={'blind_id','grounded','structurally_executable','reason'} or x['grounded'] not in ('valid','invalid','uncertain')
                or x['structurally_executable'] not in ('valid','invalid','uncertain') or not isinstance(x['reason'],str)
                or ((x['grounded']!='valid' or x['structurally_executable']!='valid') and not x['reason'].strip())):
                raise ValueError('Malformed judgment or missing reason')
        tables.append(table)
    groups={'baseline':Counter(),'supplement':Counter()};by_history={};unresolved=[]
    for bid,q in questions.items():
        meta=key['identity'][bid];arm=meta['arm'];a,b=tables[0][bid],tables[1][bid];c=groups[arm];c['generated']+=1
        if a['grounded']!=b['grounded'] or a['structurally_executable']!=b['structurally_executable'] or 'uncertain' in (a['grounded'],a['structurally_executable'],b['grounded'],b['structurally_executable']):
            c['unresolved']+=1;unresolved.append(bid);continue
        verdict='valid' if a['grounded']==a['structurally_executable']=='valid' else 'invalid';c[verdict]+=1
        if meta.get('guard_warning') is not None:c[verdict+'_flagged']+=1
        h=by_history.setdefault(meta['history_id'],{'baseline':Counter(),'supplement':Counter()});h[arm][verdict]+=1
    for row in key['ledger']:
        c=groups[row['arm']];c['scheduled']+=4;c['missing']+=row['missing_slots']
    for arm,c in groups.items():
        if c['scheduled']!=40 or c['generated']+c['missing']!=40:raise ValueError('Missing slots do not reconcile')
    outputs={arm:{**{k:v for k,v in c.items() if k not in ('scheduled','missing')},
                  'budget_capacity':c['scheduled'],'unfilled_budget_slots':c['missing'],
                  'consensus_valid_per_budget_capacity':c['valid']/c['scheduled'],
                  'consensus_valid_per_generated':{'numerator':c['valid'],'denominator':c['generated'],
                        'value':c['valid']/c['generated'] if c['generated'] else None}}
             for arm,c in groups.items()}
    paired=[(v['supplement']['valid']-v['baseline']['valid'])/4 for v in by_history.values()]
    # Include zero-yield histories as paired zero differences.
    missing_histories={x['history_id'] for x in key['ledger']}-set(by_history)
    paired.extend([0.0]*len(missing_histories))
    return {'format':'ac2-source-supplement-blind-analysis-v1','material_sha256':digest,'arms':outputs,
        'history_count':len({x['history_id'] for x in key['ledger']}),'mean_paired_valid_per_budget_difference':sum(paired)/len(paired),
        'unresolved_blind_ids':unresolved,'reviewer_declarations':declarations,
        'limitations':['Synthetic existing pilot sources are non-random and not certified novel.',
          'Source supplement outputs are provisional until the review; changing coverage does not establish accurate extraction.',
          'Forty is an upper budget capacity, not a required output count; unused slots are not in themselves failures.',
          'Valid per budget capacity measures yield, not validity; report the generated-question denominator and unresolved items separately.',
          'Paired means are descriptive on ten histories, not generalisable evidence.',
          'Identity and independence are user reported and not independently authenticated.']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--review-1',type=Path,required=True);p.add_argument('--review-2',type=Path,required=True)
    p.add_argument('--confirmation',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    raw=[x.read_bytes() for x in (a.review_1,a.review_2)];confirmation_raw=a.confirmation.read_bytes();confirmation=json.loads(confirmation_raw)
    if (confirmation.get('format')!='ac2-source-supplement-human-confirmation-v1' or confirmation.get('confirmed_by')!='user'
        or confirmation.get('completed_by_humans') is not True or confirmation.get('review_sha256')!=[sha(x) for x in raw]):
        raise ValueError('Confirmation must bind both exact reviewed files')
    protocol_raw=(STUDY/'protocol.json').read_bytes();protocol=json.loads(protocol_raw);key=json.loads((STUDY/'private/key.json').read_bytes())
    if (key['protocol_sha256']!=sha(protocol_raw) or protocol['supplement_sha256']!=sha((DEV/'source_candidate_v1.py').read_bytes())
        or protocol['guard_sha256']!=sha((DEV/'scope_guard_candidate_v2.py').read_bytes())):raise ValueError('Frozen implementation or protocol changed')
    result=analyze(json.loads((STUDY/'private/material.json').read_bytes()),key,[json.loads(x) for x in raw])
    result['review_sha256']=[sha(x) for x in raw];result['user_confirmation_sha256']=sha(confirmation_raw)
    with a.output.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'output':str(a.output),'history_count':result['history_count']}))


if __name__=='__main__':main()
