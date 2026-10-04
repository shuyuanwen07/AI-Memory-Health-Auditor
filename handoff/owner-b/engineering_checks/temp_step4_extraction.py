import json
from datetime import datetime

from app.schemas import Conversation, ConversationMessage
from app.extraction.rule_based import RuleBasedMemoryExtractor


DATASET = "handoff/owner-a/development/annotation_dataset.json"


def parse_datetime(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


with open(DATASET, "r", encoding="utf-8") as f:
    dataset = json.load(f)


extractor = RuleBasedMemoryExtractor()

for scenario in dataset["conversations"]:
    conversation = Conversation(
        conversation_id=scenario["conversation_id"],
        created_at=parse_datetime(scenario["messages"][0]["timestamp"]),
        authorised=True,
        messages=[
            ConversationMessage(
                message_id=message["message_id"],
                role=message["role"],
                content=message["content"],
                timestamp=parse_datetime(message["timestamp"]),
            )
            for message in scenario["messages"]
        ],
    )
    
    if scenario["conversation_id"] == "A008":
        print("\nRAW CANDIDATES:")
    for candidate in extractor._candidates(conversation):
        print(candidate)

    extracted = extractor.extract(conversation)

    print("=" * 80)
    print(f"{scenario['conversation_id']}")
    print("=" * 80)

    print("\nGOLD MEMORIES:")
    for memory in scenario["gold_memories"]:
        print(f"  {memory['memory_id']}: {memory['canonical_value']}")
        print(f"      source: {memory['source_message_ids']}")
        print(f"      relationships: {memory['relationships']}")

    print("\nEXTRACTED MEMORIES:")
    for memory in extracted:
        relationships = [
            (r.type.value, r.target_memory_id)
            for r in memory.relationships
        ]
        print(f"  {memory.memory_id}: {memory.canonical_value}")
        print(f"      source: {memory.source_message_ids}")
        print(f"      relationships: {relationships}")

    print()