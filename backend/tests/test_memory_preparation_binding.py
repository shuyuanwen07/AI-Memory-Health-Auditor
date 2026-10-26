"""Synthetic receipt comparison; no provider, corpus or production database."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest


_path = Path(__file__).resolve().parents[2] / "scripts/stability_memory_preparation.py"
_spec = importlib.util.spec_from_file_location("memory_preparation_binding", _path)
binding = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(binding)


def builder(*, policy="source_coverage"):
    run, conv, first, second = [str(uuid4()) for _ in range(4)]
    records = [
        {"memory_id": first, "run_id": run, "source_conversation_id": conv,
         "canonical_value": "The first stored observation", "scope": "episodic",
         "lifecycle_state": "EVICTED", "source_message_ids": ["MSG-001"],
         "observed_at": "2027-01-01T12:00:00", "write_order": 1, "relationships": []},
        {"memory_id": second, "run_id": run, "source_conversation_id": conv,
         "canonical_value": "The later stored observation", "scope": "profile",
         "lifecycle_state": "ACTIVE", "source_message_ids": ["MSG-002", "MSG-003"],
         "observed_at": "2027-02-01T12:00:00+00:00", "write_order": 2,
         "relationships": [{"type": "UPDATE", "target_memory_id": first}]},
    ]
    profile = {"context_character_budget": 16000, "max_retrieved_records": 50,
               "retain_assistant_history": True, "retention_policy": policy}
    events = [
        {"event_type": "INGESTED", "memory_id": None, "source_message_ids": [],
         "details": {"conversation_id": conv, "writer_version": "writer-v1",
                     "maintenance_policy": "update_aware_consolidation", "target_memory_capacity": 500}},
        {"event_type": "WRITTEN", "memory_id": first, "source_message_ids": ["MSG-001"],
         "details": {"canonical_value": records[0]["canonical_value"], "write_order": 1}},
        {"event_type": "WRITTEN", "memory_id": second, "source_message_ids": ["MSG-002", "MSG-003"],
         "details": {"canonical_value": records[1]["canonical_value"], "write_order": 2}},
        {"event_type": "MAINTENANCE_APPLIED", "memory_id": None, "source_message_ids": [],
         "details": {"retention_policy": policy, "group_sha256": "semantic-group-hash",
                     "decisions": [{"memory_id": first, "score": 0.4, "retained": False},
                                   {"memory_id": second, "score": 0.9, "retained": True}],
                     "selected_memory_ids": [second], "index": {first: {"memory_id": first}}}},
        {"event_type": "MAINTENANCE_APPLIED", "memory_id": first, "source_message_ids": ["MSG-001"],
         "details": {"evicted_memory_id": first, "maintenance_action": "capacity_evicted_record"}},
    ]
    for event in events:
        event.update(event_id=str(uuid4()), run_id=run, created_at="2027-03-01T12:00:00+00:00")
    return {"version": binding.OBSERVATION_VERSION, "run_id": run, "conversation_id": conv,
            "status": "completed", "exception_type": None, "profile": profile, "capacity": 500,
            "maintenance_policy": "update_aware_consolidation", "writer_version": "writer-v1",
            "records": records, "events": events, "snapshot_complete": True, "snapshot_errors": []}


def sidecar(observation=None):
    return {"version": binding.RECEIPT_VERSION, "provenance": binding.ACTUAL_PROVENANCE,
            "reconstructed": False, "observations": [
                {"attempt": 1, "observed_at": "2027-03-01T13:00:00+00:00", **(observation or builder())}]}


def test_two_random_id_runs_are_equivalent_and_inputs_unchanged():
    actual, reconstructed = sidecar(), builder()
    for event in reconstructed["events"]:
        event["created_at"] = "2028-04-02T01:02:03+00:00"
    before = deepcopy(actual)
    result = binding.compare_private_memory_preparation_receipts(actual, [reconstructed])
    assert result["passed"] is True and result["preparation_equal"] is True
    assert actual == before
    assert len(result["normalized_sha256"]) == 64


def test_recognized_reconstructed_sidecar_and_capture_time_only_difference():
    actual, reconstructed = sidecar(), sidecar()
    reconstructed.update(provenance=binding.RECONSTRUCTED_PROVENANCE, reconstructed=True)
    reconstructed["observations"][0]["observed_at"] = "2029-02-03T00:00:00Z"
    assert binding.compare_private_memory_preparation_receipts(actual, reconstructed)["passed"]


def test_records_can_be_reordered_only_by_unique_write_order():
    reconstructed = builder()
    reconstructed["records"].reverse()
    assert binding.compare_private_memory_preparation_receipts(sidecar(), reconstructed)["passed"]


def test_default_retention_omission_is_the_single_profile_default_equivalence():
    actual = sidecar(builder(policy="scope_recency"))
    reconstructed = builder(policy="scope_recency")
    reconstructed["profile"].pop("retention_policy")
    assert binding.compare_private_memory_preparation_receipts(actual, [reconstructed])["passed"]
    assert binding.validate_private_memory_preparation_receipt(
        sidecar(reconstructed), expected_profile={"retention_policy": "scope_recency"})["passed"]


def test_new_coverage_must_be_explicit_and_partial_profile_keys_are_checked():
    actual = sidecar(builder(policy="scope_recency"))
    actual["observations"][0]["profile"].pop("retention_policy")
    with pytest.raises(ValueError):
        binding.validate_private_memory_preparation_receipt(actual,
            expected_profile={"retention_policy": "source_coverage"})
    assert binding.validate_private_memory_preparation_receipt(sidecar(),
        expected_profile={"retention_policy": "source_coverage", "max_retrieved_records": 50})["passed"]


@pytest.mark.parametrize("protocol", [
    {"target_memory_profile": {"retention_policy": "source_coverage"}, "target_memory_capacity": 500},
    {"target": {"final_target_profile_flags": {"retention_policy": "source_coverage"}, "memory_capacity": 500}},
])
def test_protocol_adapter_is_stdlib_only_and_compatible_with_wrapper(protocol):
    assert binding.validate_private_memory_preparation_receipt(sidecar(), protocol=protocol)["passed"]


@pytest.mark.parametrize("field,value", [("capacity", 499), ("maintenance_policy", "append_only"),
                                        ("writer_version", "writer-v2")])
def test_frozen_control_tampering_rejected(field, value):
    with pytest.raises(ValueError):
        binding.validate_private_memory_preparation_receipt(sidecar(), **{"expected_" + field: value})


@pytest.mark.parametrize("mutate", [
    lambda o: o.update(status="failed", exception_type="RuntimeError"),
    lambda o: o.update(snapshot_complete=False),
    lambda o: o.update(snapshot_errors=[{"component": "records", "error_type": "RuntimeError"}]),
    lambda o: o["records"][0].update(run_id="wrong-run"),
    lambda o: o["records"][0].update(source_conversation_id="wrong-conversation"),
    lambda o: o["records"][1].update(write_order=1),
    lambda o: o["records"][1].update(memory_id=o["records"][0]["memory_id"]),
    lambda o: o["records"].pop(0),
    lambda o: o["events"][0].update(created_at="not-a-time"),
    lambda o: o["events"][1].update(event_id=o["events"][0]["event_id"]),
])
def test_failed_missing_or_ambiguous_capture_cannot_pass(mutate):
    observation = builder()
    mutate(observation)
    with pytest.raises(ValueError):
        binding.validate_private_memory_preparation_receipt(sidecar(observation))


@pytest.mark.parametrize("mutate", [
    lambda o: o["records"][0].update(observed_at="2027-01-01T12:00:00+00:00"),
    lambda o: o["records"][0].update(canonical_value="Altered remembered content"),
    lambda o: o["records"][0].update(lifecycle_state="ACTIVE"),
    lambda o: o["records"][1]["source_message_ids"].reverse(),
    lambda o: o["records"][1]["relationships"][0].update(type="CONFLICT"),
    lambda o: o["events"].reverse(),
    lambda o: o["events"][3]["details"].update(group_sha256="tampered-group-hash"),
    lambda o: o["events"][3]["details"]["decisions"][0].update(score=0.5),
    lambda o: o["events"][3]["details"]["decisions"][0].update(retained=True),
    lambda o: o["profile"].update(context_character_budget=16001),
    lambda o: o["events"][4]["details"].update(maintenance_action="different-action"),
])
def test_semantic_timestamp_policy_decision_and_order_changes_fail_comparison(mutate):
    reconstructed = builder()
    mutate(reconstructed)
    with pytest.raises(ValueError):
        binding.compare_private_memory_preparation_receipts(sidecar(), [reconstructed])


def test_arbitrary_id_and_time_fields_are_not_generically_removed():
    actual, reconstructed = sidecar(), builder()
    actual["observations"][0]["events"][0]["details"]["id"] = "semantic-ID-A"
    reconstructed["events"][0]["details"]["id"] = "semantic-ID-B"
    with pytest.raises(ValueError):
        binding.compare_private_memory_preparation_receipts(actual, reconstructed)
    for observation in (actual["observations"][0], reconstructed):
        observation["events"][0]["details"].pop("id")
    actual["observations"][0]["events"][0]["details"]["observed_at"] = "2020-01-01"
    reconstructed["events"][0]["details"]["observed_at"] = "2021-01-01"
    with pytest.raises(ValueError):
        binding.compare_private_memory_preparation_receipts(actual, reconstructed)


def test_private_id_literals_in_source_text_or_source_ids_are_not_rewritten():
    for field in ("canonical_value", "source_message_ids"):
        actual, reconstructed = sidecar(), builder()
        for observation in (actual["observations"][0], reconstructed):
            value = observation["records"][0]["memory_id"]
            observation["records"][0][field] = [value] if field == "source_message_ids" else value
        with pytest.raises(ValueError):
            binding.compare_private_memory_preparation_receipts(actual, reconstructed)


def test_relationship_order_is_preserved():
    actual, reconstructed = sidecar(), builder()
    for observation in (actual["observations"][0], reconstructed):
        target = observation["records"][0]["memory_id"]
        observation["records"][1]["relationships"].append({"type": "CONFLICT", "target_memory_id": target})
    reconstructed["records"][1]["relationships"].reverse()
    with pytest.raises(ValueError):
        binding.compare_private_memory_preparation_receipts(actual, reconstructed)


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(reconstructed=True),
    lambda r: r.update(provenance="unknown"),
    lambda r: r.update(version="future-version"),
    lambda r: r.update(observations=[]),
    lambda r: r["observations"][0].update(attempt=2),
    lambda r: r["observations"][0].update(observed_at="bad-time"),
])
def test_unknown_provenance_empty_or_malformed_envelopes_rejected(mutate):
    receipt = sidecar()
    mutate(receipt)
    with pytest.raises(ValueError):
        binding.validate_private_memory_preparation_receipt(receipt)


def test_reconstructed_attempt_cannot_be_hidden_as_capture_metadata():
    reconstructed = builder()
    reconstructed["attempt"] = 99
    with pytest.raises(ValueError):
        binding.compare_private_memory_preparation_receipts(sidecar(), reconstructed)


def test_unknown_envelope_fields_remain_comparison_relevant():
    actual = sidecar()
    actual["policy_receipt"] = "must-not-disappear"
    with pytest.raises(ValueError):
        binding.compare_private_memory_preparation_receipts(actual, builder())


@pytest.mark.parametrize("protocol", [{}, {"target_memory_profile": {}},
                                       {"target_memory_capacity": 500}])
def test_protocol_cannot_silently_omit_frozen_controls(protocol):
    with pytest.raises(ValueError):
        binding.validate_private_memory_preparation_receipt(sidecar(), protocol=protocol)


def test_study_target_limits_are_frozen_profile_keys_too():
    protocol = {"target": {"final_target_profile_flags": {"retention_policy": "source_coverage"},
                           "memory_capacity": 500, "max_retrieved_records": 49}}
    with pytest.raises(ValueError):
        binding.validate_private_memory_preparation_receipt(sidecar(), protocol=protocol)


def test_protocol_and_explicit_expected_controls_cannot_conflict():
    with pytest.raises(ValueError):
        binding.validate_private_memory_preparation_receipt(sidecar(),
            protocol={"target_memory_profile": {}, "target_memory_capacity": 500,
                      "maintenance_policy": "append_only"},
            expected_maintenance_policy="update_aware_consolidation")


def test_recursively_mapped_record_keys_cannot_overwrite_semantic_fields():
    receipt = sidecar()
    original = receipt["observations"][0]
    normalized = binding.normalize_private_memory_preparation_receipt(receipt)
    stable = normalized["observations"][0]["records"][0]["memory_id"]
    private = original["records"][0]["memory_id"]
    original["events"][0]["details"]["index"] = {private: "first", stable: "second"}
    with pytest.raises(ValueError):
        binding.validate_private_memory_preparation_receipt(receipt)
