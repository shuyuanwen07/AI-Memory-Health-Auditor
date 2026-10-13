"""A recomputed file checksum alone is not evidence of a server match."""
from copy import deepcopy
import pytest

from app.models import TargetResponseModel, AuditRunModel
from app.services.formal_study_summary import snapshot_digest
from test_reviewed_acceptance import study as reviewed_study

study = reviewed_study


def export(client, run):
    result = client.get(f'/api/v1/research/formal/{run}/study-summary')
    assert result.status_code == 200, result.text
    return result.json()


def verify(client, run, data):
    result = client.post(f'/api/v1/research/formal/{run}/verify-summary', json={'summary':data})
    assert result.status_code == 200, result.text
    return result.json()


def resign_file(data):
    content = dict(data)
    content.pop('receipt_sha256')
    data['receipt_sha256'] = snapshot_digest(content)


def test_original_partial_export_matches_without_creating_new_evidence(study):
    client, factory, run, _ = study
    data = export(client, run)
    before = data['provenance']['evidence_sha256']
    checked = verify(client, run, data)
    assert checked['matches_current_snapshot'] is True
    assert 'does not certify complete runs' in checked['message']
    assert export(client, run)['provenance']['evidence_sha256'] == before
    with factory() as db:
        assert db.get(AuditRunModel, run).status == 'COMPLETED'


@pytest.mark.parametrize('change,status', [
    ('without_rehash','file_checksum_mismatch'),
    ('results_with_rehash','result_values_differ'),
    ('plan_with_rehash','different_plan'),
    ('analysis_with_rehash','analysis_changed'),
])
def test_changed_file_cannot_claim_match_even_with_a_recomputed_checksum(study, change, status):
    client, _, run, _ = study
    data = deepcopy(export(client, run))
    if change in {'without_rehash', 'results_with_rehash'}:
        data['conditions'][0]['mean_percent'] = 99
    elif change == 'plan_with_rehash':
        data['provenance']['frozen_plan_sha256'] = '0' * 64
    else:
        data['provenance']['analysis_runtime_source_sha256'] = '0' * 64
    if change != 'without_rehash':
        resign_file(data)
    checked = verify(client, run, data)
    assert checked['status'] == status
    assert checked['matches_current_snapshot'] is False


def test_old_export_reports_saved_evidence_changed_after_an_answer_update(study):
    client, factory, run, _ = study
    old = export(client, run)
    with factory() as db:
        db.get(TargetResponseModel, 'NEW-R0').response_text += ' Updated engineering fixture.'
        db.commit()
    checked = verify(client, run, old)
    assert checked['status'] == 'saved_evidence_changed'
    assert checked['matches_current_snapshot'] is False


def test_unsupported_input_never_means_verified(study):
    client, _, run, _ = study
    checked = verify(client, run, {})
    assert checked['status'] == 'unsupported_file'
    assert checked['matches_current_snapshot'] is False
    assert client.post(f'/api/v1/research/formal/{run}/verify-summary', json={'summary':[]}).status_code == 422
