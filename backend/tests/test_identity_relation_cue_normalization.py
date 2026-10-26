"""Prospective08 contract: normalize duplicate valid cue tags only.

Prepared during the frozen07 run. These synthetic offline tests are deliberately
not executed until the separately versioned08 implementation is authorized.
No benchmark examples, reference answers or network transport are used.
"""
import copy
import json

import pytest

from app.extraction.llm import PipelineRequestError
from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer
from app.memory_agent.quote_candidate_catalog import build_catalog


MODEL = "openai/gpt-6-luna"
QUESTION = "Which recital descriptions could overlap?"
CONTENTS = [
    "I attended my neighbor's recital in the stone hall.",
    "My colleague Mira's recital featured a green curtain in the stone hall.",
    "I recall a recital with a green curtain, but cannot recall its date.",
]
DUPLICATE_CUES = [
    "shared_venue_only", "distinctive_detail", "shared_venue_only",
    "within_source_narrative", "distinctive_detail",
]
CANONICAL_CUES = ["shared_venue_only", "distinctive_detail", "within_source_narrative"]


def draft():
    return {
        "quotes": [{"quote_id": f"Q{i}", "candidate_id": next(c.candidate_id
                    for c in build_catalog(CONTENTS).candidates
                    if c.record_index == i and c.quote == text)}
                   for i, text in enumerate(CONTENTS, 1)],
        "mentions": [{"mention_id": f"M{i}", "quote_id": f"Q{i}"} for i in range(1, 4)],
        "relations": [
            {"relation_id": "R1", "left_mention_id": "M1", "right_mention_id": "M2",
             "level": "likely", "evidence_quote_ids": ["Q1", "Q2"],
             "cues": list(DUPLICATE_CUES),
             "caveat": "Venue and narrative cues support overlap, but do not confirm identity."},
            {"relation_id": "R2", "left_mention_id": "M2", "right_mention_id": "M3",
             "level": "possible", "evidence_quote_ids": ["Q2", "Q3"],
             "cues": ["distinctive_detail", "generic_role_only"],
             "caveat": "The curtain detail may overlap, but the third account has no name or date."},
        ],
        "limitations": "Candidate identity links only; no attendance count or year inferred.",
    }


class SavedDraftClient:
    """One synthetic JSON reply; retains its original object to catch mutation."""

    def __init__(self, value):
        self.value = copy.deepcopy(value)
        self.calls = []
        self.last_execution = None

    def complete_json(self, **request):
        self.calls.append(request)
        self.last_execution = {"request_attempts": 1, "reported_model": MODEL, "status": "parsed"}
        return self.value


def analyzer_for(value):
    client = SavedDraftClient(value)
    return TargetIdentityEvidenceAnalyzer("openrouter", MODEL, client=client), client


def analyze(agent):
    return agent.analyze(question=QUESTION, context=CONTENTS)


def expected_adjustment(relation_id, model_cues, canonical_cues):
    return {"relation_id": relation_id, "model_cues": model_cues,
            "canonical_cues": canonical_cues,
            "reason_code": "stable_duplicate_enum_cues_removed"}


def assert_raw_retained(agent, client, original):
    assert agent.last_observation["raw_model_draft"] == original
    assert agent.last_observation["raw_model_selection"] == original
    assert all(set(q) == {"quote_id", "candidate_id"} for q in original["quotes"])
    assert client.value == original
    assert len(client.calls) == 1


