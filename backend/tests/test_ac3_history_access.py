import hashlib
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ac3_study_routes as routes

def test_completed_history_is_viewable_but_never_executable(tmp_path, monkeypatch):
    src = tmp_path/'source'; src.mkdir()
    results = tmp_path/'results'; results.mkdir()
    monkeypatch.setenv('AC3_SOURCE_ROOT',str(src)); monkeypatch.setenv('AC3_RESULTS_ROOT',str(results))
    current = 'b'*64
    old = 'a'*64
    monkeypatch.setattr(routes,'formal_runtime_signature',lambda: {'source_sha256':current})
    monkeypatch.setattr(routes,'compile_mock',lambda *a: {'eligible_question_count':1,'history_count':1,
        'model_configuration': {'runtime_source_sha256':old,'ledger_schema_sha256':'c'*64,
            'target_settings_sha256':'d'*64,'target_output_token_limit':256}})
    path = src/'old-frozen.json'
    path.write_text(json.dumps({'format':'ac3-prospective-frozen-suite-v1','protocol':{'budget':{'per_request_reservation_usd':'0.01'}}}))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    folder = results/('AC3-'+digest[:24]); folder.mkdir(); review = folder/'blind-review'; review.mkdir()
    (folder/'study.json').write_text(json.dumps({'frozen_sha256':digest}))
    run = folder/'heldout-run.json'; run.write_text(json.dumps({'format':'ac3-heldout-run-export-v1','frozen_sha256':digest,'frozen_path':str(path)}))
    run_hash = hashlib.sha256(run.read_bytes()).hexdigest()
    (review/'private-key.json').write_text(json.dumps({'format':'ac3-heldout-blind-key-v1','frozen_sha256':digest,'run_sha256':run_hash}))
    (review/'blind-packet.json').write_text(json.dumps({'format':'ac3-heldout-blind-packet-v1','run_sha256':run_hash}))
    for slot in (1,2):
        (review/f'reviewer-{slot}.json').write_text(json.dumps({'format':'ac3-heldout-human-review-v1','reviewer_slot':slot,'run_sha256':run_hash}))
    app = FastAPI(); app.include_router(routes.ac3_study_router)
    with TestClient(app) as client:
        studies = client.get('/api/v1/ac3/studies/frozen').json()['studies']
        assert len(studies)==1 and studies[0]['executable'] is False
        assert client.get(f'/api/v1/ac3/studies/{digest}/status').json()['status']=='awaiting_human_review'
        assert client.get(f'/api/v1/ac3/studies/{digest}/review/blind-packet.json').status_code == 200
        assert client.post('/api/v1/ac3/studies/start',json={'frozen_file':path.name,'frozen_sha256':digest}).status_code == 409
        (review/'blind-packet.json').write_text(json.dumps({'format':'ac3-heldout-blind-packet-v1','run_sha256':'f'*64}))
        assert client.get('/api/v1/ac3/studies/frozen').json()['studies'] == []
        assert client.get(f'/api/v1/ac3/studies/{digest}/review/blind-packet.json').status_code == 404

def test_current_runtime_can_start_but_incomplete_historical_cannot_list(tmp_path, monkeypatch):
    src = tmp_path/'source'; src.mkdir()
    results = tmp_path/'results'; results.mkdir()
    monkeypatch.setenv('AC3_SOURCE_ROOT',str(src)); monkeypatch.setenv('AC3_RESULTS_ROOT',str(results))
    current = 'b'*64
    config = {'runtime_source_sha256':current,'ledger_schema_sha256':'c'*64,
              'target_settings_sha256':'d'*64,'target_output_token_limit':256}
    monkeypatch.setattr(routes,'formal_runtime_signature',lambda: {'source_sha256':current})
    monkeypatch.setattr(routes,'compile_mock',lambda *args: {'eligible_question_count':1,'history_count':1,'model_configuration':config})
    monkeypatch.setattr(routes,'run_study',lambda *args,**kwargs: {'status':'stopped','completed':0,'total':1})
    class ImmediatePool:
        def submit(self, fn): fn()
    monkeypatch.setattr(routes,'_POOL',ImmediatePool())
    path = src/'current-frozen.json'
    path.write_text(json.dumps({'format':'ac3-prospective-frozen-suite-v1','protocol':{'budget':{'per_request_reservation_usd':'0.01'}}}))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    app = FastAPI(); app.include_router(routes.ac3_study_router)
    with routes._LOCK: routes._JOBS.clear()
    with TestClient(app) as client:
        studies = client.get('/api/v1/ac3/studies/frozen').json()['studies']
        assert len(studies)==1 and studies[0]['executable'] is True
        assert client.post('/api/v1/ac3/studies/start',json={'frozen_file':path.name,'frozen_sha256':digest}).status_code == 200
        config['runtime_source_sha256'] = 'a'*64
        assert client.get('/api/v1/ac3/studies/frozen').json()['studies'] == []
        assert client.post('/api/v1/ac3/studies/start',json={'frozen_file':path.name,'frozen_sha256':digest}).status_code == 409
