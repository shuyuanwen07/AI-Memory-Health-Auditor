"""Pure synthetic tests: no original conversations, providers or databases."""
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from app.memory_agent.topic_neighborhood import meaningful_topic_terms, topic_neighborhood_proposals


def candidate(mid, text, direct=0, *, query=("observatory",), state="ACTIVE", eligible=True,
              role="user", relevance=None):
    return {"record": SimpleNamespace(id=mid, canonical_value=text, lifecycle_state=state,
                                     write_order=0, observed_at=None, source_message_ids=[]),
            "direct_relevance": direct, "relevance": direct if relevance is None else relevance,
            "eligible": eligible, "_query_terms": set(query), "source_roles": {role},
            "reason": "original", "policy_score": 20, "temporal_window_match": False}


def test_recovers_content_neighbor_without_direct_query_word():
    values = [candidate("a", "Observatory camera calibration uses sapphire filters", 2),
              candidate("b", "I tested sapphire filters and found sharper images")]
    result = topic_neighborhood_proposals(values)
    assert len(result) == 1 and result[0].memory_id == "b"
    assert set(result[0].shared_terms) == {"sapphire", "filter"}
    assert 0 < result[0].relevance < 2
    assert result[0].validation_scope == "retrieval_hint_only_not_fact_or_identity"


def test_input_records_and_selection_budgets_are_not_mutated():
    values = [candidate("a", "Observatory sapphire filters", 2), candidate("b", "Sapphire filters improved images")]
    before = deepcopy(values)
    assert topic_neighborhood_proposals(values)
    assert values == before
    assert not any("selected" in value or "context_character_budget" in value for value in values)


@pytest.mark.parametrize("state,eligible", [("EVICTED", True), ("SUPERSEDED", True),
                                          ("CONFLICTED", True), ("ACTIVE", False), (None, True)])
def test_does_not_revive_unavailable_or_nonactive_neighbor(state, eligible):
    assert topic_neighborhood_proposals([
        candidate("a", "Observatory sapphire filters", 2),
        candidate("b", "Sapphire filters improved images", state=state, eligible=eligible)]) == []


def test_unavailable_anchor_cannot_expand():
    assert topic_neighborhood_proposals([
        candidate("a", "Observatory sapphire filters", 2, state="EVICTED"),
        candidate("b", "Sapphire filters improved images")]) == []


def test_generic_words_and_source_metadata_do_not_link():
    assert meaningful_topic_terms("I like trying different things; prior assistant role content") == frozenset()
    assert topic_neighborhood_proposals([
        candidate("a", "I like trying things at the observatory", 2),
        candidate("b", "I like trying different things")]) == []


def test_generic_direct_query_overlap_cannot_be_anchor():
    assert topic_neighborhood_proposals([
        candidate("a", "I like sapphire filters", 1, query=("like", "advice")),
        candidate("b", "Sapphire filters improved images")]) == []


def test_single_shared_name_does_not_link():
    assert topic_neighborhood_proposals([
        candidate("a", "Observatory reports from Avery", 1),
        candidate("b", "Avery booked a museum visit")]) == []


def test_same_session_or_message_cannot_create_link():
    a = candidate("a", "Observatory camera calibration", 1)
    b = candidate("b", "Museum tickets for tomorrow")
    for value in (a, b):
        value["source_context_points"] = [(1, "same-time")]
        value["record"].source_message_ids = ["same-message"]
    assert topic_neighborhood_proposals([a, b]) == []


def test_no_transitive_expansion_and_no_promoted_relevance_anchor():
    values = [candidate("a", "Observatory sapphire filters", 1),
              candidate("b", "Sapphire filters copper lenses"),
              candidate("c", "Copper lenses improve photographs")]
    result = topic_neighborhood_proposals(values)
    assert [p.memory_id for p in result] == ["b"]
    values[1]["relevance"] = 100  # A different expansion must not make b direct.
    assert [p.memory_id for p in topic_neighborhood_proposals(values)] == ["b"]


def test_assistant_bridge_retains_untrusted_role_and_does_not_write_identity():
    result = topic_neighborhood_proposals([
        candidate("a", "Observatory cameras use sapphire filters", 1, role="assistant"),
        candidate("b", "Sapphire filters improved my images")])
    assert result[0].anchor_source_roles == ("assistant",)
    assert "relationship" not in asdict(result[0])
    assert result[0].validation_scope == "retrieval_hint_only_not_fact_or_identity"


def test_meaningful_overlap_requires_neighbor_coverage():
    assert topic_neighborhood_proposals([
        candidate("a", "Observatory sapphire filters", 1),
        candidate("b", "Sapphire filters " + " ".join("term" + chr(97+i) for i in range(26)))]) == []