@pytest.mark.parametrize("level", ["explicit", "likely", "possible", "distinct"])
def test_only_duplicate_valid_cues_change_with_typed_stable_adjustment(level):
    original = draft()
    original["relations"][0]["level"] = level
    before = copy.deepcopy(original)
    agent, client = analyzer_for(original)
    result = analyze(agent)

    assert result.relations[0].cues == CANONICAL_CUES
    assert result.relations[0].level == level
    assert len(result.relation_cue_adjustments) == 1
    adjustment = result.relation_cue_adjustments[0]
    assert adjustment.relation_id == "R1"  # A typed result, not an unchecked dict.
    assert adjustment.model_dump(mode="json") == expected_adjustment("R1", DUPLICATE_CUES, CANONICAL_CUES)
    assert agent.last_observation["relation_cue_adjustments"] == [adjustment.model_dump(mode="json")]
    assert result.to_advisory()["relation_cue_adjustments"] == [adjustment.model_dump(mode="json")]
    assert [mention.model_dump(mode="json") for mention in result.mentions] == before["mentions"]
    for actual, modeled in zip(result.quotes, agent.last_observation["hydrated_quote_draft"]["quotes"], strict=True):
        assert {key: getattr(actual, key) for key in modeled} == modeled
        text = CONTENTS[actual.record_index - 1]
        assert text[actual.char_start:actual.char_end] == actual.quote
    for actual, modeled in zip(result.relations, before["relations"], strict=True):
        canonical = actual.model_dump(mode="json")
        assert {key: value for key, value in canonical.items() if key != "cues"} == {
            key: value for key, value in modeled.items() if key != "cues"
        }
    assert result.relations[1].cues == before["relations"][1]["cues"]
    assert result.limitations == before["limitations"]
    assert result.quote_binding_adjustments == []
    assert agent.last_observation["status"] == "completed"
    assert_raw_retained(agent, client, before)


def test_each_relation_deduplicates_independently_in_first_occurrence_order():
    original = draft()
    original["relations"][1]["cues"] = ["generic_role_only", "distinctive_detail", "generic_role_only"]
    agent, client = analyzer_for(original)
    result = analyze(agent)
    assert [relation.cues for relation in result.relations] == [
        CANONICAL_CUES, ["generic_role_only", "distinctive_detail"],
    ]
    assert [item.model_dump(mode="json") for item in result.relation_cue_adjustments] == [
        expected_adjustment("R1", DUPLICATE_CUES, CANONICAL_CUES),
        expected_adjustment("R2", original["relations"][1]["cues"], ["generic_role_only", "distinctive_detail"]),
    ]
    assert_raw_retained(agent, client, original)


def test_already_unique_cues_preserve_order_without_a_fabricated_adjustment():
    original = draft()
    original["relations"][0]["cues"] = ["within_source_narrative", "shared_venue_only", "distinctive_detail"]
    agent, client = analyzer_for(original)
    result = analyze(agent)
    assert [r.model_dump(mode="json") for r in result.relations] == original["relations"]
    assert result.relation_cue_adjustments == []
    assert agent.last_observation["relation_cue_adjustments"] == []
    assert_raw_retained(agent, client, original)


def test_normalized_advisory_and_typed_adjustment_replay_deterministically():
    original = draft()
    first_agent, first_client = analyzer_for(original)
    second_agent, second_client = analyzer_for(original)
    first, second = analyze(first_agent), analyze(second_agent)
    assert first.advisory_json() == second.advisory_json()
    assert [a.model_dump(mode="json") for a in first.relation_cue_adjustments] == [
        a.model_dump(mode="json") for a in second.relation_cue_adjustments
    ]
    assert json.loads(first.advisory_json())["relations"][0]["cues"] == CANONICAL_CUES
    assert_raw_retained(first_agent, first_client, original)
    assert_raw_retained(second_agent, second_client, original)


@pytest.mark.parametrize("cues", [
    ["shared_venue_only", "made_up_cue", "shared_venue_only"],
    ["shared_venue_only", "SHARED_VENUE_ONLY"],
    ["shared_venue_only", 1, "shared_venue_only"],
    ["shared_venue_only", None], [], "shared_venue_only",
])
def test_unknown_cue_case_or_type_is_not_repaired_or_dropped(cues):
    original = draft()
    original["relations"][0]["cues"] = cues
    agent, client = analyzer_for(original)
    with pytest.raises(PipelineRequestError):
        analyze(agent)
    assert agent.last_observation["status"] == "failed"
    assert agent.last_observation["error_code"] == "invalid_identity_contract"
    assert agent.last_observation["relation_cue_adjustments"] == []
    assert_raw_retained(agent, client, original)


