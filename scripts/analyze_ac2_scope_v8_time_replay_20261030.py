"""Post-outcome offline check of v8 time advice against the confirmed return."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
from app.test_generator.frozen_scope_review_v8 import later_explicit_time_update_advice

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT/'output/proposal-delivery/ai-review-return-20261030-v1'
V7 = ROOT/'output/proposal-delivery/ac2-scope-v7-subject-development-20261030.json'
OUT = ROOT/'output/proposal-delivery/ac2-scope-v8-time-development-20261030.json'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    summary_path=RUN/'human-confirmed-summary.json';summary=json.loads(summary_path.read_text())
    assert summary['original_zip_sha256']==sha(RUN/'original.zip')
    assert summary['analysis_sha256']==sha(RUN/'analysis.json')
    assert summary['human_confirmation_sha256']==sha(RUN/'human-confirmation.json')
    assert summary['human_independence_confirmation_sha256']==sha(RUN/'human-independence-confirmation.json')
    v7=json.loads(V7.read_text()); previous={row['review_item_id']:row for row in v7['items']};assert len(previous)==24
    with ZipFile(RUN/'review-entries.zip') as z:
        reviews=[json.loads(z.read(f'01-AC2题目/reviewer-{i}.json')) for i in (1,2)]
    indexes=[{item['review_item_id']:item for item in review['items']} for review in reviews]
    assert all(set(index)==set(previous) for index in indexes)
    rows=[]
    for ident, prior in previous.items():
        a,b=(index[ident] for index in indexes)
        assert {k:v for k,v in a.items() if k!='review'}=={k:v for k,v in b.items() if k!='review'}
        label=a['review']['overall'];assert label==b['review']['overall'] and label in ('valid','invalid')
        source=a['source_messages']; stamps=[m['timestamp'] for m in source]
        assert all(stamps) and stamps==sorted(stamps)
        messages=[{'source_id':m['source_id'],'sequence':i,'text':m['text']} for i,m in enumerate(source)]
        ids={value for fact in a['cited_facts'] for value in fact['source_message_ids']}
        assert ids <= {m['source_id'] for m in messages}
        time_warning=later_explicit_time_update_advice(ids,messages)
        warning=prior['v7_warning'] or time_warning
        rows.append({'review_item_id':ident,'confirmed_return_consensus':label,'v7_warning':prior['v7_warning'],'v8_time_warning':time_warning,'v8_warning':warning})
    counts=Counter((row['confirmed_return_consensus'],bool(row['v8_warning'])) for row in rows)
    out={'confirmed_summary_sha256':sha(summary_path),'v7_replay_sha256':sha(V7),
         'v8_source_sha256':sha(ROOT/'backend/app/test_generator/frozen_scope_review_v8.py'),
         'counts':[{'confirmed_return_consensus':k[0],'warned':k[1],'n':v} for k,v in sorted(counts.items())],
         'items':rows,'provenance':summary['human_review_provenance'],
         'limitations':'Post-outcome offline replay on the same related synthetic examples that informed the warning. Message order is supplied synthetic order; not an independent accuracy estimate or a live API retest. A warning requests review, not an invalidity decision; an unflagged item is not certified valid.'}
    OUT.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out['counts'],indent=2))


if __name__=='__main__':main()
