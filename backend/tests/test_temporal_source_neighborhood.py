"""Temporal retrieval uses bounded stored context, never evaluation annotations."""
from datetime import datetime, timezone
from types import SimpleNamespace
import json

from app.memory_agent.store import SqlTargetMemoryStore, _retrieval_tokens
from app.schemas.target_profile import TargetMemoryProfile


def row(mid, relevance, points, *, eligible=True, value='I reviewed the hobby schedule.'):
    return dict(record=SimpleNamespace(id=mid, source_message_ids=[mid], canonical_value=value,
                                      observed_at=datetime(2026, 4, 20, tzinfo=timezone.utc), write_order=1),
                relevance=relevance, direct_relevance=relevance, policy_score=20,
                source_context_points=points, eligible=eligible, reason='direct',
                test_prompt='When did I complete this hobby task?')


def test_temporal_source_expansion_is_one_hop_same_time_bounded_and_available_only():
    a=row('A',3,[(10,'T')]);b=row('B',0,[(15,'T')]);c=row('C',0,[(20,'T')])
    other_time=row('D',0,[(11,'U')]);evicted=row('E',0,[(12,'T')],eligible=False)
    SqlTargetMemoryStore._include_temporal_neighborhood([a,b,c,other_time,evicted],a['test_prompt'])
    assert 0 < b['relevance'] < 3 and 'bounded_temporal_source_neighborhood' in b['reason']
    assert c['relevance']==other_time['relevance']==evicted['relevance']==0


def test_timestamp_and_position_must_belong_to_the_same_source_point():
    a=row('A',3,[(1,'T'),(100,'U')]);b=row('B',0,[(100,'T')])
    SqlTargetMemoryStore._include_temporal_neighborhood([a,b],a['test_prompt'])
    assert b['relevance']==0


def test_query_window_prioritizes_date_but_does_not_assert_an_event_date():
    prompt='What hobby work did I do one week ago?\nQuestion date: 2026-04-27T18:00:00+00:00'
    a=row('A',2,[(10,'T')],value='I was thinking about my hobby work today.')
    SqlTargetMemoryStore._include_temporal_neighborhood([a],prompt)
    assert a['temporal_window_match'] is True
    assert a['record'].canonical_value=='I was thinking about my hobby work today.'


def test_rendered_relative_reference_preserves_original_content_and_budget_cost():
    store=object.__new__(SqlTargetMemoryStore)
    store.profile=TargetMemoryProfile(retrieve_message_context=True)
    a=row('A',2,[(10,'T')],value='I reviewed my notes about three days ago.')
    supplied=json.loads(store._render_context(a))
    assert supplied['content']==a['record'].canonical_value
    assert supplied['relative_time_reference_only'][0]['resolved_start']=='2026-04-17'
    assert 'event_date' not in supplied
    store.profile=TargetMemoryProfile(retrieve_message_context=False)
    assert store._render_context(a)==a['record'].canonical_value


def test_compound_parts_can_match_without_changing_fact_tokens():
    assert 'ceramic' in _retrieval_tokens('ceramic-related',normalise_inflections=True)
    assert 'ceramic-related' in _retrieval_tokens('ceramic-related',normalise_inflections=True)


def test_generic_attendance_does_not_make_an_unrelated_event_a_concert_match():
    store=object.__new__(SqlTargetMemoryStore)
    store.profile=TargetMemoryProfile(retrieve_message_context=True)
    from app.schemas import TestCase as Case
    test=Case(test_id='T-TIME',run_id='R-TIME',dimension='accuracy',
        prompt='What is the order of the concerts and musical events I attended?',
        expected_behavior='not visible to retrieval',supporting_memory_ids=[],generator_version='test')
    record=SimpleNamespace(canonical_value='I attended a work seminar.',lifecycle_state='ACTIVE')
    assert store._candidate(record,test,[])['relevance']==0


def test_rare_query_names_outweigh_frequent_generic_terms():
    named=row('N',1,[(10,'T')]);named['_query_terms']={'parent','sora'};named['_memory_terms']={'sora','twins'}
    generic=[row(f'G{i}',1,[(100+i,'U')]) for i in range(12)]
    for item in generic:
        item['_query_terms']={'parent','sora'};item['_memory_terms']={'parent'}
    SqlTargetMemoryStore._include_temporal_neighborhood([named,*generic],'Who became a parent first, Sora or Jules?')
    assert named['direct_context_score']>generic[0]['direct_context_score']


