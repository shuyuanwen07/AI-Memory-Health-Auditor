"""Validate and summarize repeated AI checks without applying human labels."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'output/ac3-generated/ac2-critic-wording-stability-20261030-v1'
PACKET=ROOT/'output/proposal-delivery/AC2措辞疑点-10题双人复核-20261030.zip'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol=json.loads((RUN/'protocol.json').read_text());ledger=json.loads((RUN/'ledger.json').read_text())
    assert ledger['protocol_sha256']==sha(RUN/'protocol.json') and protocol['packet_sha256']==sha(PACKET)
    assert protocol['script_sha256']==sha(ROOT/'scripts/run_ac2_critic_wording_stability_20261030.py')
    assert protocol['critic_source_sha256']==sha(ROOT/'scripts/run_ac2_full_source_critic_development_20261030.py')
    with ZipFile(PACKET) as z:packet=json.loads(z.read('reviewer-1.json'))
    items={x['blind_id']:x for x in packet['items']};assert set(items)==set(protocol['item_ids']) and len(items)==10
    rows=ledger['rows'];assert len(rows)==30 and {(r['repetition'],r['blind_id']) for r in rows}=={(rep,i) for rep in (1,2,3) for i in items}
    outcomes=Counter(r['state'] for r in rows); repeated=[]
    for ident,item in items.items():
        record=sorted((r for r in rows if r['blind_id']==ident),key=lambda r:r['repetition'])
        material={k:item[k] for k in ('source_messages','question','reference_answer')}
        fingerprint=hashlib.sha256(json.dumps(material,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        assert all(r.get('input_sha256')==fingerprint for r in record if r['state'] in ('returned','failed','dispatched'))
        labels=[r['review']['overall'] for r in record if r['state']=='returned']
        repeated.append({'blind_id':ident,'returned':len(labels),'labels':labels,'all_three_identical':len(labels)==3 and len(set(labels))==1})
    costs=[(r.get('execution') or {}).get('reported_cost_credits') for r in rows]
    out={'protocol_sha256':sha(RUN/'protocol.json'),'ledger_sha256':sha(RUN/'ledger.json'),'states':dict(outcomes),
         'items':repeated,'identical_three':sum(x['all_three_identical'] for x in repeated),'items_total':len(repeated),
         'provider_reported_cost_sum':sum(x for x in costs if isinstance(x,(int,float))),'requests_with_reported_cost':sum(isinstance(x,(int,float)) for x in costs),
         'limitations':'Post-outcome selection of ten questions sharing three synthetic histories; model repetitions are correlated and are not independent cases. No human judgments were used. Stability does not establish accuracy. Provider usage is not an audited invoice; unreported failed-attempt costs may be unknown.'}
    (RUN/'analysis.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({'states':out['states'],'items_total':out['items_total'],'identical_three':out['identical_three'],'requests_with_reported_cost':out['requests_with_reported_cost']},indent=2))


if __name__=='__main__':main()
