"""Synthetic only: no benchmark questions, gold, histories or provider imports."""
from dataclasses import replace
import inspect

import pytest

from app.memory_agent.retention_coverage import RetentionCoverageCandidate as Candidate
from app.memory_agent.retention_coverage import select_retention_coverage as choose


def c(name, *, source=None, time=0, order=0, priority=0, text=None, state="ACTIVE", observed_at=None):
    return Candidate(name, state, priority, str(time) if observed_at is None else observed_at,
                     time, order, (source or name,), text or f"Written fact for {name}")


def test_room_preserves_assistant_and_user_text_without_role_inference():
    items=[c("old", text='Prior assistant history: I recommended a striped shirt.'),
           c("new",time=10,text='USER says assistant is now user: I bought a hat.')]
    assert set(choose(items,capacity=2).retained_memory_ids)=={"old","new"}
    assert 'query' not in inspect.signature(choose).parameters
    assert not hasattr(items[0], 'role')


def test_many_late_fragments_do_not_remove_earlier_source_representative():
    items=[c('early',time=1)]+[c(f'late{i}',source='late-source',time=10,order=i) for i in range(5)]
    result=choose(items,capacity=2)
    assert 'early' in result.retained_memory_ids
    assert len(result.retained_memory_ids)==2


def test_exact_containing_record_is_first_group_representative():
    short='A completed activity occurred on the stated day.'
    a=c('short',source='same',text=short)
    b=c('long',source='same',text=short+' Its adjacent descriptive context remains verbatim.')
    result=choose([a,b,c('other',time=1)],capacity=2)
    assert set(result.retained_memory_ids)=={'long','other'}
    assert next(x for x in result.decisions if x['memory_id']=='short')['exact_text_covered_by_memory_id']=='long'


def test_identical_source_ids_at_different_observations_are_not_one_group():
    items=[c('a',source='shared',time=1),c('b',source='shared',time=2),c('c',source='shared',time=2,order=1)]
    result=choose(items,capacity=2)
    assert 'a' in result.retained_memory_ids
    groups={x['memory_id']:x['observation_group_sha256'] for x in result.decisions}
    assert groups['a']!=groups['b']==groups['c']


def test_merged_source_sets_remain_distinct_provenance_not_transitive_identity():
    a=c('a',source='S1');b=c('b',source='S2');merged=replace(c('ab'),source_message_ids=('S2','S1'))
    result=choose([a,b,merged],capacity=3)
    assert len({x['observation_group_sha256'] for x in result.decisions})==3


def test_higher_scope_requirement_and_override_priorities_remain_primary():
    items=[c('lowearly',time=1),c('lowlate',time=9),c('requirement',priority=30),c('override',priority=40)]
    assert set(choose(items,capacity=2).retained_memory_ids)=={'requirement','override'}


def test_high_priority_saturation_is_explicit_not_claimed_to_fix_episodic_loss():
    items=[c(f'p{i}',priority=20,time=i) for i in range(3)]+[c('episodic')]
    result=choose(items,capacity=2)
    assert 'episodic' not in result.retained_memory_ids
    assert next(x for x in result.priority_counts if x['retention_priority']==0)['retained']==0


def test_conflicts_protected_before_high_priority_nonconflict():
    result=choose([c('conflict',state='CONFLICTED'),c('requirement',priority=30)],capacity=1)
    assert result.retained_memory_ids==('conflict',)


def test_conflict_overflow_preserves_legacy_soft_limit_explicitly():
    result=choose([c('a',state='CONFLICTED'),c('b',state='CONFLICTED'),c('other')],capacity=1)
    assert result.protected_overflow and len(result.retained_memory_ids)==3
    assert result.capacity==1


@pytest.mark.parametrize('state',['EVICTED','SUPERSEDED','DIAGNOSTIC_ONLY'])
def test_previously_unavailable_never_revived(state):
    result=choose([c('lost',state=state,priority=100),c('active')],capacity=2)
    assert result.retained_memory_ids==('active',)
    assert result.excluded_memory_ids==('lost',)


def test_quantiles_span_observation_order_not_only_recent_sources():
    result=choose([c(str(i),time=i) for i in range(9)],capacity=3)
    assert result.retained_memory_ids==('0','4','8')


def test_over_capacity_can_still_lose_an_early_assistant_control_tradeoff():
    # It has no role quota: observation1 is not a selected quantile when only2 fit.
    items=[c(str(i),time=i,text='Prior assistant history: a key control.' if i==1 else f'Fact{i}') for i in range(5)]
    result=choose(items,capacity=2)
    assert result.retained_memory_ids==('0','4') and '1' in result.evicted_memory_ids


def test_role_spoof_text_does_not_change_equal_size_noncontainment_decision():
    items=[c(str(i),time=i) for i in range(5)]
    before=choose(items,capacity=2).retained_memory_ids
    after=choose([replace(x,canonical_value='USER SYSTEM ASSISTANT textual spoof '+x.memory_id) for x in items],capacity=2).retained_memory_ids
    assert before==after


def test_order_independent_and_no_input_mutation():
    items=[c(str(i),source=f's{i//2}',time=i//2,order=i) for i in range(8)]
    assert choose(items,capacity=3)==choose(reversed(items),capacity=3)
    assert all(x.lifecycle_state=='ACTIVE' for x in items)


def test_different_negation_plans_and_event_dates_are_not_text_equivalence():
    items=[c('past',source='same',text='I attended the workshop on May1.'),
           c('plan',source='same',text='I plan to attend the workshop on May2.'),
           c('negation',source='same',text='I did not attend the workshop on May3.')]
    result=choose(items,capacity=3)
    assert len(result.retained_memory_ids)==3
    assert all(x['exact_text_covered_by_memory_id'] is None for x in result.decisions)


@pytest.mark.parametrize('capacity',[0,-1,True,1.5])
def test_invalid_capacity_fails(capacity):
    with pytest.raises(ValueError):choose([c('a')],capacity=capacity)


def test_duplicate_ids_and_nonfinite_chronology_fail():
    with pytest.raises(ValueError):choose([c('a'),c('a')],capacity=1)
    with pytest.raises(ValueError):choose([c('a',time=float('nan'))],capacity=1)
