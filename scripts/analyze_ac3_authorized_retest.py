"""Analyze the frozen paired retest after two independent blind reviews.

Reads source-bound exports; never generates answers or fabricates human labels.
"""
import argparse
import hashlib
import json
from pathlib import Path
from scripts.ac3_paired_blind_review import validate_reviews
from scripts.ac3_retest_paired_freeze import canonical
from scripts.ac3_retest_paired_metrics import compare, paired_history_bootstrap


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-1',type=Path,required=True)
    parser.add_argument('--review-2',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path('/ac3-results/paired-authorized-retest-20261029-v1')
    frozen=json.loads((root/'frozen-canonical.json').read_bytes())
    blind=root/'blind-review'
    packet=json.loads((blind/'private-blind-packet.json').read_bytes())
    key=json.loads((blind/'private-mapping.json').read_bytes())
    answers=json.loads((blind/'private-target-export.json').read_bytes())
    scores=json.loads((root/'private-paired-scores.json').read_bytes())
    sha=hashlib.sha256(canonical(frozen)).hexdigest()
    if (scores.get('frozen_sha256')!=sha or answers.get('frozen_sha256')!=sha
            or packet.get('frozen_sha256')!=sha
            or packet.get('target_export_sha256')!=hashlib.sha256(canonical(answers)).hexdigest()):
        raise ValueError('Frozen study, target answers, scores or review packet differ')
    checked=validate_reviews(packet,[json.loads(args.review_1.read_bytes()),json.loads(args.review_2.read_bytes())],key)
    items=[{'history_id':case['history_id'],**q} for case in frozen['suite']['cases'] for q in case['tests']]
    ids=[item['test_id'] for item in items]
    histories={item['test_id']:item['history_id'] for item in items}
    versions=frozen['protocol']['component_sha256']
    positional=(ids,histories,answers['answers'],scores['old_records'],scores['new_records'],
                versions['old_evaluator'],versions['new_evaluator'],checked['reviews'])
    result=compare(*positional)
    result['paired_history_bootstrap']=paired_history_bootstrap(*positional)
    # Keep adjudication separate from the independently collected reviews.
    # It is a user-confirmed sensitivity analysis, not a third blind reviewer.
    adjudication_path=blind/'returned-adjudication-original.json'
    confirmation=json.loads((blind/'user-confirmation.json').read_bytes())
    adjudication_raw=adjudication_path.read_bytes()
    if confirmation.get('original_sha256',{}).get(adjudication_path.name)!=hashlib.sha256(adjudication_raw).hexdigest():
        raise ValueError('The user-confirmed adjudication source changed')
    adjudication=json.loads(adjudication_raw)
    rows=adjudication.get('decisions')
    if not isinstance(rows,list) or len(rows)!=120 or len({r.get('blind_id') for r in rows})!=120:
        raise ValueError('Adjudication must contain every blind answer exactly once')
    packet_items={item['blind_id']:item for item in packet['items']}
    if {r['blind_id'] for r in rows}!=set(packet_items):raise ValueError('Adjudication IDs differ from the blind packet')
    mapped={}
    for row in rows:
        blind_id=row['blind_id']; verdict=row.get('verdict'); dimension=row.get('failure_dimension')
        if (row.get('response_sha256')!=packet_items[blind_id]['response_sha256']
                or verdict not in ('pass','fail','uncertain')
                or dimension not in (None,'accuracy','freshness','conflict_resolution','appropriate_use')
                or (verdict!='fail' and dimension is not None)
                or not isinstance(row.get('rationale'),str) or not row['rationale'].strip()):
            raise ValueError('Adjudication answer binding or judgment is invalid')
        mapped[key['mapping'][blind_id]['test_id']]={'verdict':verdict,'failure_dimension':dimension}
    sensitivity_args=(*positional[:-1],[mapped,mapped])
    result['adjudication_sensitivity']=compare(*sensitivity_args)
    result['adjudication_sensitivity']['interpretation']='User-confirmed adjudication; not two additional independent reviews.'
    result['adjudication_sha256']=hashlib.sha256(adjudication_raw).hexdigest()
    result['frozen_sha256']=sha
    result['review_sha256']=checked['review_sha256']
    result['reviewer_declarations']=checked['reviewer_declarations']
    result['source_question_validity']={'valid':120,'total':120,
        'basis':'Both reviewers accepted the source questions before target generation; review provenance is user reported.'}
    result['thresholds_from_frozen_protocol']=frozen['protocol']['thresholds']
    result['model_called_during_analysis']=False
    result['interpretation']='Descriptive independent answer review on selected synthetic histories; do not infer population-wide performance.'
    with args.output.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'output':str(args.output),'review_count':2,'model_called':False}))


if __name__=='__main__':main()
