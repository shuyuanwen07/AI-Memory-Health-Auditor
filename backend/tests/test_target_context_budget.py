"""Budget the delivered source metadata as well as canonical memory text."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace

import pytest

from app.memory_agent.store import SqlTargetMemoryStore
from app.schemas import MemoryStrategy, TargetConfiguration, TestCase as Case
from app.schemas.target_profile import TargetMemoryProfile
from app.target_ai.rule_based import memory_input_evidence, selected_memory_context


def _candidates():
    return [dict(record=SimpleNamespace(
        id=f"PRIVATE-{index}", canonical_value=f"A remembered observation {index}: " + "x" * 60,
        observed_at=datetime(2026, 2, 1, tzinfo=timezone.utc) + timedelta(days=index),
        source_message_ids=[f"SOURCE-{index}"], write_order=index,
    ), reason="relevant") for index in range(2)]


@pytest.mark.parametrize("metadata,expected_count", [(True, 1), (False, 2)])
@pytest.mark.parametrize("strategy", [MemoryStrategy.STRONG_RULE_BASED, MemoryStrategy.FULL_CONTEXT,
                                    MemoryStrategy.WEAK_FIRST_HIT])
def test_fixed_profile_budgets_delivered_json_metadata_without_changing_legacy_cost(metadata, expected_count, strategy):
    store = SqlTargetMemoryStore(None, profile=TargetMemoryProfile(
        retrieve_message_context=metadata, context_character_budget=300,
    ))
    candidates = _candidates()
    # Both canonical strings fit; their delivered JSON wrappers do not.
    assert sum(len(item["record"].canonical_value) + 3 for item in candidates) < 300
    chosen = store._apply_profile(candidates, SimpleNamespace(), strategy)
    delivered = [store._render_context(item) for item in chosen]
    assert len(chosen) == expected_count
    assert sum(len(value) + 3 for value in delivered) <= 300
    assert sum("profile_context_budget_excluded" in item["reason"] for item in candidates) == 2 - expected_count
    if not metadata:
        assert delivered == [item["record"].canonical_value for item in chosen]


def test_metadata_record_larger_than_budget_is_excluded_even_when_raw_fact_fits():
    store = SqlTargetMemoryStore(None, profile=TargetMemoryProfile(
        retrieve_message_context=True, context_character_budget=100,
    ))
    candidate = _candidates()[0]
    assert len(candidate["record"].canonical_value) + 3 < 100
    assert len(store._render_context(candidate)) + 3 > 100
    assert store._apply_profile([candidate], SimpleNamespace(), MemoryStrategy.STRONG_RULE_BASED) == []


def test_context_metadata_and_input_receipt_correspond_to_same_selected_records():
    store = SqlTargetMemoryStore(None, profile=TargetMemoryProfile(
        retrieve_message_context=True, context_character_budget=300,
    ))
    chosen = store._apply_profile(_candidates(), SimpleNamespace(), MemoryStrategy.STRONG_RULE_BASED)
    context = [store._render_context(item) for item in chosen]
    test = Case(test_id="BUDGET-TEST", run_id="BUDGET-RUN", dimension="accuracy",
                prompt="What observation was remembered?", expected_behavior="SECRET_EVALUATOR_ONLY",
                supporting_memory_ids=["SECRET_GOLD_ID"], generator_version="budget-regression",
                target_memory_context=context)
    sent = selected_memory_context(test, TargetConfiguration.STRONG)
    by_value = {value.strip(): item["record"].id for value, item in zip(context, chosen, strict=True)}
    receipt = memory_input_evidence(test, TargetConfiguration.STRONG, "reader instructions")
    receipt.sent_memory_ids = [by_value[value] for value in sent]
    assert receipt.sent_memory_ids == [item["record"].id for item in chosen]
    assert receipt.record_count == len(chosen)
    expected_hash = hashlib.sha256(json.dumps(sent, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    assert receipt.context_sha256 == expected_hash
    assert [json.loads(value)["source_message_ids"] for value in sent] == [
        item["record"].source_message_ids for item in chosen
    ]
    assert all("SECRET_" not in value for value in sent)
