"""Strict, stdlib-only comparison of observed private memory preparation.

Only declared run-local identifiers and capture timestamps are normalized.
Source timestamps, text, decisions, order, policies and unknown fields survive.
This is an integrity comparison, not evidence that retention decisions are good.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json


OBSERVATION_VERSION = "private-memory-preparation-observation-v1"
RECEIPT_VERSION = "private-memory-preparation-receipts-v1"
ACTUAL_PROVENANCE = "actual_runtime_observation"
RECONSTRUCTED_PROVENANCE = "offline_reconstruction"
_STATES = {"ACTIVE", "SUPERSEDED", "CONFLICTED", "EVICTED", "DIAGNOSTIC_ONLY"}
_EVENTS = {"INGESTED", "WRITTEN", "UPDATED", "CONFLICT_RECORDED",
           "CONTEXTUAL_OVERRIDE_RECORDED", "MAINTENANCE_APPLIED", "RETRIEVED"}
_POLICIES = {"append_only", "update_aware_consolidation"}
_SCOPES = {"profile", "preference", "project_requirement", "episodic"}
_RELATIONSHIPS = {"UPDATE", "CONFLICT", "CONTEXTUAL_OVERRIDE"}


def _fail(message):
    raise ValueError("Private memory preparation: " + message)


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        _fail("receipt must contain finite JSON values")


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _timestamp(value, *, nullable=False):
    if nullable and value is None:
        return
    if not _nonempty(value):
        _fail("missing timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail("invalid timestamp")


def _profile(value):
    if not isinstance(value, dict):
        _fail("profile must be an object")
    result = deepcopy(value)
    policy = result.get("retention_policy", "scope_recency")
    if policy not in {"scope_recency", "source_coverage"}:
        _fail("unknown retention policy")
    # This one documented serializer omission has a historical default.
    if policy == "scope_recency":
        result.pop("retention_policy", None)
    return result


def _observations(value, *, actual_only=False):
    if isinstance(value, list):
        if actual_only:
            _fail("actual runtime sidecar required")
        observations, envelope = value, {}
    elif isinstance(value, dict) and value.get("version") == OBSERVATION_VERSION:
        if actual_only:
            _fail("actual runtime sidecar required")
        observations, envelope = [value], {}
    elif isinstance(value, dict) and value.get("version") == RECEIPT_VERSION:
        provenance, reconstructed = value.get("provenance"), value.get("reconstructed")
        actual = provenance == ACTUAL_PROVENANCE and reconstructed is False
        replay = provenance == RECONSTRUCTED_PROVENANCE and reconstructed is True
        if not actual and not replay or actual_only and not actual:
            _fail("unrecognized actual/reconstructed envelope")
        observations = value.get("observations")
        # Unknown envelope fields remain comparison-relevant; no broad stripping.
        envelope = {k: deepcopy(v) for k, v in value.items()
                    if k not in {"version", "provenance", "reconstructed", "observations"}}
        if not isinstance(observations, list):
            _fail("observations must be a list")
        for index, observation in enumerate(observations, 1):
            if (not isinstance(observation, dict)
                    or type(observation.get("attempt")) is not int
                    or observation["attempt"] != index):
                _fail("observation attempts must be unique contiguous append order")
            _timestamp(observation.get("observed_at"))  # Capture time, not source time.
    else:
        _fail("unrecognized receipt version")
    if not observations:
        _fail("empty observation list")
    return observations, envelope


def _normalize_observation(observation, index):
    if not isinstance(observation, dict) or observation.get("version") != OBSERVATION_VERSION:
        _fail("unrecognized observation version")
    if "attempt" in observation and (type(observation["attempt"]) is not int or observation["attempt"] != index):
        _fail("observation attempt differs from append order")
    if "observed_at" in observation:
        _timestamp(observation["observed_at"])
    required = {"run_id", "conversation_id", "status", "exception_type", "profile", "capacity",
                "maintenance_policy", "writer_version", "records", "events", "snapshot_complete",
                "snapshot_errors"}
    if not required <= observation.keys():
        _fail("observation fields missing")
    run, conversation = observation["run_id"], observation["conversation_id"]
    if not _nonempty(run) or not _nonempty(conversation):
        _fail("run/conversation id missing")
    if (observation["status"] not in {"completed", "failed"}
            or not (observation["exception_type"] is None or _nonempty(observation["exception_type"]))
            or type(observation["capacity"]) is not int or observation["capacity"] < 1
            or observation["maintenance_policy"] not in _POLICIES
            or not _nonempty(observation["writer_version"])
            or type(observation["snapshot_complete"]) is not bool
            or not isinstance(observation["snapshot_errors"], list)):
        _fail("invalid observation status/configuration")
    records, events = observation["records"], observation["events"]
    if not isinstance(records, list) or not isinstance(events, list):
        _fail("records/events must be lists")
    ids, orders, references = set(), set(), {}
    for record in records:
        fields = {"memory_id", "run_id", "source_conversation_id", "canonical_value", "scope",
                  "lifecycle_state", "source_message_ids", "observed_at", "write_order", "relationships"}
        if not isinstance(record, dict) or not fields <= record.keys():
            _fail("record fields missing")
        mid, order = record["memory_id"], record["write_order"]
        if (not _nonempty(mid) or mid in ids or type(order) is not int or order < 1 or order in orders
                or record["run_id"] != run or record["source_conversation_id"] != conversation
                or not isinstance(record["canonical_value"], str)
                or record["scope"] not in _SCOPES or record["lifecycle_state"] not in _STATES
                or not isinstance(record["source_message_ids"], list)
                or any(not _nonempty(x) for x in record["source_message_ids"])
                or not isinstance(record["relationships"], list)):
            _fail("ambiguous record key or invalid record binding")
        _timestamp(record["observed_at"], nullable=True)
        ids.add(mid)
        orders.add(order)
        descriptor = {"write_order": order,
                      "canonical_sha256": hashlib.sha256(record["canonical_value"].encode("utf-8")).hexdigest(),
                      "source_message_ids": record["source_message_ids"], "observed_at": record["observed_at"]}
        references[mid] = "record:" + hashlib.sha256(_json(descriptor).encode("utf-8")).hexdigest()
    if len(set(references.values())) != len(records):
        _fail("ambiguous stable record key")

    def record_reference(value, *, nullable=False):
        if value is None and nullable:
            return None
        if not isinstance(value, str) or value not in references:
            _fail("private record reference has no captured record")
        return references[value]

    def details(value, key=""):
        # Body/source fields are semantic text even if they equal a private ID.
        if key in {"canonical_value", "source_message_ids"}:
            return deepcopy(value)
        if key == "conversation_id":
            if value != conversation:
                _fail("event conversation reference differs")
            return "<conversation-id>"
        if key == "memory_id" or key.endswith("_memory_id"):
            return record_reference(value, nullable=True)
        if key == "memory_ids" or key.endswith("_memory_ids"):
            if not isinstance(value, list):
                _fail("private record reference list required")
            return [record_reference(x) for x in value]
        if isinstance(value, dict):
            normalized = {}
            for k, v in value.items():
                mapped = references.get(k, k)
                if mapped in normalized:
                    _fail("mapped detail keys collide")
                normalized[mapped] = details(v, k)
            return normalized
        if isinstance(value, list):
            return [details(v) for v in value]
        return deepcopy(value)

    result = {k: deepcopy(v) for k, v in observation.items()
              if k not in {"observed_at", "attempt", "records", "events"}}
    result.update(run_id="<run-id>", conversation_id="<conversation-id>",
                  profile=_profile(observation["profile"]), attempt=index)
    result["records"] = []
    for record in sorted(records, key=lambda row: row["write_order"]):
        normalized = deepcopy(record)
        normalized.update(memory_id=references[record["memory_id"]], run_id="<run-id>",
                          source_conversation_id="<conversation-id>")
        relations = []
        for relationship in record["relationships"]:
            if (not isinstance(relationship, dict) or not {"type", "target_memory_id"} <= relationship.keys()
                    or relationship["type"] not in _RELATIONSHIPS):
                _fail("invalid relationship")
            relation = deepcopy(relationship)
            relation["target_memory_id"] = record_reference(relationship["target_memory_id"])
            relations.append(relation)
        normalized["relationships"] = relations  # Relationship order remains meaningful.
        result["records"].append(normalized)
    result["events"], event_ids = [], set()
    for event_index, event in enumerate(events, 1):
        fields = {"event_id", "run_id", "memory_id", "event_type", "source_message_ids", "details", "created_at"}
        if (not isinstance(event, dict) or not fields <= event.keys()
                or not _nonempty(event["event_id"]) or event["event_id"] in event_ids
                or event["run_id"] != run or event["event_type"] not in _EVENTS
                or not isinstance(event["source_message_ids"], list)
                or any(not _nonempty(x) for x in event["source_message_ids"])
                or not isinstance(event["details"], dict)):
            _fail("invalid event binding")
        _timestamp(event["created_at"])
        event_ids.add(event["event_id"])
        normalized = deepcopy(event)
        normalized.update(event_id=f"<event:{event_index}>", run_id="<run-id>",
                          memory_id=record_reference(event["memory_id"], nullable=True),
                          created_at="<event-capture-time>", details=details(event["details"]))
        result["events"].append(normalized)  # Never reorder event decisions.
    _json(result)
    return result


def normalize_private_memory_preparation_receipt(receipt):
    observations, envelope = _observations(receipt)
    return {"envelope": envelope, "observations": [
        _normalize_observation(observation, index) for index, observation in enumerate(observations, 1)]}


def validate_private_memory_preparation_receipt(
    sidecar, *, protocol=None, expected_profile=None, expected_capacity=None,
    expected_maintenance_policy=None, expected_writer_version=None,
    expected_observation_count=None,
):
    """Validate an actual sidecar against explicit frozen controls, or raise.

    Profile checks are partial by the caller's explicit frozen keys. Omitted
    retention_policy equals scope_recency only; source_coverage must be present.
    """
    if protocol is not None:
        if not isinstance(protocol, dict):
            _fail("protocol must be an object")
        target = protocol.get("target", {})
        if not isinstance(target, dict):
            _fail("invalid protocol target")
        declared_profile = protocol.get("target_memory_profile", target.get("final_target_profile_flags"))
        declared_capacity = protocol.get("target_memory_capacity", target.get("memory_capacity"))
        if declared_profile is not None:
            if not isinstance(declared_profile, dict):
                _fail("protocol profile must be an explicit object")
            declared_profile = dict(declared_profile)
            for key in ("max_retrieved_records", "context_character_budget", "output_token_limit"):
                if key in target:
                    if key in declared_profile and _json(declared_profile[key]) != _json(target[key]):
                        _fail("protocol target/profile limits disagree")
                    declared_profile[key] = target[key]
        if declared_profile is None and expected_profile is None:
            _fail("protocol frozen profile missing")
        if declared_capacity is None and expected_capacity is None:
            _fail("protocol frozen capacity missing")
        if declared_capacity is not None and (type(declared_capacity) is not int or declared_capacity < 1):
            _fail("protocol frozen capacity invalid")
        if expected_profile is None:
            expected_profile = declared_profile
        elif declared_profile is not None:
            for key, value in declared_profile.items():
                if key in expected_profile and _json(value) != _json(expected_profile[key]):
                    _fail("conflicting expected profile/protocol")
            expected_profile = {**declared_profile, **expected_profile}
        if expected_capacity is None:
            expected_capacity = declared_capacity
        elif declared_capacity is not None and expected_capacity != declared_capacity:
            _fail("conflicting expected capacity/protocol")
        declared_maintenance = protocol.get("target_memory_maintenance_policy", protocol.get("maintenance_policy"))
        declared_writer = protocol.get("target_memory_writer_version", protocol.get("writer_version"))
        if expected_maintenance_policy is None:
            expected_maintenance_policy = declared_maintenance
        elif declared_maintenance is not None and _json(expected_maintenance_policy) != _json(declared_maintenance):
            _fail("conflicting expected maintenance policy/protocol")
        if expected_writer_version is None:
            expected_writer_version = declared_writer
        elif declared_writer is not None and _json(expected_writer_version) != _json(declared_writer):
            _fail("conflicting expected writer version/protocol")
    observations, _ = _observations(sidecar, actual_only=True)
    normalized = normalize_private_memory_preparation_receipt(sidecar)
    if expected_observation_count is not None and (type(expected_observation_count) is not int
            or expected_observation_count < 1 or len(observations) != expected_observation_count):
        _fail("unexpected observation count")
    for original, observation in zip(observations, normalized["observations"]):
        if (observation["status"] != "completed" or observation["exception_type"] is not None
                or observation["snapshot_complete"] is not True or observation["snapshot_errors"]):
            _fail("failed or incomplete preparation cannot pass validation")
        if expected_profile is not None:
            if not isinstance(expected_profile, dict):
                _fail("expected profile must be an explicit partial object")
            for key, value in expected_profile.items():
                actual = original["profile"].get(key, "scope_recency" if key == "retention_policy" else object())
                if _json(actual) != _json(value):
                    _fail("frozen profile key differs: " + key)
        for key, value in (("capacity", expected_capacity),
                           ("maintenance_policy", expected_maintenance_policy),
                           ("writer_version", expected_writer_version)):
            if value is not None and _json(observation[key]) != _json(value):
                _fail("frozen control differs: " + key)
    return {"status": "passed", "passed": True, "observations": len(observations),
            "record_counts": [len(x["records"]) for x in normalized["observations"]],
            "event_counts": [len(x["events"]) for x in normalized["observations"]]}


def compare_private_memory_preparation_receipts(actual, reconstructed, **expected):
    """Compare actual sidecar with pure builders or a labeled replay sidecar."""
    metadata = validate_private_memory_preparation_receipt(actual, **expected)
    left = normalize_private_memory_preparation_receipt(actual)
    right = normalize_private_memory_preparation_receipt(reconstructed)
    if _json(left) != _json(right):
        _fail("actual and reconstructed preparation differ")
    return {**metadata, "preparation_equal": True,
            "normalized_sha256": hashlib.sha256(_json(left).encode("utf-8")).hexdigest()}
