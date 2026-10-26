"""Offline equivalence boundaries for the shared advisory-stage predicate."""
import itertools
import re

import pytest

from app.memory_agent.identity_applicability import identity_analysis_applicable
from app.target_ai.rule_based import _counting_question


@pytest.mark.parametrize(('question', 'expected'), [
    ('How many projects did I work on?', True),
    ('What is the number of events?', True),
    ('Give the count of accounts.', True),
    ('Are these the same event?', True),
    ('Was this the same occasion?', True),
    ('Is this the SAME PERSON?', True),
    ('Were they different events?', True),
    ('Did those events overlap?', True),
    ('Check identity.', True),
    ('Are these linked?', True),
    ('Which distinct events occurred?', True),
    ('Which accounts did I mention?', True),
    ('How many years have I worked?', False),
    ('How many days did it take?', False),
    ('What do I prefer?', False),
    ('Tell me about an unlinked fact.', False),
    ('What happened?\nQuestion date: How many events?', False),
])
def test_question_trigger_boundaries(question, expected):
    assert identity_analysis_applicable(
        question=question, selected_record_count=2,
        configuration='strong', identity_analysis='evidence_links') is expected


@pytest.mark.parametrize(('configuration', 'identity_analysis', 'count', 'expected'), [
    ('weak', 'evidence_links', 2, False),
    ('strong', 'off', 2, False),
    ('strong', 'evidence_links', 0, False),
    ('strong', 'evidence_links', 1, False),
    ('strong', 'evidence_links', 2, True),
    ('strong', 'evidence_links', 3, True),
])
def test_configuration_visibility_and_profile_boundaries(configuration, identity_analysis, count, expected):
    assert identity_analysis_applicable(
        question='How many projects did I work on?', selected_record_count=count,
        configuration=configuration, identity_analysis=identity_analysis) is expected


def test_shared_predicate_matches_original_inline_trigger():
    # This is the prior expression, kept here to detect semantic refactor drift.
    questions = ['How many projects?', 'How many years?', 'the same person',
                 'different event', 'overlap', 'identity', 'linked',
                 'distinct events', 'which accounts', 'favorite color',
                 'When?\nQuestion date: same event', '', 'HOW MANY FRIENDS?']
    for question, count, configuration, analysis in itertools.product(
            questions, range(4), ('weak', 'strong'), ('off', 'evidence_links')):
        relevant = _counting_question(question) or bool(re.search(
            r'\b(?:same\s+(?:event|occasion|person)|different\s+events?|overlap|identity|'
            r'linked|distinct\s+events?|which\s+accounts)\b', question, re.I))
        original = analysis != 'off' and configuration == 'strong' and count >= 2 and relevant
        assert identity_analysis_applicable(
            question=question, selected_record_count=count,
            configuration=configuration, identity_analysis=analysis) == original