def test_shared_entities_recover_both_birth_and_birthday_context_without_cherry_picking():
    anchor=row('A',1,[(20,'T')],value='Sora is caring for Nia and Theo.')
    birth=row('B',0,[(12,'T')],value='Nia and Theo were born in February.')
    birthday=row('C',0,[(14,'T')],value='Nia and Theo have a birthday celebration soon.')
    for item in [anchor,birth,birthday]:item['_query_terms']={'sora'}
    anchor['_memory_terms']={'sora','nia','theo'}
    birth['_memory_terms']={'nia','theo','born','february'}
    birthday['_memory_terms']={'nia','theo','birthday'}
    SqlTargetMemoryStore._include_temporal_neighborhood([anchor,birth,birthday],'Who became a parent first, Sora or Jules?')
    assert birth['relevance']>0 and birthday['relevance']>0
    assert birth['record'].canonical_value=='Nia and Theo were born in February.'
    assert birthday['record'].canonical_value=='Nia and Theo have a birthday celebration soon.'


def test_personal_event_history_uses_user_sources_but_explicit_assistant_recall_remains_available():
    def items():
        user=row('U',1,[(10,'T')]);user['source_roles']={'user'}
        assistant=row('A',1,[(11,'T')]);assistant['source_roles']={'assistant'}
        return user,assistant
    user,assistant=items()
    SqlTargetMemoryStore._include_temporal_neighborhood([user,assistant],'When did I visit the gallery?')
    assert not assistant['eligible'] and user['eligible']
    user,assistant=items()
    SqlTargetMemoryStore._include_temporal_neighborhood([user,assistant],'When did you recommend that gallery to me?')
    assert assistant['eligible']


def test_assistant_topic_can_locate_a_user_event_without_becoming_event_evidence():
    user=row('U',0,[(10,'T')],value='I saw the band live yesterday.')
    user['source_roles']={'user'}
    assistant=row('A',2,[(12,'T')],value='How was the concert?')
    assistant['source_roles']={'assistant'}
    SqlTargetMemoryStore._include_temporal_neighborhood([user,assistant],'What concerts did I attend last month?')
    assert user['eligible'] and user['relevance']>0
    assert not assistant['eligible']


def test_this_year_event_count_does_not_retrieve_unrelated_yearly_health_fact():
    from app.schemas import TestCase as Case
    store=object.__new__(SqlTargetMemoryStore)
    store.profile=TargetMemoryProfile(retrieve_message_context=True)
    test=Case(test_id='COUNT-YEAR',run_id='COUNT-RUN',dimension='accuracy',
        prompt='How many exhibitions have I attended this year?',expected_behavior='private',
        supporting_memory_ids=[],generator_version='test')
    record=SimpleNamespace(canonical_value='I have checked my glucose weekly since last year.',lifecycle_state='ACTIVE')
    assert store._candidate(record,test,[])['relevance']==0
    record.canonical_value='I attended a sculpture exhibition.'
    assert store._candidate(record,test,[])['relevance']>0


def test_weekend_candidates_survive_delivery_and_do_not_become_one_continuous_window():
    store = object.__new__(SqlTargetMemoryStore)
    store.profile = TargetMemoryProfile(retrieve_message_context=True)
    item = row('W', 2, [(10, 'T')], value='I recalled the workshop last weekend.')
    item['record'].observed_at = datetime(2025, 3, 9, tzinfo=timezone.utc)
    reference = json.loads(store._render_context(item))['relative_time_reference_only'][0]
    assert reference['range_kind'] == 'candidate_envelope'
    assert reference['ambiguity'] == 'weekend_day_last_weekend_reference'
    assert len(reference['candidate_ranges']) == 2
    assert 'intervening weekdays are not candidate dates' in reference['caution']
    assert 'event_date' not in reference


def test_query_weekend_excludes_intervening_weekday_observation():
    prompt = 'What work did I review last weekend?\nQuestion date: 2025-03-09T12:00:00+00:00'
    wednesday = row('W', 2, [(10, 'T')])
    wednesday['record'].observed_at = datetime(2025, 3, 5, tzinfo=timezone.utc)
    sunday = row('S', 2, [(20, 'U')])
    sunday['record'].observed_at = datetime(2025, 3, 2, tzinfo=timezone.utc)
    SqlTargetMemoryStore._include_temporal_neighborhood([wednesday, sunday], prompt)
    assert not wednesday.get('temporal_window_match', False)
    assert sunday['temporal_window_match'] is True


def test_source_weekend_envelope_does_not_match_a_weekday_query():
    prompt = 'What work did I review four days ago?\nQuestion date: 2025-03-09T12:00:00+00:00'
    item = row('W', 2, [(10, 'T')], value='I recalled the workshop last weekend.')
    item['record'].observed_at = datetime(2025, 3, 9, tzinfo=timezone.utc)
    SqlTargetMemoryStore._include_temporal_neighborhood([item], prompt)
    assert not item.get('temporal_window_match', False)