def test_deterministic_order_and_hard_proposal_limit():
    values = [candidate("a", "Observatory sapphire filters", 1)] + [
        candidate(str(i), "Sapphire filters improved images") for i in range(12)]
    for index, value in enumerate(values):
        value["record"].write_order = index
    expected = topic_neighborhood_proposals(values, max_neighbors=3)
    assert len(expected) == 3
    assert topic_neighborhood_proposals(list(reversed(values)), max_neighbors=3) == expected


def test_duplicate_memory_ids_rejected():
    with pytest.raises(ValueError):
        topic_neighborhood_proposals([candidate("same", "Observatory sapphire filters", 1),
                                      candidate("same", "Sapphire filters improved images")])


@pytest.mark.parametrize("options", [{"max_anchors": -1}, {"max_neighbors": True},
    {"min_shared_terms": 1}, {"attenuation": 1}, {"attenuation": float("nan")},
    {"min_neighbor_coverage": 0}, {"min_neighbor_coverage": float("inf")}])
def test_invalid_parameters_fail_closed(options):
    with pytest.raises(ValueError):
        topic_neighborhood_proposals([], **options)


def test_zero_limits_disable_proposals():
    assert topic_neighborhood_proposals([], max_anchors=0) == []
    assert topic_neighborhood_proposals([], max_neighbors=0) == []


def test_unknown_direct_score_cannot_be_anchor():
    a = candidate("a", "Observatory sapphire filters", 1)
    del a["direct_relevance"]
    assert topic_neighborhood_proposals([a, candidate("b", "Sapphire filters improved images")]) == []


def test_private_random_ids_do_not_break_anchor_or_neighbor_ties():
    def run(ids, reverse):
        values = [candidate(ids[0], "Observatory sapphire filters", 1),
                  candidate(ids[1], "Observatory sapphire filters", 1),
                  candidate(ids[2], "Sapphire filters improved images"),
                  candidate(ids[3], "Sapphire filters improved images")]
        for index, value in enumerate(values):
            value["record"].write_order = index + 1
            value["record"].observed_at = "2027-01-01T12:00:00"
            value["record"].source_message_ids = [f"MSG-{index + 1:03}"]
        byid = {value["record"].id: value["record"] for value in values}
        result = topic_neighborhood_proposals(values[::-1] if reverse else values,
                                               max_anchors=1, max_neighbors=1)
        return [(byid[p.memory_id].source_message_ids,
                 byid[p.anchor_memory_id].source_message_ids,
                 p.shared_terms, p.relevance, p.context_score) for p in result]
    assert run(["z", "y", "x", "w"], False) == run(["a", "b", "c", "d"], True)
    assert run(["z", "y", "x", "w"], False)[0][:2] == (["MSG-003"], ["MSG-001"])


def test_content_sha_breaks_equal_order_and_provenance_ties_without_ids():
    def run(ids):
        values = [candidate(ids[0], "Observatory sapphire filters", 1),
                  candidate(ids[1], "Sapphire filters improved photographs"),
                  candidate(ids[2], "Sapphire filters improved images")]
        byid = {x["record"].id: x["record"].canonical_value for x in values}
        return [(byid[p.memory_id], p.context_score) for p in
                topic_neighborhood_proposals(values, max_neighbors=1)]
    assert run(["a", "b", "c"]) == run(["z", "y", "x"])


@pytest.mark.parametrize("text", ["I'm before small", "I've been over before",
                                   "I’m interested in those small things",
                                   "They’ve been there before and after"])
def test_contractions_and_time_size_scaffolding_are_not_topic_terms(text):
    assert meaningful_topic_terms(text) == frozenset()


def test_before_small_contraction_words_cannot_make_an_anchor():
    assert topic_neighborhood_proposals([
        candidate("a", "I'm before small sapphire filters", 3,
                  query=("I'm", "before", "small")),
        candidate("b", "I've tested sapphire filters")]) == []


def test_shared_scaffolding_does_not_supply_two_content_bridge_terms():
    assert topic_neighborhood_proposals([
        candidate("a", "Observatory small equipment over the hill before sunrise", 1),
        candidate("b", "I've been over the small hill before")]) == []


def test_contraction_cleanup_preserves_positive_cross_experience_recall():
    result = topic_neighborhood_proposals([
        candidate("a", "Observatory sapphire filters improved photographs", 2),
        candidate("b", "I've tested sapphire filters before and noticed sharper images")])
    assert [x.memory_id for x in result] == ["b"]
    assert set(result[0].shared_terms) == {"sapphire", "filter"}
