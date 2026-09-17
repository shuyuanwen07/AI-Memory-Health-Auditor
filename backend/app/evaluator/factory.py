"""Evaluator selection independent of API routes and audit orchestration."""
from __future__ import annotations

import os

from app.evaluator.llm_judge import LLMBehaviourEvaluator
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.services.interfaces import BehaviourEvaluator


def configured_evaluator(provider: str | None = None, model: str | None = None) -> tuple[str, str]:
    """Return the evaluator identity recorded on a new audit run."""
    choice = (provider if provider is not None else os.getenv("EVALUATOR_PROVIDER", "rule_based")).strip().lower()
    defaults = {"openai": "gpt-5.6-luna", "deepseek": "deepseek-flash", "gemini": "gemini-2.5-flash-lite"}
    if choice not in defaults:
        return "rule_based", "rule-based-v4"
    return choice, (model or "").strip() or (os.getenv("EVALUATOR_MODEL", "").strip() if provider is None else "") or defaults[choice]


def get_behaviour_evaluator(provider: str | None = None, model: str | None = None) -> BehaviourEvaluator:
    """Return the configured evaluator, safely defaulting to deterministic rules.

    ``EVALUATOR_PROVIDER`` accepts ``rule_based`` (the default), ``openai``,
    ``deepseek``, or ``gemini``. Unknown values intentionally do not break an
    audit; they use the reproducible local evaluator instead.
    """
    choice = (provider if provider is not None else configured_evaluator()[0]).strip().lower()
    if choice in {"openai", "deepseek", "gemini"}:
        return LLMBehaviourEvaluator(choice, model=model)
    return RuleBasedBehaviourEvaluator()
