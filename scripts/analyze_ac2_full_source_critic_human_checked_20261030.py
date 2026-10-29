"""Compare the earlier AI source critic with the later user-confirmed return."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
CRITIC = ROOT/'output/ac3-generated/ac2-full-source-critic-development-20261030-v1'
RETURN = ROOT/'output/proposal-delivery/ai-review-return-20261030-v1'
OUT = ROOT/'output/proposal-delivery/ac2-full-source-critic-user-confirmed-20261030.json'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source=json.loads((CRITIC/'analysis.json').read_text()); ledger=json.loads((CRITIC/'ledger.json').read_text())
    summary=json.loads((RETURN/'human-confirmed-summary.json').read_text())
    assert source['ledger_sha256']==sha(CRITIC/'ledger.json')
    assert summary['original_zip_sha256']==sha(RETURN/'original.zip')
    assert summary['analysis_sha256']==sha(RETURN/'analysis.json')
    assert summary['human_confirmation_sha256']==sha(RETURN/'human-confirmation.json')
    assert summary['human_independence_confirmation_sha256']==sha(RETURN/'human-independence-confirmation.json')
    with ZipFile(RETURN/'review-entries.zip') as z:
        reviews=[json.loads(z.read(f'01-AC2题目/reviewer-{i}.json')) for i in (1,2)]
    indexes=[{row['review_item_id']:row for row in review['items']} for review in reviews]
    assert len(ledger['rows'])==24 and all(len(index)==24 for index in indexes)
    rows=[]
    for record in ledger['rows']:
        ident=record['review_item_id'];assert record['state']=='returned'
        a,b=(index[ident] for index in indexes)
        assert {k:v for k,v in a.items() if k!='review'}=={k:v for k,v in b.items() if k!='review'}
        expected=a['review']['overall'];assert expected==b['review']['overall'] and expected in ('valid','invalid')
        rows.append({'review_item_id':ident,'confirmed_return':expected,'source_critic':record['review']['overall']})
    assert len({r['review_item_id'] for r in rows})==24 and all(set(index)=={r['review_item_id'] for r in rows} for index in indexes)
    counts=Counter((r['confirmed_return'],r['source_critic']) for r in rows)
    output={'critic_ledger_sha256':sha(CRITIC/'ledger.json'),'critic_analysis_sha256':sha(CRITIC/'analysis.json'),
            'confirmed_summary_sha256':sha(RETURN/'human-confirmed-summary.json'),
            'counts':[{'confirmed_return':k[0],'source_critic':k[1],'n':v} for k,v in sorted(counts.items())],
            'items':rows,'provenance':summary['human_review_provenance'],
            'limitations':'Same 24 related synthetic development questions were selected after earlier outcomes. Both sets used AI; the user reports two independent humans checked the later AI-assisted return but blindness to AI and automated scores is not established. Agreement does not prove independent accuracy, causality, or population generalisation; two histories generated no saved question and are excluded.'}
    OUT.write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output['counts'],indent=2))


if __name__=='__main__': main()
