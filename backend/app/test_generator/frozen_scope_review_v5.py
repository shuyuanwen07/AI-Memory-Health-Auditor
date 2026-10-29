"""Versioned, opt-in advisory checks for a saved question suite.

The absence of a warning does not certify question validity. Source messages
must be the original, same-conversation user messages, not generated memories.
"""
import re

VERSION = 'source-scope-review-v5'
_GENERIC = re.compile(r"^What is the user's recorded stored information(?:\s+[^?]+)?\?", re.I)
_PROJECT = re.compile(r'\bfor the\s+([A-Z][A-Za-z0-9-]*)\s+project\b')
_BROAD_REQUIREMENT = re.compile(r'^For the current task, what is the recorded requirement about [^?]+\?', re.I)
_BROAD_PREFERENCE = re.compile(r"^What is the user's recorded (?:preference|communication style)\?", re.I)


def scope_warning(prompt: str, dimension: str, source_texts: list[str], *, source_complete: bool,
                  related_topic_count: int = 1) -> str | None:
    """Return a reason for human review; never infer relation completeness.

    Even a complete set of source messages does not prove that extracted
    relationships are exhaustive. Relation-dependent tests therefore require
    review instead of assuming that no recorded relation means none exists.
    """
    if not source_complete or not source_texts or any(not text.strip() for text in source_texts):
        return 'Original source messages are missing; check this question against its source before use.'
    if _GENERIC.search(prompt):
        return 'This broad question may not identify a single fact. Check the intended scope against the source.'
    if dimension == 'accuracy' and related_topic_count > 1:
        return 'Several confirmed memories share this topic. Check which source fact the question asks about.'
    match = _PROJECT.search(prompt)
    if match:
        name = re.escape(match.group(1))
        named = re.compile(r'\b(?:[Pp]roject\s+' + name + r'|' + name + r'\s+(?:project|capstone|backend|deployment|logs|service))\b')
        if not any(named.search(text) for text in source_texts):
            return 'The named project is not explicit in the source. Verify the intended scope.'
    if dimension in {'freshness', 'conflict_resolution', 'appropriate_use'}:
        return 'Verify the relevant source statements and their relationship; the relationship list may be incomplete.'
    if _BROAD_REQUIREMENT.search(prompt) or _BROAD_PREFERENCE.search(prompt):
        return 'This broad question may not identify which task or preference is intended. Verify the scope in the source.'
    return None
