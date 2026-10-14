"""Recheck a saved coverage contract immediately before target execution."""
from collections import Counter
import re

from fastapi import HTTPException

from app.schemas import Dimension, TestQualityStatus, TestType


def saved_suite_observation(metadata: dict | None) -> dict:
    """Failed refill attempts cannot replace the contract of the persisted suite."""
    history = (metadata or {}).get("generation_observations") or []
    observations = [item for item in history if isinstance(item, dict)]
    saved = [item for item in observations if item.get("saved_suite") is True]
    return (saved or observations or [{}])[-1]


def assert_generation_coverage(observation: dict, tests: list, test_budget: int | None = None) -> None:
    """Apply quotas and exact evidence slots regardless of generator version."""
    report = observation.get("dimension_coverage") or []
    plan = observation.get("coverage_plan") or []
    version = re.fullmatch(r"agent-coverage-semantic-v(\d+)", str(observation.get("agent_version", "")))
    if not report and not plan:
        if version and int(version.group(1)) >= 5:
            raise HTTPException(409, "The saved coverage plan is unavailable. Prepare a new reviewed suite before execution.")
        return  # Historical suites with no declared coverage contract stay historical.

    def value(item):
        return getattr(item, "value", item)

    accepted = [test for test in tests if value(test.quality_status) == TestQualityStatus.ACCEPTED.value]
    counts = Counter(value(test.dimension) for test in accepted)
    required = {}
    try:
        for item in report:
            dimension = Dimension(item["dimension"]).value
            if item.get("evidence_supported") is True:
                minimum = item["required_question_count"]
                if type(minimum) is not int or minimum < 0:
                    raise ValueError("invalid quota")
                required[dimension] = max(required.get(dimension, 0), minimum)
        slots = []
        for item in plan:
            dimension = Dimension(item["dimension"]).value
            kind = TestType(item["test_type"]).value if "test_type" in item else None
            ids = item["supporting_memory_ids"]
            if (not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i for i in ids)
                    or len(ids) != len(set(ids))):
                raise ValueError("invalid evidence IDs")
            slots.append((dimension, kind, frozenset(ids)))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(409, "The saved coverage contract is invalid. Prepare a new reviewed suite before execution.") from None

    shortages = [f"{dimension} needs {minimum}, has {counts[dimension]}"
                 for dimension, minimum in sorted(required.items()) if counts[dimension] < minimum]
    if shortages:
        raise HTTPException(409, "The suite does not meet its minimum accepted questions per evidence-supported ability: "
                            + "; ".join(shortages) + ". Regenerate or accept questions before execution.")

    unmatched = list(accepted)
    for dimension, kind, ids in slots:
        match = next((test for test in unmatched if value(test.dimension) == dimension
                      and (kind is None or value(test.test_type) == kind)
                      and len(test.supporting_memory_ids) == len(ids)
                      and frozenset(test.supporting_memory_ids) == ids), None)
        if match is None:
            raise HTTPException(409, f"An accepted question no longer matches the frozen {dimension} evidence slot. "
                                "Restore the planned question type and evidence or prepare a new suite before execution.")
        unmatched.remove(match)
    expected = observation.get("requested_test_count")
    if expected is None and version and int(version.group(1)) >= 5:
        expected = test_budget
    if expected is not None:
        if type(expected) is not int or expected < 1 or (test_budget is not None and expected != test_budget):
            raise HTTPException(409, "The saved coverage count differs from the frozen audit budget. Prepare a new suite before execution.")
        if len(accepted) != expected:
            raise HTTPException(409, f"The frozen suite requires {expected} accepted questions, but has {len(accepted)}. "
                                "Prepare a complete suite before execution.")
    if observation.get("count_target_met") is False:
        raise HTTPException(409, "The saved suite did not reach its frozen question count. Prepare a complete suite before execution.")
