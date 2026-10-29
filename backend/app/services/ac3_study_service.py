"""Prepare and run a reviewed AC3 study; never fabricate human outcomes.

Calling run_study can incur model charges. Inputs must already be frozen,
source-reviewed, and protocol-approved. Interrupted or unknown requests stop;
no provider retry is performed. Output is written separately from the original
review files and contains private data, including a blind-review identity key.
"""
import json
import os
import secrets
from pathlib import Path
import shutil
import tempfile
from sqlalchemy.orm import Session
from app.services.ac3_attempt_ledger import AttemptLedger
from app.services.ac3_controlled_runner import run_controlled_ac3_step
from app.services.ac3_prepare_system import prepare_staged_ac3
from app.services.ac3_run_export import export_heldout_run
from app.services.ac3_schema import ensure_ac3_ledger_schema
from scripts.ac3_fixed_suite_adapter import compile_mock, sha
from scripts.export_ac3_blind_review import make_materials


def _publish_matching(temp, target, digest):
    """Publish once, or verify the exact existing file without replacing it."""
    try:
        try:
            os.link(temp, target, follow_symlinks=False)
        except FileExistsError:
            if target.is_symlink() or not target.is_file() or sha(target.read_bytes()) != digest:
                raise ValueError('Existing study export differs from saved evidence')
    finally:
        temp.unlink(missing_ok=True)


def _study_folder(root, frozen_sha256):
    root = Path(root)
    if root.is_symlink() or not root.is_dir(): raise ValueError('Results directory must exist and not be a symlink')
    folder = root / ('AC3-' + frozen_sha256[:24])
    if folder.is_symlink(): raise ValueError('Results folder cannot be a symlink')
    folder.mkdir(mode=0o700, exist_ok=True)
    marker = folder / 'study.json'
    if marker.is_symlink(): raise ValueError('Study marker cannot be a symlink')
    if marker.exists():
        if json.loads(marker.read_text()).get('frozen_sha256') != frozen_sha256:
            raise ValueError('Existing result folder belongs to another frozen study')
    else:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os,'O_NOFOLLOW',0), 0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump({'format':'ac3-study-result-directory-v1','frozen_sha256':frozen_sha256},f); f.write('\n')
    return folder


def run_study(engine, *, frozen_path, frozen_sha256, reservation, results_root, on_progress=None):
    """Run eligible frozen questions and export anonymous blank human reviews."""
    frozen_path = Path(frozen_path)
    plan = compile_mock(frozen_path, frozen_sha256, reservation)
    cfg = plan['model_configuration']
    ensure_ac3_ledger_schema(engine, cfg.get('ledger_schema_sha256'))
    folder = _study_folder(results_root, frozen_sha256)
    scope = 'AC3' + frozen_sha256[:32]
    staged = prepare_staged_ac3(engine, frozen_path=frozen_path, frozen_sha256=frozen_sha256,
                                reservation=reservation, ledger_scope=scope)
    eligible = [item for item in plan['items'] if item['grounding_review'] == 'valid']
    completed = 0
    if on_progress: on_progress(completed, len(eligible))
    for item in eligible:
        test_id = item['test_id']
        request_key = 'AC3-' + sha(f'{frozen_sha256}|{test_id}'.encode())[:40]
        try:
            result = run_controlled_ac3_step(engine, frozen_path=frozen_path, frozen_sha256=frozen_sha256,
                reservation=reservation, scope=scope, history_conversations=staged['history_conversations'],
                history_runs=staged['history_runs'], frozen_test_id=test_id, request_key=request_key)
        except Exception as exc:
            # Do not leak private source text or provider errors to the UI.
            # Inspect the stored ledger before any subsequent operator action.
            return {'status':'stopped','completed':completed,'total':len(eligible),
                    'failed_test_id':test_id,'error_type':type(exc).__name__,
                    'automatic_retry_allowed':False,'results_folder':str(folder)}
        if result['status'] != 'completed':
            return {'status':result['status'],'completed':completed,'total':len(eligible),
                    'failed_test_id':test_id,'automatic_retry_allowed':False,'results_folder':str(folder)}
        completed += 1
        if on_progress: on_progress(completed, len(eligible))
    # All exact matching ledger receipts are needed for an answer export.
    ledger = AttemptLedger(engine)
    receipt_path = folder / 'receipts.json'
    temp_receipts = folder / ('.receipts-' + secrets.token_hex(12) + '.json')
    receipt = ledger.export_settled(scope, frozen_path, frozen_sha256, reservation, temp_receipts)
    _publish_matching(temp_receipts, receipt_path, receipt['output_sha256'])
    run_path = folder / 'heldout-run.json'
    temp_run = folder / ('.heldout-' + secrets.token_hex(12) + '.json')
    with Session(engine) as db:
        run = export_heldout_run(db, frozen_path, frozen_sha256, receipt_path, receipt['output_sha256'],
            reservation, staged['history_conversations'], staged['history_runs'], temp_run)
    _publish_matching(temp_run, run_path, run['output_sha256'])
    review_dir = folder / 'blind-review'
    if not review_dir.exists():
        private, packet, review1, review2 = make_materials(frozen_path, frozen_sha256, run_path, run['output_sha256'])
        temp = Path(tempfile.mkdtemp(prefix='.blind-', dir=folder))
        try:
            for name, value in (('private-key.json',private),('blind-packet.json',packet),('reviewer-1.json',review1),('reviewer-2.json',review2)):
                path = temp / name
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os,'O_NOFOLLOW',0), 0o600)
                with os.fdopen(fd,'w',encoding='utf-8') as stream:
                    json.dump(value,stream,ensure_ascii=False,indent=2); stream.write('\n')
            os.rename(temp,review_dir)
        except BaseException:
            shutil.rmtree(temp,ignore_errors=True); raise
    elif review_dir.is_symlink() or not review_dir.is_dir():
        raise ValueError('Invalid blind review directory')
    # Existing human files are never overwritten or silently declared complete.
    return {'status':'awaiting_human_review','completed':completed,'total':len(eligible),
            'review_dir':str(review_dir),'results_folder':str(folder),'human_review_completed':False,
            'provider_cost_status':'provider_report_unreconciled'}
