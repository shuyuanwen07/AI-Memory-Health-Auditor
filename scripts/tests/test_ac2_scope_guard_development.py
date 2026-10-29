"""Tests for the offline candidate, not for the frozen production generator."""
import importlib.util
from pathlib import Path


def _candidate():
    p = Path('output/proposal-delivery/ac2-scope-guard-development-20261029/scope_guard_candidate.py')
    spec = importlib.util.spec_from_file_location('ac2_scope_guard', p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generic_accuracy_abstains_without_revealing_answer():
    guard = _candidate()
    assert guard.issue("What is the user's recorded stored information? State the relevant fact only.",
                       ['The pantry uses a canvas cart.'])
    assert guard.issue('What is recorded about the pantry?', ['The pantry uses a canvas cart.']) is None


def test_generated_project_must_be_an_explicit_proper_source_label():
    guard = _candidate()
    prompt = "What is the user's current task for the Shared project?"
    assert guard.issue(prompt, ['We use a shared project folder for client work.'])
    assert guard.issue('Which database for the Cedar project?', ['Project Cedar uses PostgreSQL.']) is None
    assert guard.issue('Which database for the Cedar project?', ['The Cedar backend uses PostgreSQL.']) is None


def test_ambiguous_relationship_types_trigger_review_only_when_multiple():
    guard = _candidate()
    prompt = "Two recorded constraints about the user's stored information conflict. What should be clarified?"
    assert guard.issue(prompt, [], ['CONFLICT', 'CONFLICT'])
    assert guard.issue(prompt, [], ['CONFLICT']) is None
    prompt = 'For communication style, how should its task-specific requirement relate to the general preference?'
    assert guard.issue(prompt, [], ['CONTEXTUAL_OVERRIDE', 'CONTEXTUAL_OVERRIDE'])
    assert guard.issue(prompt, [], ['CONTEXTUAL_OVERRIDE']) is None


def test_specific_project_scope_is_not_rejected_only_for_multiple_overrides():
    guard = _candidate()
    prompt = 'For the Cedar project, how should its task-specific requirement relate to the preference?'
    assert guard.issue(prompt, ['Project Cedar uses Java.'], ['CONTEXTUAL_OVERRIDE'] * 2) is None
