"""Operator-only AC3 study launcher and blind-review downloads.

The app-wide OperatorAccessMiddleware applies to every route. Only reviewed,
prospectively frozen source packages can be started; private answer/score/key
files are deliberately not downloadable here.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import shutil
from threading import Lock
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.database.session import engine
from app.services.ac3_study_service import run_study
from app.services.formal_freeze import formal_runtime_signature
from scripts.ac3_fixed_suite_adapter import compile_mock

ac3_study_router = APIRouter(prefix='/api/v1/ac3/studies', tags=['AC3 research'])
_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ac3-study')
_JOBS, _LOCK = {}, Lock()
_ALLOWED_DOWNLOADS = {'blind-packet.json','reviewer-1.json','reviewer-2.json'}


def _root():
    return Path(os.getenv('AC3_SOURCE_ROOT','/output')).resolve()


def _results_root():
    return Path(os.getenv('AC3_RESULTS_ROOT','/ac3-results')).resolve()


def _read_candidate(relative, expected, *, require_current=True):
    if not isinstance(relative, str) or not relative or len(relative) > 1000 or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('Invalid frozen study identity')
    root = _root()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size > 20_000_000:
        raise ValueError('Frozen study is unavailable')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected: raise ValueError('Frozen study digest changed')
    frozen = json.loads(raw)
    if frozen.get('format') != 'ac3-prospective-frozen-suite-v1': raise ValueError('Not a frozen AC3 study')
    budget = frozen['protocol']['budget']
    try:
        reserve = Decimal(str(budget['per_request_reservation_usd']))
    except (KeyError, InvalidOperation, ValueError) as exc:
        raise ValueError('Frozen request cost assumption is missing') from exc
    if not reserve.is_finite() or reserve <= 0: raise ValueError('Frozen request cost assumption is invalid')
    plan = compile_mock(path, expected, str(reserve))
    cfg = plan['model_configuration']
    if (not re.fullmatch(r'[0-9a-f]{64}', str(cfg.get('runtime_source_sha256', ''))) or
        not cfg.get('ledger_schema_sha256') or not cfg.get('target_settings_sha256') or
        not isinstance(cfg.get('target_output_token_limit'), int) or cfg['target_output_token_limit'] < 1):
        raise ValueError('Frozen runtime or execution settings are incomplete')
    if require_current and cfg['runtime_source_sha256'] != formal_runtime_signature()['source_sha256']:
        raise ValueError('Frozen runtime does not match current runtime')
    return path, str(reserve), plan


def _completed_history(study_id, expected_source=None):
    """Validate saved run and blind materials before exposing an older study."""
    root = _results_root()
    folder = root / ('AC3-' + study_id[:24])
    review = folder / 'blind-review'
    paths = [folder / 'study.json', folder / 'heldout-run.json', review / 'private-key.json',
             *(review / name for name in sorted(_ALLOWED_DOWNLOADS))]
    try:
        if (folder.is_symlink() or review.is_symlink() or not folder.resolve().is_relative_to(root)
                or any(path.is_symlink() or not path.is_file() or path.stat().st_size > 20_000_000 for path in paths)):
            return False
        marker, run, key, packet, reviewer1, reviewer2 = [json.loads(path.read_bytes()) for path in paths]
        source = Path(run['frozen_path']).resolve()
        run_hash = hashlib.sha256(paths[1].read_bytes()).hexdigest()
        if (marker.get('frozen_sha256') != study_id or run.get('format') != 'ac3-heldout-run-export-v1'
                or run.get('frozen_sha256') != study_id or not source.is_relative_to(_root())
                or not source.is_file() or (expected_source is not None and source != expected_source.resolve())
                or hashlib.sha256(source.read_bytes()).hexdigest() != study_id
                or key.get('format') != 'ac3-heldout-blind-key-v1' or key.get('frozen_sha256') != study_id
                or key.get('run_sha256') != run_hash or packet.get('format') != 'ac3-heldout-blind-packet-v1'
                or packet.get('run_sha256') != run_hash):
            return False
        for slot, reviewer in enumerate((reviewer1, reviewer2), 1):
            if (reviewer.get('format') != 'ac3-heldout-human-review-v1'
                    or reviewer.get('reviewer_slot') != slot or reviewer.get('run_sha256') != run_hash):
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False


class StudyStart(BaseModel):
    frozen_file: str = Field(min_length=1, max_length=1000)
    frozen_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class ReviewSubmission(BaseModel):
    reviewer_1_json: str = Field(min_length=1, max_length=1_000_000)
    reviewer_2_json: str = Field(min_length=1, max_length=1_000_000)


@ac3_study_router.get('/frozen')
def list_frozen_studies():
    root = _root()
    if not root.is_dir(): return {'studies':[]}
    studies = []
    # Bounded discovery, and only candidate files explicitly named frozen.
    for path in root.rglob('*frozen*.json'):
        if len(studies) >= 50: break
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(root) or path.stat().st_size > 20_000_000: continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            relative = str(path.relative_to(root))
            candidate, reserve, plan = _read_candidate(relative, digest, require_current=False)
            executable = plan['model_configuration']['runtime_source_sha256'] == formal_runtime_signature()['source_sha256']
            if not executable and not _completed_history(digest, candidate): continue
            studies.append({'file':relative,'sha256':digest,'questions':plan['eligible_question_count'],
                            'histories':plan['history_count'],'reservation_usd':reserve,'executable':executable})
        except (ValueError, KeyError, OSError, json.JSONDecodeError):
            continue
    return {'studies':studies}


@ac3_study_router.post('/start')
def start_study(request: StudyStart):
    try:
        path, reservation, plan = _read_candidate(request.frozen_file, request.frozen_sha256)
        root = _results_root()
        if not root.is_dir(): raise ValueError('Results directory is unavailable')
    except (ValueError, KeyError, OSError, json.JSONDecodeError):
        raise HTTPException(409, 'The reviewed frozen study is not ready to run.')
    digest = request.frozen_sha256
    with _LOCK:
        if _JOBS.get(digest, {}).get('status') == 'running':
            return dict(_JOBS[digest])
        _JOBS[digest] = {'study_id':digest,'status':'running','completed':0,'total':plan['eligible_question_count']}
    def progress(completed, total):
        with _LOCK: _JOBS[digest].update(completed=completed,total=total)
    def work():
        try:
            isolated_engine = engine.execution_options(isolation_level='SERIALIZABLE')
            result = run_study(isolated_engine, frozen_path=path, frozen_sha256=digest,
                               reservation=reservation, results_root=root, on_progress=progress)
            safe = {key:value for key,value in result.items() if key in {'status','completed','total','failed_test_id','error_type','human_review_completed','provider_cost_status'}}
        except Exception as exc:
            safe = {'status':'stopped','error_type':type(exc).__name__}
        with _LOCK: _JOBS[digest].update(safe)
    _POOL.submit(work)
    return dict(_JOBS[digest])


@ac3_study_router.get('/summaries')
def list_reviewed_summaries():
    """Return aggregate reports only, preserving distinct study identities."""
    root = _results_root()
    if not root.is_dir(): return {'studies':[]}
    found = []
    for marker in root.glob('AC3-*/latest-review.json'):
        if len(found) >= 25: break
        try:
            folder = marker.parent
            if folder.is_symlink() or marker.is_symlink(): continue
            digest = json.loads((folder/'study.json').read_text())['frozen_sha256']
            if not re.fullmatch(r'[0-9a-f]{64}',digest) or folder.name != 'AC3-' + digest[:24]: continue
            run = json.loads((folder/'heldout-run.json').read_text())
            frozen_path = Path(run['frozen_path']).resolve()
            if not frozen_path.is_relative_to(_root()) or not frozen_path.is_file(): continue
            raw = frozen_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest: continue
            frozen = json.loads(raw)
            role = frozen.get('study_role')
            if role not in ('primary_validation','stability_repeat'): role = 'unclassified'
            summary = get_study_summary(digest)
            found.append((marker.stat().st_mtime, {'study_id':digest,'study_role':role,'summary':summary}))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, HTTPException):
            continue
    found.sort(key=lambda item:item[0], reverse=True)
    return {'studies':[entry for _,entry in found]}


@ac3_study_router.get('/{study_id}/status')
def study_status(study_id: str):
    if not re.fullmatch(r'[0-9a-f]{64}',study_id): raise HTTPException(404, 'Study not found.')
    with _LOCK:
        job = _JOBS.get(study_id)
        if job: return dict(job)
    if _completed_history(study_id):
        return {'study_id':study_id,'status':'awaiting_human_review'}
    # The process may have restarted. The operator can resume the same frozen
    # study; the durable ledger prevents repeated or unresolved dispatches.
    return {'study_id':study_id,'status':'not_active'}


@ac3_study_router.get('/{study_id}/review/{filename}')
def download_review_material(study_id: str, filename: str):
    if not re.fullmatch(r'[0-9a-f]{64}',study_id) or filename not in _ALLOWED_DOWNLOADS:
        raise HTTPException(404, 'Review material not found.')
    root = _results_root()
    path = root / ('AC3-' + study_id[:24]) / 'blind-review' / filename
    resolved = path.resolve()
    if not _completed_history(study_id) or path.is_symlink() or not resolved.is_relative_to(root) or not resolved.is_file():
        raise HTTPException(404, 'Review material not found.')
    return FileResponse(resolved, media_type='application/json', filename=filename, headers={'Cache-Control':'no-store'})


@ac3_study_router.post('/{study_id}/reviews')
def submit_blind_reviews(study_id: str, submission: ReviewSubmission):
    """Store both source reviews unchanged and publish only aggregate metrics."""
    if not re.fullmatch(r'[0-9a-f]{64}',study_id): raise HTTPException(404, 'Study not found.')
    root = _results_root()
    folder = root / ('AC3-' + study_id[:24])
    if folder.is_symlink() or not folder.resolve().is_relative_to(root) or not folder.is_dir():
        raise HTTPException(404, 'Study not found.')
    try:
        marker = json.loads((folder/'study.json').read_text())
        if marker.get('frozen_sha256') != study_id: raise ValueError('Study identity mismatch')
        run_path, key_path = folder/'heldout-run.json', folder/'blind-review'/'private-key.json'
        if any(p.is_symlink() or not p.is_file() for p in (run_path,key_path)):
            raise ValueError('The saved run or blind key is unavailable')
        run = json.loads(run_path.read_text())
        frozen_path = Path(run['frozen_path']).resolve()
        if not frozen_path.is_relative_to(_root()) or not frozen_path.is_file():
            raise ValueError('Frozen source is unavailable')
        texts = [submission.reviewer_1_json, submission.reviewer_2_json]
        # Parse before writing; actual semantics and blinded identities are
        # validated by the same analyzer used for the dashboard.
        for raw in texts: json.loads(raw)
        digests = [hashlib.sha256(raw.encode('utf-8')).hexdigest() for raw in texts]
        destination = folder / ('reviews-' + digests[0][:16] + '-' + digests[1][:16])
        temp = Path(tempfile.mkdtemp(prefix='.reviews-', dir=folder))
        try:
            review_paths = [temp/'reviewer-1.json', temp/'reviewer-2.json']
            for path, raw in zip(review_paths,texts,strict=True):
                fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0), 0o600)
                with os.fdopen(fd,'w',encoding='utf-8',newline='') as stream: stream.write(raw)
            from scripts.publish_ac3_heldout_summary import build_summary
            paths = {'frozen':frozen_path,'run':run_path,'blind_key':key_path,'review_1':review_paths[0],'review_2':review_paths[1]}
            hashes = {'frozen':study_id,'run':hashlib.sha256(run_path.read_bytes()).hexdigest(),
                      'blind_key':hashlib.sha256(key_path.read_bytes()).hexdigest(),'review_1':digests[0],'review_2':digests[1]}
            summary = build_summary(paths,hashes)
            with (temp/'summary.json').open('x',encoding='utf-8') as stream:
                json.dump(summary,stream,ensure_ascii=False,indent=2); stream.write('\n')
            os.chmod(temp/'summary.json',0o600)
            if destination.exists():
                if destination.is_symlink() or any((destination/p.name).read_bytes()!=p.read_bytes() for p in review_paths):
                    raise ValueError('Existing review evidence differs')
                shutil.rmtree(temp)
            else:
                os.rename(temp,destination)
        except BaseException:
            shutil.rmtree(temp,ignore_errors=True); raise
        # Pointer changes only the current aggregate. Every review submission is
        # kept in its own immutable content-addressed directory.
        fd, pointer = tempfile.mkstemp(prefix='.latest-',dir=folder)
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump({'review_directory':destination.name},stream); stream.write('\n')
        os.replace(pointer,folder/'latest-review.json')
        return {'status':'reviewed','summary':summary}
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError):
        raise HTTPException(422, 'The two reviews are incomplete, do not match this study, or lack the required independent blind-review declarations.')


@ac3_study_router.get('/{study_id}/summary')
def get_study_summary(study_id: str):
    if not re.fullmatch(r'[0-9a-f]{64}',study_id): raise HTTPException(404, 'Study not found.')
    root = _results_root(); folder = root / ('AC3-' + study_id[:24])
    try:
        if folder.is_symlink() or not folder.resolve().is_relative_to(root): raise ValueError
        if json.loads((folder/'study.json').read_text()).get('frozen_sha256') != study_id: raise ValueError
        name = json.loads((folder/'latest-review.json').read_text())['review_directory']
        if not re.fullmatch(r'reviews-[0-9a-f]{16}-[0-9a-f]{16}',name): raise ValueError
        path = folder/name/'summary.json'
        if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()): raise ValueError
        summary = json.loads(path.read_text())
        if summary.get('format') != 'ac3-heldout-public-summary-v1': raise ValueError
        return summary
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(404, 'Reviewed results are not yet available.')
