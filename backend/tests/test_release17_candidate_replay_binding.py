"""Same selection contract in v10 still requires all four actual bindings."""
import copy
import importlib
from pathlib import Path

import pytest


KEYS = ('candidate_catalog', 'raw_model_selection', 'hydrated_quote_draft',
        'candidate_selection_receipt')


@pytest.fixture
def compare(monkeypatch):
    scripts = Path('/scripts') if Path('/scripts').is_dir() else Path(__file__).resolve().parents[2] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    return importlib.import_module('replay_stability_study').compare_identity_observation


def observation():
    return {'prompt_template_version': 'target-identity-evidence-v10-source-explicitness',
            'status': 'completed', 'raw_model_draft': {'quotes': []},
            **{key: {'binding': key} for key in KEYS}}


@pytest.mark.parametrize('failed', [False, True])
def test_v10_actual_valid_or_rejected_selection_remains_replayable(compare, failed):
    saved = observation()
    if failed:
        saved.update(status='failed', hydrated_quote_draft=None, candidate_selection_receipt=None)
    assert compare(saved, copy.deepcopy(saved)) is True


@pytest.mark.parametrize('key', KEYS)
@pytest.mark.parametrize('mutation', ['delete', 'tamper', 'delete_both'])
def test_v10_missing_or_changed_selection_binding_rejected_both_directions(compare, key, mutation):
    saved = observation()
    changed = copy.deepcopy(saved)
    if mutation.startswith('delete'):
        del changed[key]
    else:
        changed[key] = {'tampered': True}
    if mutation == 'delete_both':
        del saved[key]
    with pytest.raises(AssertionError):
        compare(saved, changed)
    with pytest.raises(AssertionError):
        compare(changed, saved)


@pytest.mark.parametrize('version', [None, '', 'target-identity-evidence-v7-legacy',
                                   'target-identity-evidence-v8-candidate-selection',
                                   'target-identity-evidence-v9-single-relation-pair',
                                   'target-identity-evidence-v11-unreviewed'])
def test_v10_version_cannot_change_in_either_direction(compare, version):
    saved = observation()
    changed = copy.deepcopy(saved)
    changed['prompt_template_version'] = version
    with pytest.raises(AssertionError):
        compare(saved, changed)
    with pytest.raises(AssertionError):
        compare(changed, saved)


@pytest.mark.parametrize('fields', [False, True])
def test_unreviewed_future_version_fails_closed_with_or_without_selection_fields(compare, fields):
    saved = observation() if fields else {}
    saved['prompt_template_version'] = 'target-identity-evidence-v11-unreviewed'
    with pytest.raises(AssertionError, match='Unsupported candidate observation version'):
        compare(saved, copy.deepcopy(saved))
