from types import SimpleNamespace

from app.schemas import Dimension, Memory, MemoryRelationship, MemoryStatus, RelationshipType, TestQualityStatus
from app.test_generator.quality import RuleBasedTestQualityValidator
from app.test_generator.rule_based import RuleBasedTestGenerator


def test_distinct_update_topics_produce_grounded_conflict_resolution_slots():
    pairs = [
        ("The user used MySQL for the tracker.", "The user now uses PostgreSQL for the tracker."),
        ("The team meeting used to start at 9:00 AM.", "The team meeting now starts at 10:00 AM."),
        ("The project was previously named Comet.", "The project is now named Aurora."),
        ("Weekly reports used to be sent on Friday.", "Weekly reports are now sent on Thursday."),
        ("The laptop previously ran Ubuntu 22.04.", "The laptop now runs Fedora 41."),
    ]
    memories = []
    for index, (prior_fact, current_fact) in enumerate(pairs, start=1):
        prior_id, current_id = f"M{index * 2 - 1:03d}", f"M{index * 2:03d}"
        memories.extend([
            Memory(memory_id=prior_id, conversation_id="C", canonical_value=prior_fact,
                   status=MemoryStatus.CONFIRMED, source_message_ids=[f"S{index * 2 - 1:03d}"]),
            Memory(memory_id=current_id, conversation_id="C", canonical_value=current_fact,
                   status=MemoryStatus.CONFIRMED, source_message_ids=[f"S{index * 2:03d}"],
                   relationships=[MemoryRelationship(type=RelationshipType.UPDATE, target_memory_id=prior_id)]),
        ])

    tests = RuleBasedTestGenerator().generate(memories, SimpleNamespace(run_id="R", test_budget=20))
    conflict_resolution = [test for test in tests if test.dimension == Dimension.CONFLICT_RESOLUTION]

    assert len(conflict_resolution) == 5
    assert all("recorded stored information" not in test.prompt for test in conflict_resolution)
    assert all(RuleBasedTestQualityValidator().validate(test, memories).quality_status == TestQualityStatus.ACCEPTED
               for test in conflict_resolution)
