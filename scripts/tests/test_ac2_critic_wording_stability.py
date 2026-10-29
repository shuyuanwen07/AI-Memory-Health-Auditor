import json
from pathlib import Path
from zipfile import ZipFile
import pytest
from scripts import run_ac2_critic_wording_stability_20261030 as probe


def test_freeze_repetition_accounting_and_no_redispatch(tmp_path, monkeypatch):
    packet=tmp_path/'packet.zip';out=tmp_path/'out'
    items=[{'blind_id':f'Q{i}','source_messages':[],'question':'Q?','reference_answer':'A',
            'review':{'overall':'','notes':''}} for i in range(10)]
    with ZipFile(packet,'w') as z:
        for i in (1,2):z.writestr(f'reviewer-{i}.json',json.dumps({'source_sha256':'hash','items':items}))
    monkeypatch.setattr(probe,'PACKET',packet);monkeypatch.setattr(probe,'OUT',out)
    monkeypatch.setattr(probe,'PARENT',Path(probe.__file__).parent/'run_ac2_full_source_critic_development_20261030.py')
    class FakeClient:
        def __init__(self,*_):self.calls=0;self.last_execution=None
        def complete_json(self,**kwargs):
            self.calls+=1;self.last_execution={'status':'recorded'}
            if self.calls==2:raise RuntimeError('unknown outcome')
            return {**{key:'valid' for key in probe.FIELDS},'notes':'Checked'}
    monkeypatch.setattr(probe,'PipelineLLMClient',FakeClient)
    probe.freeze();probe.run();rows=json.loads((out/'ledger.json').read_text())['rows']
    assert len(rows)==30 and rows[1]['state']=='failed'
    assert sum(row['state']=='returned' for row in rows)==29
    with pytest.raises(ValueError,match='Existing ledger'):probe.run()
