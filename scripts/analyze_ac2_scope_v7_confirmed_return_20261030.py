"""Compare the historical v7 warning replay with the user-confirmed return."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT/'output/proposal-delivery/ai-review-return-20261030-v1'
REPLAY = ROOT/'output/proposal-delivery/ac2-scope-v7-subject-development-20261030.json'
DEST = ROOT/'output/proposal-delivery/ac2-scope-v7-user-confirmed-development-20261030.json'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    summary_path=RUN/'human-confirmed-summary.json';summary=json.loads(summary_path.read_text())
    assert summary['original_zip_sha256']==sha(RUN/'original.zip')
    assert summary['analysis_sha256']==sha(RUN/'analysis.json')
    assert summary['human_confirmation_sha256']==sha(RUN/'human-confirmation.json')
    assert summary['human_independence_confirmation_sha256']==sha(RUN/'human-independence-confirmation.json')
    replay=json.loads(REPLAY.read_text()); rows={r['review_item_id']:r for r in replay['items']}; assert len(rows)==24
    with ZipFile(RUN/'review-entries.zip') as z:
        reviews=[json.loads(z.read(f'01-AC2题目/reviewer-{i}.json')) for i in (1,2)]
    by_id=[{x['review_item_id']:x for x in review['items']} for review in reviews]
    assert all(set(v)==set(rows) for v in by_id)
    counts=Counter(); result=[]
    for ident,row in rows.items():
        a,b=(review[ident]['review']['overall'] for review in by_id)
        assert a==b and a in ('valid','invalid')
        warned=bool(row['v7_warning']);counts[(a,warned)]+=1
        result.append({'review_item_id':ident,'confirmed_return_consensus':a,'v7_warning':row['v7_warning']})
    out={'review_summary_sha256':sha(summary_path),'replay_sha256':sha(REPLAY),'counts':[{'confirmed_return_consensus':k[0],'warned':k[1],'n':v} for k,v in sorted(counts.items())],
         'items':result,'provenance':summary['human_review_provenance'],
         'limitations':'Post-outcome offline comparison on the same selected synthetic questions used to design v7. Warning means review, not invalidity. Reviewer identities are not independently authenticated; human exposure to automated scores or prior AI suggestions is not established. The comparison does not measure performance on new data.'}
    DEST.write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps(out['counts'],indent=2))


if __name__=='__main__': main()
