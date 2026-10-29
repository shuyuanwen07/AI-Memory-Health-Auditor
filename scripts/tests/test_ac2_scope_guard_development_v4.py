"""Fail-closed advisory prototype; no warning is not proof of validity."""
import importlib.util
from pathlib import Path


def guard():
    path = Path('output/proposal-delivery/ac2-scope-guard-development-20261029/scope_guard_candidate_v4.py')
    spec = importlib.util.spec_from_file_location('scope_guard_v4', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_missing_source_requires_review_even_for_specific_question():
    warning = guard().issue('Which language does the Cedar project use?', [], [])
    assert warning and 'Source' in warning
    warning = guard().issue('Which language does the Cedar project use?', ['  '], [])
    assert warning and 'Source' in warning


def test_unknown_relationships_do_not_silently_become_no_relationships():
    warning = guard().issue('How should I handle this task?', ['A user described two related facts.'], None)
    assert warning and 'Relationship context' in warning


def test_present_empty_relations_differ_from_unknown_relations():
    assert guard().issue('Which language does the Cedar project use?', ['Cedar project uses Python.'], []) is None


def test_broad_stored_information_remains_advisory_even_with_source():
    warning = guard().issue("What is the user's recorded stored information for the Cedar project?",
                            ['Cedar project uses Python.', 'Cedar project starts Monday.'], [])
    assert warning
