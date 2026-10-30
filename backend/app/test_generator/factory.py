"""Factory for the replaceable behavioural-test generation boundary."""
from app.extraction.llm import PipelineLLMClient, pipeline_provider
from app.services.interfaces import TestGenerator
from app.test_generator.topic_scoped_v41 import TopicScopedRuleBasedTestGenerator


def get_test_generator(
    provider: str | None = None,
    model: str | None = None,
    semantic_review_provider: str | None = None,
    semantic_review_model: str | None = None,
) -> TestGenerator:
    """Build the configured generator and its independent semantic critic."""
    choice = provider or pipeline_provider()
    if choice == "rule_based":
        return TopicScopedRuleBasedTestGenerator()
    from app.test_generator.agent import AgentTestGenerator
    reviewer_choice = semantic_review_provider or choice
    reviewer_model = semantic_review_model or (model if reviewer_choice == choice else None)
    return AgentTestGenerator(
        PipelineLLMClient(choice, model),
        PipelineLLMClient(reviewer_choice, reviewer_model),
        PipelineLLMClient(reviewer_choice, reviewer_model),
    )
