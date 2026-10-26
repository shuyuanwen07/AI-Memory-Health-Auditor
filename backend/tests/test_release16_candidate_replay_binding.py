"""Candidate v9 replay bindings cannot be bypassed by version metadata."""
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
    return {'prompt_template_version': 'target-identity-evidence-v9-single-relation-pair',
            'status': 'completed', 'raw_model_draft': {'quotes': []},
            **{key: {'binding': key} for key in KEYS}}


@pytest.mark.parametrize('failed', [False, True])
def test_v9_complete_and_rejected_drafts_replay_with_all_bindings(compare, failed):
    saved = observation()
    if failed:
        saved.update(status='failed', hydrated_quote_draft=None, candidate_selection_receipt=None)
    assert compare(saved, copy.deepcopy(saved)) is True


@pytest.mark.parametrize('key', KEYS)
@pytest.mark.parametrize('mutation', ['delete', 'tamper', 'delete_both'])
def test_v9_all_four_bindings_are_mandatory_and_exact(compare, key, mutation):
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


@pytest.mark.parametrize('version', [None, '', 'target-identity-evidence-v7-exact-span-identity-scope',
                                   'target-identity-evidence-v8-candidate-selection',
                                   'target-identity-evidence-v11-unreviewed'])
def test_v9_version_change_is_rejected_in_both_directions(compare, version):
    saved = observation()
    changed = copy.deepcopy(saved)
    changed['prompt_template_version'] = version
    with pytest.raises(AssertionError, match='version differs'):
        compare(saved, changed)
    with pytest.raises(AssertionError, match='version differs'):
        compare(changed, saved)


@pytest.mark.parametrize('version', [None, '', 'target-identity-evidence-v7-exact-span-identity-scope',
                                   'target-identity-evidence-v11-unreviewed'])
def test_candidate_fields_with_two_unsupported_versions_cannot_silently_skip(compare, version):
    saved = observation()
    saved['prompt_template_version'] = version
    with pytest.raises(AssertionError, match='Unsupported candidate observation version'):
        compare(saved, copy.deepcopy(saved))


def test_v9_version_requires_bindings_even_when_both_objects_omit_all_four(compare):
    saved = observation()
    for key in KEYS:
        del saved[key]
    with pytest.raises(AssertionError, match='Missing candidate selection evidence'):
        compare(saved, copy.deepcopy(saved))


def test_unknown_candidate_version_without_any_fields_cannot_be_treated_as_legacy(compare):
    saved = {'prompt_template_version': 'target-identity-evidence-v11-unreviewed', 'status': 'failed'}
    with pytest.raises(AssertionError, match='Unsupported candidate observation version'):
        compare(saved, copy.deepcopy(saved))
