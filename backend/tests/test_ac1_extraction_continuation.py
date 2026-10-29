"""Synthetic continuation never repeats an already attempted history."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
from unittest.mock import patch
from scripts.run_ac1_extraction import prepare_freeze
from scripts.run_ac1_extraction_remaining import prepare_addendum,run_remaining


def test_known_partial_is_retained_and_only_untouched_history_runs(tmp_path):
    source=tmp_path/'source.json'
    source.write_text(json.dumps({'format':'ac1-ac2-reviewed-source-v1','history_count':2,
      'histories':[{'history_id':f'H{i}','source_messages':[{'message_id':f'S{i}','order':1,'role':'user','text':f'synthetic {i}'}],'reviewed_reference':{'facts':[],'relationships':[]}} for i in (1,2)]}))
    with patch('scripts.run_ac1_extraction.source_code_sha',return_value='fixture'), patch('scripts.run_ac1_extraction.verify_source_bundle'):
        frozen_data=prepare_freeze(source)
    frozen=tmp_path/'frozen.json';frozen.write_text(json.dumps(frozen_data)); frozen_sha=hashlib.sha256(frozen.read_bytes()).hexdigest()
    folder=tmp_path/'journal';folder.mkdir();(folder/'protocol.json').write_text(json.dumps({'frozen_sha256':frozen_sha}))
    now=datetime.now(timezone.utc).isoformat()
    (folder/'H1.started.json').write_text(json.dumps({'history_id':'H1','frozen_sha256':frozen_sha,'started_at_utc':now}))
    previous={'history_id':'H1','frozen_sha256':frozen_sha,'status':'partial','candidates':[],
       'agent_stages':[{'role':'relationship_analysis','status':'failed','execution':{'request_attempts':1,'last_http_status':200}}]}
    (folder/'H1.result.json').write_text(json.dumps(previous))
    observed=[]
    class Extractor:
        last_agent_stages=[]
        def extract(self,conversation): observed.append(conversation.conversation_id);return []
    with patch('scripts.run_ac1_extraction.source_code_sha',return_value='fixture'), \
         patch('scripts.run_ac1_extraction_remaining.source_code_sha',return_value='fixture'):
        spec=prepare_addendum(frozen,frozen_sha,source,folder)
        assert spec['remaining_history_ids']==['H2'] and spec['previous_outcomes'][0]['status']=='partial'
        add=tmp_path/'add.json';add.write_text(json.dumps(spec)); add_sha=hashlib.sha256(add.read_bytes()).hexdigest()
        result=run_remaining(frozen,frozen_sha,source,folder,add,add_sha,extractor_factory=lambda *_:Extractor())
        assert result['continued_histories']==1 and observed==['H2']
    assert json.loads((folder/'H1.result.json').read_text())==previous
