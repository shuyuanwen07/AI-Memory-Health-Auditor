"""Synthetic bounded source packing; relevance does not establish identity."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.memory_agent.store import SqlTargetMemoryStore
from app.schemas import MemoryStrategy
from app.schemas.target_profile import TargetMemoryProfile


NOW=datetime(2026,1,1,tzinfo=timezone.utc)


def row(i,source,strength,*,text=None,role='user',window=False,direct=1,day=0):
    return {'record':SimpleNamespace(id=f'private-{i}',canonical_value=text or f'Observed item number {i}.',
        source_message_ids=[source],observed_at=NOW+timedelta(days=day),write_order=i),
        'reason':'synthetic','relevance':direct,'direct_relevance':direct,'context_score':strength,
        'policy_score':20,'source_roles':{role},'temporal_window_match':window,'relationship_types':[]}


def store(records=2,budget=16000):
    return SqlTargetMemoryStore(None,profile=TargetMemoryProfile(retrieve_message_context=True,
        max_retrieved_records=records,context_character_budget=budget))


def choose(s,priority,question='Which records describe my observations?'):
    chosen=s._apply_profile(list(reversed(priority)),SimpleNamespace(prompt=question),MemoryStrategy.STRONG_RULE_BASED)
    assert len(chosen)<=s.profile.max_retrieved_records
    assert sum(len(s._render_context(r))+3 for r in chosen)<=s.profile.context_character_budget
    return chosen


def test_different_strengths_cannot_fragment_round_robin_source_coverage():
    a=[row(i,'SOURCE-A',100-i/7) for i in range(6)]
    b=row(9,'SOURCE-B',.2)
    s=store()
    got=s._source_coverage_priority([*a,b],SimpleNamespace(prompt='My observations?'))
    assert got[:2]==[a[0],b]
    assert {r['record'].source_message_ids[0] for r in choose(s,[*a,b])}=={'SOURCE-A','SOURCE-B'}


def test_substantive_hint_is_not_a_separate_source_bucket_or_identity_claim():
    a=row(1,'SOURCE-A',12,direct=3)
    another=row(2,'SOURCE-A',11,direct=2)
    another['topic_neighborhood']={'validation_scope':'retrieval_hint_only_not_fact_or_identity'}
    b=row(3,'SOURCE-B',.2,direct=1)
    assert choose(store(),[a,another,b])==[a,b]
    assert b['record'].source_message_ids==['SOURCE-B']


def test_original_incoming_order_still_breaks_equal_discrete_tier_ties():
    first=row(1,'A',1)
    later=row(2,'B',100)
    assert store()._source_coverage_priority([first,later],SimpleNamespace(prompt='My records?'))==[first,later]


def test_temporal_window_is_finite_priority_and_does_not_rewrite_source_dates():
    outside=row(1,'A',100,window=False,day=-100)
    inside=row(2,'B',.1,window=True)
    other_inside=row(3,'C',.01,window=True)
    saved=outside['record'].observed_at
    chosen=choose(store(),[outside,inside,other_inside],'Which observations were in the last week?')
    assert chosen==[inside,other_inside]
    assert outside['record'].observed_at==saved and not outside['temporal_window_match']
    assert 'profile_record_limit_excluded' in outside['reason']


def test_character_budget_skip_does_not_truncate_or_force_an_oversized_source():
    oversized=row(1,'A',100,text='A continuous original source passage. '*200)
    compact=row(2,'B',.1,text='A compact original observation.')
    got=choose(store(budget=300),[oversized,compact])
    assert got==[compact]
    assert len(oversized['record'].canonical_value)>1000
    assert 'profile_character_limit_excluded' in oversized['reason']


def test_full_provenance_tuple_and_observation_time_remain_distinct():
    first=row(1,'A',10,text='Observed the same activity.')
    later=row(2,'A',9,text='Observed the same activity.',day=1)
    another=row(3,'B',8,text='Observed the same activity.')
    got=choose(store(records=3),[first,later,another])
    assert got==[first,another,later]
    assert len(got)==3


def test_explicit_assistant_recall_retains_shared_intent_without_new_advice_bias():
    assistant=row(1,'A',.1,role='assistant',text='Prior assistant suggestion about a route.')
    user=row(2,'B',100,text='I recorded a route preference.')
    assert choose(store(records=1),[user,assistant],'Remind me what we discussed last time about my route.')==[assistant]
    assert choose(store(records=1),[assistant,user],'Can you suggest a route for my next trip?')==[user]


def test_packing_never_reads_original_history_or_evaluator_fields():
    class QuestionOnly:
        prompt='What were my observations?'
        def __getattr__(self,name):raise AssertionError('Unexpected input access: '+name)
    candidates=[row(1,'A',100),row(2,'A',99),row(3,'B',.1)]
    s=store()
    assert s._source_coverage_priority(candidates,QuestionOnly())[:2]==[candidates[0],candidates[2]]


def test_explicit_relationship_policy_outside_window_precedes_ordinary_window_hint():
    outside=row(1,'A',.1,window=False)
    outside.update(policy_score=60,relationship_types=['CONFLICT'])
    inside=row(2,'B',100,window=True)
    got=choose(store(records=1),[inside,outside],'Which of my notes conflict?')
    assert got==[outside]
    assert outside['temporal_window_match'] is False
    assert outside['record'].observed_at==NOW


def test_personal_indirect_user_attribution_precedes_direct_assistant_support():
    assistant=row(1,'A',100,role='assistant',direct=3)
    indirect=row(2,'B',.1,role='user',direct=0)
    indirect['relevance']=.5
    assert choose(store(records=1),[assistant,indirect],'What preference did I record?')==[indirect]


def test_explicit_assistant_recall_attribution_precedes_direct_user_support():
    user=row(1,'A',100,direct=3)
    assistant=row(2,'B',.1,role='assistant',direct=0)
    assistant['relevance']=.5
    assert choose(store(records=1),[user,assistant],'Remind me what we discussed last time about my notes.')==[assistant]


def test_unknown_intent_does_not_acquire_a_default_user_role_preference():
    assistant=row(1,'A',1,role='assistant')
    user=row(2,'B',100,role='user')
    assert choose(store(records=1),[assistant,user],'Which notes were recorded?')==[assistant]


def test_unknown_or_mixed_source_attribution_is_not_fabricated():
    mixed=row(1,'A',1)
    mixed['source_roles']={'user','assistant'}
    unknown=row(2,'B',100)
    unknown['source_roles']=set()
    got=choose(store(),[mixed,unknown],'Which notes were recorded?')
    assert got==[mixed,unknown]
    assert mixed['source_roles']=={'user','assistant'} and unknown['source_roles']==set()


import pytest


@pytest.mark.parametrize('record_limit,character_limit',[(50,16000),(100,32000)])
def test_legacy_and_prospective_shared_upper_bounds_are_enforced_without_source_merges(record_limit,character_limit):
    candidates=[row(i,f'SOURCE-{i}',1,text='A short original observation.')for i in range(130)]
    s=store(records=record_limit,budget=character_limit)
    got=choose(s,candidates)
    assert len(got)==record_limit
    assert len({tuple(item['record'].source_message_ids)for item in got})==record_limit
    assert all(item['record'].canonical_value=='A short original observation.'for item in got)
    assert all(item['record'].observed_at==NOW for item in got)
