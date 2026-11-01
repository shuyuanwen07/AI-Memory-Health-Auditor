"""Reconcile immutable, source-bound independent reviews; publish only explicit bases."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUESTION_FIELDS = ('source_grounding','question_executability','reference_answer_validity','dimension_alignment')
LABELS = {'valid','invalid','uncertain'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def index(rows, key):
    result = {key(row):row for row in rows}
    if len(result) != len(rows):
        raise ValueError('Duplicate reviewed identity')
    return result


def decision(left, right, fields):
    for field in fields:
        if left.get(field) not in LABELS or right.get(field) not in LABELS:
            raise ValueError('Missing or invalid review judgment: '+field)
    if all(left[f] == right[f] == 'valid' for f in fields):
        return 'valid'
    if all(left[f] == right[f] for f in fields) and any(left[f] == 'invalid' for f in fields):
        return 'invalid'
    return 'uncertain'


def reconcile(review_dir, out):
    blank = read(review_dir/'reviewer-1-blank.json')
    one, two = (read(review_dir/f'reviewer-{n}-completed.json') for n in (1,2))
    reference = index(blank['histories'],lambda r:r['history_id'])
    a,b = (index(v['histories'],lambda r:r['history_id']) for v in (one,two))
    if reference.keys()!=a.keys() or reference.keys()!=b.keys() or len(reference)!=10:
        raise ValueError('Reviews must cover all ten actual histories')
    counts={k:{'valid':0,'invalid':0,'uncertain':0} for k in ('questions','facts','relationships','source_coverage')}
    rows=[]
    specs=[('facts',lambda r:r['memory_id'],('memory_id','canonical_value','source_message_ids'),('fact_validity',)),
           ('relationships',lambda r:(r['source_memory_id'],r['type'],r['target_memory_id']),('source_memory_id','type','target_memory_id'),('relationship_validity',)),
           ('questions',lambda r:r['test_id'],('test_id','dimension','test_type','question','expected_behavior','supporting_memory_ids'),QUESTION_FIELDS)]
    for hid, ref in reference.items():
        if a[hid]['source_messages']!=ref['source_messages'] or b[hid]['source_messages']!=ref['source_messages']:
            raise ValueError('Reviewed source text changed: '+hid)
        coverage=decision(a[hid],b[hid],('source_coverage_validity',));counts['source_coverage'][coverage]+=1
        for section,key,content,fields in specs:
            original=index(ref[section],key);left=index(a[hid][section],key);right=index(b[hid][section],key)
            if original.keys()!=left.keys() or original.keys()!=right.keys():
                raise ValueError('Reviewed identity set changed: '+hid+'/'+section)
            for identity,item in original.items():
                if any({f:r.get(f) for f in content}!={f:item.get(f) for f in content} for r in (left[identity],right[identity])):
                    raise ValueError('Reviewed object changed: '+hid+'/'+str(identity))
                outcome=decision(left[identity],right[identity],fields);counts[section][outcome]+=1
                rows.append({'history_id':hid,'section':section,'identity':identity,'outcome':outcome})
    protocol=read(review_dir/'protocol.json')
    for rel,expected in protocol['source_sha256'].items():
        if sha(ROOT/rel)!=expected:raise ValueError('Frozen source record changed')
    n=sum(counts['questions'].values())
    if n!=protocol['questions'] or n>40:raise ValueError('Question total mismatch')
    source_summary_rel=next(p for p in protocol['source_sha256'] if p.endswith('/summary.json'))
    summary={'format':'ac2-ten-reviewed-question-cohort-v1','basis':'Two independent Astra high AI source-only reviews; human confirmation remains separate.',
             'question_total':n,'valid_questions':counts['questions']['valid'],'invalid_questions':counts['questions']['invalid'],
             'uncertain_questions':counts['questions']['uncertain'],'planned_slots':40,'missing':40-n,'histories':10,
             'approved_question_ids':[r['identity'] for r in rows if r['section']=='questions' and r['outcome']=='valid'],
             'source_summary_sha256':protocol['source_sha256'][source_summary_rel],
             'source_summary_path':source_summary_rel,'counts':counts,'rows':rows,
             'review_sha256':{f'reviewer-{i}-completed.json':sha(review_dir/f'reviewer-{i}-completed.json') for i in (1,2)}}
    out.mkdir(parents=True,exist_ok=False)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


def execution_check(summary_path, execution_path, confirmation):
    """Publish technical availability only, bound to the reviewed exact suite."""
    observation=read(execution_path)
    protocol_path=execution_path.parent/'protocol.json'
    protocol=read(protocol_path)
    if (observation.get('protocol_sha256')!=sha(protocol_path)
            or protocol.get('review_summary_sha256')!=sha(summary_path)
            or not confirmation or protocol.get('human_confirmation_sha256')!=sha(confirmation)
            or observation.get('planned_answers')!=40):
        raise ValueError('Execution observation must bind this exact confirmed question cohort')
    histories=observation.get('histories',[])
    expected={f'prospective-{i:02d}' for i in range(1,30,3)}
    if len(histories)!=10 or {r.get('history_id') for r in histories}!=expected:
        raise ValueError('Execution observation must retain all ten planned histories')
    answers=observation.get('returned_answers')
    assessed=sum(r.get('evaluations_returned') or 0 for r in histories)
    if type(answers) is not int or not 0<=assessed<=answers<=40:
        raise ValueError('Invalid execution availability counts')
    if answers!=sum(r.get('answers_returned') or 0 for r in histories):
        raise ValueError('Returned answer total differs from source observations')
    complete=(answers==assessed==40 and all(r.get('status')=='completed_automatic'
              and r.get('target_max_receipts_verified')==4
              and r.get('judge_max_receipts_verified')==4
              and r.get('writer_max_receipt_verified') is True for r in histories))
    return {'planned':40,'answers':answers,'assessments':assessed,
            'status':'complete' if complete else 'partial','basis':'automatic',
            'source_summary_sha256':sha(execution_path),'protocol_sha256':sha(protocol_path),
            'interpretation':'Technical execution availability; not human answer accuracy or question validity.'}


def publish(summary_path, confirmation=None, execution_summary=None):
    result=read(summary_path)
    status='ai_preliminary'
    if confirmation:
        c=read(confirmation)
        if c.get('two_distinct_humans') is not True or c.get('independent') is not True or not str(c.get('user_statement','')).strip() or c.get('review_summary_sha256')!=sha(summary_path):
            raise ValueError('Source-bound explicit human confirmation is required')
        status='human_confirmed'
    run_dir=(ROOT/result['source_summary_path']).parent
    source_summary=read(run_dir/'summary.json')
    sources=read(run_dir/'source-selection.json')['conversations']
    baseline_dir=ROOT/'output/proposal-delivery/ac2-astra-diverse-product-20261101-v1'
    for s in sources:
        old=read(baseline_dir/(s['conversation_id']+'.json'))
        actual=next(r['request']['messages'] for r in old['requests'] if r['path']=='/conversations')
        expected=[{'message_id':m['source_message_id'],'role':m['role'],'content':m['text'],'timestamp':m['timestamp'],'original_timestamp':m['timestamp']} for m in s['messages']]
        if actual!=expected:raise ValueError('Original source messages changed; cannot publish unchanged-source comparison')
    path=ROOT/'frontend/public/reports/ac2-astra-ten-source-v1.json';report=read(path)
    if (report['planned_question_slots'],report['saved_questions'],report['all_valid'],report['invalid'])!=(40,28,14,14):raise ValueError('Original study does not match baseline')
    report['ten_scene_retest']={'histories':10,'planned_slots':40,'saved':result['question_total'],'valid':result['valid_questions'],
         'invalid':result['invalid_questions'],'unresolved':result['uncertain_questions'],'missing':result['missing'],
         'review_status':status,'source_unchanged':True,'evidence_path':'/experiments',
         'revised_questions':source_summary.get('generation_accounting',{}).get('revised_questions',0),
         'confirmed_relationships':result['counts']['relationships']['valid'],
         'unresolved_relationships':result['counts']['relationships']['uncertain'],
         'baseline':{'planned_slots':40,'saved':28,'valid':14,'invalid':14,'unresolved':0,'missing':12},
         'ai_review_summary_sha256':sha(summary_path),'human_confirmation_sha256':sha(confirmation) if confirmation else None}
    if execution_summary:
        report['ten_scene_retest']['execution_check']=execution_check(summary_path,execution_summary,confirmation)
    tmp=path.with_suffix('.json.tmp');tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-dir',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--summary',type=Path)
    parser.add_argument('--publish',action='store_true')
    parser.add_argument('--confirmation',type=Path)
    parser.add_argument('--execution-summary',type=Path)
    args=parser.parse_args()
    if args.review_dir and args.output:
        r=reconcile(args.review_dir,args.output);summary=args.output/'summary.json'
    elif args.summary:r=read(args.summary);summary=args.summary
    else:parser.error('Provide --review-dir with --output, or --summary')
    if args.publish:publish(summary,args.confirmation,args.execution_summary)
    print(json.dumps({k:r[k] for k in ('question_total','valid_questions','invalid_questions','uncertain_questions','missing')},ensure_ascii=False))
