"""Content scoring and explicit finite-tier policy tradeoff observations.

Original release14 goals are retained as descriptive receipts, not silently
claimed as recovered. Continuous strength cannot bypass finite source tiers.
"""
import json
from types import SimpleNamespace

from app.memory_agent.store import SqlTargetMemoryStore
from app.schemas import MemoryStrategy
from app.schemas.target_profile import TargetMemoryProfile


def row(i, terms, *, query=("planetarium", "night", "tour"), role="user", source=None):
    return dict(record=SimpleNamespace(id=str(i), canonical_value=" ".join(terms),
        observed_at=None, write_order=i, source_message_ids=[source or str(i)]),
        eligible=True, _query_terms=set(query), _memory_terms=set(terms),
        relevance=len(set(query) & set(terms)), direct_relevance=len(set(query) & set(terms)),
        reason="test", source_roles={role}, policy_score=20, relationship_types=[])


def store():
    return SqlTargetMemoryStore(None, profile=TargetMemoryProfile(
        retrieve_message_context=True, max_retrieved_records=2, context_character_budget=16000))


def describe_tradeoff(scenario, original_goal_met, wanted, selected):
    print(json.dumps({'policy_tradeoff': scenario, 'original_release14_goal_met': original_goal_met,
        'wanted_records': [row['record'].id for row in wanted],
        'selected_records': [row['record'].id for row in selected],
        'lost_wanted_records': [row['record'].id for row in wanted if row not in selected]}))


def test_strong_assistant_vs_personal_matches_descriptive_policy_tradeoff():
    weak = [row(i, ["tour", f"other{i}"]) for i in range(55)]
    evidence = row(100, ["planetarium", "night", "tour"], role="assistant")
    items = [*weak, evidence]
    s = store()
    s._annotate_lexical_strength(items)
    selected = s._apply_profile(s._select(items, MemoryStrategy.STRONG_RULE_BASED),
        SimpleNamespace(prompt="Remind me of my planetarium night tour."), MemoryStrategy.STRONG_RULE_BASED)
    describe_tradeoff('strong_assistant_vs_personal_without_explicit_history_intent',
                      evidence in selected, [evidence], selected)
    assert evidence['record'].canonical_value == 'planetarium night tour'
    assert evidence['direct_context_score'] > max(item['direct_context_score'] for item in weak)
    assert len(selected) <= 2


def test_complementary_same_message_fragment_inherits_bounded_content_score():
    anchor = row(1, ["planetarium", "night", "tour"], source="A")
    complement = row(2, ["booking", "closes", "Thursday"], source="A")
    weak = [row(i, ["tour", f"other{i}"]) for i in range(3, 58)]
    items = [anchor, complement, *weak]
    s = store()
    s._annotate_lexical_strength(items)
    s._include_message_context(items)
    assert complement["direct_relevance"] == 0
    assert complement["context_score"] == anchor["direct_context_score"] * .85
    selected = s._apply_profile(s._select(items, MemoryStrategy.STRONG_RULE_BASED),
        SimpleNamespace(prompt="Tell me about the planetarium night tour."), MemoryStrategy.STRONG_RULE_BASED)
    describe_tradeoff('indirect_complement_vs_other_direct_sources',
                      anchor in selected and complement in selected, [anchor, complement], selected)
    assert anchor in selected
    assert complement in s._source_coverage_priority(items, SimpleNamespace(prompt='My tour?'))


def test_frequency_score_uses_only_eligible_private_records():
    good = row(1, ["planetarium", "night"])
    unavailable = row(2, ["planetarium"])
    unavailable["eligible"] = False
    SqlTargetMemoryStore._annotate_lexical_strength([good, unavailable])
    assert good["direct_context_score"] == 2
    assert "context_score" not in unavailable


def test_explicit_relationship_policy_remains_a_priority():
    general = row(1, ["planetarium", "night", "tour"])
    policy = row(2, ["tour"])
    policy["policy_score"] = 60
    items = [general, policy]
    s = store()
    s._annotate_lexical_strength(items)
    assert s._source_coverage_priority(items, SimpleNamespace(prompt="My tour?"))[0] is policy


def test_outside_window_strength_descriptive_policy_tradeoff_preserves_candidate():
    # A retained old observation may need to be supplied to explain why it
    # does not establish the requested period. Its date is never rewritten.
    outside = row(100, ["planetarium", "night", "tour"])
    outside["temporal_window_match"] = False
    weak_inside = [row(i, ["tour", f"other{i}"]) for i in range(55)]
    for item in weak_inside:
        item["temporal_window_match"] = True
    items = [*weak_inside, outside]
    s = store()
    s._annotate_lexical_strength(items)
    got = s._source_coverage_priority(items, SimpleNamespace(prompt="My planetarium night tour last week?"))
    describe_tradeoff('outside_window_strength_does_not_bypass_window_tier',
                      got[0] is outside, [outside], got[:2])
    assert len(got) == len(items) and outside in got
    assert outside["temporal_window_match"] is False


def test_indirect_user_topic_hint_descriptive_policy_tradeoff_preserves_candidate():
    experience = row(1, ["telescope", "successful", "trial"], query=("planetarium",))
    experience.update(relevance=.5, context_score=2, topic_neighborhood={"validation_scope":"retrieval_hint_only_not_fact_or_identity"})
    assistant = row(2, ["planetarium", "night", "tour"], role="assistant")
    assistant["context_score"] = 20
    s = store()
    got = s._source_coverage_priority([assistant, experience], SimpleNamespace(prompt="Any advice for my next visit?"))
    describe_tradeoff('indirect_user_topic_hint_vs_direct_assistant_support',
                      got[0] is experience, [experience], got[:1])
    assert experience in got
    assert experience["direct_relevance"] == 0
