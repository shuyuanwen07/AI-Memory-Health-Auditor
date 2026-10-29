"""Operator AC3 routes do not leak private evidence or dispatch drafts."""
import hashlib
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import ac3_study_routes as routes


class ImmediatePool:
    def submit(self, fn): fn()


def client():
    app=FastAPI(); app.include_router(routes.ac3_study_router); return TestClient(app)


def test_draft_not_started_and_private_files_not_downloadable(tmp_path, monkeypatch):
    source=tmp_path/'source'; source.mkdir(); results=tmp_path/'results'; results.mkdir()
    monkeypatch.setenv('AC3_SOURCE_ROOT',str(source)); monkeypatch.setenv('AC3_RESULTS_ROOT',str(results))
    draft=source/'draft-frozen.json'; draft.write_text(json.dumps({'format':'draft'}))
    digest=hashlib.sha256(draft.read_bytes()).hexdigest()
    with client() as c:
        assert c.get('/api/v1/ac3/studies/frozen').json()=={'studies':[]}
        assert c.post('/api/v1/ac3/studies/start',json={'frozen_file':draft.name,'frozen_sha256':digest}).status_code==409
        folder=results/('AC3-'+digest[:24])/'blind-review'; folder.mkdir(parents=True)
        (folder/'private-key.json').write_text('{"sensitive":true}')
        (folder/'heldout-run.json').write_text('{"scores":"private"}')
        (folder/'reviewer-1.json').write_text('{"decisions":[]}')
        assert c.get(f'/api/v1/ac3/studies/{digest}/review/private-key.json').status_code==404
        assert c.get(f'/api/v1/ac3/studies/{digest}/review/heldout-run.json').status_code==404
        assert c.get(f'/api/v1/ac3/studies/{digest}/review/reviewer-1.json').status_code==404


def test_status_reports_only_sanitized_progress(tmp_path, monkeypatch):
    source=tmp_path/'source'; source.mkdir(); results=tmp_path/'results'; results.mkdir()
    monkeypatch.setenv('AC3_SOURCE_ROOT',str(source)); monkeypatch.setenv('AC3_RESULTS_ROOT',str(results))
    path=source/'reviewed-frozen.json'; path.write_text('{}'); digest=hashlib.sha256(path.read_bytes()).hexdigest()
    plan={'eligible_question_count':2,'history_count':1}
    monkeypatch.setattr(routes,'_read_candidate',lambda *_:(path,'0.01',plan))
    monkeypatch.setattr(routes,'_POOL',ImmediatePool())
    def fake_run(_engine, **kwargs):
        kwargs['on_progress'](2,2)
        return {'status':'awaiting_human_review','completed':2,'total':2,'private_answer':'never expose','private_key':'never expose'}
    monkeypatch.setattr(routes,'run_study',fake_run)
    with routes._LOCK: routes._JOBS.clear()
    with client() as c:
        response=c.post('/api/v1/ac3/studies/start',json={'frozen_file':path.name,'frozen_sha256':digest})
        assert response.status_code==200
        status=c.get(f'/api/v1/ac3/studies/{digest}/status').json()
        assert status['status']=='awaiting_human_review' and status['completed']==2
        assert 'private_answer' not in status and 'private_key' not in status
