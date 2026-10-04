import json
import re
from datetime import datetime

from app.schemas import Conversation, ConversationMessage
from app.extraction.rule_based import RuleBasedMemoryExtractor


DATASET = "handoff/owner-a/development/annotation_dataset.json"


def parse_datetime(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def terms(value):
    words = re.findall(r"[a-z0-9][a-z0-9_+-]*", value.lower())
    stop_words = {
        "a", "an", "and", "are", "as", "at", "be", "been", "but",
        "by", "for", "from", "has", "have", "i", "in", "is", "it",
        "my", "of", "on", "or", "our", "that", "the", "their",
        "this", "to", "was", "we", "with", "you", "your",
        "now", "currently", "previously", "before", "later",
        "earlier", "generally", "very", "really",
    }

    result = set()

    for word in words:
        for part in word.split("-"):
            if len(part) > 2 and part not in stop_words:
                result.add(part.rstrip("s"))

    return result


def similarity(gold, extracted):
    gold_terms = terms(gold["canonical_value"])
    extracted_terms = terms(extracted.canonical_value)

    if not gold_terms or not extracted_terms:
        return 0.0

    overlap = gold_terms & extracted_terms
    return len(overlap) / len(gold_terms)


def find_best_match(gold, extracted_memories, used_ids):
    candidates = [
        memory
        for memory in extracted_memories
        if memory.memory_id not in used_ids
        and set(gold["source_message_ids"]) & set(memory.source_message_ids)
    ]

    if not candidates:
        return None, 0.0

    best = max(
        candidates,
        key=lambda memory: similarity(gold, memory),
    )

    return best, similarity(gold, best)


with open(DATASET, "r", encoding="utf-8") as f:
    dataset = json.load(f)


extractor = RuleBasedMemoryExtractor()

total_gold = 0
total_extracted = 0
total_matched = 0
total_missing = 0
total_extra = 0

total_gold_relationships = 0
total_matched_relationships = 0
total_missing_relationships = 0
total_extra_relationships = 0


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

    extracted = extractor.extract(conversation)

    gold_memories = scenario["gold_memories"]

    total_gold += len(gold_memories)
    total_extracted += len(extracted)

    used_extracted = set()
    gold_to_extracted = {}

    print("=" * 80)
    print(scenario["conversation_id"])
    print("=" * 80)

    print("\nMEMORY MATCHING:")

    for gold in gold_memories:
        match, score = find_best_match(
            gold,
            extracted,
            used_extracted,
        )

        if match is None or score < 0.50:
            total_missing += 1

            print(f"  MISSING: {gold['memory_id']}")
            print(f"    Gold:   {gold['canonical_value']}")
            print(f"    Source: {gold['source_message_ids']}")
            continue

        used_extracted.add(match.memory_id)
        gold_to_extracted[gold["memory_id"]] = match.memory_id
        total_matched += 1

        print(f"  MATCH:   {gold['memory_id']} -> {match.memory_id}")
        print(f"    Gold:      {gold['canonical_value']}")
        print(f"    Extracted: {match.canonical_value}")
        print(f"    Source:    {match.source_message_ids}")
        print(f"    Similarity: {score:.2f}")

    extra = [
        memory
        for memory in extracted
        if memory.memory_id not in used_extracted
    ]

    total_extra += len(extra)

    for memory in extra:
        print(f"  EXTRA:   {memory.memory_id}")
        print(f"    Extracted: {memory.canonical_value}")
        print(f"    Source:    {memory.source_message_ids}")

    print("\nRELATIONSHIPS:")

    extracted_by_id = {
        memory.memory_id: memory
        for memory in extracted
    }

    for gold in gold_memories:
        for gold_relationship in gold["relationships"]:
            total_gold_relationships += 1

            source_extracted_id = gold_to_extracted.get(gold["memory_id"])
            target_extracted_id = gold_to_extracted.get(
                gold_relationship["target_memory_id"]
            )

            if source_extracted_id is None or target_extracted_id is None:
                total_missing_relationships += 1
                print(
                    f"  MISSING: {gold['memory_id']} "
                    f"--{gold_relationship['type']}--> "
                    f"{gold_relationship['target_memory_id']}"
                )
                continue

            source_memory = extracted_by_id[source_extracted_id]

            found = any(
                relationship.type.value == gold_relationship["type"]
                and relationship.target_memory_id == target_extracted_id
                for relationship in source_memory.relationships
            )

            if found:
                total_matched_relationships += 1
                print(
                    f"  MATCH:   {gold['memory_id']} "
                    f"--{gold_relationship['type']}--> "
                    f"{gold_relationship['target_memory_id']}"
                )
            else:
                total_missing_relationships += 1
                print(
                    f"  MISSING: {gold['memory_id']} "
                    f"--{gold_relationship['type']}--> "
                    f"{gold_relationship['target_memory_id']}"
                )

    for memory in extracted:
        for relationship in memory.relationships:
            gold_source = next(
                (
                    gold_id
                    for gold_id, extracted_id in gold_to_extracted.items()
                    if extracted_id == memory.memory_id
                ),
                None,
            )

            gold_target = next(
                (
                    gold_id
                    for gold_id, extracted_id in gold_to_extracted.items()
                    if extracted_id == relationship.target_memory_id
                ),
                None,
            )

            if gold_source is None:
                continue

            exists_in_gold = any(
                gold["memory_id"] == gold_source
                and any(
                    r["type"] == relationship.type.value
                    and r["target_memory_id"] == gold_target
                    for r in gold["relationships"]
                )
                for gold in gold_memories
            )

            if not exists_in_gold:
                total_extra_relationships += 1
                print(
                    f"  EXTRA:   {gold_source} "
                    f"--{relationship.type.value}--> "
                    f"{gold_target}"
                )


print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

print(f"Gold memories:             {total_gold}")
print(f"Extracted memories:        {total_extracted}")
print(f"Matched memories:          {total_matched}")
print(f"Missing memories:          {total_missing}")
print(f"Extra memories:            {total_extra}")

if total_gold:
    print(f"Memory recall:             {total_matched / total_gold:.1%}")

if total_extracted:
    print(f"Memory precision:          {total_matched / total_extracted:.1%}")

print()
print(f"Gold relationships:        {total_gold_relationships}")
print(f"Matched relationships:     {total_matched_relationships}")
print(f"Missing relationships:     {total_missing_relationships}")
print(f"Extra relationships:       {total_extra_relationships}")

if total_gold_relationships:
    print(
        f"Relationship recall:       "
        f"{total_matched_relationships / total_gold_relationships:.1%}"
    )

print("=" * 80)