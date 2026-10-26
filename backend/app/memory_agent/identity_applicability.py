"""Shared pure applicability rule for the optional identity advisory stage."""
import re

from app.target_ai.rule_based import _counting_question


def identity_analysis_applicable(*, question: str, selected_record_count: int,
                                 configuration: str, identity_analysis: str) -> bool:
    """Mirror the controlled target's existing trigger without model dispatch.

    ``configuration`` is the canonical target configuration (``strong`` or
    ``weak``); the selected count is after the normal visibility selection.
    """
    if identity_analysis == "off":
        return False
    relevant = _counting_question(question) or bool(re.search(
        r"\b(?:same\s+(?:event|occasion|person)|different\s+events?|overlap|identity|"
        r"linked|distinct\s+events?|which\s+accounts)\b", question, re.I))
    return configuration == "strong" and selected_record_count >= 2 and relevant
