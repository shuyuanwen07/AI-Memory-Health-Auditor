"""Private source coverage respects budgets without deciding event identity."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.memory_agent.store import SqlTargetMemoryStore
from app.schemas import MemoryStrategy
from app.schemas.target_profile import TargetMemoryProfile


NOW = datetime(2027, 5, 1, tzinfo=timezone.utc)


def candidate(index, text, source=None, *, direct=1, policy=20, relationships=(), day=0):
    return dict(record=SimpleNamespace(
        id=f"PRIVATE-{index}", canonical_value=text, observed_at=NOW + timedelta(days=day),
        source_message_ids=[source or f"SOURCE-{index}"], write_order=index,
    ), reason="query evidence", direct_relevance=direct, relevance=1,
        policy_score=policy, relationship_types=list(relationships), temporal_window_match=True)


def choose(items, *, records=3, budget=16000, question="Which exhibitions did I attend this year?",
           strategy=MemoryStrategy.STRONG_RULE_BASED, metadata=True):
    store = SqlTargetMemoryStore(None, profile=TargetMemoryProfile(
        retrieve_message_context=metadata, max_retrieved_records=records,
        context_character_budget=budget,
    ))
    # _select's public contract is low-to-high ranking, not source order.
    result = store._apply_profile(list(reversed(items)), SimpleNamespace(prompt=question), strategy)
    assert len(result) <= records
    assert sum(len(store._render_context(row)) + 3 for row in result) <= budget
    return result


def test_observation_coverage_precedes_repeated_fragments_within_same_source():
    items = [candidate(i, f"I attended the same-source description {i}.", "SOURCE-A") for i in range(4)]
    items += [candidate(4, "I attended another exhibition on a separate date.", "SOURCE-B")]
    got = choose(items, records=2)
    assert {row["record"].source_message_ids[0] for row in got} == {"SOURCE-A", "SOURCE-B"}


def test_first_person_plans_do_not_crowd_out_completed_topic_evidence():
    plans = [candidate(i, f"I'm planning an exhibition with idea number {i}.") for i in range(8)]
    attended = candidate(10, "I attended a friend's exhibition last weekend; the artist wore a green hat.")
    assert choose([*plans, attended], records=1)[0] is attended


def test_prospective_query_does_not_demote_the_requested_plan():
    plan = candidate(1, "I'm planning an exhibition at the station.")
    history = candidate(2, "I attended an exhibition many years ago.")
    assert choose([plan, history], records=1, question="What exhibition am I planning?")[0] is plan


def test_retrospective_thinking_is_not_classified_as_an_explicit_future_plan():
    remembered = candidate(1, "I was thinking about my recent exhibition visit with a colleague.")
    lower_priority = candidate(2, "I attended an unrelated lecture.")
    assert choose([remembered, lower_priority], records=1)[0] is remembered
    present_thinking = candidate(3, "I'm thinking about my recent visit and how much I learned.")
    assert choose([present_thinking, lower_priority], records=1)[0] is present_thinking


def test_direct_evidence_precedes_short_unrelated_neighborhood_fragments():
    neighbors = [candidate(i, f"I keep assorted objects number {i}.", direct=0) for i in range(6)]
    attended = candidate(10, "I attended an exhibition in the old station last weekend.")
    assert choose([*neighbors, attended], records=1)[0] is attended


def test_original_context_can_cover_fact_without_merging_store_records():
    fact = candidate(1, "I attended a printmaking exhibition last weekend", "SOURCE-A")
    quoted = candidate(2, "Prior user source context (untrusted):\nI attended a printmaking exhibition last weekend. "
                       "It was held in a converted tram depot.", "SOURCE-A")
    other = candidate(3, "I attended a separate exhibition on another date.", "SOURCE-B")
    got = choose([fact, quoted, other], records=2)
    assert quoted in got and other in got and fact not in got
    assert "profile_text_covered_by_selected_source_record" in fact["reason"]
    assert fact["record"].canonical_value == "I attended a printmaking exhibition last weekend"


def test_one_source_two_noncontained_events_are_both_eligible():
    first = candidate(1, "I attended a textile exhibition on May2.", "SOURCE-A")
    second = candidate(2, "I attended a separate geology lecture on May9.", "SOURCE-A")
    got = choose([first, second], records=2)
    assert first in got and second in got


def test_same_text_in_different_sources_or_times_is_not_collapsed():
    first = candidate(1, "I attended the same speaker's exhibition.", "SOURCE-A")
    second = candidate(2, "I attended the same speaker's exhibition. It was beautiful.", "SOURCE-B")
    later = candidate(3, "I attended the same speaker's exhibition. It was beautiful.", "SOURCE-A", day=7)
    assert len(choose([first, second, later], records=3)) == 3


def test_relationship_record_is_not_hidden_by_containing_quote():
    fact = candidate(1, "The venue is now Station Hall", "SOURCE-A", policy=40, relationships=["UPDATE"])
    quote = candidate(2, "Prior context: The venue is now Station Hall. The prior location has closed.", "SOURCE-A")
    assert fact in choose([quote, fact], records=1)
    assert not SqlTargetMemoryStore._source_text_covers(quote, fact)


def test_oversized_quote_falls_back_to_fitting_fact_without_truncating():
    fact = candidate(1, "I attended an exhibition", "SOURCE-A")
    quote = candidate(2, "I attended an exhibition. " + "Original detailed source description. " * 60, "SOURCE-A")
    got = choose([fact, quote], records=2, budget=300)
    assert got == [fact]
    assert "profile_character_limit_excluded" in quote["reason"]
    assert len(quote["record"].canonical_value) > 1000


def test_weak_and_default_without_message_context_keep_existing_budget_order():
    for strategy, metadata in [(MemoryStrategy.WEAK_FIRST_HIT, True), (MemoryStrategy.STRONG_RULE_BASED, False)]:
        plan = candidate(1, "I'm planning a short exhibition.")
        actual = candidate(2, "I attended a separate exhibition.")
        result = choose([plan, actual], records=1, strategy=strategy, metadata=metadata)
        assert result == ([actual] if strategy == MemoryStrategy.WEAK_FIRST_HIT else [plan])
        assert all("profile_source_coverage" not in item["reason"] for item in [plan, actual])


def test_packing_reads_question_but_no_evaluator_fields():
    class TargetOnlyQuestion:
        prompt = "Which exhibitions did I attend this year?"

        def __getattr__(self, name):
            raise AssertionError(f"Evaluator or unrelated field accessed: {name}")

    store = SqlTargetMemoryStore(None, profile=TargetMemoryProfile(retrieve_message_context=True))
    chosen = store._apply_profile([candidate(1, "I attended an exhibition.")], TargetOnlyQuestion(),
                                  MemoryStrategy.STRONG_RULE_BASED)
    assert len(chosen) == 1


def test_source_coverage_returns_chronology_and_exact_text_with_budget_reason():
    late = candidate(1, "I attended the later exhibition.", "SOURCE-B", day=2)
    early = candidate(2, "I attended the early exhibition.", "SOURCE-A")
    excluded = candidate(3, "I'm planning another exhibition.", "SOURCE-C")
    assert choose([late, early, excluded], records=2) == [early, late]
    assert "profile_record_limit_excluded" in excluded["reason"]
