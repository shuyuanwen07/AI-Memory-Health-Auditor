"""Controlled source-only extraction with synthetic fake model responses."""
import hashlib,json
from pathlib import Path
from unittest.mock import patch
import pytest
from scripts.run_ac1_extraction import prepare_freeze, run


@pytest.fixture
def files(tmp_path):
    source=tmp_path/'reviewed-source.json'
    source.write_text(json.dumps({'format':'ac1-ac2-reviewed-source-v1','history_count':1,
        'reference_qualifications':[{'history_id':'H1','fact_id':'F8','status':'unresolved'}],
        'histories':[{'history_id':'H1','source_messages':[{'message_id':'S1','order':1,'role':'user','text':'Synthetic source only'}],
                      'reviewed_reference':{'facts':[{'memory_id':'F8','canonical_value':'SECRET GOLD MUST NOT BE SENT'}],'relationships':[]}}]}))
    with patch('scripts.run_ac1_extraction.source_code_sha',return_value='runtime-fixture'), \
         patch('scripts.run_ac1_extraction.verify_source_bundle'):
        config=prepare_freeze(source)
    frozen=tmp_path/'frozen.json'; frozen.write_text(json.dumps(config)); digest=hashlib.sha256(frozen.read_bytes()).hexdigest()
    return source,frozen,digest,tmp_path/'results'


def test_source_only_output_and_resume_without_provider_repeat(files):
    source,frozen,digest,folder=files; observed=[]
    class Memory:
        def model_dump(self,mode): return {'memory_id':'M1','canonical_value':'synthetic candidate','source_message_ids':['S1'],'relationships':[]}
    class Extractor:
        last_agent_stages=[]
        def extract(self,conversation):
            observed.append(conversation.model_dump(mode='json')); return [Memory()]
    def factory(provider,model):
        assert provider=='openrouter' and model=='openai/gpt-6-luna'; return Extractor()
    with patch('scripts.run_ac1_extraction.source_code_sha',return_value='runtime-fixture'):
        result=run(frozen,digest,source,folder,extractor_factory=factory)
        assert result['histories_completed']==1 and not result['human_output_review_completed']
        assert run(frozen,digest,source,folder,extractor_factory=factory)['histories_completed']==1
    assert len(observed)==1 and 'SECRET GOLD' not in json.dumps(observed)
    assert observed[0]['messages'][0]['timestamp'].startswith('2000-01-01')
    assert json.loads((folder/'H1.result.json').read_text())['status']=='completed'
    from scripts.prepare_ac1_extraction_review import make_packets
    packets,_=make_packets(frozen,digest,source,folder)
    assert packets[0]['histories'][0]['reviewed_reference_facts'][0]['reference_status']=='unresolved'
    assert packets[0]['histories'][0]['candidates'][0]['review']['supported'] is None
    assert packets[0]['reviewer_declaration']['completed_by_human'] is None


def test_unknown_previous_attempt_blocks_resend(files):
    source,frozen,digest,folder=files;folder.mkdir();(folder/'protocol.json').write_text(json.dumps({'frozen_sha256':digest}))
    (folder/'H1.started.json').write_text('{}')
    with patch('scripts.run_ac1_extraction.source_code_sha',return_value='runtime-fixture'):
        with pytest.raises(ValueError,match='unresolved'):
            run(frozen,digest,source,folder,extractor_factory=lambda *_:pytest.fail('must not call'))


def test_runtime_change_preserves_output_but_does_not_claim_success(files):
    source,frozen,digest,folder=files
    class Memory:
        def model_dump(self,mode): return {'memory_id':'M1','canonical_value':'synthetic','source_message_ids':['S1'],'relationships':[]}
    class Extractor:
        last_agent_stages=[]
        def extract(self,_conversation): return [Memory()]
    with patch('scripts.run_ac1_extraction.source_code_sha',side_effect=['runtime-fixture','runtime-fixture','changed']):
        with pytest.raises(ValueError,match='Runtime changed'):
            run(frozen,digest,source,folder,extractor_factory=lambda *_:Extractor())
    assert json.loads((folder/'H1.result.json').read_text())['status']=='runtime_changed'


def test_each_remote_role_can_dispatch_once_without_automatic_retry():
    from scripts.run_ac1_extraction import OneRequestPerRole
    observer=OneRequestPerRole('openai/gpt-6-luna')
    def receipt(role,attempt=1):
        return {'phase':'before_send','attempt_index':attempt,'request_contract':
                {'role':role,'provider_name':'openrouter','model':'openai/gpt-6-luna'}}
    observer(receipt('memory_extraction'))
    with pytest.raises(ValueError,match='repeated'):
        observer(receipt('memory_extraction'))
    with pytest.raises(ValueError,match='repeated'):
        observer(receipt('relationship_analysis',2))
    observer(receipt('relationship_analysis'))
    observer(receipt('independent_memory_review'))