@pytest.mark.parametrize("violation", [
    "duplicate_quote_id", "duplicate_quoted_span", "duplicate_relation_id", "duplicate_relation_pair",
    "duplicate_mention_id", "duplicate_mention_quote_reference", "unknown_endpoint", "self_endpoint",
    "unknown_quote_reference", "missing_endpoint_evidence", "duplicate_evidence_reference", "nonexact_quote",
])
def test_other_quote_mention_relation_and_evidence_contracts_still_reject(violation):
    original = draft()
    if violation == "duplicate_quote_id":
        original["quotes"][1]["quote_id"] = "Q1"
    elif violation == "duplicate_quoted_span":
        original["quotes"][1]["candidate_id"] = original["quotes"][0]["candidate_id"]
    elif violation == "duplicate_relation_id":
        original["relations"][1]["relation_id"] = "R1"
    elif violation == "duplicate_relation_pair":
        original["relations"][1].update(left_mention_id="M2", right_mention_id="M1",
                                        evidence_quote_ids=["Q2", "Q1"])
    elif violation == "duplicate_mention_id":
        original["mentions"][1]["mention_id"] = "M1"
    elif violation == "duplicate_mention_quote_reference":
        original["mentions"][1]["quote_id"] = "Q1"
    elif violation == "unknown_endpoint":
        original["relations"][1]["right_mention_id"] = "M9"
    elif violation == "self_endpoint":
        original["relations"][1]["right_mention_id"] = "M2"
    elif violation == "unknown_quote_reference":
        original["mentions"][2]["quote_id"] = "Q9"
    elif violation == "missing_endpoint_evidence":
        original["relations"][1]["evidence_quote_ids"] = ["Q1", "Q2"]
    elif violation == "duplicate_evidence_reference":
        original["relations"][1]["evidence_quote_ids"] = ["Q2", "Q3", "Q2"]
    else:
        original["quotes"][1]["candidate_id"] = "C999999"
    agent, client = analyzer_for(original)
    with pytest.raises(PipelineRequestError):
        analyze(agent)
    assert agent.last_observation["status"] == "failed"
    assert agent.last_observation["error_code"] == "invalid_identity_contract"
    assert_raw_retained(agent, client, original)


def test_later_graph_failure_retains_original_draft_and_attempted_cue_adjustment():
    original = draft()
    original["relations"][1].update(left_mention_id="M2", right_mention_id="M1",
                                    evidence_quote_ids=["Q2", "Q1"])
    agent, client = analyzer_for(original)
    with pytest.raises(PipelineRequestError):
        analyze(agent)
    assert agent.last_observation["status"] == "failed"
    assert agent.last_observation["output_data"] is None
    assert agent.last_observation["unvalidated_output_data"] == original
    assert agent.last_observation["relation_cue_adjustments"] == [
        expected_adjustment("R1", DUPLICATE_CUES, CANONICAL_CUES),
    ]
    assert_raw_retained(agent, client, original)


def test_normalized_result_still_obeys_complete_advisory_budget_and_preserves_failure_trace(monkeypatch):
    original = draft()
    agent, client = analyzer_for(original)
    monkeypatch.setattr(agent, "MAX_ADVISORY_CHARACTERS", 1)
    with pytest.raises(PipelineRequestError):
        analyze(agent)
    assert agent.last_observation["status"] == "failed"
    assert agent.last_observation["error_diagnostics"]["reason_code"] == "advisory_budget_exceeded"
    assert agent.last_observation["relation_cue_adjustments"] == [
        expected_adjustment("R1", DUPLICATE_CUES, CANONICAL_CUES),
    ]
    assert agent.last_observation["output_data"] is None
    assert_raw_retained(agent, client, original)
