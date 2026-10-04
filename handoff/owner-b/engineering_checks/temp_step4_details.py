import json

DATASET = "handoff/owner-a/development/annotation_dataset.json"

with open(DATASET, "r", encoding="utf-8") as f:
    dataset = json.load(f)

for scenario in dataset["conversations"]:
    print("=" * 80)
    print(scenario["conversation_id"])
    print("=" * 80)

    print("\nSOURCE MESSAGES:")
    for message in scenario["messages"]:
        print(f"  {message['message_id']} [{message['role']}]")
        print(f"    {message['content']}")

    print("\nACCEPTED TESTS:")
    for test in scenario["gold_tests"]:
        if test["quality_label"] == "accept":
            print(f"  {test['test_id']} [{test['dimension']}]")
            print(f"    prompt: {test['prompt']}")
            print(f"    expected: {test['expected_behavior']}")
            print(f"    memories: {test['supporting_memory_ids']}")

    print()