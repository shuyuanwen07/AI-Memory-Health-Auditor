import hashlib
import json
from scripts.compare_ac2_wording_human_return_20261030 import compare
from scripts.tests.test_check_ac2_wording_recheck_20261030 import build_blank, build_return


def test_comparison_keeps_disagreement_and_uncertain_separate(tmp_path):
    packet, returned, model = tmp_path/'packet.zip', tmp_path/'returned.zip', tmp_path/'model'
    model.mkdir(); build_blank(packet); build_return(packet,returned)
    ledger=model/'ledger.json';ledger.write_text('{}')
    protocol=model/'protocol.json';protocol.write_text(json.dumps({'packet_sha256':hashlib.sha256(packet.read_bytes()).hexdigest()}))
    items=[{'blind_id':str(i),'labels':['valid']*3,'all_three_identical':True} for i in range(10)]
    items[0]['labels']=['invalid']*3;items[1]['labels']=['uncertain']*3
    (model/'analysis.json').write_text(json.dumps({'ledger_sha256':hashlib.sha256(ledger.read_bytes()).hexdigest(),
        'protocol_sha256':hashlib.sha256(protocol.read_bytes()).hexdigest(),'items':items}))
    result=compare(returned,model,packet)
    assert result['comparison_counts']=={'disagreement':1,'unstable_or_incomplete_model':1,'agreement':8}
    assert 'does not establish' in result['provenance']
