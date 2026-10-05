"""Validate raw response reviews and prepare explicit, non-destructive adjudication."""
import csv
import hashlib
import io
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/local/owner-c-heldout-v1'

def read(path):
    for enc in ('utf-8-sig','gb18030'):
        try:return list(csv.DictReader(io.StringIO(path.read_bytes().decode(enc))))
        except UnicodeError:pass
    raise ValueError(f'Unsupported encoding: {path}')

def verdict(value):
    value=value.strip().lower()
    if value not in {'true','false'}:raise ValueError(f'Invalid verdict: {value}')
    return value=='true'

def main():
    results=json.loads((BASE/'results.json').read_text())
    lookup={r['test']['test_id']:r for r in results}
    sources={c['conversation_id']:{m['message_id'] for m in c['messages']} for c in json.loads((ROOT/'handoff/owner-a-custodian/heldout/source_conversations.json').read_text())['conversations']}
    reviews=[]
    for name in ('actual_response_review_1.csv','actual_response_review_2.csv'):
        rows=read(BASE/name)
        assert len(rows)==len(lookup) and len({r['test_id'] for r in rows})==len(rows)
        assert {r['test_id'] for r in rows}==set(lookup)
        for r in rows:
            original=lookup[r['test_id']]
            assert r['conversation_id']==original['conversation_id'] and r['response_id']==original['response']['response_id']
            assert r['prompt']==original['test']['prompt'] and r['response_text']==original['response']['response_text']
            passed=verdict(r['human_passed'])
            assert r['human_failure_dimension'] in {'none','accuracy','freshness','conflict_resolution','appropriate_use'}
            assert passed==(r['human_failure_dimension']=='none')
            ids=set(re.split(r'[|,\s]+',r['source_message_ids'].strip()))
            assert ids and ids<=sources[r['conversation_id']] and r['note'].strip()
        reviews.append({r['test_id']:r for r in rows})
    rows=[];disputes=[]
    for tid,record in lookup.items():
        a,b=reviews[0][tid],reviews[1][tid]
        va,vb=verdict(a['human_passed']),verdict(b['human_passed'])
        agree=va==vb and a['human_failure_dimension']==b['human_failure_dimension']
        proposed_pass=va;proposed_dim=a['human_failure_dimension'];note='Both reviewers agree; retain the judgement after checking the source evidence.'
        if tid=='A019-T002':
            proposed_pass=False;proposed_dim='appropriate_use'
            note='The current Pebble submission requires grayscale, but the response gives the general colourful-chart preference. This is inappropriate contextual use, not an unresolved-authority conflict.'
        if tid=='A020-T001':
            proposed_pass=True;proposed_dim='none'
            note='The response states a source-supported notebook practice. The generic question does not explicitly request drawing units. Reviewer 1 justification supports this pass decision despite the FALSE field.'
        evidence=sorted(set(re.split(r'[|,\s]+',a['source_message_ids'].strip()))|set(re.split(r'[|,\s]+',b['source_message_ids'].strip())))
        row={'conversation_id':record['conversation_id'],'test_id':tid,'response_id':record['response']['response_id'],
             'reviewer_1_passed':va,'reviewer_1_dimension':a['human_failure_dimension'],
             'reviewer_2_passed':vb,'reviewer_2_dimension':b['human_failure_dimension'],
             'proposed_final_passed':proposed_pass,'proposed_final_dimension':proposed_dim,
             'final_source_message_ids':'|'.join(evidence),'decision_note':note,
             'decision_status':'agreed' if agree else 'pending_user_confirmation',
             'automated_passed':record['evaluation']['passed']}
        rows.append(row)
        if not agree:disputes.append(tid)
    with (BASE/'response_adjudication_draft.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    report={'status':'pending_confirmation' if disputes else 'prepared','reviewed_responses':len(rows),
            'raw_verdict_agreements':sum(verdict(reviews[0][t]['human_passed'])==verdict(reviews[1][t]['human_passed']) for t in lookup),
            'raw_verdict_and_dimension_agreements':len(rows)-len(disputes),'disputed_test_ids':disputes,
            'raw_review_sha256':{n:hashlib.sha256((BASE/n).read_bytes()).hexdigest() for n in ['actual_response_review_1.csv','actual_response_review_2.csv']},
            'raw_reviews_modified':False,'provenance_note':'Reviewer 1 received assistant judgement suggestions before revising the worksheet; this is not evidence of two independent blind raw label sets. Reviewer 2 independence has not been verified.',
            'comparison_note':'Final automated-versus-reference results await explicit adjudication of the two disputed rows.'}
    (ROOT/'handoff/owner-c/step4_comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
