"""Factory for the replaceable memory-extraction boundary."""
from app.extraction.llm import PipelineLLMClient, pipeline_provider
from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.services.interfaces import MemoryExtractor


def get_memory_extractor(provider: str | None = None, model: str | None = None) -> MemoryExtractor:
    """Build the configured extractor. ``rule_based`` is the safe default."""
    choice = provider or pipeline_provider()
    if choice == "rule_based":
        return RuleBasedMemoryExtractor()
    from app.extraction.llm_extractor import LLMMemoryExtractor
    return LLMMemoryExtractor(PipelineLLMClient(choice, model))
