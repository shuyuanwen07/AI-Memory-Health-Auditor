"""An exploratory explanation-consistency gate for semantic failure categories.

The gate never changes pass/fail and never chooses a different category. It
only withholds the category when the explanation offers no relevant category
cue or describes both a factual mismatch and an unresolved conflict. Cues are
not proof that a label is right; this is a conservative review-routing aid.
"""
import re

_SUPPORT = {
    'accuracy': re.compile(r'\b(?:accurac(?:y|e)|inaccurate|incorrect|wrong|unsupported|invent(?:ed|s)?|fabricat(?:e|ed|es)|substitut(?:e|es|ed)|misstat(?:e|es|ed)|factual(?:ly)?)\b', re.I),
    'freshness': re.compile(r'\b(?:freshness|stale|outdated|obsolete|later|latest|newer|updated?|updates|supersed(?:e|ed|es))\b', re.I),
    'conflict_resolution': re.compile(r'\b(?:conflicts?|conflicting|disagreement|contradict(?:ion|ory|ing)?|unresolved|incompatible)\b', re.I),
    'appropriate_use': re.compile(r'\b(?:appropriate.use|scoped?|task.specific|project.specific|capstone.specific|contextual|overrid(?:e|es|den)|general\s+(?:\w+\s+){0,3}preference|\w+.specific\s+\w*\s*requirement|requirement.*preference|preference.*requirement)\b', re.I),
}


def supported_category(category: str | None, explanation: str) -> str | None:
    """Return the proposed category or None; never infer a replacement."""
    if category not in _SUPPORT or not isinstance(explanation, str) or not explanation.strip():
        return None
    if not _SUPPORT[category].search(explanation):
        return None
    if category == 'accuracy' and _SUPPORT['conflict_resolution'].search(explanation):
        return None
    return category
