"""Verify selection lineage; observations are post-outcome development evidence."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
old=ROOT/'output/proposal-delivery/ac2-partial-twenty-five-history-development-20261029-v1'
three=ROOT/'output/proposal-delivery/ac2-fact-slots-product-three-development-20261029-v1'
nine=ROOT/'output/proposal-delivery/ac2-fact-slots-product-nine-development-20261029-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def main():
    diagnostic=load(old/'candidate-inventory-diagnostic.json')
    assert diagnostic['ledger_sha256']==sha(old/'ledger.json')
    failed={x['history_id'] for x in diagnostic['rows'] if x['generation_state']=='failed'}
    assert len(failed)==diagnostic['no_suite_histories_with_at_least_one_candidate']==12
    three_protocol=load(three/'protocol.json');nine_protocol=load(nine/'protocol.json')
    first=set(three_protocol['history_ids']);second=set(nine_protocol['history_ids'])
    assert len(first)==3 and len(second)==9 and not first&second and first|second==failed
    assert three_protocol['source_sha256']==nine_protocol['source_sha256']
    results=[]
    for path in (three,nine):
        p=load(path/'protocol.json');ledger=load(path/'ledger.json');summary=load(path/'summary.json')
        assert sha(path/'protocol.json')==ledger['protocol_sha256']==summary['protocol_sha256']
        assert sha(path/'ledger.json')==summary['ledger_sha256']
        assert [x['history_id'] for x in ledger['histories']]==p['history_ids']
        results.append({'histories':len(p['history_ids']),'saved_suite_histories':summary['histories_with_saved_suite'],'saved_questions':summary['saved_questions'],'states':summary['states']})
    result={'old_ledger_sha256':sha(old/'ledger.json'),'old_diagnostic_sha256':sha(old/'candidate-inventory-diagnostic.json'),
            'three_ledger_sha256':sha(three/'ledger.json'),'nine_ledger_sha256':sha(nine/'ledger.json'),
            'old_no_suite_histories':12,'selection_disjoint_and_complete':True,'cohorts':results,
            'note':'Histories were selected because prior generation failed. Counts show development coverage only, not valid questions, independent evaluation, or causal effect.'}
    (nine/'selection-lineage-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
