import json

from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.schemas.annotation import AnnotationConversation


DATASET_PATH = "handoff/owner-a/development/annotation_dataset.json"


with open(DATASET_PATH, encoding="utf-8") as f:
    data = json.load(f)


extractor = RuleBasedMemoryExtractor()


for conversation_data in data["conversations"]:
    conversation_id = conversation_data["conversation_id"]

    # Only inspect the scenarios relevant to our current Step 5 analysis.
    if conversation_id not in {
        "A001",
        "A002",
        "A003",
        "A006",
        "A007",
        "A008",
        "A011",
        "A012",
        "A013",
        "A016",
        "A017",
        "A018",
    }:
        continue

    print("=" * 80)
    print(conversation_id)

    conversation = AnnotationConversation.model_validate(conversation_data)
    memories = extractor.extract(conversation)

    for memory in memories:
        print(f"Memory ID: {memory.memory_id}")
        print(f"  canonical_value: {memory.canonical_value}")
        print(f"  timestamp:       {memory.timestamp}")

        if memory.relationships:
            print("  relationships:")
            for relationship in memory.relationships:
                print(
                    f"    - {relationship.type}"
                    f" -> {relationship.target_memory_id}"
                )
        else:
            print("  relationships:   none")

        print()