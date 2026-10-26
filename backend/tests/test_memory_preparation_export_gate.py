"""Public gate binds every private store receipt, independently of source truth."""
import hashlib
import json
from pathlib import Path
import sys

scripts = Path('/scripts') if Path('/scripts/export_stability_package.py').exists() else Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(scripts))
from export_stability_package import memory_preparation_receipt_gate
from stability_configuration import study_trial_memory_controls


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def fixture(tmp_path, monkeypatch):
    # The strict receipt schema is covered by the normalizer's dedicated
    # tests; this fixture isolates denominator/hash/wire/replay gate binding.
    import stability_memory_preparation
    monkeypatch.setattr(stability_memory_preparation, 'validate_private_memory_preparation_receipt', lambda *a, **k: {'passed':True})
    protocol = {'memory_preparation_receipt_required':True,
                'target':{'output_token_limit':8192,'final_target_profile_flags':{}}}
    trial = {'split':'evaluation','case_id':'SYNTHETIC','round':1,'arm':'strong_rule_based','directory':'cell'}
    save(tmp_path/'trial-matrix.json', {'trials':[trial]})
    memory = study_trial_memory_controls(protocol)
    save(tmp_path/'cell/pilot-protocol.json', {**memory,'memory_preparation_receipt_required':True,
        'output_token_limit':memory['target_memory_profile']['output_token_limit']})
    path = tmp_path/'cell/private-memory-preparation-receipts.json'
    save(path, {'synthetic_stub':True})
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    save(tmp_path/'cell/actual-wire-validation.json', {'evidence_sha256':{path.name:digest}})
    save(tmp_path/'study-execution.json', {'status':'completed'})
    replay = {'status':'passed','memory_preparation_receipt_required':True,'memory_preparation_comparisons':1,
              'rows':[{**trial,'status':'compared','memory_preparation_compared':True,'memory_preparation_receipt_sha256':digest}]}
    return protocol, replay, path


def test_bound_actual_store_receipt_and_replay_pass(tmp_path, monkeypatch):
    protocol, replay, _ = fixture(tmp_path, monkeypatch)
    gate = memory_preparation_receipt_gate(protocol, tmp_path, replay)
    assert gate['status'] == 'pass'
    assert gate['observed']['validated_actual_receipts'] == gate['observed']['replay_bound_receipts'] == 1


def test_raw_file_tampering_cannot_reuse_old_replay(tmp_path, monkeypatch):
    protocol, replay, path = fixture(tmp_path, monkeypatch)
    path.write_text('{"different":true}')
    assert memory_preparation_receipt_gate(protocol, tmp_path, replay)['status'] == 'fail'


def test_missing_or_duplicate_replay_cell_cannot_pass(tmp_path, monkeypatch):
    protocol, replay, _ = fixture(tmp_path, monkeypatch)
    replay['rows'] *= 2
    assert memory_preparation_receipt_gate(protocol, tmp_path, replay)['status'] == 'fail'


def test_missing_actual_sidecar_is_not_a_safe_empty_receipt(tmp_path, monkeypatch):
    protocol, replay, path = fixture(tmp_path, monkeypatch)
    path.unlink()
    gate = memory_preparation_receipt_gate(protocol, tmp_path, replay)
    assert gate['status'] == 'fail' and gate['observed']['missing_receipts'] == 1


def test_legacy_studies_do_not_acquire_a_new_gate(tmp_path):
    assert memory_preparation_receipt_gate({}, tmp_path, {}) is None
    assert memory_preparation_receipt_gate({'memory_preparation_receipt_required':False}, tmp_path, {}) is None


def test_missing_matrix_is_pending(tmp_path):
    assert memory_preparation_receipt_gate({'memory_preparation_receipt_required':True}, tmp_path, {})['status'] == 'pending'
