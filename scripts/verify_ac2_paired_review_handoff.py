"""Check frozen AC2 generation and blind-review handoff without revealing arm results."""
import hashlib
import json
from pathlib import Path
from scripts.ac2_paired_retest_freeze import frozen_digest


def sha(raw):return hashlib.sha256(raw).hexdigest()


def verify(protocol_path, output_path, review_dir):
    protocol_raw=protocol_path.read_bytes();protocol=json.loads(protocol_raw)
    output_raw=output_path.read_bytes();output=json.loads(output_raw)
    if (protocol.get('format')!='ac2-paired-cli-freeze-v1'
            or protocol.get('inputs_sha256')!=frozen_digest(protocol['inputs'])
            or output.get('frozen_protocol_sha256')!=protocol['inputs_sha256']
            or output.get('model_called') is not False or output.get('database_written') is not False):
        raise ValueError('Frozen protocol or run provenance is inconsistent')
    histories=protocol['inputs']['history_ids'];arms=output.get('conditions',{})
    if len(histories)!=30 or len(set(histories))!=30 or set(arms)!={'baseline','candidate'}:
        raise ValueError('Unexpected history or condition coverage')
    generated=0
    for records in arms.values():
        if len(records)!=30 or {r.get('history_id') for r in records}!=set(histories):
            raise ValueError('A condition is missing or repeats a history')
        for row in records:
            tests=row.get('tests',[]);count=row.get('generated_count');missing=row.get('missing_slots')
            if type(count) is not int or type(missing) is not int or count!=len(tests) or count+missing!=4:
                raise ValueError('Generated and missing slots do not reconcile')
            if row.get('status') not in ('completed','error'):
                raise ValueError('Run status is not retained')
            if any(not isinstance(t.get('quality_assessment'),dict) for t in tests):
                raise ValueError('A generated item has no saved gate assessment')
            generated+=count
    reviews=[json.loads((review_dir/f'reviewer-{i}.json').read_bytes()) for i in (1,2)]
    packet_raw=(review_dir/'blind-packet.json').read_bytes()
    packet_sha=sha(json.dumps(json.loads(packet_raw),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())
    allowed={'blind_id','history_id','source_messages','reviewed_reference','prompt','expected_behavior',
             'grounded','structurally_executable','reason'}
    for slot,review in enumerate(reviews,1):
        rows=review.get('decisions',[])
        if (review.get('reviewer_slot')!=slot or review.get('packet_sha256')!=packet_sha or len(rows)!=generated
                or len({r['blind_id'] for r in rows})!=generated):
            raise ValueError('Blind reviewer packet is incomplete or not bound to the source')
        if any(set(row)!=allowed or row['grounded'] is not None or row['structurally_executable'] is not None
               or row['reason']!='' for row in rows):
            raise ValueError('Review packet contains labels, gate fields, or changed item shape')
    if reviews[0]['decisions']!=reviews[1]['decisions']:
        raise ValueError('Reviewers received different blinded items')
    return {'format':'ac2-paired-review-handoff-check-v1','frozen_protocol_sha256':sha(protocol_raw),
            'raw_output_sha256':sha(output_raw),'blind_packet_canonical_sha256':packet_sha,
            'blind_packet_file_sha256':sha(packet_raw),
            'review_sha256':[sha((review_dir/f'reviewer-{i}.json').read_bytes()) for i in (1,2)],
            'histories':30,'conditions':2,'scheduled_slots':240,'generated_questions':generated,
            'missing_slots':240-generated,'human_results_present':False,'model_called':False,
            'limitations':['Checks the recorded handoff and fields, not the validity of the generated questions.',
                           'The private allocation key is not included in reviewer packages.']}


if __name__=='__main__':
    root=Path('output/proposal-delivery/human-return-2026-10-29-ff607492')
    review_dir=Path('output/proposal-delivery/ac2-paired-review-2026-10-29-v1')
    result=verify(root/'ac2-frozen.json',root/'ac2-output.json',review_dir)
    with (root/'ac2-handoff-check.json').open('x',encoding='utf8') as f:
        json.dump(result,f,indent=2);f.write('\n')
