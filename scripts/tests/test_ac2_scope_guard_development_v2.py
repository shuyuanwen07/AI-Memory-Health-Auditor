"""Regression tests for the scope-review candidate; no production mutation."""
import importlib.util
from pathlib import Path


def _candidate():
    p = Path('output/proposal-delivery/ac2-scope-guard-development-20261029/scope_guard_candidate_v2.py')
    spec = importlib.util.spec_from_file_location('ac2_scope_guard_v2', p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repeated_entity_may_need_an_attribute():
    guard = _candidate()
    prompt = 'What is recorded about The pantry? State the relevant fact only.'
    assert guard.issue(prompt, ['The pantry uses a cart.', 'The pantry labels a shelf.'])
    assert guard.issue(prompt, ['The pantry uses a cart.']) is None


def test_multiple_overrides_make_generic_requirement_and_preference_unclear():
    guard = _candidate()
    relationships = ['CONTEXTUAL_OVERRIDE', 'CONTEXTUAL_OVERRIDE']
    assert guard.issue('For the current task, what is the recorded requirement about working arrangement?', [], relationships)
    assert guard.issue("What is the user's recorded preference?", [], relationships)
    assert guard.issue("What is the user's recorded communication style?", [], relationships)
    assert guard.issue("What is the user's recorded preference?", [], ['CONTEXTUAL_OVERRIDE']) is None


def test_explicit_scope_is_not_flagged_merely_for_multiple_overrides():
    guard = _candidate()
    prompt = 'For the current task, what is the recorded requirement for the Cedar project?'
    assert guard.issue(prompt, ['Project Cedar uses Java.'], ['CONTEXTUAL_OVERRIDE'] * 2) is None


def test_v1_fixes_are_preserved():
    guard = _candidate()
    assert guard.issue("What is the user's recorded stored information?", [])
    assert guard.issue('What is the current task for the Shared project?', ['a shared project folder'])
    assert guard.issue('Two stored information constraints conflict.', [], ['CONFLICT', 'CONFLICT'])
