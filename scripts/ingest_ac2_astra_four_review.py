"""Reconcile two source-bound human-confirmed reviews; no invented decisions.

The user must provide a separate confirmation JSON containing their actual
statement and declarations. Original AI labels and returned files are retained.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / 'output/proposal-delivery/ac2-astra-product-four-source-20261101-v1'
REPORT = ROOT / 'frontend/public/reports/ac2-astra-comparison-v1.json'
FIELDS = ('source_grounding', 'question_executability', 'reference_answer_validity')
CONTENT = ('history_id', 'test_id', 'source_messages', 'dimension', 'question', 'expected_behavior')

def sha(data): return hashlib.sha256(data).hexdigest()
def read(path):
    raw = path.read_bytes()
    return raw, json.loads(raw)

def reconcile(reference, first, second):
    def index(doc):
        rows = doc['items']
        result = {row['test_id']: row for row in rows}
        if len(rows) != len(result): raise ValueError('Duplicate question ID')
        return result
    original, a, b = map(index, (reference, first, second))
    if len(original) != 16 or original.keys() != a.keys() or original.keys() != b.keys():
        raise ValueError('Review sets do not cover the 16 original questions')
    counts = {'agreed_valid': 0, 'agreed_invalid': 0, 'uncertain_or_disagreement': 0}
    by_item = []
    for item_id in sorted(original):
        for row in (a[item_id], b[item_id]):
            if any(row.get(k) != original[item_id].get(k) for k in CONTENT):
                raise ValueError(f'Question or source changed: {item_id}')
            if any(row.get(k) not in {'valid', 'invalid', 'uncertain'} for k in FIELDS):
                raise ValueError(f'Missing or invalid judgment: {item_id}')
        if all(a[item_id][f] == b[item_id][f] == 'valid' for f in FIELDS): outcome='agreed_valid'
        elif all(a[item_id][f] == b[item_id][f] for f in FIELDS) and any(a[item_id][f] == 'invalid' for f in FIELDS): outcome='agreed_invalid'
        else: outcome='uncertain_or_disagreement'
        counts[outcome] += 1
        by_item.append({'test_id':item_id,'history_id':original[item_id]['history_id'],'outcome':outcome})
    return counts, by_item

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--reviewer-1',type=Path,required=True)
    parser.add_argument('--reviewer-2',type=Path,required=True)
    parser.add_argument('--confirmation',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.reviewer_1.resolve() == args.reviewer_2.resolve():
        raise ValueError('Two separate review files are required')
    raw_ref, ref=read(STUDY/'reviewer-1-blank.json')
    raw1, one=read(args.reviewer_1); raw2, two=read(args.reviewer_2)
    raw_confirm, confirm=read(args.confirmation)
    if (confirm.get('two_distinct_humans') is not True or confirm.get('independent') is not True
        or not isinstance(confirm.get('user_statement'),str) or not confirm['user_statement'].strip()):
        raise ValueError('An explicit user confirmation of the two independent human checks is required')
    counts,items=reconcile(ref,one,two)
    args.output.mkdir(parents=True,exist_ok=False)
    for name,raw in (('reviewer-1.json',raw1),('reviewer-2.json',raw2),('confirmation.json',raw_confirm)):
        (args.output/name).write_bytes(raw)
    summary={'format':'ac2-astra-four-human-review-v1','source_template_sha256':sha(raw_ref),
             'review_sha256':[sha(raw1),sha(raw2)],'confirmation_sha256':sha(raw_confirm),
             'basis':'User reports two independent humans checked the supplied judgments; identities and AI exposure not independently authenticated.',
             'scheduled':16,'counts':counts,'items':items}
    summary_path=args.output/'summary.json';summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    report=json.loads(REPORT.read_text());follow=report.get('product_followup',{})
    if follow.get('histories') != 4 or follow.get('generated') != 16:
        raise ValueError('Published follow-up does not match the reviewed study; report not updated')
    follow.update(review_status='human_confirmed',reviewed_valid=counts['agreed_valid'],
                  reviewed_invalid=counts['agreed_invalid'],reviewed_unresolved=counts['uncertain_or_disagreement'],
                  human_review_summary_sha256=sha(summary_path.read_bytes()))
    report['product_followup']=follow
    temp=REPORT.with_suffix('.json.tmp');temp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');temp.replace(REPORT)
    print(json.dumps(counts,ensure_ascii=False))

if __name__=='__main__':main()
