import json

path = "handoff/owner-a/development/annotation_dataset.json"

with open(path, encoding="utf-8") as f:
    data = json.load(f)

for conversation in data["conversations"]:
    print("=" * 80)
    print(conversation["conversation_id"])

    for test in conversation["gold_tests"]:
        print(
            f"{test['test_id']} | "
            f"{test['dimension']} | "
            f"{test['test_type']} | "
            f"{test['quality_label']} | "
            f"memories={test['supporting_memory_ids']}"
        )
        print(f"  prompt: {test['prompt']}")
        print(f"  expected: {test['expected_behavior']}")
        print(f"  note: {test['quality_note']}")
        print()