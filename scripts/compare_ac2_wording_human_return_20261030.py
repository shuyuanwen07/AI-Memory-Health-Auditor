"""Source-bound exploratory comparison after the ten-item return arrives.

This script does not assert human participation or blindness, does not change
prior decisions, and does not treat repeated AI calls as independent cases.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
from scripts.check_ac2_wording_recheck_20261030 import PACKET, validate

ROOT = Path(__file__).resolve().parents[1]
MODEL_RUN = ROOT/'output/ac3-generated/ac2-critic-wording-stability-20261030-v1'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(returned_zip, model_run=MODEL_RUN, packet=PACKET):
    integrity=validate(packet,returned_zip)
    model=json.loads((model_run/'analysis.json').read_text())
    protocol=json.loads((model_run/'protocol.json').read_text())
    assert model['ledger_sha256']==sha(model_run/'ledger.json')
    assert model['protocol_sha256']==sha(model_run/'protocol.json')
    assert protocol['packet_sha256']==sha(packet)
    with ZipFile(returned_zip) as z:
        names=z.namelist();reviews=[]
        for slot in (1,2):
            suffix=f'reviewer-{slot}.json'
            matches=[n for n in names if n==suffix or n.endswith('/'+suffix)]
            assert len(matches)==1
            review=json.loads(z.read(matches[0]))
            reviews.append({item['blind_id']:item['review']['overall'] for item in review['items']})
    model_items={row['blind_id']:row for row in model['items']}
    assert len(model_items)==10 and all(set(review)==set(model_items) for review in reviews)
    rows=[];counts=Counter()
    for ident,item in model_items.items():
        left,right=(review[ident] for review in reviews)
        human=left if left==right and left in ('valid','invalid') else 'unresolved'
        labels=item['labels'];ai=labels[0] if item['all_three_identical'] and len(labels)==3 else 'unstable_or_incomplete'
        if ai not in ('valid','invalid'):ai='unstable_or_incomplete'
        relation=('unresolved_review' if human=='unresolved' else
                  'unstable_or_incomplete_model' if ai=='unstable_or_incomplete' else
                  'agreement' if human==ai else 'disagreement')
        counts[relation]+=1
        rows.append({'blind_id':ident,'reviewer_1':left,'reviewer_2':right,'review_consensus':human,
                     'model_repeat_labels':labels,'model_consensus':ai,'comparison':relation})
    return {'returned_sha256':sha(returned_zip),'packet_sha256':sha(packet),'model_analysis_sha256':sha(model_run/'analysis.json'),
            'integrity':integrity,'comparison_counts':dict(counts),'items':rows,
            'provenance':'Content validation does not establish who reviewed it, independence, blindness or exposure; record user confirmation separately.',
            'limitations':'Post-outcome selected questions share three synthetic histories. Model repeats are correlated. This is descriptive agreement, not an accuracy, causal or population estimate. Questions with reviewer disagreement, uncertainty or unstable model judgments remain separate.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('returned_zip',type=Path)
    print(json.dumps(compare(parser.parse_args().returned_zip),ensure_ascii=False,indent=2))
