"""Scope checks remain advisory and cannot certify a question as valid."""
import importlib.util
from pathlib import Path


def guard(version):
    path = Path('output/proposal-delivery/ac2-scope-guard-development-20261029') / f'scope_guard_candidate_{version}.py'
    spec = importlib.util.spec_from_file_location('guard_' + version, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generic_stored_information_with_suffix_prompts_review():
    prompt = "What is the user's recorded stored information for the user?"
    source = ['I live in Sydney.', 'I work at a school.']
    assert guard('v2').issue(prompt, source) is None  # frozen historical gap
    assert guard('v3').issue(prompt, source) is not None


def test_generic_prompt_with_named_scope_still_needs_review():
    prompt = "What is the user's recorded stored information for the Cedar project?"
    source = ['The Cedar project uses Python.', 'The Cedar project starts on Monday.']
    assert guard('v3').issue(prompt, source) is not None


def test_specific_question_is_not_automatically_flagged():
    prompt = "Which language does the Cedar project use?"
    assert guard('v3').issue(prompt, ['The Cedar project uses Python.']) is None
