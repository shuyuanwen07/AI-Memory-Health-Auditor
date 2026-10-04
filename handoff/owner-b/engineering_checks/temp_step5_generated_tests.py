import json
from datetime import datetime, timezone

from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.schemas import (
    AuditRun,
    AuditStatus,
    TargetConfiguration,
    TargetProvider,
)
from app.schemas.annotation import AnnotationConversation
from app.test_generator.rule_based import RuleBasedTestGenerator


DATASET_PATH = "handoff/owner-a/development/annotation_dataset.json"


with open(DATASET_PATH, encoding="utf-8") as f:
    data = json.load(f)


extractor = RuleBasedMemoryExtractor()
generator = RuleBasedTestGenerator()


for conversation_data in data["conversations"]:
    print("=" * 80)
    print(conversation_data["conversation_id"])

    conversation = AnnotationConversation.model_validate(conversation_data)

    # Extract the memories from the conversation.
    memories = extractor.extract(conversation)

    # Create a valid AuditRun using the same schema/configuration
    # pattern already used by the project's tests.
    audit = AuditRun(
        run_id=f"STEP5-{conversation.conversation_id}",
        conversation_id=conversation.conversation_id,
        status=AuditStatus.CREATED,
        target_configuration=TargetConfiguration.WEAK,
        provider=TargetProvider.RULE_BASED,
        model="rule-based-target-ai",
        temperature=0,
        random_seed=42,
        test_budget=100,
        prompt_template_version="rule-based-v1",
        created_at=datetime.now(timezone.utc),
    )

    # Generate behavioural tests from the extracted memories.
    tests = generator.generate(memories, audit)

    print(f"Extracted memories: {len(memories)}")
    print(f"Generated tests:    {len(tests)}")
    print()

    for test in tests:
        print(
            f"{test.test_id} | "
            f"{test.dimension} | "
            f"{test.test_type} | "
            f"memories={test.supporting_memory_ids}"
        )
        print(f"  prompt:   {test.prompt}")
        print(f"  expected: {test.expected_behavior}")
        print()

