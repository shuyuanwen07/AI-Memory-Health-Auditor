"""Prepare blind reviews for a complete private paired target export.

The caller must revalidate frozen sources, reviews and database receipt
provenance before writing these materials. No automated scores are used.
"""
import hashlib
import secrets
from scripts.ac3_retest_paired_freeze import canonical


def make_packets(frozen,questions,target_export):
    frozen_sha=hashlib.sha256(canonical(frozen)).hexdigest()
    if target_export.get('format')!='ac3-paired-target-export-v1' or target_export.get('frozen_sha256')!=frozen_sha:
        raise ValueError('Target export does not match the frozen study')
    answers=target_export.get('answers')
    if (not isinstance(questions,list) or len(questions)!=120 or not isinstance(answers,list) or len(answers)!=120
            or len({q['test_id'] for q in questions})!=120 or len({a['test_id'] for a in answers})!=120):
        raise ValueError('Expected all 120 unique questions and answers')
    by_answer={a['test_id']:a for a in answers}
    histories={c['history_id']:c for c in frozen['suite']['cases']}
    if len(histories)!=30 or set(by_answer)!={q['test_id'] for q in questions}:
        raise ValueError('History or question coverage differs')
    items=[];mapping={}
    for q in questions:
        answer=by_answer[q['test_id']];history=histories.get(q['history_id'])
        if (not history or answer.get('history_id')!=q['history_id'] or answer.get('status')!='answered'
                or not isinstance(answer.get('answer'),str) or not answer['answer'].strip()
                or hashlib.sha256(answer['answer'].encode()).hexdigest()!=answer.get('response_sha256')):
            raise ValueError('A saved answer differs from the frozen question or digest')
        blind=secrets.token_hex(16)
        while blind in mapping:blind=secrets.token_hex(16)
        mapping[blind]={'test_id':q['test_id'],'history_id':q['history_id'],'response_sha256':answer['response_sha256']}
        items.append({'blind_id':blind,'source_messages':history['source_messages'],
                      'question':q['question'],'expected_behavior':q['expected_behavior'],
                      'answer':answer['answer'],'response_sha256':answer['response_sha256']})
    secrets.SystemRandom().shuffle(items)
    export_sha=hashlib.sha256(canonical(target_export)).hexdigest()
    packet={'format':'ac3-paired-blind-packet-v1','frozen_sha256':frozen_sha,'target_export_sha256':export_sha,
            'items':items}
    packet_sha=hashlib.sha256(canonical(packet)).hexdigest()
    reviews=[]
    for slot in (1,2):
        reviews.append({'format':'ac3-paired-human-review-v1','reviewer_slot':slot,'packet_sha256':packet_sha,
            'reviewer_declaration':{'reviewer_label':None,'completed_by_human':None,'completed_independently':None,
                                    'has_seen_automatic_results':None,'has_seen_other_review':None,'used_ai_assistance':None},
            'decisions':[{**item,'verdict':None,'failure_dimension':None,'rationale':''} for item in items]})
    private={'format':'ac3-paired-blind-key-v1','frozen_sha256':frozen_sha,'target_export_sha256':export_sha,
             'packet_sha256':packet_sha,'mapping':mapping}
    return packet,reviews,private


def validate_reviews(packet,reviews,private):
    """Validate two complete returns without resolving uncertainty or disagreement."""
    if (not isinstance(packet,dict) or packet.get('format')!='ac3-paired-blind-packet-v1'
            or not isinstance(private,dict) or private.get('format')!='ac3-paired-blind-key-v1'
            or private.get('packet_sha256')!=hashlib.sha256(canonical(packet)).hexdigest()
            or private.get('frozen_sha256')!=packet.get('frozen_sha256')
            or private.get('target_export_sha256')!=packet.get('target_export_sha256')):
        raise ValueError('Packet or private key changed')
    cases=packet.get('items');mapping=private.get('mapping')
    if not isinstance(cases,list) or len(cases)!=120 or not isinstance(mapping,dict):
        raise ValueError('Expected 120 blind items')
    by_id={item['blind_id']:item for item in cases}
    if len(by_id)!=120 or set(by_id)!=set(mapping) or len({v['test_id'] for v in mapping.values()})!=120:
        raise ValueError('Blind mapping is incomplete or duplicated')
    if not isinstance(reviews,list) or len(reviews)!=2:raise ValueError('Exactly two reviewers are required')
    labels=set();mapped=[]
    for slot,review in enumerate(reviews,1):
        if (review.get('format')!='ac3-paired-human-review-v1' or review.get('reviewer_slot')!=slot
                or review.get('packet_sha256')!=private['packet_sha256']):
            raise ValueError('Reviewer return is not bound to this packet')
        declaration=review.get('reviewer_declaration',{});label=declaration.get('reviewer_label')
        if (not isinstance(label,str) or not label.strip() or label.strip().casefold() in labels
                or declaration.get('completed_by_human') is not True or declaration.get('completed_independently') is not True
                or declaration.get('has_seen_automatic_results') is not False or declaration.get('has_seen_other_review') is not False
                or type(declaration.get('used_ai_assistance')) is not bool):
            raise ValueError('Independent blinded human review declarations are incomplete')
        labels.add(label.strip().casefold());rows=review.get('decisions')
        if not isinstance(rows,list) or len(rows)!=120:raise ValueError('Reviewer decisions are incomplete')
        result={}
        for row in rows:
            blind=row.get('blind_id');source=by_id.get(blind);ident=mapping.get(blind)
            if not source or not ident or ident['test_id'] in result:
                raise ValueError('Unknown or duplicate reviewer item')
            if {k:v for k,v in row.items() if k not in ('verdict','failure_dimension','rationale')}!=source:
                raise ValueError('Reviewed question, source or answer changed')
            verdict,dimension,reason=row.get('verdict'),row.get('failure_dimension'),row.get('rationale')
            if (verdict not in ('pass','fail','uncertain') or not isinstance(reason,str) or not reason.strip()
                    or dimension not in (None,'accuracy','freshness','conflict_resolution','appropriate_use')
                    or (verdict!='fail' and dimension is not None)):
                raise ValueError('Invalid judgment, category or rationale')
            result[ident['test_id']]={'verdict':verdict,'failure_dimension':dimension}
        mapped.append(result)
    return {'format':'ac3-paired-review-validation-v1','reviews':mapped,
            'review_sha256':[hashlib.sha256(canonical(r)).hexdigest() for r in reviews],
            'reviewer_declarations':[r['reviewer_declaration'] for r in reviews],
            'adjudicated':False,'human_identity_independently_authenticated':False,
            'limitation':'Preserves uncertainty and disagreement; does not authenticate identity or validate factual correctness.'}
