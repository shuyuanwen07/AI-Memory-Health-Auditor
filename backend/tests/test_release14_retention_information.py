"""Synthetic information-tiebreak experiments, not benchmark-answer fixtures."""
from dataclasses import replace

import pytest

from app.memory_agent.retention_coverage import RetentionCoverageCandidate as Candidate
from app.memory_agent.retention_coverage import (
    INFORMATION_VERSION, VERSION, _content_tokens, select_retention_coverage as choose,
)


def c(name, text, *, order, source='one', priority=0):
    return Candidate(name, 'ACTIVE', priority, '2030-05-01', 10, order, (source,), text)


def test_default_v1_recency_remains_unchanged_and_opt_in_is_versioned():
    items=[c('body','The Solstice Music Festival is in Clearhaven.',order=1),
           c('request',"I'd really love to know more about it; please give me helpful advice.",order=2)]
    old=choose(items,capacity=1)
    new=choose(items,capacity=1,representative_policy='content_information')
    assert old.version==VERSION and old.retained_memory_ids==('request',)
    assert new.version==INFORMATION_VERSION and new.retained_memory_ids==('body',)
    assert all('content_information_score'not in x for x in old.decisions)
    assert new.decisions[0]['content_information_score'] is not None


def test_short_specific_body_beats_long_repeated_discourse():
    items=[c('body','The named summit is Stonebridge2029.',order=1),
           c('late','Please help me. I would really love to know more. '*20,order=2)]
    assert choose(items,capacity=1,representative_policy='content_information').retained_memory_ids==('body',)


def test_three_clause_shoe_observation_keeps_specific_storage_location():
    items=[c('praise',"I've heard great things and they look amazing.",order=1),
           c('place','I keep my trainers in the hallway cupboard for storage.',order=2),
           c('request',"I'd love some more helpful suggestions, please.",order=3)]
    assert choose(items,capacity=1,representative_policy='content_information').retained_memory_ids==('place',)


def test_exact_coverage_and_novelty_still_precede_information():
    body='I attended the seminar on May12 at the named hall.'
    items=[c('short',body,order=1),c('context',body+' Its adjacent account remains verbatim.',order=2),
           c('unrelated','Quasar Zirconium Amber Solstice Stonebridge.',order=3)]
    result=choose(items,capacity=2,representative_policy='content_information')
    assert set(result.retained_memory_ids)=={'context','unrelated'}


def test_earliest_write_order_breaks_information_tie_within_observation():
    items=[c('early','Silver Cedar',order=1),c('late','Cedar Silver',order=2)]
    assert choose(items,capacity=1,representative_policy='content_information').retained_memory_ids==('early',)


def test_source_and_scope_allocations_do_not_depend_on_role_labels():
    assistant=c('assistant','Prior assistant source: I suggested a striped jacket.',order=1,source='a')
    user=c('user','A terse user statement.',order=2,source='b')
    result=choose([assistant,user],capacity=2,representative_policy='content_information')
    assert set(result.retained_memory_ids)=={'assistant','user'}
    requirement=replace(user,retention_priority=30)
    assert choose([assistant,requirement],capacity=1,representative_policy='content_information').retained_memory_ids==('user',)


def test_numbers_dates_and_arbitrary_names_survive_token_filter():
    tokens=_content_tokens('I attended on May 12 2030 with Qevra at Zorvyn.')
    assert {'may','12','2030','qevra','zorvyn'}<=tokens
    assert {'not','never','without'}<=_content_tokens('I did not attend, never completed it, without approval.')


def test_unknown_policy_fails_closed():
    with pytest.raises(ValueError):choose([c('x','Some written fact.',order=1)],capacity=1,representative_policy='anything_else')
