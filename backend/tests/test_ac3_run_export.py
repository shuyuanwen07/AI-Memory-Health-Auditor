"""Synthetic integration only: no provider, real review or acceptance claim."""
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest
from sqlalchemy import select
from app.models import TargetResponseModel, EvaluationResultModel
from app.services.ac3_staging import stage_reviewed_suite
from app.services.ac3_run_export import build_heldout_run, export_heldout_run
from scripts.ac3_fixed_suite_adapter import sha
from test_ac3_database_mapping import saved_histories as saved_histories, fake_compile, add_fixture_audits


def fake_export_compile(path, expected, reservation, snapshot=None):
    result = fake_compile(path, expected, reservation, snapshot)
    result['model_configuration']['evaluator_implementation_version'] = 'rule-based-v65'
    result['model_configuration']['pipeline_implementation_version'] = 'rule-based-v36'
    return result


@pytest.fixture
def prepared(saved_histories, tmp_path):
    db, frozen, _, mapping = saved_histories
    data = json.loads(frozen.read_text())
    now = datetime.now(timezone.utc)
    data['frozen_at_utc'] = (now - timedelta(minutes=1)).isoformat()
    data['protocol'] = {'model_configuration': {'target_provider':'rule_based', 'evaluator_provider':'rule_based',
                                                'pipeline_provider':'rule_based'}, 'budget': {'max_new_estimated_usd':0}}
    frozen.write_text(json.dumps(data))
    digest = sha(frozen.read_bytes())
    add_fixture_audits(db)
    runs = {f'H{i}': f'R{i}' for i in range(8)}
    with patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_compile):
        stage_reviewed_suite(db, frozen, digest, '0', mapping, runs)
    receipts = []
    for n in range(8):
        for q in range(4):
            remote_id, run = f'H{n}-Q{q}', f'R{n}'
            local_id = 'AC3' + sha(f'{digest}|{run}|{remote_id}'.encode())[:32].upper()
            response_id = f'ANS{n}-{q}'
            answer = f'Synthetic answer {n}-{q}'
            db.add(TargetResponseModel(id=response_id, test_id=local_id, run_id=run,
                                       response_text=answer, model='fixture', temperature=0))
            db.add(EvaluationResultModel(id=f'E{n}-{q}', test_id=local_id, response_id=response_id,
                                         passed=True, failure_type=None, reason='synthetic', evaluator='rule-based-v65'))
            receipts.append({'test_id': remote_id, 'response_text': answer, 'request_key': remote_id,
                             'contract_sha256': 'a' * 64, 'reported_cost_usd':'0.001',
                             'dispatched_at_utc': now.isoformat()})
    db.commit()
    receipt_path = tmp_path / 'synthetic-receipts.json'
    receipt_path.write_text(json.dumps({'format':'ac3-settled-receipts-v1','frozen_sha256':digest,
                                        'receipt_count':32,'reported_cost_status':'provider_report_unreconciled',
                                        'responses':receipts}))
    return db, frozen, digest, mapping, runs, receipt_path


def perform(f):
    db, frozen, digest, mapping, runs, receipt = f
    with patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_export_compile):
        return build_heldout_run(db, frozen, digest, receipt, sha(receipt.read_bytes()), '0', mapping, runs)


def test_bridges_real_db_shapes_without_claiming_human_review(prepared):
    result = perform(prepared)
    assert result['format'] == 'ac3-heldout-run-export-v1'
    assert len(result['responses']) == 32
    assert result['responses'][0]['automatic'] == {'verdict':'pass','failure_dimension':None}
    assert 'not independently authenticated' in result['provenance_limitations']


def test_export_feeds_blind_packet_without_automatic_scores(prepared, tmp_path):
    from scripts.export_ac3_blind_review import make_materials
    db, frozen, digest, mapping, runs, receipt = prepared
    output = tmp_path / 'heldout.json'
    with patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_export_compile):
        result = export_heldout_run(db, frozen, digest, receipt, sha(receipt.read_bytes()), '0', mapping, runs, output)
    with patch('scripts.export_ac3_blind_review.compile_mock', side_effect=fake_compile):
        key, packet, first, second = make_materials(frozen, digest, output, result['output_sha256'])
    assert result['response_count'] == len(packet['cases']) == 32
    assert len(key['blind_to_test']) == 32
    assert all('automatic' not in row for row in packet['cases'])
    assert not first['reviewer_declaration']['completed_by_human']
    assert not second['reviewer_declaration']['completed_by_human']
    with pytest.raises(FileExistsError):
        with patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_export_compile):
            export_heldout_run(db, frozen, digest, receipt, sha(receipt.read_bytes()), '0', mapping, runs, output)


def test_altered_answer_is_rejected(prepared):
    db = prepared[0]
    row = db.scalar(select(TargetResponseModel))
    row.response_text = 'tampered'
    db.commit()
    with pytest.raises(ValueError, match='response'):
        perform(prepared)


def test_multiple_evaluations_are_rejected(prepared):
    db = prepared[0]
    row = db.scalar(select(EvaluationResultModel))
    db.add(EvaluationResultModel(id='EXTRA', test_id=row.test_id, response_id=row.response_id,
                                 passed=False, failure_type='accuracy', reason='synthetic', evaluator='fixture-evaluator'))
    db.commit()
    with pytest.raises(ValueError, match='Exactly one'):
        perform(prepared)


@pytest.mark.parametrize('version', [None, 'rule-based-v4'])
def test_missing_or_mismatched_implementation_version_is_rejected(prepared, version):
    db, frozen, digest, mapping, runs, receipt = prepared
    def compile_with_version(*args, **kwargs):
        result = fake_compile(*args, **kwargs)
        if version is not None:
            result['model_configuration']['evaluator_implementation_version'] = version
        return result
    with patch('scripts.ac3_database_mapping.compile_mock', side_effect=compile_with_version):
        with pytest.raises(ValueError, match='implementation'):
            build_heldout_run(db, frozen, digest, receipt, sha(receipt.read_bytes()), '0', mapping, runs)


def test_mismatched_pipeline_implementation_is_rejected(prepared):
    db, frozen, digest, mapping, runs, receipt = prepared
    def wrong_version(*args, **kwargs):
        result = fake_export_compile(*args, **kwargs)
        result['model_configuration']['pipeline_implementation_version'] = 'rule-based-v2'
        return result
    with patch('scripts.ac3_database_mapping.compile_mock', side_effect=wrong_version):
        with pytest.raises(ValueError, match='pipeline implementation'):
            build_heldout_run(db, frozen, digest, receipt, sha(receipt.read_bytes()), '0', mapping, runs)


def test_dispatch_before_freeze_is_rejected(prepared):
    receipt = prepared[-1]
    data = json.loads(receipt.read_text())
    data['responses'][0]['dispatched_at_utc'] = '2000-01-01T00:00:00+00:00'
    receipt.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='predates'):
        perform(prepared)


@pytest.mark.parametrize('change, error', [
    ('missing_cost', 'cost'), ('bad_contract', 'contract'), ('duplicate_request', 'distinct request')])
def test_receipt_metadata_is_required(prepared, change, error):
    receipt = prepared[-1]
    data = json.loads(receipt.read_text())
    if change == 'missing_cost':
        data['responses'][0]['reported_cost_usd'] = None
    elif change == 'bad_contract':
        data['responses'][0]['contract_sha256'] = 'bad'
    else:
        data['responses'][0]['request_key'] = data['responses'][1]['request_key']
    receipt.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=error):
        perform(prepared)
