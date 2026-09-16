"""Factory for the replaceable behavioural-test generation boundary."""
from app.extraction.llm import PipelineLLMClient, pipeline_provider
from app.services.interfaces import TestGenerator
from app.test_generator.rule_based import RuleBasedTestGenerator


def get_test_generator(provider: str | None = None, model: str | None = None) -> TestGenerator:
    """Build the configured generator. ``rule_based`` remains the default."""
    choice = provider or pipeline_provider()
    if choice == "rule_based":
        return RuleBasedTestGenerator()
    from app.test_generator.llm_generator import LLMTestGenerator
    return LLMTestGenerator(PipelineLLMClient(choice, model))
