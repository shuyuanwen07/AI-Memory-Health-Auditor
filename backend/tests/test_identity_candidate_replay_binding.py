"""Offline replay must cover selection evidence, including rejected drafts."""
import copy
import importlib
from pathlib import Path

import pytest


@pytest.fixture
def compare(monkeypatch):
    scripts = Path('/scripts') if Path('/scripts/replay_stability_study.py').is_file() else Path(__file__).resolve().parents[2] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    return importlib.import_module('replay_stability_study').compare_identity_observation


def observation():
    return {'prompt_template_version': 'target-identity-evidence-v8-candidate-selection',
            'status': 'completed', 'raw_model_draft': {'quotes': []},
            'candidate_catalog': {'catalog_sha256': 'snapshot-a'},
            'raw_model_selection': {'quotes': []},
            'hydrated_quote_draft': {'quotes': []},
            'candidate_selection_receipt': {'bindings': []}}


def test_complete_candidate_observation_matches(compare):
    saved = observation()
    assert compare(saved, copy.deepcopy(saved)) is True


@pytest.mark.parametrize('field', ['candidate_catalog', 'raw_model_selection',
                                 'hydrated_quote_draft', 'candidate_selection_receipt'])
@pytest.mark.parametrize('mutation', ['delete', 'tamper'])
def test_candidate_observation_missing_or_tampered_is_rejected(compare, field, mutation):
    saved = observation()
    changed = copy.deepcopy(saved)
    if mutation == 'delete':
        del changed[field]
    else:
        changed[field] = {'tampered': True}
    with pytest.raises(AssertionError):
        compare(saved, changed)
    with pytest.raises(AssertionError):
        compare(changed, saved)


def test_rejected_selection_none_bindings_are_still_required(compare):
    saved = observation()
    saved.update(status='failed', hydrated_quote_draft=None, candidate_selection_receipt=None)
    assert compare(saved, copy.deepcopy(saved)) is True
    changed = copy.deepcopy(saved)
    del changed['candidate_selection_receipt']
    with pytest.raises(AssertionError):
        compare(saved, changed)


def test_candidate_version_downgrade_is_rejected(compare):
    saved = observation()
    changed = copy.deepcopy(saved)
    changed['prompt_template_version'] = 'target-identity-evidence-v7-exact-span-identity-scope'
    with pytest.raises(AssertionError):
        compare(saved, changed)


def test_legacy_observation_does_not_invent_selection_evidence(compare):
    legacy = {'prompt_template_version': 'target-identity-evidence-v7-exact-span-identity-scope',
              'status': 'completed', 'raw_model_draft': {'quotes': []}}
    assert compare(legacy, copy.deepcopy(legacy)) is False


def test_entire_candidate_observation_sidecar_cannot_be_removed(compare):
    module=importlib.import_module('replay_stability_study')
    saved=observation()
    with pytest.raises(AssertionError):module.compare_identity_observations([], [saved])
    with pytest.raises(AssertionError):module.compare_identity_observations([{'last_observation':saved}], [])
    module.compare_identity_observations([], [])
    module.compare_identity_observations([{'last_observation':saved}], [copy.deepcopy(saved)])
