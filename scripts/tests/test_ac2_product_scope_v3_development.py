"""Regression checks for the offline advisory; these do not test generalisation."""
import importlib.util
from pathlib import Path


PATH = (Path(__file__).resolve().parents[2] /
        'output/proposal-delivery/ac2-product-scope-v3-development-20261029/scope_candidate.py')
spec = importlib.util.spec_from_file_location('scope_candidate_v3_development', PATH)
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


def warn(prompt, *, complete=True, dimension='accuracy', topic_count=1):
    return candidate.scope_warning(prompt, dimension, ['I prefer a paper map.'],
                                   source_complete=complete, related_topic_count=topic_count)


def test_missing_source_remains_fail_safe():
    assert 'missing' in warn('What is the recorded value?', complete=False).lower()


def test_unqualified_task_and_preference_require_review():
    assert warn('For the current task, what is the recorded requirement about event venue? State the relevant requirement only.')
    assert warn("What is the user's recorded preference? State the relevant fact only.")
    assert warn("What is the user's recorded communication style? State the relevant fact only.")


def test_existing_relation_gate_remains_in_force():
    assert warn('Which location applies now?', dimension='freshness')


def test_extra_warning_does_not_claim_a_single_fact_is_invalid():
    # Even a single real preference is conservatively flagged: the user can
    # assess it; this is a review warning, not a verdict or source mutation.
    assert warn("What is the user's recorded preference? State the relevant fact only.")
    assert warn('Where does the user live?') is None
